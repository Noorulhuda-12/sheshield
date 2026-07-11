from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, JSON, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from .database import Base


class Camera(Base):
    __tablename__ = "cameras"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    source = Column(String, nullable=False)   # "0" webcam | file path | rtsp:// URL
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    zone = Column(String, default="public")    # public | private
    enabled = Column(Boolean, default=True)
    incidents = relationship("Incident", back_populates="camera")


class PoliceStation(Base):
    __tablename__ = "police_stations"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    phone = Column(String, default="")         # duty officer number if registered
    email = Column(String, default="")
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)


class Incident(Base):
    __tablename__ = "incidents"
    id = Column(Integer, primary_key=True)
    camera_id = Column(Integer, ForeignKey("cameras.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    kind = Column(String)                      # harassment_suspected | violence | fall | pursuit | anomaly
    fused_score = Column(Float)
    signal_breakdown = Column(JSON)            # {"proximity":0.9,"motion":0.7,...}
    status = Column(String, default="pending_review")  # pending_review | confirmed | dismissed
    evidence_path = Column(String, default="")          # raw clip (restricted)
    evidence_blurred_path = Column(String, default="")  # privacy-blurred shareable clip
    nearest_station_id = Column(Integer, ForeignKey("police_stations.id"), nullable=True)
    nearest_station_km = Column(Float, nullable=True)
    camera = relationship("Camera", back_populates="incidents")
    alerts = relationship("AlertLog", back_populates="incident")


class AlertLog(Base):
    __tablename__ = "alert_log"
    id = Column(Integer, primary_key=True)
    incident_id = Column(Integer, ForeignKey("incidents.id"))
    sent_at = Column(DateTime, default=datetime.utcnow)
    channel = Column(String)                   # sms | email | psca_simulated
    recipient = Column(String)
    payload = Column(JSON)
    simulated = Column(Boolean, default=False) # audit trail: was this real or simulated?
    incident = relationship("Incident", back_populates="alerts")
