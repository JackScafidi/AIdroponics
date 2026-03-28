#!/usr/bin/env python3
"""
Collect and label training images from the running Claudroponics system.

This script subscribes to the two camera topics, saves raw frames, and
provides a minimal labelling workflow so you can build a dataset while
the system is running.

Modes:
  collect   — save frames from /camera/overhead/image_raw and /camera/side/image_raw
  label     — interactive terminal labeller for saved frames
  split     — split labelled images into train/val/test and write YOLO label files

Usage:
    # Collect 200 frames per camera (press Ctrl+C to stop early)
    python collect_training_data.py collect --output ./data/raw --limit 200

    # Label saved frames interactively
    python collect_training_data.py label --raw ./data/raw --out ./data/labelled

    # Split into train/val/test (80/10/10)
    python collect_training_data.py split --labelled ./data/labelled --out ./data
"""

import argparse
import json
import os
import random
import shutil
import sys
import time
from pathlib import Path


# ─── Class names (must match dataset_config.yaml) ─────────────────────────────
CLASS_NAMES = [
    "healthy",
    "mature_ready",
    "nitrogen_deficiency",
    "calcium_deficiency",
    "iron_deficiency",
    "overwatered",
    "disease_suspected",
    "seedling",
]
CLASS_INDEX = {name: i for i, name in enumerate(CLASS_NAMES)}


# ─── Collect mode ─────────────────────────────────────────────────────────────

