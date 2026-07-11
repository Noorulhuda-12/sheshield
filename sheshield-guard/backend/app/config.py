"""Central configuration. Every threshold that controls detection lives here
so tuning does not require touching pipeline code."""
import os


class Settings:
    # --- Database ---
    # SQLite by default so the project runs with zero setup.
    # Set DATABASE_URL=postgresql://user:pass@host/db for production (PostGIS optional).
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./sheshield.db")

    # --- Detection model ---
    YOLO_MODEL: str = os.getenv("YOLO_MODEL", "yolov8n.pt")  # swap for TensorRT .engine on Jetson
    PERSON_CLASS_ID: int = 0
    DETECT_EVERY_N_FRAMES: int = int(os.getenv("DETECT_EVERY_N_FRAMES", "3"))
    CONF_THRESHOLD: float = 0.4

    # --- Signal thresholds (normalized units unless stated) ---
    # Proximity: pairwise distance / mean bbox height. <1.0 means "within arm's reach".
    PROXIMITY_NEAR: float = 0.8
    # Pursuit: seconds one track must shadow another while both move.
    PURSUIT_SECONDS: float = 6.0
    PURSUIT_MAX_GAP: float = 1.6          # max normalized distance to count as "following"
    PURSUIT_MIN_SPEED: float = 0.02       # both tracks must actually be moving
    # Motion-violence heuristic: frame-diff energy inside a multi-person region.
    VIOLENCE_ENERGY_THRESHOLD: float = 0.16
    # Fall: aspect-ratio flip + vertical drop of bbox center within this many seconds.
    FALL_DROP_SECONDS: float = 0.7
    FALL_DROP_FRACTION: float = 0.25      # center must drop >25% of frame height
    # Loitering
    LOITER_SECONDS: float = 90.0
    LOITER_RADIUS: float = 0.06           # normalized movement radius

    # --- Fusion / escalation ---
    EMA_ALPHA: float = 0.3                # temporal smoothing factor
    SUSPECT_SCORE: float = 0.35           # camera enters SUSPECT state
    CRITICAL_SCORE: float = 0.6           # incident created, evidence recorded
    CONSECUTIVE_WINDOWS: int = 4          # score must persist this many windows
    INCIDENT_COOLDOWN_SECONDS: float = 60 # no duplicate incidents per camera within this

    # --- Evidence ---
    EVIDENCE_DIR: str = os.getenv("EVIDENCE_DIR", "./evidence")
    RING_BUFFER_SECONDS: float = 15.0     # pre-incident footage kept in memory
    POST_INCIDENT_SECONDS: float = 15.0
    BLUR_FACES_IN_SHARED_CLIP: bool = True  # privacy-by-design: shared copy is blurred

    # --- Alerting (all OFF unless credentials provided; nothing fires silently) ---
    TWILIO_SID: str = os.getenv("TWILIO_SID", "")
    TWILIO_TOKEN: str = os.getenv("TWILIO_TOKEN", "")
    TWILIO_FROM: str = os.getenv("TWILIO_FROM", "")
    SMTP_HOST: str = os.getenv("SMTP_HOST", "")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASS: str = os.getenv("SMTP_PASS", "")
    # There is NO public police API in Pakistan. This endpoint is a labeled simulation.
    # Real dispatch paths: call 15, PSCA Women Safety App, WhatsApp 0307-0000015.
    PSCA_SIMULATED_ENDPOINT: str = os.getenv("PSCA_SIMULATED_ENDPOINT", "internal://simulated-psca")
    HUMAN_CONFIRM_REQUIRED: bool = True   # NEVER auto-dispatch. Operator must confirm.


settings = Settings()
