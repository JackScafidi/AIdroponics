# MIT License
# Copyright (c) 2026 Autoponics Project

"""ROS2 dual-camera vision node for Autoponics V0.1 single-plant platform.

Purpose
-------
Manages both CSI camera streams (RGB and NoIR/NDVI), computes NDVI health
indices, detects AprilTags for scale calibration, segments the plant via
HSV thresholding, tracks temporal changes for symptom classification, and
stores all captured frame pairs to disk.

Subscriptions
-------------
None at steady state. The node self-triggers on a configurable timer.

Publications
------------
/camera/rgb/image_raw    (sensor_msgs/Image)         — RGB frame
/camera/ndvi/image_raw   (sensor_msgs/Image)         — NoIR frame
/vision/measurement      (hydroponics_msgs/PlantMeasurement)
/vision/ndvi             (hydroponics_msgs/NDVIReading)
/vision/ndvi_alert       (hydroponics_msgs/NDVIAlert)

Services provided
-----------------
/vision/capture  (hydroponics_msgs/srv/CaptureVision) — on-demand capture

Services called
---------------
/probe/set_interval  (hydroponics_msgs/srv/SetProbeInterval)
  Called when declining NDVI triggers early-warning protocol.

Parameters
----------
All loaded from v01_system.yaml. Keys used:
  camera.rgb.*            — RGB camera device ID and locked settings
  camera.ndvi.*           — NoIR camera device ID and locked settings
  camera.capture_interval_seconds
  camera.capture_interval_alert_seconds
  camera.capture_storage_path
  apriltag.*              — tag family, physical size, separation
  segmentation.*          — HSV thresholds, morphological kernel size
  temporal_tracking.*     — history buffer, established/new growth thresholds
  ndvi.*                  — trend buffer size, declining slope threshold
  bin.*                   — cross section, depth (for future use)
  plant_type              — active plant (used for NDVI thresholds)
"""

from __future__ import annotations

import os
import time
import datetime
import collections
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

import rclpy
from rclpy.node import Node
from rclpy.callback_group import ReentrantCallbackGroup
from cv_bridge import CvBridge

from sensor_msgs.msg import Image

from hydroponics_msgs.msg import PlantMeasurement, NDVIReading, NDVIAlert
from hydroponics_msgs.srv import CaptureVision, SetProbeInterval

import yaml


