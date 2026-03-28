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

"""mock_cameras.py — Simulated dual-camera node for hardware-free vision testing.

Generates synthetic inspection images (numpy/CV2 if available, otherwise plain
bytearray) showing 4 plant positions as colored circles/rectangles.
Publishes sensor_msgs/Image on trigger.
"""

from __future__ import annotations

import random
from typing import Tuple

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy

from std_msgs.msg import String
from sensor_msgs.msg import Image
from hydroponics_msgs.srv import TriggerInspection

# Try to import numpy/cv2 for richer images — fall back gracefully
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

# ---- Colour palette for plant health states (BGR order) ----
_COLOURS = {
    "healthy":                  (34, 139, 34),
    "nitrogen_deficiency":      (0, 165, 255),
    "phosphorus_deficiency":    (0, 100, 200),
    "potassium_deficiency":     (50, 50, 200),
    "iron_deficiency":          (180, 180, 0),
    "disease_fungal":           (255, 50, 50),
    "disease_bacterial":        (200, 0, 200),
}

_STAGES = ["SEEDLING", "VEGETATIVE", "MATURE", "HARVESTED"]


class MockCamerasNode(Node):
    """Publishes synthetic inspection images for each /trigger_inspection call."""

    def __init__(self) -> None:
        super().__init__("mock_cameras_node")

        self.declare_parameter("image_width",  640)
        self.declare_parameter("image_height", 480)
        self.declare_parameter("plant_count",  4)

        self._width:  int = int(self.get_parameter("image_width").value)
        self._height: int = int(self.get_parameter("image_height").value)
        self._count:  int = int(self.get_parameter("plant_count").value)

        # Randomise initial plant states
        self._states = [random.choice(_STAGES) for _ in range(self._count)]
        self._health = [
            random.choice(list(_COLOURS.keys())) for _ in range(self._count)
        ]

        reliable_qos = QoSProfile(reliability=ReliabilityPolicy.RELIABLE, depth=5)

        # Publishers
        self._overhead_pub = self.create_publisher(
            Image, "/hydroponics/camera/overhead", reliable_qos)
        self._side_pub = self.create_publisher(
            Image, "/hydroponics/camera/side", reliable_qos)

        # Service: TriggerInspection — captures images on demand
        self._trigger_srv = self.create_service(
            TriggerInspection, "trigger_inspection", self._on_trigger)

        self.get_logger().info(
            f"MockCamerasNode started — {self._width}x{self._height}, "
            f"{self._count} plants, numpy={'yes' if HAS_NUMPY else 'no'}"
        )

    # ---------------------------------------------------------------------- #
    # Service handler
    # ---------------------------------------------------------------------- #

    def _on_trigger(
        self,
        _req: TriggerInspection.Request,
        response: TriggerInspection.Response,
    ) -> TriggerInspection.Response:
        self.get_logger().info("[mock_cameras] Inspection triggered — generating images")

        overhead = self._make_overhead_image()
        side     = self._make_side_image()

        self._overhead_pub.publish(overhead)
        self._side_pub.publish(side)

        response.success = True
        response.scan_number = 0
        return response

    # ---------------------------------------------------------------------- #
    # Image generation
    # ---------------------------------------------------------------------- #

    def _make_overhead_image(self) -> Image:
        """640×640 overhead view: 4 green circles representing plant canopies."""
        w = 640
        h = 640
        if HAS_NUMPY:
            img = np.zeros((h, w, 3), dtype=np.uint8)
            img[:] = (20, 30, 20)  # dark background
            spacing = w // (self._count + 1)
            for i, health in enumerate(self._health):
                cx = spacing * (i + 1)
                cy = h // 2
                radius = random.randint(40, 80)
                colour = _COLOURS.get(health, (34, 139, 34))
                _draw_circle(img, cx, cy, radius, colour)
            return self._ndarray_to_image(img, "overhead")
        else:
            return self._blank_image(w, h, (20, 30, 20), "overhead")

    def _make_side_image(self) -> Image:
        """640×480 side view: 4 rectangles representing plant heights."""
        w = 640
        h = 480
        if HAS_NUMPY:
            img = np.zeros((h, w, 3), dtype=np.uint8)
            img[:] = (15, 20, 15)
            spacing = w // (self._count + 1)
            for i, (health, stage) in enumerate(zip(self._health, self._states)):
                cx   = spacing * (i + 1)
                ph   = {"SEEDLING": 40, "VEGETATIVE": 90, "MATURE": 130,
                        "HARVESTED": 30}.get(stage, 80)
                pw   = 30
                top  = h - 80 - ph
                colour = _COLOURS.get(health, (34, 139, 34))
                _draw_rect(img, cx - pw//2, top, pw, ph, colour)
            return self._ndarray_to_image(img, "side")
        else:
            return self._blank_image(w, h, (15, 20, 15), "side")

    # ---------------------------------------------------------------------- #
    # Helpers
    # ---------------------------------------------------------------------- #

    def _ndarray_to_image(self, arr: "np.ndarray", frame_id: str) -> Image:
        msg = Image()
        msg.header.stamp    = self.get_clock().now().to_msg()
        msg.header.frame_id = frame_id
        msg.height          = arr.shape[0]
        msg.width           = arr.shape[1]
        msg.encoding        = "bgr8"
        msg.is_bigendian    = False
        msg.step            = arr.shape[1] * 3
        msg.data            = arr.tobytes()
        return msg

    def _blank_image(
        self, w: int, h: int, bg: Tuple[int, int, int], frame_id: str
    ) -> Image:
        """Plain-colour fallback when numpy is not available."""
        msg = Image()
        msg.header.stamp    = self.get_clock().now().to_msg()
        msg.header.frame_id = frame_id
        msg.height = h
        msg.width  = w
        msg.encoding = "bgr8"
        msg.is_bigendian = False
        msg.step = w * 3
        # Fill with background colour
        row = bytes(bg) * w
        msg.data = bytes(row * h)
        return msg


# --------------------------------------------------------------------------- #
# Minimal pixel drawing helpers (no OpenCV dependency)
# --------------------------------------------------------------------------- #

def _draw_circle(
    img: "np.ndarray", cx: int, cy: int, r: int, colour: Tuple[int, int, int]
) -> None:
    import numpy as np
    h, w = img.shape[:2]
    y, x = np.ogrid[:h, :w]
    mask = (x - cx) ** 2 + (y - cy) ** 2 <= r ** 2
    img[mask] = colour


def _draw_rect(
    img: "np.ndarray", x: int, y: int, w: int, h: int, colour: Tuple[int, int, int]
) -> None:
    img_h, img_w = img.shape[:2]
    x1 = max(0, x);    x2 = min(img_w, x + w)
    y1 = max(0, y);    y2 = min(img_h, y + h)
    img[y1:y2, x1:x2] = colour


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

def main(args=None) -> None:
    rclpy.init(args=args)
    node = MockCamerasNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
