# MIT License
#
# Copyright (c) 2026 Claudroponics
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""YOLOv8 CPU inference wrapper for plant health and maturity detection.

Wraps the ``ultralytics`` YOLO instance-segmentation API, maps raw
prediction outputs to typed :class:`PlantDetection` dataclasses, and
provides graceful mock-mode fallback when the model file is absent.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Valid class labels (must match YOLO training config)
# ---------------------------------------------------------------------------

HEALTH_CLASSES: tuple[str, ...] = (
    "healthy",
    "nitrogen_deficiency",
    "phosphorus_deficiency",
    "potassium_deficiency",
    "iron_deficiency",
    "disease_fungal",
    "disease_bacterial",
)

MATURITY_CLASSES: tuple[str, ...] = (
    "immature",
    "vegetative",
    "mature",
    "overmature",
)


# ---------------------------------------------------------------------------
# Detection result dataclass
# ---------------------------------------------------------------------------

@dataclass
class PlantDetection:
    """Single plant detection from YOLO instance segmentation.

    Attributes:
        bbox: Bounding box as ``[x1, y1, x2, y2]`` in pixel coordinates
            (floats, relative to the input image).
        mask: Binary segmentation mask (H x W, dtype uint8, values 0/255).
            May be ``None`` if the model did not produce a mask for this
            detection (e.g. in mock mode or detection-only models).
        health_class: Predicted health state label.  One of
            :data:`HEALTH_CLASSES`.
        maturity_class: Predicted maturity stage label.  One of
            :data:`MATURITY_CLASSES`.
        confidence: Detection confidence score in ``[0.0, 1.0]``.
    """

    bbox: list[float]
    mask: Optional[np.ndarray]
    health_class: str
    maturity_class: str
    confidence: float


# ---------------------------------------------------------------------------
# YoloInference
# ---------------------------------------------------------------------------