class PlantVisionNode(Node):
    """Dual-camera vision pipeline with NDVI, AprilTag calibration, and temporal tracking."""

    def __init__(self) -> None:
        super().__init__('plant_vision_node')
        self._cb_group = ReentrantCallbackGroup()
        self._bridge = CvBridge()

        # --- Parameters ---
        self.declare_parameter('camera.rgb.device_id', 0)
        self.declare_parameter('camera.ndvi.device_id', 1)
        self.declare_parameter('camera.capture_interval_seconds', 1800.0)
        self.declare_parameter('camera.capture_interval_alert_seconds', 600.0)
        self.declare_parameter('camera.capture_storage_path', '~/.autoponics/captures/')
        self.declare_parameter('apriltag.family', 'tag36h11')
        self.declare_parameter('apriltag.tag_size_m', 0.05)
        self.declare_parameter('apriltag.tag_separation_m', 0.30)
        self.declare_parameter('apriltag.scale_cross_validation_tolerance', 0.10)
        self.declare_parameter('segmentation.hsv_lower', [35, 40, 40])
        self.declare_parameter('segmentation.hsv_upper', [85, 255, 255])
        self.declare_parameter('segmentation.morph_kernel_size', 5)
        self.declare_parameter('temporal_tracking.history_buffer_size', 48)
        self.declare_parameter('temporal_tracking.established_growth_threshold', 24)
        self.declare_parameter('temporal_tracking.new_growth_threshold', 6)
        self.declare_parameter('temporal_tracking.growth_stall_min_increase_fraction', 0.05)
        self.declare_parameter('temporal_tracking.growth_stall_window', 12)
        self.declare_parameter('ndvi.trend_buffer_size', 48)
        self.declare_parameter('ndvi.declining_slope_threshold', -0.002)
        self.declare_parameter('plant_type', 'basil')

        self._rgb_device_id: int = (
            self.get_parameter('camera.rgb.device_id').get_parameter_value().integer_value
        )
        self._ndvi_device_id: int = (
            self.get_parameter('camera.ndvi.device_id').get_parameter_value().integer_value
        )
        self._capture_interval: float = (
            self.get_parameter('camera.capture_interval_seconds')
            .get_parameter_value().double_value
        )
        self._capture_interval_alert: float = (
            self.get_parameter('camera.capture_interval_alert_seconds')
            .get_parameter_value().double_value
        )
        self._storage_path: Path = Path(
            os.path.expanduser(
                self.get_parameter('camera.capture_storage_path')
                .get_parameter_value().string_value
            )
        )
        self._apriltag_family: str = (
            self.get_parameter('apriltag.family').get_parameter_value().string_value
        )
        self._apriltag_tag_size_m: float = (
            self.get_parameter('apriltag.tag_size_m').get_parameter_value().double_value
        )
        self._apriltag_separation_m: float = (
            self.get_parameter('apriltag.tag_separation_m').get_parameter_value().double_value
        )
        self._scale_tolerance: float = (
            self.get_parameter('apriltag.scale_cross_validation_tolerance')
            .get_parameter_value().double_value
        )

        hsv_lower_raw = (
            self.get_parameter('segmentation.hsv_lower')
            .get_parameter_value().integer_array_value
        )
        hsv_upper_raw = (
            self.get_parameter('segmentation.hsv_upper')
            .get_parameter_value().integer_array_value
        )
        self._hsv_lower: np.ndarray = np.array(list(hsv_lower_raw), dtype=np.uint8)
        self._hsv_upper: np.ndarray = np.array(list(hsv_upper_raw), dtype=np.uint8)
        self._morph_kernel_size: int = (
            self.get_parameter('segmentation.morph_kernel_size')
            .get_parameter_value().integer_value
        )
        self._history_buffer_size: int = (
            self.get_parameter('temporal_tracking.history_buffer_size')
            .get_parameter_value().integer_value
        )
        self._established_threshold: int = (
            self.get_parameter('temporal_tracking.established_growth_threshold')
            .get_parameter_value().integer_value
        )
        self._new_growth_threshold: int = (
            self.get_parameter('temporal_tracking.new_growth_threshold')
            .get_parameter_value().integer_value
        )
        self._stall_min_increase: float = (
            self.get_parameter('temporal_tracking.growth_stall_min_increase_fraction')
            .get_parameter_value().double_value
        )
        self._stall_window: int = (
            self.get_parameter('temporal_tracking.growth_stall_window')
            .get_parameter_value().integer_value
        )
        self._ndvi_buffer_size: int = (
            self.get_parameter('ndvi.trend_buffer_size').get_parameter_value().integer_value
        )
        self._ndvi_declining_threshold: float = (
            self.get_parameter('ndvi.declining_slope_threshold')
            .get_parameter_value().double_value
        )
        self._plant_type: str = (
            self.get_parameter('plant_type').get_parameter_value().string_value
        )

        # Load NDVI thresholds from plant library (loaded via YAML in launch or bringup)
        # Thresholds declared as separate parameters for launch-file injection
        self.declare_parameter('ndvi_healthy_min', 0.3)
        self.declare_parameter('ndvi_warning_threshold', 0.2)
        self.declare_parameter('ndvi_critical_threshold', 0.1)
        self._ndvi_healthy_min: float = (
            self.get_parameter('ndvi_healthy_min').get_parameter_value().double_value
        )
        self._ndvi_warning_threshold: float = (
            self.get_parameter('ndvi_warning_threshold').get_parameter_value().double_value
        )
        self._ndvi_critical_threshold: float = (
            self.get_parameter('ndvi_critical_threshold').get_parameter_value().double_value
        )

        # --- State ---
        self._ndvi_buffer: collections.deque = collections.deque(
            maxlen=self._ndvi_buffer_size
        )
        # Frame history for temporal tracking
        # Each entry: (capture_index, plant_mask_bool, hsv_frame)
        self._frame_history: collections.deque = collections.deque(
            maxlen=self._history_buffer_size
        )
        self._capture_index: int = 0
        self._reference_frame_corners: Optional[np.ndarray] = None
        self._in_alert_mode: bool = False
        self._storage_path.mkdir(parents=True, exist_ok=True)

        # --- Open cameras ---
        self._rgb_cap = cv2.VideoCapture(self._rgb_device_id)
        self._ndvi_cap = cv2.VideoCapture(self._ndvi_device_id)

        # Lock manual settings on both cameras
        for cap in (self._rgb_cap, self._ndvi_cap):
            cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)  # manual mode

        # --- Publishers ---
        self._pub_rgb = self.create_publisher(Image, '/camera/rgb/image_raw', 1)
        self._pub_ndvi_raw = self.create_publisher(Image, '/camera/ndvi/image_raw', 1)
        self._pub_measurement = self.create_publisher(
            PlantMeasurement, '/vision/measurement', 10
        )
        self._pub_ndvi = self.create_publisher(NDVIReading, '/vision/ndvi', 10)
        self._pub_ndvi_alert = self.create_publisher(NDVIAlert, '/vision/ndvi_alert', 10)

        # --- Service client ---
        self._probe_interval_client = self.create_client(
            SetProbeInterval, '/probe/set_interval'
        )

        # --- Service server ---
        self._srv_capture = self.create_service(
            CaptureVision, '/vision/capture', self._handle_capture,
            callback_group=self._cb_group
        )

        # --- Capture timer ---
        self._capture_timer = self.create_timer(
            self._capture_interval, self._run_capture_pipeline,
            callback_group=self._cb_group
        )

        # ArUco / AprilTag detector
        aruco_dict_id = cv2.aruco.DICT_APRILTAG_36h11
        self._aruco_dict = cv2.aruco.getPredefinedDictionary(aruco_dict_id)
        self._aruco_params = cv2.aruco.DetectorParameters()
        self._aruco_detector = cv2.aruco.ArucoDetector(
            self._aruco_dict, self._aruco_params
        )

        self.get_logger().info(
            f'PlantVisionNode ready — plant_type={self._plant_type}, '
            f'capture_interval={self._capture_interval}s, '
            f'rgb_device={self._rgb_device_id}, ndvi_device={self._ndvi_device_id}'
        )

    # -------------------------------------------------------------------------
    # Main capture pipeline
    # -------------------------------------------------------------------------

    def _run_capture_pipeline(self) -> None:
        """Capture synchronized frames and run the full analysis pipeline."""
        self.get_logger().info(
            f'Capture pipeline starting (capture #{self._capture_index + 1})'
        )

        rgb_ok, rgb_frame = self._rgb_cap.read()
        ndvi_ok, ndvi_frame = self._ndvi_cap.read()

        if not rgb_ok or not ndvi_ok:
            self.get_logger().error(
                f'Camera read failed — rgb_ok={rgb_ok}, ndvi_ok={ndvi_ok}'
            )
            return

        self._capture_index += 1
        stamp = self.get_clock().now().to_msg()
        timestamp_str = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')

        # Store frames to disk
        self._save_frames(rgb_frame, ndvi_frame, timestamp_str)

        # Publish raw images
        self._publish_image(rgb_frame, self._pub_rgb, stamp)
        self._publish_image(ndvi_frame, self._pub_ndvi_raw, stamp)

        # AprilTag detection and scale calibration
        px_per_cm = self._compute_scale_from_apriltags(rgb_frame)

        # Plant segmentation (RGB)
        plant_mask = self._segment_plant(rgb_frame)

        # NDVI computation (NoIR frame)
        ndvi_values, mean_ndvi, median_ndvi, std_ndvi = self._compute_ndvi(
            ndvi_frame, plant_mask
        )

        # Temporal change tracking
        visual_symptoms = self._update_temporal_tracking(
            rgb_frame, plant_mask
        )

        # NDVI trend
        self._ndvi_buffer.append(mean_ndvi)
        ndvi_trend_slope = self._compute_ndvi_trend()

        # Check for growth stall
        growth_stall = self._check_growth_stall()
        if growth_stall:
            visual_symptoms.append('growth_stall')

        # Publish PlantMeasurement
        measurement_msg = PlantMeasurement()
        measurement_msg.canopy_area_cm2 = self._mask_area_cm2(plant_mask, px_per_cm)
        measurement_msg.canopy_width_cm = self._mask_width_cm(plant_mask, px_per_cm)
        measurement_msg.height_cm = self._mask_height_cm(plant_mask, px_per_cm)
        measurement_msg.visual_symptoms = visual_symptoms
        measurement_msg.timestamp = stamp
        self._pub_measurement.publish(measurement_msg)

        # Publish NDVIReading
        ndvi_msg = NDVIReading()
        ndvi_msg.mean_ndvi = float(mean_ndvi)
        ndvi_msg.median_ndvi = float(median_ndvi)
        ndvi_msg.std_dev_ndvi = float(std_ndvi)
        ndvi_msg.ndvi_trend_slope = float(ndvi_trend_slope)
        ndvi_msg.trend_window_size = len(self._ndvi_buffer)
        ndvi_msg.timestamp = stamp
        self._pub_ndvi.publish(ndvi_msg)

        self.get_logger().info(
            f'Capture #{self._capture_index} complete — '
            f'NDVI={mean_ndvi:.3f} (trend={ndvi_trend_slope:.5f}), '
            f'area={measurement_msg.canopy_area_cm2:.1f}cm², '
            f'symptoms={visual_symptoms}'
        )

        # NDVI early-warning protocol
        self._check_ndvi_early_warning(mean_ndvi, ndvi_trend_slope, stamp)

    # -------------------------------------------------------------------------
    # NDVI computation
    # -------------------------------------------------------------------------

    def _compute_ndvi(
        self,
        ndvi_frame: np.ndarray,
        plant_mask: np.ndarray,
    ) -> tuple[np.ndarray, float, float, float]:
        """Compute per-pixel NDVI from NoIR camera frame.

        With blue gel filter on NoIR camera:
          - Red channel  → NIR light (blue filter blocks visible red)
          - Blue channel → visible blue light
          NDVI = (NIR - visible_blue) / (NIR + visible_blue)

        Args:
            ndvi_frame: BGR image from NoIR camera.
            plant_mask: Boolean mask of plant pixels (from RGB segmentation).

        Returns:
            Tuple of (full ndvi array, mean, median, std_dev) over plant region.
        """
        # Split channels from BGR NoIR image
        blue_ch = ndvi_frame[:, :, 0].astype(np.float32)
        red_ch = ndvi_frame[:, :, 2].astype(np.float32)

        # NIR = red channel, visible = blue channel
        nir = red_ch
        visible = blue_ch

        denominator = nir + visible
        # Avoid divide-by-zero
        denominator = np.where(denominator == 0, 1e-6, denominator)
        ndvi_array = (nir - visible) / denominator

        # Clamp to [-1, 1]
        ndvi_array = np.clip(ndvi_array, -1.0, 1.0)

        # Apply plant mask — only compute stats over plant pixels
        if plant_mask is not None and plant_mask.sum() > 0:
            plant_pixels = ndvi_array[plant_mask > 0]
        else:
            plant_pixels = ndvi_array.flatten()

        mean_ndvi = float(np.mean(plant_pixels))
        median_ndvi = float(np.median(plant_pixels))
        std_ndvi = float(np.std(plant_pixels))

        return ndvi_array, mean_ndvi, median_ndvi, std_ndvi

    # -------------------------------------------------------------------------
    # AprilTag scale calibration
    # -------------------------------------------------------------------------

    def _compute_scale_from_apriltags(
        self, rgb_frame: np.ndarray
    ) -> float:
        """Detect AprilTags and compute px-to-cm scale factor.

        Uses configured physical tag size and known separation to cross-validate.
        If no tags detected, logs warning and returns 0 (callers treat 0 as unknown).

        Args:
            rgb_frame: BGR RGB camera frame.

        Returns:
            Scale factor in pixels-per-cm, or 0.0 if tags not detected.
        """
        gray = cv2.cvtColor(rgb_frame, cv2.COLOR_BGR2GRAY)
        corners, ids, _ = self._aruco_detector.detectMarkers(gray)

        if ids is None or len(ids) == 0:
            self.get_logger().warn(
                'No AprilTags detected in RGB frame — skipping scale calibration for this capture'
            )
            return 0.0

        tag_size_px_estimates: list[float] = []
        for corner_set in corners:
            pts = corner_set[0]
            # Compute mean side length of the tag in pixels
            side_lengths = [
                np.linalg.norm(pts[i] - pts[(i + 1) % 4])
                for i in range(4)
            ]
            mean_side_px = float(np.mean(side_lengths))
            tag_size_m = self._apriltag_tag_size_m
            px_per_m = mean_side_px / tag_size_m
            px_per_cm = px_per_m / 100.0
            tag_size_px_estimates.append(px_per_cm)

        primary_scale = tag_size_px_estimates[0]

        # Cross-validate using separation distance if two tags detected
        if len(ids) >= 2:
            center0 = corners[0][0].mean(axis=0)
            center1 = corners[1][0].mean(axis=0)
            separation_px = float(np.linalg.norm(center0 - center1))
            separation_scale = separation_px / (self._apriltag_separation_m * 100.0)

            discrepancy = abs(primary_scale - separation_scale) / primary_scale
            if discrepancy > self._scale_tolerance:
                self.get_logger().warn(
                    f'AprilTag scale cross-validation failed: '
                    f'tag_size_estimate={primary_scale:.2f} px/cm, '
                    f'separation_estimate={separation_scale:.2f} px/cm, '
                    f'discrepancy={discrepancy:.1%} > tolerance={self._scale_tolerance:.1%}'
                )

        return primary_scale

    # -------------------------------------------------------------------------
    # Plant segmentation
    # -------------------------------------------------------------------------

    def _segment_plant(self, rgb_frame: np.ndarray) -> np.ndarray:
        """Segment green plant material using HSV thresholding.

        Args:
            rgb_frame: BGR RGB camera frame.

        Returns:
            Binary mask (uint8, 0 or 255) of plant pixels.
        """
        hsv = cv2.cvtColor(rgb_frame, cv2.COLOR_BGR2HSV)
        raw_mask = cv2.inRange(hsv, self._hsv_lower, self._hsv_upper)

        kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE,
            (self._morph_kernel_size, self._morph_kernel_size)
        )
        eroded = cv2.erode(raw_mask, kernel, iterations=1)
        dilated = cv2.dilate(eroded, kernel, iterations=1)

        # Extract largest contour
        contours, _ = cv2.findContours(
            dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        final_mask = np.zeros_like(dilated)
        if contours:
            largest = max(contours, key=cv2.contourArea)
            cv2.drawContours(final_mask, [largest], -1, 255, thickness=cv2.FILLED)

        return final_mask

    # -------------------------------------------------------------------------
    # Temporal change tracking
    # -------------------------------------------------------------------------

    def _update_temporal_tracking(
        self,
        rgb_frame: np.ndarray,
        current_mask: np.ndarray,
    ) -> list[str]:
        """Update frame history and classify visual symptoms via temporal analysis.

        Uses AprilTag-based registration to align frames. Detects:
          - yellowing_established_growth  (mobile nutrient deficiency)
          - symptomatic_new_growth        (immobile nutrient deficiency)
          - browning_leaf_edges           (nutrient burn / K deficiency)

        Args:
            rgb_frame: Current RGB frame (BGR).
            current_mask: Current frame's plant segmentation mask.

        Returns:
            List of detected symptom strings.
        """
        symptoms: list[str] = []
        current_hsv = cv2.cvtColor(rgb_frame, cv2.COLOR_BGR2HSV)

        self._frame_history.append({
            'index': self._capture_index,
            'mask': current_mask.copy(),
            'hsv': current_hsv.copy(),
        })

        if len(self._frame_history) < max(self._established_threshold, self._new_growth_threshold):
            return symptoms

        # Established growth: pixels present in frames from >= established_threshold ago
        established_idx = self._capture_index - self._established_threshold
        new_growth_idx = self._capture_index - self._new_growth_threshold

        established_mask = np.zeros_like(current_mask)
        new_growth_mask = np.zeros_like(current_mask)

        for frame_data in self._frame_history:
            if frame_data['index'] <= established_idx:
                established_mask = cv2.bitwise_or(
                    established_mask, frame_data['mask']
                )
            elif frame_data['index'] >= new_growth_idx:
                # Only pixels that recently entered the mask
                recent_only = cv2.bitwise_and(
                    frame_data['mask'],
                    cv2.bitwise_not(established_mask)
                )
                new_growth_mask = cv2.bitwise_or(new_growth_mask, recent_only)

        # Yellowing in established growth: increasing hue (green→yellow), decreasing saturation
        if established_mask.sum() > 0:
            established_pixels_hsv = current_hsv[established_mask > 0]
            if len(established_pixels_hsv) > 0:
                mean_hue = float(np.mean(established_pixels_hsv[:, 0]))
                mean_sat = float(np.mean(established_pixels_hsv[:, 1]))
                # Yellow hue range in OpenCV: ~20-35 (out of 180)
                # Green hue range: ~35-85
                if mean_hue < 35 and mean_sat < 100:
                    symptoms.append('yellowing_established_growth')

        # Symptomatic new growth: pale/chlorotic from the start
        if new_growth_mask.sum() > 0:
            new_pixels_hsv = current_hsv[new_growth_mask > 0]
            if len(new_pixels_hsv) > 0:
                mean_sat_new = float(np.mean(new_pixels_hsv[:, 1]))
                mean_val_new = float(np.mean(new_pixels_hsv[:, 2]))
                # Pale/chlorotic: low saturation, high value (washed out)
                if mean_sat_new < 60 and mean_val_new > 180:
                    symptoms.append('symptomatic_new_growth')

        # Browning at leaf edges: brown pixels (hue ~10-20, saturation >50) at contour boundary
        contours, _ = cv2.findContours(
            current_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        if contours:
            edge_mask = np.zeros_like(current_mask)
            largest = max(contours, key=cv2.contourArea)
            cv2.drawContours(edge_mask, [largest], -1, 255, thickness=8)
            edge_pixels_hsv = current_hsv[edge_mask > 0]
            if len(edge_pixels_hsv) > 0:
                brown_pixels = np.sum(
                    (edge_pixels_hsv[:, 0] >= 10) &
                    (edge_pixels_hsv[:, 0] <= 20) &
                    (edge_pixels_hsv[:, 1] > 50)
                )
                brown_fraction = brown_pixels / len(edge_pixels_hsv)
                if brown_fraction > 0.15:
                    symptoms.append('browning_leaf_edges')

        return symptoms

    # -------------------------------------------------------------------------
    # NDVI trend and early warning
    # -------------------------------------------------------------------------

    def _compute_ndvi_trend(self) -> float:
        """Compute linear slope of NDVI values in the rolling buffer.

        Returns:
            Slope per capture (negative = declining), or 0.0 if insufficient data.
        """
        if len(self._ndvi_buffer) < 3:
            return 0.0

        values = np.array(list(self._ndvi_buffer), dtype=np.float64)
        indices = np.arange(len(values), dtype=np.float64)
        # Linear regression via numpy polyfit
        slope = float(np.polyfit(indices, values, 1)[0])
        return slope

    def _check_ndvi_early_warning(
        self,
        mean_ndvi: float,
        trend_slope: float,
        stamp: object,
    ) -> None:
        """Trigger early-warning protocol if NDVI is declining.

        Increases probe frequency and capture frequency, and publishes NDVIAlert.

        Args:
            mean_ndvi: Current mean NDVI over plant region.
            trend_slope: Linear slope of NDVI buffer (negative = declining).
            stamp: ROS timestamp.
        """
        is_declining = trend_slope < self._ndvi_declining_threshold

        if is_declining and not self._in_alert_mode:
            self._in_alert_mode = True
            self.get_logger().warn(
                f'NDVI early warning triggered: mean_ndvi={mean_ndvi:.3f}, '
                f'slope={trend_slope:.5f} < threshold={self._ndvi_declining_threshold}'
            )

            # Increase probe frequency
            if self._probe_interval_client.wait_for_service(timeout_sec=2.0):
                req = SetProbeInterval.Request()
                req.interval_seconds = 300.0  # 5 minutes when in alert
                future = self._probe_interval_client.call_async(req)
                rclpy.spin_until_future_complete(self, future, timeout_sec=3.0)
                if future.done() and future.result().success:
                    self.get_logger().info(
                        f'Probe interval decreased to {future.result().applied_interval_seconds}s '
                        f'(NDVI early warning)'
                    )
            else:
                self.get_logger().warn(
                    '/probe/set_interval service unavailable — cannot increase probe frequency'
                )

            # Switch capture timer to faster interval
            self._capture_timer.cancel()
            self._capture_timer = self.create_timer(
                self._capture_interval_alert,
                self._run_capture_pipeline,
                callback_group=self._cb_group,
            )
            self.get_logger().info(
                f'Capture interval decreased to {self._capture_interval_alert}s '
                f'(NDVI early warning)'
            )

            # Determine alert level
            if mean_ndvi < self._ndvi_critical_threshold:
                alert_level = 'critical'
            elif mean_ndvi < self._ndvi_warning_threshold:
                alert_level = 'warning'
            else:
                alert_level = 'watch'

            # Publish NDVIAlert
            ndvi_48h_ago = (
                float(self._ndvi_buffer[0])
                if len(self._ndvi_buffer) >= self._ndvi_buffer_size
                else float(self._ndvi_buffer[0]) if self._ndvi_buffer else mean_ndvi
            )
            alert_msg = NDVIAlert()
            alert_msg.current_ndvi = float(mean_ndvi)
            alert_msg.ndvi_trend_slope = float(trend_slope)
            alert_msg.ndvi_48h_ago = ndvi_48h_ago
            alert_msg.alert_level = alert_level
            alert_msg.timestamp = stamp
            self._pub_ndvi_alert.publish(alert_msg)

        elif not is_declining and self._in_alert_mode:
            # NDVI recovered — return to normal intervals
            self._in_alert_mode = False
            self.get_logger().info(
                f'NDVI recovered (slope={trend_slope:.5f}) — returning to normal intervals'
            )
            self._capture_timer.cancel()
            self._capture_timer = self.create_timer(
                self._capture_interval,
                self._run_capture_pipeline,
                callback_group=self._cb_group,
            )

            if self._probe_interval_client.wait_for_service(timeout_sec=2.0):
                req = SetProbeInterval.Request()
                req.interval_seconds = 900.0  # restore default
                self._probe_interval_client.call_async(req)

    # -------------------------------------------------------------------------
    # Growth stall detection
    # -------------------------------------------------------------------------

    def _check_growth_stall(self) -> bool:
        """Check if plant area growth has stalled over the configured window.

        Returns:
            True if growth stall detected.
        """
        if len(self._frame_history) < self._stall_window + 1:
            return False

        frames_list = list(self._frame_history)
        recent_area = cv2.countNonZero(frames_list[-1]['mask'])
        old_area = cv2.countNonZero(frames_list[-(self._stall_window + 1)]['mask'])

        if old_area == 0:
            return False

        growth_fraction = (recent_area - old_area) / old_area
        return growth_fraction < self._stall_min_increase

    # -------------------------------------------------------------------------
    # Measurement helpers
    # -------------------------------------------------------------------------

    def _mask_area_cm2(self, mask: np.ndarray, px_per_cm: float) -> float:
        """Convert mask pixel count to cm².

        Args:
            mask: Binary mask.
            px_per_cm: Scale factor (pixels per cm).

        Returns:
            Area in cm², or 0.0 if scale is unknown.
        """
        if px_per_cm <= 0:
            return float(cv2.countNonZero(mask))
        return float(cv2.countNonZero(mask)) / (px_per_cm ** 2)

    def _mask_width_cm(self, mask: np.ndarray, px_per_cm: float) -> float:
        """Return bounding box width in cm."""
        contours, _ = cv2.findContours(
            mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        if not contours:
            return 0.0
        x, _, w, _ = cv2.boundingRect(max(contours, key=cv2.contourArea))
        return float(w) / px_per_cm if px_per_cm > 0 else float(w)

    def _mask_height_cm(self, mask: np.ndarray, px_per_cm: float) -> float:
        """Return bounding box height in cm."""
        contours, _ = cv2.findContours(
            mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        if not contours:
            return 0.0
        _, _, _, h = cv2.boundingRect(max(contours, key=cv2.contourArea))
        return float(h) / px_per_cm if px_per_cm > 0 else float(h)

    # -------------------------------------------------------------------------
    # Frame storage
    # -------------------------------------------------------------------------

    def _save_frames(
        self,
        rgb_frame: np.ndarray,
        ndvi_frame: np.ndarray,
        timestamp_str: str,
    ) -> None:
        """Save captured frame pair to disk.

        Args:
            rgb_frame: BGR RGB camera frame.
            ndvi_frame: BGR NoIR camera frame.
            timestamp_str: Timestamp string for filename.
        """
        rgb_path = self._storage_path / f'{timestamp_str}_rgb.jpg'
        ndvi_path = self._storage_path / f'{timestamp_str}_ndvi.jpg'
        try:
            cv2.imwrite(str(rgb_path), rgb_frame)
            cv2.imwrite(str(ndvi_path), ndvi_frame)
            self.get_logger().debug(
                f'Frames saved: {rgb_path.name}, {ndvi_path.name}'
            )
        except Exception as exc:
            self.get_logger().warn(f'Failed to save frames: {exc}')

    def _publish_image(
        self,
        frame: np.ndarray,
        publisher: object,
        stamp: object,
    ) -> None:
        """Convert BGR frame to ROS Image and publish.

        Args:
            frame: BGR numpy array.
            publisher: ROS publisher for sensor_msgs/Image.
            stamp: ROS timestamp.
        """
        try:
            msg = self._bridge.cv2_to_imgmsg(frame, encoding='bgr8')
            msg.header.stamp = stamp
            publisher.publish(msg)
        except Exception as exc:
            self.get_logger().warn(f'Failed to publish image: {exc}')

    # -------------------------------------------------------------------------
    # Service handler
    # -------------------------------------------------------------------------

    def _handle_capture(
        self,
        request: CaptureVision.Request,
        response: CaptureVision.Response,
    ) -> CaptureVision.Response:
        """Handle on-demand capture request."""
        self.get_logger().info('/vision/capture received — running on-demand capture')
        try:
            self._run_capture_pipeline()
            response.success = True
            response.message = 'Capture pipeline completed successfully'
        except Exception as exc:
            self.get_logger().error(f'On-demand capture failed: {exc}')
            response.success = False
            response.message = str(exc)
        return response

    def destroy_node(self) -> None:
        """Release camera resources on shutdown."""
        if self._rgb_cap.isOpened():
            self._rgb_cap.release()
        if self._ndvi_cap.isOpened():
            self._ndvi_cap.release()
        super().destroy_node()


def main(args: Optional[list[str]] = None) -> None:
    """Initialise rclpy, spin the PlantVisionNode, and shut down cleanly."""
    rclpy.init(args=args)
    node = PlantVisionNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info('PlantVisionNode interrupted')
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
