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

"""Dual-camera sequential capture manager using OpenCV VideoCapture.

Handles device enumeration, settings lock (resolution, focus, exposure),
and retry logic for camera open failures.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CameraSettings:
    """Immutable capture settings applied to each camera on open."""

    width: int = 1920
    height: int = 1080
    fourcc: str = "MJPG"


class CameraOpenError(RuntimeError):
    """Raised when a camera cannot be opened after all retries."""


class CameraManager:
    """Manages two USB cameras for sequential overhead + side capture.

    Cameras are opened on demand and released immediately after each
    capture pair to avoid holding the device file between inspections.
    """

    _MAX_RETRIES: int = 3
    _RETRY_DELAY_S: float = 0.5

    def __init__(
        self,
        overhead_device_id: int,
        side_device_id: int,
        settings: CameraSettings,
    ) -> None:
        self._overhead_id: int = overhead_device_id
        self._side_id: int = side_device_id
        self._settings: CameraSettings = settings
        logger.info(
            "CameraManager initialised: overhead=%d  side=%d  %dx%d %s",
            overhead_device_id,
            side_device_id,
            settings.width,
            settings.height,
            settings.fourcc,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def capture_overhead(self) -> np.ndarray:
        """Capture a single frame from the overhead camera.

        Returns:
            BGR image as a numpy array (H x W x 3).

        Raises:
            CameraOpenError: If the camera cannot be opened.
            RuntimeError: If frame grab fails.
        """
        return self._capture(self._overhead_id, "overhead")

    def capture_side(self) -> np.ndarray:
        """Capture a single frame from the side camera.

        Returns:
            BGR image as a numpy array (H x W x 3).

        Raises:
            CameraOpenError: If the camera cannot be opened.
            RuntimeError: If frame grab fails.
        """
        return self._capture(self._side_id, "side")

    @staticmethod
    def enumerate_devices(max_index: int = 10) -> list[int]:
        """Probe device indices 0..max_index-1 and return those that open.

        This is a convenience utility for debugging camera wiring. It
        briefly opens and closes each device index to test availability.
        """
        available: list[int] = []
        for idx in range(max_index):
            cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
            if cap.isOpened():
                available.append(idx)
                cap.release()
        logger.info("Enumerated camera devices: %s", available)
        return available

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _open_camera(self, device_id: int, label: str) -> cv2.VideoCapture:
        """Open a camera device with retry logic and apply settings.

        Args:
            device_id: OS device index (e.g. /dev/video0 -> 0).
            label: Human-readable name for log messages.

        Returns:
            An opened ``cv2.VideoCapture`` with settings applied.

        Raises:
            CameraOpenError: After ``_MAX_RETRIES`` unsuccessful attempts.
        """
        fourcc_code: int = cv2.VideoWriter.fourcc(*self._settings.fourcc)

        for attempt in range(1, self._MAX_RETRIES + 1):
            cap = cv2.VideoCapture(device_id, cv2.CAP_V4L2)
            if cap.isOpened():
                self._apply_settings(cap, fourcc_code)
                logger.debug(
                    "%s camera (device %d) opened on attempt %d",
                    label,
                    device_id,
                    attempt,
                )
                return cap

            logger.warning(
                "%s camera (device %d) open failed, attempt %d/%d",
                label,
                device_id,
                attempt,
                self._MAX_RETRIES,
            )
            cap.release()
            if attempt < self._MAX_RETRIES:
                time.sleep(self._RETRY_DELAY_S)

        raise CameraOpenError(
            f"{label} camera (device {device_id}) could not be opened "
            f"after {self._MAX_RETRIES} attempts"
        )

    def _apply_settings(
        self, cap: cv2.VideoCapture, fourcc_code: int
    ) -> None:
        """Lock resolution, codec, and disable auto-focus/exposure."""
        cap.set(cv2.CAP_PROP_FOURCC, fourcc_code)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._settings.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._settings.height)

        # Disable auto-focus (manual = 0, value irrelevant for fixed-focus).
        cap.set(cv2.CAP_PROP_AUTOFOCUS, 0)

        # Disable auto-exposure (mode 1 = manual on many UVC cameras).
        cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 1)

        actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if actual_w != self._settings.width or actual_h != self._settings.height:
            logger.warning(
                "Requested %dx%d but camera negotiated %dx%d",
                self._settings.width,
                self._settings.height,
                actual_w,
                actual_h,
            )

    def _capture(self, device_id: int, label: str) -> np.ndarray:
        """Open camera, grab one frame, release, and return the image.

        Args:
            device_id: OS device index.
            label: Human-readable camera name for logs.

        Returns:
            BGR image as numpy array.

        Raises:
            CameraOpenError: If device cannot be opened.
            RuntimeError: If ``cap.read()`` fails.
        """
        cap: cv2.VideoCapture = self._open_camera(device_id, label)
        try:
            # Discard first frame (often partially-exposed on cold start).
            cap.read()

            ret: bool
            frame: Optional[np.ndarray]
            ret, frame = cap.read()
            if not ret or frame is None:
                raise RuntimeError(
                    f"{label} camera (device {device_id}): frame grab failed"
                )
            logger.debug(
                "%s capture OK: shape=%s  dtype=%s",
                label,
                frame.shape,
                frame.dtype,
            )
            return frame
        finally:
            cap.release()
