"""Person detection + tracking. YOLOv8 with ByteTrack via ultralytics.
Swap YOLO_MODEL for a TensorRT .engine file on Jetson - the API is identical."""
import numpy as np
from ultralytics import YOLO
from ..config import settings


class PersonTracker:
    def __init__(self):
        self.model = YOLO(settings.YOLO_MODEL)

    def track(self, frame: np.ndarray):
        """Returns list of dicts: {id, box(x1,y1,x2,y2 normalized), center, height}."""
        results = self.model.track(
            frame,
            persist=True,
            classes=[settings.PERSON_CLASS_ID],
            conf=settings.CONF_THRESHOLD,
            tracker="bytetrack.yaml",
            verbose=False,
        )
        h, w = frame.shape[:2]
        out = []
        r = results[0]
        if r.boxes is None or r.boxes.id is None:
            return out
        for box, tid in zip(r.boxes.xyxy.cpu().numpy(), r.boxes.id.cpu().numpy()):
            x1, y1, x2, y2 = box / np.array([w, h, w, h])
            out.append({
                "id": int(tid),
                "box": (float(x1), float(y1), float(x2), float(y2)),
                "center": (float((x1 + x2) / 2), float((y1 + y2) / 2)),
                "height": float(y2 - y1),
            })
        return out
