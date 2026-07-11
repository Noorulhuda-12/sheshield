"""Per-frame safety signals computed from track histories + raw frames.

HONESTY NOTE: motion-violence here is a heuristic (frame-difference energy
inside multi-person regions), not a trained action model. It exists so the
system runs end-to-end on any laptop today. Replace it with a trained
X3D-M / MoViNet-A2 / PoseC3D model via pipeline/advanced.py - the fusion
layer consumes the same 0..1 score either way. See docs/TRAINING.md."""
import time
from collections import deque
import cv2
import numpy as np
from ..config import settings


class TrackHistory:
    """Rolling position history per track id."""
    def __init__(self, maxlen=150):
        self.tracks = {}  # id -> deque[(t, cx, cy, height)]
        self.maxlen = maxlen

    def update(self, detections):
        now = time.time()
        seen = set()
        for d in detections:
            seen.add(d["id"])
            dq = self.tracks.setdefault(d["id"], deque(maxlen=self.maxlen))
            dq.append((now, d["center"][0], d["center"][1], d["height"]))
        # drop stale tracks (>5s unseen)
        for tid in list(self.tracks):
            if tid not in seen and now - self.tracks[tid][-1][0] > 5:
                del self.tracks[tid]

    def speed(self, tid, window=1.0):
        dq = self.tracks.get(tid)
        if not dq or len(dq) < 2:
            return 0.0
        now = dq[-1][0]
        pts = [(t, x, y) for t, x, y, _ in dq if now - t <= window]
        if len(pts) < 2:
            return 0.0
        (t0, x0, y0), (t1, x1, y1) = pts[0], pts[-1]
        dt = max(t1 - t0, 1e-3)
        return float(np.hypot(x1 - x0, y1 - y0) / dt)


class SignalEngine:
    def __init__(self):
        self.history = TrackHistory()
        self.prev_gray = None
        self.pursuit_state = {}   # (follower, target) -> first_seen_time
        self.loiter_state = {}    # tid -> (anchor_x, anchor_y, since)

    # ---------- individual signals, each returns 0..1 ----------

    def proximity(self, dets):
        """Closest pairwise distance normalized by mean bbox height (depth proxy)."""
        score = 0.0
        for i in range(len(dets)):
            for j in range(i + 1, len(dets)):
                a, b = dets[i], dets[j]
                mean_h = max((a["height"] + b["height"]) / 2, 1e-3)
                d = np.hypot(a["center"][0] - b["center"][0],
                             a["center"][1] - b["center"][1]) / mean_h
                if d < settings.PROXIMITY_NEAR:
                    score = max(score, 1.0 - d / settings.PROXIMITY_NEAR)
        return float(score)

    def pursuit(self, dets):
        """One moving track persistently shadowing another moving track."""
        now = time.time()
        score = 0.0
        ids = {d["id"]: d for d in dets}
        active_pairs = set()
        for a in dets:
            for b in dets:
                if a["id"] == b["id"]:
                    continue
                mean_h = max((a["height"] + b["height"]) / 2, 1e-3)
                d = np.hypot(a["center"][0] - b["center"][0],
                             a["center"][1] - b["center"][1]) / mean_h
                sa = self.history.speed(a["id"])
                sb = self.history.speed(b["id"])
                if d < settings.PURSUIT_MAX_GAP and sa > settings.PURSUIT_MIN_SPEED and sb > settings.PURSUIT_MIN_SPEED:
                    key = (a["id"], b["id"])
                    active_pairs.add(key)
                    since = self.pursuit_state.setdefault(key, now)
                    elapsed = now - since
                    score = max(score, min(elapsed / settings.PURSUIT_SECONDS, 1.0))
        # reset pairs no longer in pursuit
        for key in list(self.pursuit_state):
            if key not in active_pairs:
                del self.pursuit_state[key]
        return float(score)

    def motion_violence(self, frame, dets):
        """Frame-diff energy inside union region of >=2 close persons. Heuristic."""
        if len(dets) < 2:
            self.prev_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            return 0.0
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if self.prev_gray is None or self.prev_gray.shape != gray.shape:
            self.prev_gray = gray
            return 0.0
        h, w = gray.shape
        # union bbox of all persons
        x1 = int(min(d["box"][0] for d in dets) * w)
        y1 = int(min(d["box"][1] for d in dets) * h)
        x2 = int(max(d["box"][2] for d in dets) * w)
        y2 = int(max(d["box"][3] for d in dets) * h)
        roi_now = gray[y1:y2, x1:x2]
        roi_prev = self.prev_gray[y1:y2, x1:x2]
        self.prev_gray = gray
        if roi_now.size == 0:
            return 0.0
        diff = cv2.absdiff(roi_now, roi_prev)
        energy = float((diff > 25).mean())  # fraction of ROI pixels with strong change
        return float(min(energy / settings.VIOLENCE_ENERGY_THRESHOLD, 1.0))

    def fall(self, dets):
        """Sudden vertical drop of a track's center + wide aspect ratio."""
        now = time.time()
        score = 0.0
        for d in dets:
            dq = self.history.tracks.get(d["id"])
            if not dq or len(dq) < 3:
                continue
            recent = [(t, y) for t, _, y, _ in dq if now - t <= settings.FALL_DROP_SECONDS]
            if len(recent) < 2:
                continue
            drop = recent[-1][1] - recent[0][1]  # y grows downward
            x1, y1, x2, y2 = d["box"]
            wide = (x2 - x1) > (y2 - y1) * 1.2   # lying-down aspect ratio
            if drop > settings.FALL_DROP_FRACTION and wide:
                score = 1.0
        return float(score)

    def loitering(self, dets):
        now = time.time()
        score = 0.0
        seen = set()
        for d in dets:
            seen.add(d["id"])
            cx, cy = d["center"]
            if d["id"] not in self.loiter_state:
                self.loiter_state[d["id"]] = (cx, cy, now)
                continue
            ax, ay, since = self.loiter_state[d["id"]]
            if np.hypot(cx - ax, cy - ay) > settings.LOITER_RADIUS:
                self.loiter_state[d["id"]] = (cx, cy, now)  # moved: reset anchor
            else:
                score = max(score, min((now - since) / settings.LOITER_SECONDS, 1.0))
        for tid in list(self.loiter_state):
            if tid not in seen:
                del self.loiter_state[tid]
        return float(score)

    # ---------- entry point ----------

    def compute(self, frame, dets, advanced_scores=None):
        """Returns dict of named 0..1 signals. advanced_scores lets trained
        models (X3D violence, PoseC3D interaction, RTFM anomaly) override or
        add signals - see pipeline/advanced.py."""
        self.history.update(dets)
        signals = {
            "proximity": self.proximity(dets),
            "pursuit": self.pursuit(dets),
            "motion_violence": self.motion_violence(frame, dets),
            "fall": self.fall(dets),
            "loitering": self.loitering(dets),
            "persons": float(len(dets)),
        }
        if advanced_scores:
            signals.update(advanced_scores)  # e.g. {"violence_x3d":0.8,"anomaly_rtfm":0.6}
        return signals
