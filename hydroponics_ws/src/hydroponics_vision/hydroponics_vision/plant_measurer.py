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

"""Plant physical measurement extraction from camera images.

Provides canopy-area measurement from overhead segmentation masks,
plant-height measurement from side-view images, HSV colour histograms
for longitudinal health tracking, and leaf-count estimation from
instance-segmentation outputs.
"""

from __future__ import annotations

import logging
from typing import Any

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# HSV histogram parameters
# ---------------------------------------------------------------------------

_HSV_H_BINS: int = 36   # 10° per bin
_HSV_S_BINS: int = 32
_HSV_V_BINS: int = 32
_HSV_H_RANGE: list[float] = [0.0, 180.0]
_HSV_S_RANGE: list[float] = [0.0, 256.0]
_HSV_V_RANGE: list[float] = [0.0, 256.0]

# Green-hue window in OpenCV HSV (H: 0-180).
# Topmost-green pixel detection uses these thresholds.
_GREEN_LOWER: np.ndarray = np.array([35, 40, 40], dtype=np.uint8)
_GREEN_UPPER: np.ndarray = np.array([85, 255, 255], dtype=np.uint8)


class PlantMeasurer:
    """Extracts physical measurements from segmentation masks and images.

    All measurements are converted to real-world units (cm or cm²) using
    the calibration factors supplied at construction time.

    Args:
        overhead_px_per_cm: Pixels per centimetre in overhead images.
        side_px_per_cm: Pixels per centimetre in side-view images.
    """

    def __init__(
        self,
        overhead_px_per_cm: float,
        side_px_per_cm: float,
    ) -> None:
        if overhead_px_per_cm <= 0:
            raise ValueError(
                f"overhead_px_per_cm must be positive, got {overhead_px_per_cm}"
            )
        if side_px_per_cm <= 0:
            raise ValueError(
                f"side_px_per_cm must be positive, got {side_px_per_cm}"
            )
        self._overhead_px_per_cm: float = overhead_px_per_cm
        self._side_px_per_cm: float = side_px_per_cm
        logger.info(
            "PlantMeasurer initialised: overhead=%.1f px/cm  side=%.1f px/cm",
            overhead_px_per_cm,
            side_px_per_cm,
        )

    # ------------------------------------------------------------------
    # Public measurement API
    # ------------------------------------------------------------------

    def measure_canopy_area(self, mask: np.ndarray) -> float:
        """Compute canopy area in cm² from a binary segmentation mask.

        Counts non-zero pixels in the overhead segmentation mask and
        converts to cm² using the overhead calibration factor.

        Args:
            mask: 2-D uint8 or bool array where non-zero values indicate
                plant pixels (H x W).

        Returns:
            Canopy area in cm².  Returns ``0.0`` if the mask is empty or
            contains no foreground pixels.
        """
        if mask is None or mask.size == 0:
            logger.warning("measure_canopy_area: received empty mask; returning 0.0")
            return 0.0

        if mask.ndim != 2:
            logger.warning(
                "measure_canopy_area: expected 2-D mask, got shape %s; "
                "using first channel",
                mask.shape,
            )
            mask = mask[:, :, 0]

        pixel_count: int = int(np.count_nonzero(mask))
        # Area in cm²: pixels / (px_per_cm)^2
        area_cm2: float = pixel_count / (self._overhead_px_per_cm ** 2)
        logger.debug(
            "measure_canopy_area: %d px  →  %.2f cm²", pixel_count, area_cm2
        )
        return area_cm2

    def measure_height(
        self,
        side_image: np.ndarray,
        plant_roi: dict[str, int],
    ) -> float:
        """Estimate plant height in cm from the side-view image.

        Crops the image to the plant's ROI, isolates green pixels via an
        HSV threshold, and measures the distance from the bottom of the ROI
        to the topmost green pixel row.

        Args:
            side_image: Full-frame BGR side-view image (H x W x 3).
            plant_roi: Dictionary with keys ``x``, ``y``, ``w``, ``h``
                defining the crop region in pixel coordinates.

        Returns:
            Estimated height in cm.  Returns ``0.0`` if no green pixels are
            detected within the ROI.
        """
        if side_image is None or side_image.size == 0:
            logger.warning("measure_height: received empty side_image; returning 0.0")
            return 0.0

        # Validate and extract ROI.
        try:
            x: int = int(plant_roi["x"])
            y: int = int(plant_roi["y"])
            w: int = int(plant_roi["w"])
            h: int = int(plant_roi["h"])
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning(
                "measure_height: invalid plant_roi %s (%s); returning 0.0",
                plant_roi,
                exc,
            )
            return 0.0

        img_h, img_w = side_image.shape[:2]
        # Clamp ROI to image bounds.
        x = max(0, min(x, img_w - 1))
        y = max(0, min(y, img_h - 1))
        w = max(1, min(w, img_w - x))
        h = max(1, min(h, img_h - y))

        roi_crop: np.ndarray = side_image[y : y + h, x : x + w]

        # Convert to HSV and threshold for green pixels.
        hsv: np.ndarray = cv2.cvtColor(roi_crop, cv2.COLOR_BGR2HSV)
        green_mask: np.ndarray = cv2.inRange(hsv, _GREEN_LOWER, _GREEN_UPPER)

        rows_with_green: np.ndarray = np.any(green_mask > 0, axis=1)
        if not np.any(rows_with_green):
            logger.debug(
                "measure_height: no green pixels found in ROI %s; returning 0.0",
                plant_roi,
            )
            return 0.0

        # Top of the plant = first row (smallest index) that contains green.
        top_row: int = int(np.argmax(rows_with_green))
        # Height in pixels = distance from top of plant to bottom of ROI.
        height_px: int = h - top_row
        height_cm: float = height_px / self._side_px_per_cm

        logger.debug(
            "measure_height: top_row=%d  h=%d  height_px=%d  height_cm=%.2f",
            top_row,
            h,
            height_px,
            height_cm,
        )
        return height_cm

    def compute_color_histogram(
        self,
        image: np.ndarray,
        mask: np.ndarray,
    ) -> np.ndarray:
        """Compute a normalised joint HSV histogram for a masked plant region.

        The histogram is flattened to a 1-D array and L1-normalised so
        that values sum to 1.0.  It can be stored as a compact health
        signature and compared across inspections via histogram intersection.

        Args:
            image: BGR image containing the plant (H x W x 3).
            mask: 2-D uint8 mask (same spatial extent as ``image``) where
                non-zero pixels belong to the plant.

        Returns:
            Flat normalised histogram of shape
            ``(_HSV_H_BINS * _HSV_S_BINS * _HSV_V_BINS,)``.
            Returns a zero-filled array of the same shape if inputs are
            invalid or the mask is empty.
        """
        hist_size: int = _HSV_H_BINS * _HSV_S_BINS * _HSV_V_BINS
        zero_hist: np.ndarray = np.zeros(hist_size, dtype=np.float32)

        if image is None or image.size == 0:
            logger.warning(
                "compute_color_histogram: empty image; returning zero histogram"
            )
            return zero_hist

        if mask is None or mask.size == 0 or not np.any(mask):
            logger.warning(
                "compute_color_histogram: empty mask; returning zero histogram"
            )
            return zero_hist

        if image.ndim != 3 or image.shape[2] != 3:
            logger.warning(
                "compute_color_histogram: expected BGR image (H x W x 3), "
                "got shape %s; returning zero histogram",
                image.shape,
            )
            return zero_hist

        # Ensure mask is 2-D and same height/width as image.
        if mask.ndim != 2:
            mask = mask[:, :, 0]
        mask_u8: np.ndarray = (mask > 0).astype(np.uint8) * 255

        hsv: np.ndarray = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

        hist: np.ndarray = cv2.calcHist(
            [hsv],
            [0, 1, 2],
            mask_u8,
            [_HSV_H_BINS, _HSV_S_BINS, _HSV_V_BINS],
            _HSV_H_RANGE + _HSV_S_RANGE + _HSV_V_RANGE,
        )

        # Flatten and L1-normalise.
        flat: np.ndarray = hist.flatten().astype(np.float32)
        total: float = float(flat.sum())
        if total > 0.0:
            flat /= total

        logger.debug(
            "compute_color_histogram: hist sum after normalise = %.4f",
            float(flat.sum()),
        )
        return flat

    @staticmethod
    def estimate_leaf_count(detections: list[Any]) -> int:
        """Estimate the number of leaves from instance segmentation results.

        Counts the number of detection instances whose mask is non-empty,
        treating each segmented instance as an individual leaf.  This is an
        approximation; a dedicated leaf-segmentation model would be needed
        for high-accuracy counts.

        Args:
            detections: List of :class:`~hydroponics_vision.yolo_inference.PlantDetection`
                objects (or any objects with a ``mask`` attribute) returned
                by the YOLO inference step.

        Returns:
            Number of detected leaf instances (>= 0).
        """
        if not detections:
            return 0

        count: int = 0
        for det in detections:
            mask = getattr(det, "mask", None)
            if mask is not None and np.any(mask):
                count += 1

        logger.debug("estimate_leaf_count: %d leaf instances detected", count)
        return count
