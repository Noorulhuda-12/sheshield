# SheShield-Guard

Advanced multi-camera CCTV safety console for women's safety in public and
private spaces. Extends SheShield (fall / SOS gesture / facial distress) with
**person-to-person analysis**: proximity, pursuit/stalking, violent-motion
detection, anomaly hooks, multi-signal fusion, privacy-blurred evidence
recording, and human-confirmed alerting routed to the nearest police station.

## What is real vs simulated — read this first

- **Real:** live RTSP/webcam/file ingestion, YOLOv8+ByteTrack tracking,
  proximity/pursuit/violence/fall/loiter signals, fusion + escalation,
  evidence clips (raw + face-blurred), nearest-station routing, Twilio SMS
  and SMTP email (when you supply credentials), full audit log.
- **Heuristic (upgradeable):** the violent-motion signal is frame-difference
  based until you train X3D / PoseC3D / RTFM per `docs/TRAINING.md`. The
  fusion layer treats trained scores and heuristics identically.
- **Simulated (always):** the "PSCA endpoint" channel. Pakistan has no public
  police API. Real dispatch = call **15**, the PSCA Women Safety App, or
  WhatsApp **0307-0000015**. Every alert row records `simulated=true/false`.
  Production alerting to police requires an MoU with PSCA/Punjab Police.
- **Never automatic:** no alert leaves the system without an operator
  clicking Confirm. This is deliberate false-alarm protection, not a gap.

## Quickstart (no Docker, CPU laptop)

```bash
# Backend
cd backend
pip install -r requirements.txt
python seed.py 0            # 0 = default webcam; or: python seed.py path/to/video.mp4
uvicorn app.main:app --reload --port 8000

# Frontend (new terminal)
cd frontend
npm install
npm run dev                 # open http://localhost:5173
```

Demo tip: two people approaching each other quickly and moving erratically in
frame will raise `proximity` + `motion_violence`, escalate the camera to
SUSPECT then CRITICAL, create an incident with an evidence clip, and surface
Confirm/Dismiss on the dashboard.

Docker: `docker compose up --build` (webcams need a device passthrough; RTSP
and file sources work out of the box).

## Architecture

```
RTSP / webcam / file
      │  (thread per camera)
      ▼
YOLOv8n + ByteTrack ──► SignalEngine ──► AdvancedModels (optional, cascaded)
   every N frames        proximity        X3D violence / PoseC3D / RTFM
                         pursuit               │
                         motion_violence       ▼
                         fall / loiter    FusionEngine  (weights + EMA +
                              │           consecutive-window escalation)
                              ▼                │ CRITICAL (edge-triggered)
                    ring-buffer ±15s           ▼
                    evidence recorder ◄── Incident (pending_review) ──► WebSocket
                    raw + face-blurred                                    │
                                                                          ▼
                                              React console: live tiles (MJPEG),
                                              threat meters, incident feed, map
                                                          │ operator Confirm
                                                          ▼
                                        Alert broker: Twilio SMS + email to
                                        nearest station (haversine/PostGIS)
                                        + labeled simulated PSCA channel
```

Live view is annotated MJPEG (zero client dependencies). For sub-second
multi-viewer streaming, put go2rtc/MediaMTX in front of the RTSP sources and
swap the tile `<img>` for a WebRTC player — the backend does not change.

## Roadmap to research grade

1. Train the three models in `docs/TRAINING.md` (free Kaggle/Colab GPUs).
2. Port to Jetson Orin Nano: TensorRT INT8 export, DeepStream multi-stream
   (~3–4 cameras per Nano with the full pipeline).
3. Collect a consented local dataset; report frame-level AUC, AP, FPS,
   latency, and false-alarm rate before/after fusion.
4. Pursue a PSCA / university MoU before any claim of real police dispatch.

## Ethics

"Harassment" is not a visual class any model outputs reliably; this system
detects proxies (violent motion, pursuit, proximity, anomaly) and REQUIRES a
human decision before action. Faces of bystanders are blurred in every clip
that leaves the system. Do not deploy on people who have not consented or
outside a lawful CCTV context.
