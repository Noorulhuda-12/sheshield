"""Alert dispatch. Design rules (non-negotiable):

1. HUMAN-IN-THE-LOOP: nothing leaves this system until an operator clicks
   Confirm on the dashboard. Auto-dispatching an unverified AI alert to
   police would be irresponsible and would destroy trust after the first
   false alarm.
2. HONESTY: Pakistan has no public police API. Real dispatch = a human
   calls 15, uses the PSCA Women Safety App, or WhatsApp 0307-0000015.
   The "psca_simulated" channel below is a labeled mock for demo/thesis;
   every AlertLog row records simulated=True/False for the audit trail.
3. PRIVACY: only the face-blurred evidence clip is referenced in outbound
   messages; the raw clip stays access-controlled."""
import logging
import smtplib
from email.message import EmailMessage
from sqlalchemy.orm import Session
from ..config import settings
from .. import models

log = logging.getLogger("alerts")


def _log_alert(db: Session, incident_id: int, channel: str, recipient: str,
               payload: dict, simulated: bool):
    db.add(models.AlertLog(incident_id=incident_id, channel=channel,
                           recipient=recipient, payload=payload, simulated=simulated))
    db.commit()


def _build_message(inc: models.Incident) -> str:
    cam = inc.camera
    return (
        f"SHESHIELD-GUARD ALERT (operator-confirmed)\n"
        f"Type: {inc.kind} | Confidence: {inc.fused_score:.2f}\n"
        f"Camera: {cam.name} @ {cam.latitude:.5f},{cam.longitude:.5f}\n"
        f"Time (UTC): {inc.created_at.isoformat()}\n"
        f"Maps: https://maps.google.com/?q={cam.latitude},{cam.longitude}\n"
        f"Evidence (privacy-blurred): {inc.evidence_blurred_path}\n"
        f"NOTE: This is a courtesy notification, not an official dispatch. "
        f"Call 15 for emergency response."
    )


def dispatch(db: Session, incident: models.Incident) -> list[dict]:
    """Called ONLY after operator confirmation. Returns per-channel results."""
    results = []
    body = _build_message(incident)
    station = db.get(models.PoliceStation, incident.nearest_station_id) \
        if incident.nearest_station_id else None

    # --- Channel 1: Twilio SMS to registered station duty number ---
    if settings.TWILIO_SID and settings.TWILIO_TOKEN and station and station.phone:
        try:
            from twilio.rest import Client
            Client(settings.TWILIO_SID, settings.TWILIO_TOKEN).messages.create(
                to=station.phone, from_=settings.TWILIO_FROM, body=body)
            _log_alert(db, incident.id, "sms", station.phone, {"body": body}, simulated=False)
            results.append({"channel": "sms", "recipient": station.phone, "ok": True, "simulated": False})
        except Exception as e:
            log.exception("Twilio send failed")
            results.append({"channel": "sms", "ok": False, "error": str(e)})
    else:
        _log_alert(db, incident.id, "sms", station.phone if station else "unregistered",
                   {"body": body, "note": "Twilio not configured - logged only"}, simulated=True)
        results.append({"channel": "sms", "ok": True, "simulated": True})

    # --- Channel 2: Email to station ---
    if settings.SMTP_HOST and station and station.email:
        try:
            msg = EmailMessage()
            msg["Subject"] = f"[SheShield-Guard] Confirmed {incident.kind} incident #{incident.id}"
            msg["From"] = settings.SMTP_USER
            msg["To"] = station.email
            msg.set_content(body)
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as s:
                s.starttls()
                s.login(settings.SMTP_USER, settings.SMTP_PASS)
                s.send_message(msg)
            _log_alert(db, incident.id, "email", station.email, {"body": body}, simulated=False)
            results.append({"channel": "email", "recipient": station.email, "ok": True, "simulated": False})
        except Exception as e:
            log.exception("SMTP send failed")
            results.append({"channel": "email", "ok": False, "error": str(e)})
    else:
        _log_alert(db, incident.id, "email", station.email if station else "unregistered",
                   {"body": body, "note": "SMTP not configured - logged only"}, simulated=True)
        results.append({"channel": "email", "ok": True, "simulated": True})

    # --- Channel 3: PSCA endpoint - ALWAYS simulated (no public API exists) ---
    payload = {
        "incident_id": incident.id, "kind": incident.kind, "score": incident.fused_score,
        "lat": incident.camera.latitude, "lon": incident.camera.longitude,
        "nearest_station": station.name if station else None,
        "endpoint": settings.PSCA_SIMULATED_ENDPOINT,
    }
    _log_alert(db, incident.id, "psca_simulated", settings.PSCA_SIMULATED_ENDPOINT,
               payload, simulated=True)
    results.append({"channel": "psca_simulated", "ok": True, "simulated": True})
    return results
