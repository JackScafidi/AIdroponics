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

"""ROS 2 vision node for Claudroponics plant inspection pipeline.

Orchestrates dual-camera capture, YOLOv8 segmentation, physical
measurement, and deficiency classification.  Exposes a
``TriggerInspection`` service and publishes
``InspectionResult`` / ``ChannelHealthSummary`` messages.
"""

from __future__ import annotations

import time
import uuid
import logging
from typing import Optional

import cv2
import numpy as np

import rclpy
from rclpy.node import Node
from rclpy.client import Client
from rclpy.service import Service
from rclpy.publisher import Publisher
from cv_bridge import CvBridge

from sensor_msgs.msg import Image
from std_msgs.msg import Header

from hydroponics_msgs.msg import (
    InspectionResult,
    ChannelHealthSummary,
    PlantPositionState,
)
from hydroponics_msgs.srv import TriggerInspection, SetInspectionLight

from hydroponics_vision.camera_manager import CameraManager, CameraSettings
from hydroponics_vision.yolo_inference import YoloInference, PlantDetection
from hydroponics_vision.plant_measurer import PlantMeasurer
from hydroponics_vision.deficiency_classifier import (
    DeficiencyClassifier,
    ChannelAggregate,
)

logger = logging.getLogger(__name__)


class VisionNode(Node):
    """Main ROS 2 node for the hydroponics vision inspection pipeline.

    Lifecycle
    ---------
    1. Declare and read all parameters from ``vision_params.yaml``.
    2. Construct helper objects (CameraManager, YoloInference, etc.).
    3. Create publishers, service servers, and service clients.
    4. Serve ``TriggerInspection`` requests synchronously inside a
       dedicated handler.

    Topics published
    ----------------
    ``/inspection/overhead``        ``sensor_msgs/Image``
    ``/inspection/side``            ``sensor_msgs/Image``
    ``/inspection_result``          ``hydroponics_msgs/InspectionResult``
    ``/channel_health_summary``     ``hydroponics_msgs/ChannelHealthSummary``

    Services provided
    -----------------
    ``/trigger_inspection``         ``hydroponics_msgs/srv/TriggerInspection``

    Services called
    ---------------
    ``/set_inspection_light``       ``hydroponics_msgs/srv/SetInspectionLight``
    """

    def __init__(self) -> None:
        super().__init__("vision_node")

        # ------------------------------------------------------------------
        # Parameter declarations
        # ------------------------------------------------------------------
        self.declare_parameter("overhead_camera_id", 0)
        self.declare_parameter("side_camera_id", 2)
        self.declare_parameter("model_path", "models/yolov8n-seg-plants.pt")
        self.declare_parameter("confidence_threshold", 0.5)
        self.declare_parameter("iou_threshold", 0.45)
        self.declare_parameter("inference_size", 640)
        self.declare_parameter("led_stabilize_delay_ms", 200)
        # plant_rois is a list of string representations; real projects use
        # YAML parameter arrays.  Declared as string list and parsed below.
        self.declare_parameter("plant_rois", [""])
        self.declare_parameter("overhead_px_per_cm", 38.0)
        self.declare_parameter("side_px_per_cm", 30.0)

        # ------------------------------------------------------------------
        # Read parameters
        # ------------------------------------------------------------------
        overhead_id: int = (
            self.get_parameter("overhead_camera_id").get_parameter_value().integer_value
        )
        side_id: int = (
            self.get_parameter("side_camera_id").get_parameter_value().integer_value
        )
        model_path: str = (
            self.get_parameter("model_path").get_parameter_value().string_value
        )
        confidence_threshold: float = (
            self.get_parameter("confidence_threshold")
            .get_parameter_value()
            .double_value
        )
        iou_threshold: float = (
            self.get_parameter("iou_threshold").get_parameter_value().double_value
        )
        inference_size: int = (
            self.get_parameter("inference_size").get_parameter_value().integer_value
        )
        led_delay_ms: int = (
            self.get_parameter("led_stabilize_delay_ms")
            .get_parameter_value()
            .integer_value
        )
        overhead_px_per_cm: float = (
            self.get_parameter("overhead_px_per_cm")
            .get_parameter_value()
            .double_value
        )
        side_px_per_cm: float = (
            self.get_parameter("side_px_per_cm")
            .get_parameter_value()
            .double_value
        )

        # plant_rois from YAML arrives as a list of parameter values when
        # loaded via --params-file; we store the raw parameter and parse
        # each entry lazily.
        self._plant_rois: list[dict[str, int]] = self._load_plant_rois()
        self._led_delay_s: float = led_delay_ms / 1000.0

        self.get_logger().info(
            "VisionNode params: overhead_cam=%d  side_cam=%d  model='%s'  "
            "conf=%.2f  iou=%.2f  imgsz=%d  led_delay=%.3fs  "
            "overhead_px_per_cm=%.1f  side_px_per_cm=%.1f  rois=%d",
            overhead_id,
            side_id,
            model_path,
            confidence_threshold,
            iou_threshold,
            inference_size,
            self._led_delay_s,
            overhead_px_per_cm,
            side_px_per_cm,
            len(self._plant_rois),
        )

        # ------------------------------------------------------------------
        # Helper objects
        # ------------------------------------------------------------------
        cam_settings = CameraSettings()
        self._camera_manager = CameraManager(
            overhead_device_id=overhead_id,
            side_device_id=side_id,
            settings=cam_settings,
        )

        self._yolo = YoloInference(
            model_path=model_path,
            confidence_threshold=confidence_threshold,
            iou_threshold=iou_threshold,
            inference_size=inference_size,
        )
        # Pre-warm the model at startup so the first inspection isn't slow.
        self._yolo.load()

        self._measurer = PlantMeasurer(
            overhead_px_per_cm=overhead_px_per_cm,
            side_px_per_cm=side_px_per_cm,
        )

        self._classifier = DeficiencyClassifier()
        self._bridge = CvBridge()

        # ------------------------------------------------------------------
        # Scan counter
        # ------------------------------------------------------------------
        self._scan_counter: int = 0

        # ------------------------------------------------------------------
        # Publishers
        # ------------------------------------------------------------------
        self._pub_overhead: Publisher = self.create_publisher(
            Image, "/inspection/overhead", 1
        )
        self._pub_side: Publisher = self.create_publisher(
            Image, "/inspection/side", 1
        )
        self._pub_result: Publisher = self.create_publisher(
            InspectionResult, "/inspection_result", 10
        )
        self._pub_health: Publisher = self.create_publisher(
            ChannelHealthSummary, "/channel_health_summary", 10
        )

        # ------------------------------------------------------------------
        # Service clients
        # ------------------------------------------------------------------
        self._light_client: Client = self.create_client(
            SetInspectionLight, "/set_inspection_light"
        )

        # ------------------------------------------------------------------
        # Service server
        # ------------------------------------------------------------------
        self._inspection_srv: Service = self.create_service(
            TriggerInspection,
            "/trigger_inspection",
            self._handle_trigger_inspection,
        )

        self.get_logger().info("VisionNode ready — waiting for /trigger_inspection calls")

    # ------------------------------------------------------------------
    # Service handler
    # ------------------------------------------------------------------

    def _handle_trigger_inspection(
        self,
        request: TriggerInspection.Request,
        response: TriggerInspection.Response,
    ) -> TriggerInspection.Response:
        """Handle a TriggerInspection service call end-to-end.

        Execution order
        ~~~~~~~~~~~~~~~
        1. Turn inspection LEDs on via ``/set_inspection_light``.
        2. Wait for LED stabilisation delay.
        3. Capture overhead and side images.
        4. Turn inspection LEDs off.
        5. Run YOLO inference on both images.
        6. Run PlantMeasurer for each configured plant ROI.
        7. Classify deficiencies and aggregate channel health.
        8. Publish raw images, InspectionResult, ChannelHealthSummary.
        9. Return success=True and current scan_number.

        Any exception at any step sets success=False and logs the error.
        """
        self.get_logger().info("TriggerInspection received — starting scan")

        try:
            # Step 1: lights on.
            self._set_light(on=True)

            # Step 2: LED stabilisation delay.
            time.sleep(self._led_delay_s)

            # Step 3: capture images.
            overhead_img: np.ndarray = self._camera_manager.capture_overhead()
            side_img: np.ndarray = self._camera_manager.capture_side()

            # Step 4: lights off (done before heavy CPU work).
            self._set_light(on=False)

            # Step 5: YOLO inference on both images.
            overhead_detections: list[PlantDetection] = self._yolo.predict(overhead_img)
            side_detections: list[PlantDetection] = self._yolo.predict(side_img)

            self.get_logger().debug(
                "Inference: %d overhead detections, %d side detections",
                len(overhead_detections),
                len(side_detections),
            )

            # Step 6 & 7: per-plant measurement and classification.
            plant_states: list[PlantPositionState] = []
            health_class_list: list[str] = []
            total_canopy: float = 0.0

            for idx, roi in enumerate(self._plant_rois):
                pps = self._process_plant(
                    idx=idx,
                    roi=roi,
                    overhead_img=overhead_img,
                    side_img=side_img,
                    overhead_detections=overhead_detections,
                )
                plant_states.append(pps)
                health_class_list.append(pps.health_state)
                total_canopy += pps.canopy_area_cm2

            # Step 7 continued: aggregate channel health.
            agg: ChannelAggregate = DeficiencyClassifier.aggregate_channel(
                health_class_list
            )
            agg.avg_canopy_area_cm2 = (
                total_canopy / len(self._plant_rois) if self._plant_rois else 0.0
            )

            # Step 8a: increment counter and build messages.
            self._scan_counter += 1
            stamp = self.get_clock().now().to_msg()

            # Determine channel-level disease flag.
            disease_detected: bool = any(
                DeficiencyClassifier.is_disease(h) for h in health_class_list
            )
            # Primary disease type string (first found, or empty).
            disease_type: str = ""
            for h in health_class_list:
                if DeficiencyClassifier.is_disease(h):
                    disease_type = h
                    break

            # Step 8b: publish raw images.
            self._publish_images(overhead_img, side_img, stamp)

            # Step 8c: publish InspectionResult.
            result_msg = InspectionResult()
            result_msg.header = Header(stamp=stamp)
            result_msg.plants = plant_states
            result_msg.scan_number = self._scan_counter
            result_msg.disease_detected = disease_detected
            result_msg.disease_type = disease_type
            result_msg.deficiency_trends = agg.deficiency_trends
            self._pub_result.publish(result_msg)

            # Step 8d: publish ChannelHealthSummary.
            health_msg = ChannelHealthSummary()
            health_msg.header = Header(stamp=stamp)
            health_msg.avg_canopy_area_cm2 = agg.avg_canopy_area_cm2
            health_msg.healthy_count = agg.healthy_count
            health_msg.deficient_count = agg.deficient_count
            health_msg.diseased_count = agg.diseased_count
            health_msg.primary_deficiency = agg.primary_deficiency
            health_msg.deficiency_prevalence = agg.deficiency_prevalence
            self._pub_health.publish(health_msg)

            self.get_logger().info(
                "Scan #%d complete — healthy=%d  deficient=%d  diseased=%d  "
                "primary_deficiency='%s'  avg_canopy=%.1f cm²",
                self._scan_counter,
                agg.healthy_count,
                agg.deficient_count,
                agg.diseased_count,
                agg.primary_deficiency,
                agg.avg_canopy_area_cm2,
            )

            # Step 9: return success.
            response.success = True
            response.scan_number = self._scan_counter
            return response

        except Exception as exc:  # noqa: BLE001 — intentional broad catch
            self.get_logger().error(
                "TriggerInspection failed: %s", str(exc), exc_info=True
            )
            # Ensure lights are always turned off even on error.
            try:
                self._set_light(on=False)
            except Exception as light_exc:
                self.get_logger().warning(
                    "Could not turn off inspection light after error: %s",
                    str(light_exc),
                )
            response.success = False
            response.scan_number = self._scan_counter
            return response

    # ------------------------------------------------------------------
    # Per-plant processing
    # ------------------------------------------------------------------

    def _process_plant(
        self,
        idx: int,
        roi: dict[str, int],
        overhead_img: np.ndarray,
        side_img: np.ndarray,
        overhead_detections: list[PlantDetection],
    ) -> PlantPositionState:
        """Build a PlantPositionState for one plant position.

        Selects the highest-confidence detection that falls within the ROI,
        measures canopy area from its mask, measures height from the side
        image, estimates leaf count, and classifies the health state.

        Args:
            idx: Zero-based plant position index.
            roi: Dict with keys ``x``, ``y``, ``w``, ``h`` (pixels).
            overhead_img: Full overhead BGR image.
            side_img: Full side-view BGR image.
            overhead_detections: All detections from the overhead image.

        Returns:
            Populated :class:`PlantPositionState` message object.
        """
        pps = PlantPositionState()
        pps.position_index = idx
        pps.plant_id = str(uuid.uuid4())
        pps.last_inspection = self.get_clock().now().to_msg()

        # Find the best detection whose bounding-box centre lies inside the ROI.
        best_det: Optional[PlantDetection] = self._best_detection_in_roi(
            overhead_detections, roi
        )

        if best_det is not None:
            pps.health_state = best_det.health_class
            pps.status = self._maturity_to_status(best_det.maturity_class)

            # Canopy area from mask.
            if best_det.mask is not None:
                pps.canopy_area_cm2 = self._measurer.measure_canopy_area(
                    best_det.mask
                )
            else:
                # Fallback: estimate area from bounding box.
                pps.canopy_area_cm2 = self._bbox_area_cm2(best_det.bbox)

            pps.leaf_count = self._measurer.estimate_leaf_count([best_det])
        else:
            # No detection in this ROI — plant absent or occluded.
            pps.health_state = "healthy"
            pps.status = "EMPTY"
            pps.canopy_area_cm2 = 0.0
            pps.leaf_count = 0

        # Height always measured from the side image.
        pps.height_cm = self._measurer.measure_height(side_img, roi)

        return pps

    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------

    def _set_light(self, on: bool) -> None:
        """Call /set_inspection_light synchronously with a timeout.

        Logs a warning but does not raise if the service is unavailable,
        so that the rest of the inspection pipeline can continue.

        Args:
            on: ``True`` to switch lights on, ``False`` to switch off.
        """
        if not self._light_client.wait_for_service(timeout_sec=1.0):
            self.get_logger().warning(
                "/set_inspection_light service unavailable; "
                "proceeding without light control"
            )
            return

        req = SetInspectionLight.Request()
        req.on = on
        future = self._light_client.call_async(req)
        # Spin until the future completes (we are already inside a service
        # callback, so we use rclpy.spin_until_future_complete with a timeout).
        rclpy.spin_until_future_complete(self, future, timeout_sec=2.0)
        if future.done():
            resp = future.result()
            if not resp.success:
                self.get_logger().warning(
                    "/set_inspection_light returned success=False (on=%s)", on
                )
        else:
            self.get_logger().warning(
                "/set_inspection_light call timed out (on=%s)", on
            )

    def _publish_images(
        self,
        overhead_img: np.ndarray,
        side_img: np.ndarray,
        stamp: object,
    ) -> None:
        """Convert BGR arrays to ROS Image messages and publish.

        Args:
            overhead_img: BGR overhead image array.
            side_img: BGR side-view image array.
            stamp: ROS time stamp (``builtin_interfaces/Time``).
        """
        try:
            overhead_msg: Image = self._bridge.cv2_to_imgmsg(
                overhead_img, encoding="bgr8"
            )
            overhead_msg.header.stamp = stamp
            self._pub_overhead.publish(overhead_msg)
        except Exception as exc:
            self.get_logger().warning(
                "Failed to publish overhead image: %s", str(exc)
            )

        try:
            side_msg: Image = self._bridge.cv2_to_imgmsg(side_img, encoding="bgr8")
            side_msg.header.stamp = stamp
            self._pub_side.publish(side_msg)
        except Exception as exc:
            self.get_logger().warning(
                "Failed to publish side image: %s", str(exc)
            )

    def _best_detection_in_roi(
        self,
        detections: list[PlantDetection],
        roi: dict[str, int],
    ) -> Optional[PlantDetection]:
        """Return the highest-confidence detection whose centre is inside roi.

        Args:
            detections: Detections from the full image.
            roi: Dict with keys ``x``, ``y``, ``w``, ``h``.

        Returns:
            Best :class:`PlantDetection` or ``None`` if no match.
        """
        rx: int = roi.get("x", 0)
        ry: int = roi.get("y", 0)
        rw: int = roi.get("w", 0)
        rh: int = roi.get("h", 0)

        best: Optional[PlantDetection] = None
        best_conf: float = -1.0

        for det in detections:
            if len(det.bbox) < 4:
                continue
            cx: float = (det.bbox[0] + det.bbox[2]) / 2.0
            cy: float = (det.bbox[1] + det.bbox[3]) / 2.0
            if (rx <= cx <= rx + rw) and (ry <= cy <= ry + rh):
                if det.confidence > best_conf:
                    best_conf = det.confidence
                    best = det

        return best

    def _bbox_area_cm2(self, bbox: list[float]) -> float:
        """Estimate plant area in cm² from a bounding box (fallback).

        Args:
            bbox: ``[x1, y1, x2, y2]`` in pixels.

        Returns:
            Area in cm², or ``0.0`` if bbox is invalid.
        """
        if len(bbox) < 4:
            return 0.0
        w_px: float = max(0.0, bbox[2] - bbox[0])
        h_px: float = max(0.0, bbox[3] - bbox[1])
        area_px2: float = w_px * h_px
        # overhead calibration: (px/cm)^2
        from hydroponics_vision.plant_measurer import PlantMeasurer  # local ref
        return area_px2 / (self._measurer._overhead_px_per_cm ** 2)  # noqa: SLF001

    @staticmethod
    def _maturity_to_status(maturity_class: str) -> str:
        """Map a YOLO maturity class to a PlantPositionState status string.

        Args:
            maturity_class: One of the known maturity labels.

        Returns:
            A ``PlantPositionState.status`` compatible string.
        """
        _MAP: dict[str, str] = {
            "immature": "SEEDLING",
            "vegetative": "VEGETATIVE",
            "mature": "MATURE",
            "overmature": "SPENT",
        }
        return _MAP.get(maturity_class, "VEGETATIVE")

    def _load_plant_rois(self) -> list[dict[str, int]]:
        """Read plant_rois from the node's parameter server.

        The YAML structure for ``plant_rois`` uses a list of sub-mappings.
        In ROS 2 Python, nested YAML parameters are flattened into dot-
        separated keys.  We try the native list first, then fall back to
        the default geometry used in ``vision_params.yaml``.

        Returns:
            List of ``{x, y, w, h}`` dicts, one per plant position.
        """
        defaults: list[dict[str, int]] = [
            {"x": 160, "y": 200, "w": 400, "h": 600},
            {"x": 560, "y": 200, "w": 400, "h": 600},
            {"x": 960, "y": 200, "w": 400, "h": 600},
            {"x": 1360, "y": 200, "w": 400, "h": 600},
        ]

        try:
            raw = self.get_parameter("plant_rois").get_parameter_value().string_array_value
            if raw and raw != [""]:
                import json
                rois: list[dict[str, int]] = []
                for entry in raw:
                    try:
                        rois.append(json.loads(entry))
                    except (json.JSONDecodeError, TypeError):
                        self.get_logger().warning(
                            "Could not parse plant_roi entry '%s'; using defaults",
                            entry,
                        )
                        return defaults
                if rois:
                    return rois
        except Exception:
            pass

        self.get_logger().info(
            "plant_rois not set via parameters; using built-in defaults "
            "(4 plants, 1920x1080 layout)"
        )
        return defaults


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(args: Optional[list[str]] = None) -> None:
    """Initialise rclpy, spin the VisionNode, and shut down cleanly."""
    rclpy.init(args=args)
    node = VisionNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("VisionNode interrupted by KeyboardInterrupt")
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
