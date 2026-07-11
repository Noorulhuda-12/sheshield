"""Seeds the DB with demo cameras and Faisalabad police stations.
Station coordinates are approximate (sourced from OpenStreetMap-style data);
verify phone/email with each station before registering real duty contacts.
Run:  python seed.py [optional_video_path_or_camera_index]"""
import sys
from app.database import Base, engine, SessionLocal
from app import models

Base.metadata.create_all(bind=engine)
db = SessionLocal()

STATIONS = [
    # (name, lat, lon)  - approximate Faisalabad locations
    ("Civil Lines Police Station",   31.4221, 73.0891),
    ("Kotwali Police Station",       31.4187, 73.0791),
    ("Peoples Colony Police Station", 31.4304, 73.1105),
    ("Madina Town Police Station",   31.4402, 73.1180),
    ("Gulberg Police Station",       31.4329, 73.0679),
    ("Jhang Bazar Police Station",   31.4126, 73.0741),
    ("Women Police Station Faisalabad", 31.4180, 73.0830),
]

if not db.query(models.PoliceStation).count():
    for name, lat, lon in STATIONS:
        db.add(models.PoliceStation(name=name, latitude=lat, longitude=lon))
    print(f"Seeded {len(STATIONS)} police stations.")

source = sys.argv[1] if len(sys.argv) > 1 else "0"  # default: webcam 0
if not db.query(models.Camera).count():
    db.add(models.Camera(name="Demo Cam - Clock Tower Area", source=source,
                         latitude=31.4187, longitude=73.0791, zone="public"))
    print(f"Seeded demo camera with source={source!r}.")

db.commit()
db.close()
print("Done. Start the server: uvicorn app.main:app --reload --port 8000")
