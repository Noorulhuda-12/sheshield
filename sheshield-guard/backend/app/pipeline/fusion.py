"""Multi-signal fusion + temporal smoothing + escalation state machine.

Why fusion: no single signal reliably means "harassment". Requiring
agreement across signals + persistence over time is the primary
false-alarm defense (the make-or-break property of any real deployment)."""
import time
from ..config import settings

# Weights encode: violent motion between close people is the strongest cue;
# pursuit is a strong precursor; fall matters on its own; loitering is weak alone.
# Calibration invariants (verified in tests): fall alone escalates;
# violent motion + close proximity escalates; sustained pursuit + very close
# proximity escalates; proximity or loitering alone can never escalate.
WEIGHTS = {
    "motion_violence": 0.50,
    "violence_x3d":    0.55,   # trained model, if plugged in (advanced.py)
    "interaction_posec3d": 0.55,
    "anomaly_rtfm":    0.35,
    "pursuit":         0.40,
    "proximity":       0.20,
    "fall":            0.75,
    "loitering":       0.10,
}

# Kind classification: which dominant signal names the incident.
KIND_MAP = [
    ("fall", "fall"),
    ("violence_x3d", "violence"),
    ("motion_violence", "violence"),
    ("interaction_posec3d", "harassment_suspected"),
    ("pursuit", "pursuit"),
    ("anomaly_rtfm", "anomaly"),
    ("proximity", "harassment_suspected"),
    ("loitering", "anomaly"),
]


class FusionEngine:
    """One instance per camera."""
    def __init__(self):
        self.ema = 0.0
        self.hot_windows = 0
        self.state = "CLEAR"          # CLEAR | SUSPECT | CRITICAL
        self.last_incident_at = 0.0
        self.last_signals = {}

    def step(self, signals: dict):
        """Feed one signal window. Returns (state, fused_score, incident_kind_or_None).
        incident_kind is non-None exactly once per escalation (edge-triggered)."""
        self.last_signals = signals
        # Weighted fusion, capped at 1. Proximity alone can never escalate:
        # it only counts when at least one behavioral signal is also active.
        behavioral = any(signals.get(k, 0) > 0.3 for k in
                         ("motion_violence", "violence_x3d", "interaction_posec3d",
                          "pursuit", "fall", "anomaly_rtfm"))
        raw = 0.0
        for name, w in WEIGHTS.items():
            v = signals.get(name, 0.0)
            if name == "proximity" and not behavioral:
                v = 0.0
            raw += w * v
        raw = min(raw, 1.0)

        # Temporal smoothing (EMA) - a single spiky frame cannot trigger anything.
        self.ema = settings.EMA_ALPHA * raw + (1 - settings.EMA_ALPHA) * self.ema

        incident_kind = None
        if self.ema >= settings.CRITICAL_SCORE:
            self.hot_windows += 1
            if (self.hot_windows >= settings.CONSECUTIVE_WINDOWS
                    and self.state != "CRITICAL"
                    and time.time() - self.last_incident_at > settings.INCIDENT_COOLDOWN_SECONDS):
                self.state = "CRITICAL"
                self.last_incident_at = time.time()
                incident_kind = self._classify(signals)
        elif self.ema >= settings.SUSPECT_SCORE:
            self.state = "SUSPECT"
            self.hot_windows = 0
        else:
            self.state = "CLEAR"
            self.hot_windows = 0

        return self.state, round(self.ema, 3), incident_kind

    @staticmethod
    def _classify(signals):
        for key, kind in KIND_MAP:
            if signals.get(key, 0.0) >= 0.5:
                return kind
        return "anomaly"
