"""Plug-in interface for trained deep models. All are OPTIONAL - the system
runs on heuristics without them. Once you train a model (docs/TRAINING.md),
drop the weights in ./weights/ and enable the flag; fusion.py already carries
weights for each score name.

Contract: each adapter buffers frames and, when ready, returns
{score_name: float 0..1} which SignalEngine merges into the signal dict.
"""
import os
from collections import deque
import numpy as np

WEIGHTS_DIR = os.getenv("WEIGHTS_DIR", "./weights")


class X3DViolenceAdapter:
    """RGB violence classifier. Train X3D-M / MoViNet-A2 on SCVD + UBI-Fights
    (see docs/TRAINING.md #1). Expects a TorchScript file x3d_violence.pt that
    maps a (1,3,T,H,W) clip -> violence probability."""
    SCORE_NAME = "violence_x3d"
    CLIP_LEN = 16          # frames per inference clip
    SIZE = 182             # X3D-M input side

    def __init__(self):
        self.buffer = deque(maxlen=self.CLIP_LEN)
        self.model = None
        path = os.path.join(WEIGHTS_DIR, "x3d_violence.pt")
        if os.path.exists(path):
            import torch
            self.model = torch.jit.load(path).eval()
            self.torch = torch

    @property
    def enabled(self):
        return self.model is not None

    def push(self, frame_bgr) -> dict:
        if not self.enabled:
            return {}
        import cv2
        f = cv2.resize(frame_bgr, (self.SIZE, self.SIZE))[:, :, ::-1] / 255.0
        self.buffer.append(f.astype(np.float32))
        if len(self.buffer) < self.CLIP_LEN:
            return {}
        clip = np.stack(self.buffer).transpose(3, 0, 1, 2)[None]  # 1,C,T,H,W
        with self.torch.no_grad():
            prob = float(self.torch.sigmoid(self.model(self.torch.from_numpy(clip))).item())
        return {self.SCORE_NAME: prob}


class PoseC3DInteractionAdapter:
    """Skeleton-based two-person interaction classifier (MMAction2 PoseC3D,
    fine-tuned on NTU RGB+D 120 mutual actions). Heavy: run it CASCADED -
    only when proximity/pursuit are already elevated - so the expensive pose
    stage does not run on empty scenes. See docs/TRAINING.md #2 for the full
    MMAction2 inference wiring; this stub defines the integration point."""
    SCORE_NAME = "interaction_posec3d"

    def __init__(self):
        self.enabled = os.path.exists(os.path.join(WEIGHTS_DIR, "posec3d_ntu120.pth"))
        # Full wiring requires mmaction2 + mmpose installed; intentionally not
        # imported here so the base system stays lightweight.

    def push(self, frame_bgr, gate_active: bool) -> dict:
        if not self.enabled or not gate_active:
            return {}
        raise NotImplementedError(
            "Install mmaction2/mmpose and complete this adapter per docs/TRAINING.md #2."
        )


class RTFMAnomalyAdapter:
    """Weakly-supervised video anomaly detection (RTFM on I3D features,
    trained on UCF-Crime). Runs on a sliding window of I3D snippet features.
    See docs/TRAINING.md #3."""
    SCORE_NAME = "anomaly_rtfm"

    def __init__(self):
        self.enabled = os.path.exists(os.path.join(WEIGHTS_DIR, "rtfm_ucfcrime.pkl"))

    def push(self, frame_bgr) -> dict:
        if not self.enabled:
            return {}
        raise NotImplementedError(
            "Complete per docs/TRAINING.md #3 (I3D feature extractor + RTFM head)."
        )


class AdvancedModels:
    """Facade used by the camera worker."""
    def __init__(self):
        self.x3d = X3DViolenceAdapter()
        self.posec3d = PoseC3DInteractionAdapter()
        self.rtfm = RTFMAnomalyAdapter()

    def scores(self, frame_bgr, base_signals: dict) -> dict:
        out = {}
        out.update(self.x3d.push(frame_bgr))
        gate = base_signals.get("proximity", 0) > 0.4 or base_signals.get("pursuit", 0) > 0.4
        if self.posec3d.enabled:
            out.update(self.posec3d.push(frame_bgr, gate))
        if self.rtfm.enabled:
            out.update(self.rtfm.push(frame_bgr))
        return out
