"""Geofenced nearest-station routing.
Uses haversine over the seeded stations table (works on SQLite).
On Postgres+PostGIS, replace with ST_Distance for index-backed queries."""
import math
from sqlalchemy.orm import Session
from .. import models


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def nearest_station(db: Session, lat: float, lon: float):
    best, best_d = None, float("inf")
    for st in db.query(models.PoliceStation).all():
        d = haversine_km(lat, lon, st.latitude, st.longitude)
        if d < best_d:
            best, best_d = st, d
    return best, best_d
