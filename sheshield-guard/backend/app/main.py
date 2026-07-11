import asyncio
import os
from fastapi import FastAPI, Depends, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from sqlalchemy.orm import Session
from .database import Base, engine, get_db, SessionLocal
from . import models
from .pipeline.manager import manager
from .alerts import broker
from .config import settings

Base.metadata.create_all(bind=engine)
app = FastAPI(title="SheShield-Guard", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
def startup():
    manager.start_all()


# ---------- Cameras ----------

@app.get("/api/cameras")
def list_cameras(db: Session = Depends(get_db)):
    cams = db.query(models.Camera).all()
    return [{
        "id": c.id, "name": c.name, "source": c.source, "zone": c.zone,
        "latitude": c.latitude, "longitude": c.longitude, "enabled": c.enabled,
        "live": c.id in manager.workers,
        **(manager.workers[c.id].status if c.id in manager.workers else {}),
    } for c in cams]


@app.post("/api/cameras")
def add_camera(payload: dict, db: Session = Depends(get_db)):
    cam = models.Camera(
        name=payload["name"], source=str(payload["source"]),
        latitude=float(payload["latitude"]), longitude=float(payload["longitude"]),
        zone=payload.get("zone", "public"),
    )
    db.add(cam)
    db.commit()
    db.refresh(cam)
    manager.start_camera(cam)
    return {"id": cam.id}


@app.get("/api/cameras/{cam_id}/stream")
def mjpeg_stream(cam_id: int):
    worker = manager.workers.get(cam_id)
    if not worker:
        raise HTTPException(404, "camera not running")

    def gen():
        import time
        while True:
            if worker.latest_jpeg:
                yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                       + worker.latest_jpeg + b"\r\n")
            time.sleep(1 / 15)

    return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame")


# ---------- Incidents & review ----------

@app.get("/api/incidents")
def list_incidents(limit: int = 50, db: Session = Depends(get_db)):
    incs = (db.query(models.Incident)
            .order_by(models.Incident.created_at.desc()).limit(limit).all())
    return [{
        "id": i.id, "camera_id": i.camera_id,
        "camera_name": i.camera.name if i.camera else None,
        "created_at": i.created_at.isoformat(), "kind": i.kind,
        "score": i.fused_score, "signals": i.signal_breakdown, "status": i.status,
        "nearest_station": (db.get(models.PoliceStation, i.nearest_station_id).name
                            if i.nearest_station_id else None),
        "nearest_station_km": i.nearest_station_km,
        "has_evidence": bool(i.evidence_blurred_path),
    } for i in incs]


@app.post("/api/incidents/{inc_id}/confirm")
def confirm_incident(inc_id: int, db: Session = Depends(get_db)):
    """HUMAN-IN-THE-LOOP gate: this endpoint is the ONLY path to outbound alerts."""
    inc = db.get(models.Incident, inc_id)
    if not inc:
        raise HTTPException(404)
    if inc.status == "confirmed":
        return {"status": "already_confirmed"}
    inc.status = "confirmed"
    db.commit()
    results = broker.dispatch(db, inc)
    manager.bus.publish({"type": "incident_update", "id": inc.id,
                         "status": "confirmed", "alerts": results})
    return {"status": "confirmed", "alerts": results}


@app.post("/api/incidents/{inc_id}/dismiss")
def dismiss_incident(inc_id: int, db: Session = Depends(get_db)):
    inc = db.get(models.Incident, inc_id)
    if not inc:
        raise HTTPException(404)
    inc.status = "dismissed"
    db.commit()
    manager.bus.publish({"type": "incident_update", "id": inc.id, "status": "dismissed"})
    return {"status": "dismissed"}


@app.get("/api/incidents/{inc_id}/evidence")
def get_evidence(inc_id: int, db: Session = Depends(get_db)):
    """Serves the PRIVACY-BLURRED clip only. Raw clip requires filesystem access."""
    inc = db.get(models.Incident, inc_id)
    if not inc or not inc.evidence_blurred_path or not os.path.exists(inc.evidence_blurred_path):
        raise HTTPException(404, "evidence not ready")
    return FileResponse(inc.evidence_blurred_path, media_type="video/mp4")


# ---------- Stations ----------

@app.get("/api/stations")
def list_stations(db: Session = Depends(get_db)):
    return [{"id": s.id, "name": s.name, "latitude": s.latitude,
             "longitude": s.longitude, "phone": s.phone} for s in
            db.query(models.PoliceStation).all()]


# ---------- Live event stream ----------

@app.websocket("/ws/events")
async def ws_events(ws: WebSocket):
    await ws.accept()
    q = manager.bus.subscribe()
    try:
        while True:
            try:
                event = q.get_nowait()
                await ws.send_json(event)
            except Exception:
                await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        pass
    finally:
        manager.bus.unsubscribe(q)
