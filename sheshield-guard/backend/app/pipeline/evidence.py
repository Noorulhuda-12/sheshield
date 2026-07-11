"""Evidence recording with privacy-by-design.

Two copies per incident:
- RAW clip: restricted, for legal chain-of-custody.
- BLURRED clip: all detected faces Gaussian-blurred; this is the only copy
  attached to outbound alerts (GDPR-style third-party protection)."""
import os
import time
import threading
from collections import deque
import cv2
from ..config import settings

_face_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
)


def blur_faces(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = _face_cascade.detectMultiScale(gray, 1.15, 5, minSize=(24, 24))
    out = frame.copy()
    for (x, y, w, h) in faces:
        roi = out[y:y + h, x:x + w]
        out[y:y + h, x:x + w] = cv2.GaussianBlur(roi, (51, 51), 0)
    return out


class EvidenceRecorder:
    """Keeps a rolling pre-incident buffer; on trigger, records buffer +
    post-incident frames to disk in a background thread."""
    def __init__(self, camera_id: int, fps: float = 15.0):
        self.camera_id = camera_id
        self.fps = fps
        maxlen = int(settings.RING_BUFFER_SECONDS * fps)
        self.ring = deque(maxlen=maxlen)
        self._recording = None  # (frames_remaining, raw_writer, blur_writer, paths)
        os.makedirs(settings.EVIDENCE_DIR, exist_ok=True)

    def push(self, frame):
        self.ring.append(frame.copy())
        if self._recording:
            remaining, raw_w, blur_w, paths = self._recording
            raw_w.write(frame)
            blur_w.write(blur_faces(frame) if settings.BLUR_FACES_IN_SHARED_CLIP else frame)
            remaining -= 1
            if remaining <= 0:
                raw_w.release()
                blur_w.release()
                self._recording = None
            else:
                self._recording = (remaining, raw_w, blur_w, paths)

    def trigger(self, incident_id: int):
        """Start writing: dump ring buffer immediately, then keep recording
        POST_INCIDENT_SECONDS more via push(). Returns (raw_path, blurred_path)."""
        if self._recording:
            return self._recording[3]
        ts = int(time.time())
        h, w = self.ring[-1].shape[:2] if self.ring else (480, 640)
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        raw_path = os.path.join(settings.EVIDENCE_DIR, f"inc{incident_id}_cam{self.camera_id}_{ts}_raw.mp4")
        blur_path = os.path.join(settings.EVIDENCE_DIR, f"inc{incident_id}_cam{self.camera_id}_{ts}_blurred.mp4")
        raw_w = cv2.VideoWriter(raw_path, fourcc, self.fps, (w, h))
        blur_w = cv2.VideoWriter(blur_path, fourcc, self.fps, (w, h))
        for f in list(self.ring):
            raw_w.write(f)
            blur_w.write(blur_faces(f) if settings.BLUR_FACES_IN_SHARED_CLIP else f)
        remaining = int(settings.POST_INCIDENT_SECONDS * self.fps)
        self._recording = (remaining, raw_w, blur_w, (raw_path, blur_path))
        return raw_path, blur_path
