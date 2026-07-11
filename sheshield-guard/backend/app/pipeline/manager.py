"""Per-camera worker threads. Each worker:
  capture frame -> (every N frames) YOLO track -> signals -> fusion
  -> on CRITICAL: create Incident + trigger evidence + broadcast event.

Live view is served as annotated MJPEG (works in any <img> tag, zero client
deps). Upgrade path for sub-second multi-viewer streaming: go2rtc/MediaMTX
WebRTC gateway in front of the raw RTSP - documented in README."""
import threading
import time
import queue
import cv2
from ..config import settings
from ..database import SessionLocal
from .. import models
from .detector import PersonTracker
from .signals import SignalEngine
from .fusion import FusionEngine
from .advanced import AdvancedModels
from .evidence import EvidenceRecorder
from ..alerts.stations import nearest_station

STATE_COLORS = {"CLEAR": (111, 174, 26), "SUSPECT": (36, 165, 245), "CRITICAL": (77, 72, 229)}  # BGR


class CameraWorker(threading.Thread):
    def __init__(self, camera: models.Camera, event_bus: "EventBus"):
        super().__init__(daemon=True)
        self.cam = camera
        self.bus = event_bus
        self.tracker = PersonTracker()
        self.signals = SignalEngine()
        self.fusion = FusionEngine()
        self.advanced = AdvancedModels()
        self.recorder = EvidenceRecorder(camera.id)
        self.latest_jpeg = None
        self.status = {"state": "CLEAR", "score": 0.0, "signals": {}, "fps": 0.0}
        self.stop_flag = False

    def run(self):
        src = int(self.cam.source) if self.cam.source.isdigit() else self.cam.source
        cap = cv2.VideoCapture(src)
        frame_i, last_dets = 0, []
        t0, frames_since = time.time(), 0
        while not self.stop_flag:
            ok, frame = cap.read()
            if not ok:
                if isinstance(src, str) and not src.startswith("rtsp"):
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)  # loop video files (demo mode)
                    continue
                time.sleep(2)
                cap = cv2.VideoCapture(src)  # reconnect RTSP
                continue
            frame = cv2.resize(frame, (640, int(640 * frame.shape[0] / frame.shape[1])))
            frame_i += 1

            if frame_i % settings.DETECT_EVERY_N_FRAMES == 0:
                last_dets = self.tracker.track(frame)
                base = self.signals.compute(frame, last_dets)
                adv = self.advanced.scores(frame, base)
                sig = {**base, **adv}
                state, score, incident_kind = self.fusion.step(sig)
                self.status = {"state": state, "score": score,
                               "signals": {k: round(v, 2) for k, v in sig.items()},
                               "fps": self.status["fps"]}
                self.bus.publish({"type": "camera_status", "camera_id": self.cam.id, **self.status})
                if incident_kind:
                    self._create_incident(incident_kind, score, sig)

            self.recorder.push(frame)
            annotated = self._annotate(frame, last_dets)
            _, jpg = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 70])
            self.latest_jpeg = jpg.tobytes()

            frames_since += 1
            if time.time() - t0 >= 2:
                self.status["fps"] = round(frames_since / (time.time() - t0), 1)
                t0, frames_since = time.time(), 0
        cap.release()

    def _annotate(self, frame, dets):
        h, w = frame.shape[:2]
        color = STATE_COLORS[self.status["state"]]
        out = frame.copy()
        for d in dets:
            x1, y1, x2, y2 = [int(v * s) for v, s in zip(d["box"], (w, h, w, h))]
            cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
            cv2.putText(out, f'#{d["id"]}', (x1, y1 - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
        cv2.rectangle(out, (0, 0), (w, 4), color, -1)  # state strip
        return out

    def _create_incident(self, kind, score, sig):
        db = SessionLocal()
        try:
            station, dist_km = nearest_station(db, self.cam.latitude, self.cam.longitude)
            inc = models.Incident(
                camera_id=self.cam.id, kind=kind, fused_score=score,
                signal_breakdown={k: round(v, 3) for k, v in sig.items()},
                nearest_station_id=station.id if station else None,
                nearest_station_km=round(dist_km, 2) if station else None,
            )
            db.add(inc)
            db.commit()
            db.refresh(inc)
            raw, blurred = self.recorder.trigger(inc.id)
            inc.evidence_path, inc.evidence_blurred_path = raw, blurred
            db.commit()
            self.bus.publish({
                "type": "incident", "id": inc.id, "camera_id": self.cam.id,
                "camera_name": self.cam.name, "kind": kind, "score": score,
                "signals": inc.signal_breakdown,
                "nearest_station": station.name if station else None,
                "nearest_station_km": inc.nearest_station_km,
                "created_at": inc.created_at.isoformat(),
                "status": "pending_review",
            })
        finally:
            db.close()


class EventBus:
    """Fan-out of pipeline events to all connected WebSocket clients."""
    def __init__(self):
        self.subscribers: list[queue.Queue] = []
        self.lock = threading.Lock()

    def subscribe(self):
        q = queue.Queue(maxsize=200)
        with self.lock:
            self.subscribers.append(q)
        return q

    def unsubscribe(self, q):
        with self.lock:
            if q in self.subscribers:
                self.subscribers.remove(q)

    def publish(self, event: dict):
        with self.lock:
            for q in self.subscribers:
                try:
                    q.put_nowait(event)
                except queue.Full:
                    pass


class PipelineManager:
    def __init__(self):
        self.workers: dict[int, CameraWorker] = {}
        self.bus = EventBus()

    def start_all(self):
        db = SessionLocal()
        for cam in db.query(models.Camera).filter_by(enabled=True).all():
            self.start_camera(cam)
        db.close()

    def start_camera(self, cam: models.Camera):
        if cam.id in self.workers:
            return
        w = CameraWorker(cam, self.bus)
        self.workers[cam.id] = w
        w.start()

    def stop_camera(self, cam_id: int):
        w = self.workers.pop(cam_id, None)
        if w:
            w.stop_flag = True


manager = PipelineManager()
