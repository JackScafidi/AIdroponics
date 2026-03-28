# Claudroponics — YOLOv8 Training Guide

This directory contains scripts to build and train the plant health detection
model used by `hydroponics_vision`.

## Classes

| Index | Name | Description |
|---|---|---|
| 0 | healthy | Normal plant, no action needed |
| 1 | mature_ready | Canopy large enough to harvest |
| 2 | nitrogen_deficiency | Yellowing lower leaves |
| 3 | calcium_deficiency | Tip burn, brown leaf edges |
| 4 | iron_deficiency | Interveinal chlorosis on young leaves |
| 5 | overwatered | Wilting + dark stems |
| 6 | disease_suspected | Lesions or mold — triggers safety halt |
| 7 | seedling | Small plant, not yet measurable |

## Workflow

### 1 — Collect frames from the running system

```bash
# Source ROS2 workspace first
source hydroponics_ws/install/setup.bash

# Start data collection (Ctrl+C to stop)
python collect_training_data.py collect --output ./data/raw --limit 500
```

Each camera produces up to `--limit` JPEG files in `data/raw/`.

### 2 — Label frames

```bash
python collect_training_data.py label --raw ./data/raw --out ./data/labelled
```

A window opens for each unlabelled frame. Press 0-7 to assign a class,
`s` to skip, `q` to quit.

### 3 — Split into train / val / test

```bash
python collect_training_data.py split \
    --labelled ./data/labelled \
    --out ./data \
    --train-frac 0.8 \
    --val-frac 0.1
```

### 4 — Train

```bash
pip install ultralytics

# Quick test (nano model, 20 epochs)
python train_yolo.py --model yolov8n.pt --epochs 20 --device cpu

# Full training (small model, GPU recommended)
python train_yolo.py --model yolov8s.pt --epochs 150 --device 0 --export
```

Results land in `runs/detect/claudroponics*/`.

### 5 — Deploy

When prompted, type `y` to copy `best.pt` to the vision node:

```
hydroponics_ws/src/hydroponics_vision/models/plant_health.pt
```

Or copy manually:

```bash
cp runs/detect/claudroponics/weights/best.pt \
   ../hydroponics_ws/src/hydroponics_vision/models/plant_health.pt
```

## Model Selection Guide

| Model | Parameters | RPi 5 CPU FPS | Recommended for |
|---|---|---|---|
| yolov8n | 3.2M | ~4 fps | Fast prototyping |
| yolov8s | 11.2M | ~2 fps | **Default deployment** |
| yolov8m | 25.9M | ~0.8 fps | High-accuracy offline eval |

The vision node calls inference once per inspection cycle (not continuously),
so even 1–2 fps is acceptable.

## Pre-trained Weights

If you do not have your own dataset yet, a community-contributed checkpoint
trained on ~3000 frames of DWC lettuce and herbs can be used as a starting
point. Retrain from that checkpoint rather than `yolov8s.pt` for faster
convergence.

## Minimum Recommended Dataset Size

| Class | Min images |
|---|---|
| healthy | 300 |
| mature_ready | 200 |
| deficiency classes (×4) | 100 each |
| disease_suspected | 150 |
| seedling | 100 |
| **Total** | **~1 150** |

Use data augmentation (`mosaic=1.0`, `hsv_s=0.7`) to stretch a smaller
dataset.
