# Training the Advanced Models

The base system runs on heuristics. These three trained models upgrade it to
research grade. All are trainable on free GPUs (Kaggle: 30h/week, Colab).
Drop finished weights into `backend/weights/` — the adapters in
`app/pipeline/advanced.py` auto-enable when the files exist.

## 1. X3D-M violence classifier → `weights/x3d_violence.pt`

Datasets: SCVD (Kaggle, CC BY-NC-SA 4.0) + UBI-Fights (frame-level labels).
Do NOT redistribute RWF-2000 — its authors withdrew redistribution; use it
only as a private benchmark if you already hold a copy.

```python
# Kaggle notebook, PyTorch
import torch
model = torch.hub.load('facebookresearch/pytorchvideo', 'x3d_m', pretrained=True)
model.blocks[-1].proj = torch.nn.Linear(model.blocks[-1].proj.in_features, 1)
# Train: BCEWithLogitsLoss, clips of 16 frames @ 182x182, AdamW lr=1e-4,
# ~10-15 epochs. Aim: >=85% accuracy on a held-out SCVD split.
scripted = torch.jit.script(model.eval())
scripted.save('x3d_violence.pt')
```

Report: video-level accuracy + frame-level false-alarm rate on UBI-Fights.

## 2. PoseC3D two-person interaction → `weights/posec3d_ntu120.pth`

Framework: MMAction2 (OpenMMLab). Data: NTU RGB+D 120 mutual-action subset
(26 classes incl. punch, kick, push, slap — request academic access), plus
SBU-Kinect / UT-Interaction for fine-tuning.

```bash
pip install -U openmim && mim install mmengine mmcv mmdet mmpose mmaction2
# Fine-tune the NTU120 PoseC3D config on the 26 mutual classes:
python tools/train.py configs/skeleton/posec3d/slowonly_r50_ntu120_xsub_keypoint.py \
  --cfg-options load_from=<pretrained_ckpt> train_dataloader.batch_size=8
```

Deployment note: PoseC3D needs a pose stage (HRNet). Run it CASCADED — the
adapter only fires when proximity/pursuit gate is active — otherwise a Jetson
cannot hold the pipeline. Map aggressive classes (punch/kick/push/grab) to the
`interaction_posec3d` score; benign classes (handshake/hug) suppress it.

## 3. RTFM anomaly head → `weights/rtfm_ucfcrime.pkl`

Data: UCF-Crime pre-extracted I3D features (publicly hosted — search
"UCF-Crime I3D features" / the DeepMIL and RTFM repos). Training the RTFM
head on features takes <1 GPU-hour.

```bash
git clone https://github.com/tianyu0207/RTFM && cd RTFM
# point list files at the downloaded I3D features, then:
python main.py   # expect ~84% frame-level AUC on UCF-Crime
```

Live inference: extract I3D features over a sliding window (64 frames,
stride 25) and score each window. Expect a modest AUC drop vs offline
whole-video scoring — report both numbers honestly.

## 4. Edge deployment (connects to your compression paper)

```bash
# YOLO: export TensorRT INT8 on the Jetson itself
yolo export model=yolov8n.pt format=engine int8=True data=coco8.yaml
# then set YOLO_MODEL=yolov8n.engine
sudo nvpmodel -m 0 && sudo jetson_clocks
```

Measure and report per model: FPS/stream, latency ms/clip, AP/AUC drop
after INT8, and false-alarm rate before/after fusion. That table IS the
core result for both the thesis and the compression paper.