def collect(args: argparse.Namespace) -> None:
    """Subscribe to camera topics and save frames as JPEG files."""
    try:
        import rclpy
        from rclpy.node import Node
        from sensor_msgs.msg import Image
        import cv2
        from cv_bridge import CvBridge
    except ImportError as e:
        raise SystemExit(
            f"Missing dependency: {e}\n"
            "This mode requires a sourced ROS2 workspace with cv_bridge."
        )

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    bridge = CvBridge()
    counts = {"overhead": 0, "side": 0}
    limit = args.limit

    class FrameCollector(Node):
        def __init__(self):
            super().__init__("frame_collector")
            self.sub_overhead = self.create_subscription(
                Image, "/camera/overhead/image_raw",
                lambda msg: self._save(msg, "overhead"), 10
            )
            self.sub_side = self.create_subscription(
                Image, "/camera/side/image_raw",
                lambda msg: self._save(msg, "side"), 10
            )
            self.get_logger().info(f"Saving frames to {output}")

        def _save(self, msg: Image, camera: str) -> None:
            if counts[camera] >= limit:
                return
            try:
                frame = bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")
            except Exception:
                return
            ts = int(time.time() * 1000)
            path = output / f"{camera}_{ts:016d}.jpg"
            cv2.imwrite(str(path), frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
            counts[camera] += 1
            if counts[camera] % 10 == 0:
                self.get_logger().info(
                    f"{camera}: {counts[camera]}/{limit} frames saved"
                )

    rclpy.init()
    node = FrameCollector()
    try:
        while rclpy.ok() and any(v < limit for v in counts.values()):
            rclpy.spin_once(node, timeout_sec=0.1)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

    total = sum(counts.values())
    print(f"\nCollected {total} frames → {output}")


# ─── Label mode ───────────────────────────────────────────────────────────────

def label(args: argparse.Namespace) -> None:
    """
    Show each collected frame and ask the user to assign a class label.
    Saves label as a JSON sidecar: image.jpg → image.json
    {"class": "healthy", "bbox": [cx, cy, w, h]}  (normalised YOLO format)
    bbox defaults to full frame (1 plant per frame assumption).
    """
    try:
        import cv2
    except ImportError:
        raise SystemExit("OpenCV required: pip install opencv-python")

    raw = Path(args.raw)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    images = sorted(raw.glob("*.jpg"))
    if not images:
        raise SystemExit(f"No .jpg files found in {raw}")

    print("\nClass labels:")
    for i, name in enumerate(CLASS_NAMES):
        print(f"  {i} — {name}")
    print("  s — skip   q — quit\n")

    labelled = 0
    for img_path in images:
        label_path = out / (img_path.stem + ".json")
        if label_path.exists():
            continue  # already labelled

        frame = cv2.imread(str(img_path))
        if frame is None:
            continue

        display = cv2.resize(frame, (640, 480))
        cv2.imshow("Label Frame (0-7 / s=skip / q=quit)", display)
        key = cv2.waitKey(0) & 0xFF

        if key == ord("q"):
            break
        if key == ord("s"):
            continue

        digit = key - ord("0")
        if 0 <= digit < len(CLASS_NAMES):
            record = {
                "class": CLASS_NAMES[digit],
                "class_idx": digit,
                "bbox": [0.5, 0.5, 1.0, 1.0],  # full-frame bbox
                "source_image": str(img_path),
            }
            label_path.write_text(json.dumps(record, indent=2))
            # Copy image to output dir
            shutil.copy2(img_path, out / img_path.name)
            labelled += 1

    cv2.destroyAllWindows()
    print(f"\nLabelled {labelled} images → {out}")


# ─── Split mode ───────────────────────────────────────────────────────────────

def split(args: argparse.Namespace) -> None:
    """
    Read labelled JSON sidecars, write YOLO .txt label files, and
    partition into train/val/test directories.
    """
    labelled_dir = Path(args.labelled)
    out_dir = Path(args.out)

    json_files = sorted(labelled_dir.glob("*.json"))
    if not json_files:
        raise SystemExit(f"No JSON label files in {labelled_dir}")

    records = []
    for jf in json_files:
        try:
            data = json.loads(jf.read_text())
        except json.JSONDecodeError:
            continue
        img_path = labelled_dir / (jf.stem + ".jpg")
        if not img_path.exists():
            continue
        records.append((img_path, data))

    random.shuffle(records)
    n = len(records)
    n_train = int(n * args.train_frac)
    n_val   = int(n * args.val_frac)
    splits = {
        "train": records[:n_train],
        "val":   records[n_train:n_train + n_val],
        "test":  records[n_train + n_val:],
    }

    for split_name, items in splits.items():
        img_dir   = out_dir / "images" / split_name
        label_dir = out_dir / "labels" / split_name
        img_dir.mkdir(parents=True, exist_ok=True)
        label_dir.mkdir(parents=True, exist_ok=True)

        for img_path, data in items:
            shutil.copy2(img_path, img_dir / img_path.name)
            cx, cy, w, h = data["bbox"]
            cls = data["class_idx"]
            txt = label_dir / (img_path.stem + ".txt")
            txt.write_text(f"{cls} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}\n")

        print(f"  {split_name}: {len(items)} images")

    print(f"\nDataset written to {out_dir}")
    print("Now run: python train_yolo.py --data dataset_config.yaml")


# ─── Entry point ──────────────────────────────────────────────────────────────

def main() -> None:
    p = argparse.ArgumentParser(description="Collect and label training data")
    sub = p.add_subparsers(dest="mode", required=True)

    # collect
    c = sub.add_parser("collect", help="Save frames from running robot")
    c.add_argument("--output", default="./data/raw")
    c.add_argument("--limit",  type=int, default=500,
                   help="Max frames per camera")

    # label
    la = sub.add_parser("label", help="Interactive terminal labeller")
    la.add_argument("--raw", default="./data/raw")
    la.add_argument("--out", default="./data/labelled")

    # split
    sp = sub.add_parser("split", help="Split labelled data into train/val/test")
    sp.add_argument("--labelled",   default="./data/labelled")
    sp.add_argument("--out",        default="./data")
    sp.add_argument("--train-frac", type=float, default=0.8, dest="train_frac")
    sp.add_argument("--val-frac",   type=float, default=0.1, dest="val_frac")

    args = p.parse_args()

    if args.mode == "collect":
        collect(args)
    elif args.mode == "label":
        label(args)
    elif args.mode == "split":
        split(args)


if __name__ == "__main__":
    main()