class YoloInference:
    """YOLOv8 segmentation inference wrapper with lazy model loading.

    The ``ultralytics`` package is imported only when :meth:`predict` is
    called for the first time (or explicitly via :meth:`load`), keeping
    import time low and enabling the rest of the node to start even if
    ``ultralytics`` is not installed.

    When the model file does not exist, the wrapper logs a warning and
    operates in *mock mode*, returning an empty detection list on every
    call so that the rest of the pipeline can be tested without hardware.

    Args:
        model_path: Path to the ``.pt`` weights file.
        confidence_threshold: Minimum detection confidence ``(0, 1]``.
        iou_threshold: NMS IoU threshold ``(0, 1]``.
        inference_size: Square image size passed to YOLO (e.g. 640).
    """

    def __init__(
        self,
        model_path: str,
        confidence_threshold: float,
        iou_threshold: float,
        inference_size: int,
    ) -> None:
        self._model_path: str = model_path
        self._conf: float = confidence_threshold
        self._iou: float = iou_threshold
        self._imgsz: int = inference_size
        self._model: Optional[object] = None
        self._mock_mode: bool = False

        logger.info(
            "YoloInference created: model='%s'  conf=%.2f  iou=%.2f  size=%d",
            model_path,
            confidence_threshold,
            iou_threshold,
            inference_size,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Explicitly load (or reload) the YOLO model from disk.

        Called automatically on the first :meth:`predict` call.  Invoke
        directly to pre-warm the model at node startup.

        Sets ``_mock_mode = True`` if the model file is not found, so that
        subsequent :meth:`predict` calls return empty lists with a warning
        rather than raising an exception.
        """
        if not os.path.isfile(self._model_path):
            logger.warning(
                "YoloInference: model file not found at '%s'; "
                "entering mock mode — predict() will return []",
                self._model_path,
            )
            self._mock_mode = True
            return

        try:
            from ultralytics import YOLO  # noqa: PLC0415 — lazy import
            self._model = YOLO(self._model_path, task="segment")
            # Force CPU; avoids CUDA dependency on embedded hardware.
            logger.info(
                "YoloInference: model loaded from '%s'", self._model_path
            )
            self._mock_mode = False
        except Exception as exc:  # broad catch: import errors, file errors, etc.
            logger.warning(
                "YoloInference: failed to load model from '%s' (%s); "
                "entering mock mode",
                self._model_path,
                exc,
            )
            self._mock_mode = True

    def predict(self, image: np.ndarray) -> list[PlantDetection]:
        """Run inference on a BGR image and return per-plant detections.

        Args:
            image: BGR numpy array (H x W x 3, dtype uint8) as returned
                by OpenCV or :class:`~hydroponics_vision.camera_manager.CameraManager`.

        Returns:
            List of :class:`PlantDetection` objects, one per detected
            plant instance.  Returns ``[]`` in mock mode or if the image
            is invalid.
        """
        if image is None or image.size == 0:
            logger.warning("YoloInference.predict: empty image provided; returning []")
            return []

        # Lazy-load on first call.
        if self._model is None and not self._mock_mode:
            self.load()

        if self._mock_mode:
            logger.debug("YoloInference.predict: mock mode — returning []")
            return []

        try:
            return self._run_inference(image)
        except Exception as exc:
            logger.error(
                "YoloInference.predict: inference error (%s); returning []", exc
            )
            return []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run_inference(self, image: np.ndarray) -> list[PlantDetection]:
        """Execute YOLO inference and convert results to PlantDetection list.

        Args:
            image: Valid BGR image array.

        Returns:
            List of :class:`PlantDetection` instances.
        """
        results = self._model(  # type: ignore[operator]
            image,
            conf=self._conf,
            iou=self._iou,
            imgsz=self._imgsz,
            device="cpu",
            verbose=False,
        )

        detections: list[PlantDetection] = []

        for result in results:
            boxes = result.boxes
            masks_data = result.masks  # may be None for detection-only models

            if boxes is None or len(boxes) == 0:
                continue

            num_detections: int = len(boxes)

            for i in range(num_detections):
                # ---- Bounding box ----
                xyxy = boxes.xyxy[i].cpu().numpy().tolist()

                # ---- Confidence ----
                conf_val: float = float(boxes.conf[i].cpu().item())

                # ---- Class index and label lookup ----
                cls_idx: int = int(boxes.cls[i].cpu().item())
                names: dict[int, str] = result.names  # {idx: label_str}

                raw_label: str = names.get(cls_idx, "healthy")
                health_class, maturity_class = self._split_label(raw_label)

                # ---- Segmentation mask ----
                seg_mask: Optional[np.ndarray] = None
                if masks_data is not None and i < len(masks_data.data):
                    raw_mask: np.ndarray = (
                        masks_data.data[i].cpu().numpy()
                    )
                    # Binarise and convert to uint8 (0/255).
                    seg_mask = (raw_mask > 0.5).astype(np.uint8) * 255

                detections.append(
                    PlantDetection(
                        bbox=xyxy,
                        mask=seg_mask,
                        health_class=health_class,
                        maturity_class=maturity_class,
                        confidence=conf_val,
                    )
                )

        logger.debug(
            "YoloInference._run_inference: %d detection(s) returned",
            len(detections),
        )
        return detections

    @staticmethod
    def _split_label(raw_label: str) -> tuple[str, str]:
        """Parse a compound YOLO label into (health_class, maturity_class).

        The training convention encodes both dimensions as a single string
        with ``"|"`` as separator, e.g. ``"nitrogen_deficiency|vegetative"``.
        If only one component is present it is matched against both class
        lists; unrecognised labels fall back to safe defaults.

        Args:
            raw_label: Label string from ``result.names``.

        Returns:
            ``(health_class, maturity_class)`` tuple with validated values.
        """
        parts: list[str] = raw_label.split("|")

        health_class: str = "healthy"
        maturity_class: str = "vegetative"

        if len(parts) >= 2:
            candidate_health: str = parts[0].strip()
            candidate_maturity: str = parts[1].strip()
            if candidate_health in HEALTH_CLASSES:
                health_class = candidate_health
            else:
                logger.debug(
                    "_split_label: '%s' not in HEALTH_CLASSES; defaulting to 'healthy'",
                    candidate_health,
                )
            if candidate_maturity in MATURITY_CLASSES:
                maturity_class = candidate_maturity
            else:
                logger.debug(
                    "_split_label: '%s' not in MATURITY_CLASSES; "
                    "defaulting to 'vegetative'",
                    candidate_maturity,
                )
        elif len(parts) == 1:
            single: str = parts[0].strip()
            if single in HEALTH_CLASSES:
                health_class = single
            elif single in MATURITY_CLASSES:
                maturity_class = single
            else:
                logger.debug(
                    "_split_label: '%s' unrecognised; using defaults", single
                )

        return health_class, maturity_class
