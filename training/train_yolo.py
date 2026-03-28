#!/usr/bin/env python3
"""
Train YOLOv8 model for Claudroponics plant health classification.

Usage:
    python train_yolo.py [--model yolov8n.pt] [--epochs 100] [--imgsz 640]
                         [--data dataset_config.yaml] [--device cpu]

The trained model is saved to runs/detect/claudroponics_*/weights/best.pt.
Copy best.pt to hydroponics_ws/src/hydroponics_vision/models/plant_health.pt
to deploy it on the robot.
"""

import argparse
import shutil
from pathlib import Path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Train YOLOv8 for plant health detection")
    p.add_argument("--model",   default="yolov8n.pt",
                   help="Base model checkpoint (yolov8n/s/m/l/x.pt)")
    p.add_argument("--data",    default="dataset_config.yaml",
                   help="Dataset YAML path")
    p.add_argument("--epochs",  type=int, default=150,
                   help="Training epochs")
    p.add_argument("--imgsz",   type=int, default=640,
                   help="Input image size (pixels)")
    p.add_argument("--batch",   type=int, default=16,
                   help="Batch size (-1 for auto-batch)")
    p.add_argument("--device",  default="0",
                   help="Device: 0 (GPU), cpu, or mps")
    p.add_argument("--workers", type=int, default=4,
                   help="DataLoader worker threads")
    p.add_argument("--patience", type=int, default=30,
                   help="Early stopping patience (epochs)")
    p.add_argument("--project", default="runs/detect",
                   help="Output project directory")
    p.add_argument("--name",    default="claudroponics",
                   help="Run name (auto-incremented)")
    p.add_argument("--resume",  action="store_true",
                   help="Resume interrupted training")
    p.add_argument("--export",  action="store_true",
                   help="Export to ONNX + TFLite after training")
    return p.parse_args()


def train(args: argparse.Namespace) -> Path:
    try:
        from ultralytics import YOLO
    except ImportError:
        raise SystemExit(
            "ultralytics not installed. Run: pip install ultralytics"
        )

    model = YOLO(args.model)

    results = model.train(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        workers=args.workers,
        patience=args.patience,
        project=args.project,
        name=args.name,
        resume=args.resume,
        # Logging
        verbose=True,
        plots=True,
        save=True,
        save_period=10,          # checkpoint every 10 epochs
        # Augmentation overrides (dataset_config.yaml hyp section)
        flipud=0.0,
        fliplr=0.5,
        hsv_h=0.015,
        hsv_s=0.7,
        hsv_v=0.4,
        degrees=5.0,
        translate=0.1,
        scale=0.3,
        mosaic=1.0,
    )

    best_weights = Path(results.save_dir) / "weights" / "best.pt"
    print(f"\nTraining complete. Best weights: {best_weights}")
    return best_weights


def validate(best_weights: Path, args: argparse.Namespace) -> None:
    from ultralytics import YOLO
    model = YOLO(str(best_weights))
    metrics = model.val(data=args.data, imgsz=args.imgsz, device=args.device)
    print(f"\nValidation mAP50: {metrics.box.map50:.4f}")
    print(f"Validation mAP50-95: {metrics.box.map:.4f}")
    print("\nPer-class AP50:")
    for name, ap in zip(metrics.names.values(), metrics.box.ap50):
        print(f"  {name:<25} {ap:.4f}")


def export_model(best_weights: Path, args: argparse.Namespace) -> None:
    from ultralytics import YOLO
    model = YOLO(str(best_weights))

    # ONNX — for possible Coral/CUDA inference
    onnx_path = model.export(format="onnx", imgsz=args.imgsz, simplify=True)
    print(f"ONNX export: {onnx_path}")

    # TFLite INT8 — for Raspberry Pi CPU inference
    tflite_path = model.export(
        format="tflite", imgsz=args.imgsz, int8=True
    )
    print(f"TFLite INT8 export: {tflite_path}")


def deploy(best_weights: Path) -> None:
    """Copy best.pt to the vision node's models directory."""
    dest = Path(__file__).parent.parent / (
        "hydroponics_ws/src/hydroponics_vision/models/plant_health.pt"
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(best_weights, dest)
    print(f"\nDeployed → {dest}")


def main() -> None:
    args = parse_args()

    # Validate dataset exists
    if not Path(args.data).exists():
        raise SystemExit(
            f"Dataset config not found: {args.data}\n"
            "Run collect_training_data.py first, or download a dataset."
        )

    best_weights = train(args)
    validate(best_weights, args)

    if args.export:
        export_model(best_weights, args)

    # Offer to deploy
    deploy_prompt = input("\nDeploy best.pt to vision node? [y/N] ").strip().lower()
    if deploy_prompt == "y":
        deploy(best_weights)


if __name__ == "__main__":
    main()
