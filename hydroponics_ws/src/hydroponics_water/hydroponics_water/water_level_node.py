# MIT License
# Copyright (c) 2026 Autoponics Project

"""ROS2 water level node for Autoponics V0.1 single-plant platform.

Purpose
-------
Monitors water level in the DWC bin via an ultrasonic distance sensor,
triggers reactive auto top-off when level drops below the configured
threshold, and logs consumption data for future predictive modelling.

Subscriptions
-------------
None at steady state. The node self-triggers on a timer.

Publications
------------
/water/level           (hydroponics_msgs/WaterLevel)
/water/topoff_event    (hydroponics_msgs/TopOffEvent)
/water/error           (std_msgs/String)

Services called
---------------
/probe/trigger  (hydroponics_msgs/srv/TriggerProbe)
  Called after each top-off cycle to capture fresh sensor readings.

Parameters
----------
All loaded from v01_system.yaml under the 'water' and 'bin' keys.
"""

from __future__ import annotations

import csv
import os
import time
from pathlib import Path
from typing import Optional

import rclpy
from rclpy.node import Node
from rclpy.callback_group import ReentrantCallbackGroup
from std_msgs.msg import String, Float32

from hydroponics_msgs.msg import WaterLevel, TopOffEvent
from hydroponics_msgs.srv import TriggerProbe


class WaterLevelNode(Node):
    """Ultrasonic water level monitor with reactive auto top-off."""

    def __init__(self) -> None:
        super().__init__('water_level_node')
        self._cb_group = ReentrantCallbackGroup()

        # --- Parameters ---
        self.declare_parameter('water.read_interval_seconds', 300.0)
        self.declare_parameter('water.ultrasonic_trigger_pin', 23)
        self.declare_parameter('water.ultrasonic_echo_pin', 24)
        self.declare_parameter('water.topoff_low_threshold_percent', 60.0)
        self.declare_parameter('water.topoff_target_percent', 85.0)
        self.declare_parameter('water.solenoid_gpio_pin', 25)
        self.declare_parameter('water.fill_poll_interval_seconds', 1.0)
        self.declare_parameter('water.max_fill_time_seconds', 120.0)
        self.declare_parameter('water.post_fill_mixing_delay_seconds', 60.0)
        self.declare_parameter('water.log_path', '~/.autoponics/water_log.csv')
        self.declare_parameter('water.consumption_alert_multiplier', 1.5)
        self.declare_parameter('bin.cross_section_cm2', 900.0)
        self.declare_parameter('bin.depth_cm', 25.0)
        self.declare_parameter('bin.sensor_mount_height_cm', 10.0)

        self._read_interval: float = (
            self.get_parameter('water.read_interval_seconds')
            .get_parameter_value().double_value
        )
        self._trigger_pin: int = (
            self.get_parameter('water.ultrasonic_trigger_pin')
            .get_parameter_value().integer_value
        )
        self._echo_pin: int = (
            self.get_parameter('water.ultrasonic_echo_pin')
            .get_parameter_value().integer_value
        )
        self._low_threshold: float = (
            self.get_parameter('water.topoff_low_threshold_percent')
            .get_parameter_value().double_value
        )
        self._fill_target: float = (
            self.get_parameter('water.topoff_target_percent')
            .get_parameter_value().double_value
        )
        self._solenoid_pin: int = (
            self.get_parameter('water.solenoid_gpio_pin')
            .get_parameter_value().integer_value
        )
        self._fill_poll_interval: float = (
            self.get_parameter('water.fill_poll_interval_seconds')
            .get_parameter_value().double_value
        )
        self._max_fill_time: float = (
            self.get_parameter('water.max_fill_time_seconds')
            .get_parameter_value().double_value
        )
        self._mixing_delay: float = (
            self.get_parameter('water.post_fill_mixing_delay_seconds')
            .get_parameter_value().double_value
        )
        self._log_path: Path = Path(
            os.path.expanduser(
                self.get_parameter('water.log_path').get_parameter_value().string_value
            )
        )
        self._consumption_alert_multiplier: float = (
            self.get_parameter('water.consumption_alert_multiplier')
            .get_parameter_value().double_value
        )
        self._bin_cross_section_cm2: float = (
            self.get_parameter('bin.cross_section_cm2').get_parameter_value().double_value
        )
        self._bin_depth_cm: float = (
            self.get_parameter('bin.depth_cm').get_parameter_value().double_value
        )
        self._sensor_mount_height_cm: float = (
            self.get_parameter('bin.sensor_mount_height_cm')
            .get_parameter_value().double_value
        )

        # --- State ---
        self._last_level_percent: float = 100.0
        self._previous_level_percent: float = 100.0
        # Rolling average of fill volumes for consumption rate alerting
        self._consumption_history: list[float] = []

        # --- Ensure log directory exists ---
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_log()

        # --- Publishers ---
        self._pub_level = self.create_publisher(WaterLevel, '/water/level', 10)
        self._pub_topoff = self.create_publisher(TopOffEvent, '/water/topoff_event', 10)
        self._pub_error = self.create_publisher(String, '/water/error', 10)
        # Solenoid command (GPIO relay)
        self._pub_solenoid = self.create_publisher(String, '/solenoid_cmd', 10)

        # --- Service clients ---
        self._probe_trigger_client = self.create_client(
            TriggerProbe, '/probe/trigger'
        )

        # --- Subscriber: simulated/real ultrasonic distance topic ---
        # In V0.1, the ESP32 publishes distance to /ultrasonic_distance_cm
        self._sub_distance = self.create_subscription(
            Float32, '/ultrasonic_distance_cm', self._distance_callback, 10,
            callback_group=self._cb_group
        )
        self._latest_distance_cm: Optional[float] = None

        # --- Level read timer ---
        self._level_timer = self.create_timer(
            self._read_interval, self._read_and_evaluate,
            callback_group=self._cb_group
        )

        self.get_logger().info(
            f'WaterLevelNode ready — read_interval={self._read_interval}s, '
            f'low_threshold={self._low_threshold}%, '
            f'fill_target={self._fill_target}%'
        )

    # -------------------------------------------------------------------------
    # Distance callback
    # -------------------------------------------------------------------------

    def _distance_callback(self, msg: Float32) -> None:
        """Receive ultrasonic distance reading from ESP32."""
        self._latest_distance_cm = msg.data

    # -------------------------------------------------------------------------
    # Level read and evaluate
    # -------------------------------------------------------------------------

    def _read_and_evaluate(self) -> None:
        """Read water level, publish it, and trigger top-off if needed."""
        level_cm, level_percent = self._get_water_level()
        self._last_level_percent = level_percent

        stamp = self.get_clock().now().to_msg()
        level_msg = WaterLevel()
        level_msg.level_cm = level_cm
        level_msg.level_percent = level_percent
        level_msg.timestamp = stamp
        self._pub_level.publish(level_msg)

        self._log_reading(level_cm, level_percent, 'reading', 0.0)

        self.get_logger().info(
            f'Water level: {level_percent:.1f}% ({level_cm:.1f} cm)'
        )

        if level_percent < self._low_threshold:
            self.get_logger().info(
                f'Water level {level_percent:.1f}% below threshold {self._low_threshold}% '
                f'— triggering top-off'
            )
            self._run_topoff_cycle(level_before=level_percent)

    # -------------------------------------------------------------------------
    # Top-off cycle
    # -------------------------------------------------------------------------

    def _run_topoff_cycle(self, level_before: float) -> None:
        """Open solenoid, fill to target with ultrasonic feedback, then close.

        Safety: closes valve after max_fill_time_seconds regardless of level.

        Args:
            level_before: Water level percent at start of fill.
        """
        self.get_logger().info('Top-off cycle starting — opening solenoid valve')
        self._set_solenoid(on=True)

        fill_start = time.monotonic()
        reached_target = False
        current_level = level_before

        while (time.monotonic() - fill_start) < self._max_fill_time:
            time.sleep(self._fill_poll_interval)
            _, current_level = self._get_water_level()
            if current_level >= self._fill_target:
                reached_target = True
                break

        self._set_solenoid(on=False)

        if not reached_target:
            error_msg = (
                f'Top-off safety timeout: level reached {current_level:.1f}% '
                f'in {self._max_fill_time}s (target {self._fill_target}%). '
                f'Check sensor calibration or water supply.'
            )
            self.get_logger().error(error_msg)
            err = String()
            err.data = error_msg
            self._pub_error.publish(err)

        level_after = current_level
        fill_cm = max(0.0, (level_after - level_before) / 100.0 * self._bin_depth_cm)
        volume_mL = fill_cm * self._bin_cross_section_cm2 * 10.0  # cm³ → mL

        self.get_logger().info(
            f'Top-off complete: level {level_before:.1f}% → {level_after:.1f}% '
            f'(~{volume_mL:.0f} mL added)'
        )

        stamp = self.get_clock().now().to_msg()
        topoff_msg = TopOffEvent()
        topoff_msg.volume_added_mL = volume_mL
        topoff_msg.level_before_percent = level_before
        topoff_msg.level_after_percent = level_after
        topoff_msg.timestamp = stamp
        self._pub_topoff.publish(topoff_msg)

        self._log_reading(
            level_after / 100.0 * self._bin_depth_cm,
            level_after,
            'topoff',
            volume_mL,
        )

        # Check for above-normal consumption rate
        self._consumption_history.append(volume_mL)
        if len(self._consumption_history) >= 3:
            avg = sum(self._consumption_history[:-1]) / len(self._consumption_history[:-1])
            if volume_mL > avg * self._consumption_alert_multiplier:
                self.get_logger().warn(
                    f'Water consumption above normal: {volume_mL:.0f} mL '
                    f'vs average {avg:.0f} mL'
                )

        # Wait for mixing then trigger probe
        self.get_logger().info(
            f'Waiting {self._mixing_delay}s for mixing before probing'
        )
        time.sleep(self._mixing_delay)
        self._trigger_probe()

    # -------------------------------------------------------------------------
    # Level computation
    # -------------------------------------------------------------------------

    def _get_water_level(self) -> tuple[float, float]:
        """Convert ultrasonic distance reading to water level cm and percent.

        The sensor is mounted above the bin rim. It measures distance to the
        water surface. Shorter distance = higher water level.

          water_cm = bin_depth_cm - (distance_cm - sensor_mount_height_cm)

        Returns:
            Tuple of (level_cm, level_percent).
        """
        if self._latest_distance_cm is None:
            # No reading yet — return a safe default
            self.get_logger().warn(
                'No ultrasonic distance reading available — returning 100% level'
            )
            return self._bin_depth_cm, 100.0

        total_depth = self._sensor_mount_height_cm + self._bin_depth_cm
        # Distance from sensor to water surface
        distance_to_water = float(self._latest_distance_cm)
        # Water depth = how much water is in the bin
        water_cm = total_depth - distance_to_water
        water_cm = max(0.0, min(water_cm, self._bin_depth_cm))
        level_percent = (water_cm / self._bin_depth_cm) * 100.0
        return water_cm, level_percent

    # -------------------------------------------------------------------------
    # Hardware helpers
    # -------------------------------------------------------------------------

    def _set_solenoid(self, on: bool) -> None:
        """Send solenoid valve open/close command.

        Args:
            on: True to open valve, False to close.
        """
        msg = String()
        msg.data = f'solenoid:{self._solenoid_pin}:{"1" if on else "0"}'
        self._pub_solenoid.publish(msg)

    def _trigger_probe(self) -> None:
        """Call /probe/trigger service to take a reading after top-off."""
        if not self._probe_trigger_client.wait_for_service(timeout_sec=2.0):
            self.get_logger().warn(
                '/probe/trigger service unavailable — skipping post-fill probe'
            )
            return
        req = TriggerProbe.Request()
        future = self._probe_trigger_client.call_async(req)
        rclpy.spin_until_future_complete(self, future, timeout_sec=30.0)
        if future.done() and future.result().success:
            self.get_logger().info('Post-fill probe cycle completed')
        else:
            self.get_logger().warn('Post-fill probe cycle failed or timed out')

    # -------------------------------------------------------------------------
    # CSV logging
    # -------------------------------------------------------------------------

    def _init_log(self) -> None:
        """Create the CSV log file with headers if it does not exist."""
        if not self._log_path.exists():
            with open(self._log_path, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'timestamp', 'level_cm', 'level_percent',
                    'event_type', 'volume_added_mL',
                    'probe_ec_after', 'probe_ph_after',
                ])

    def _log_reading(
        self,
        level_cm: float,
        level_percent: float,
        event_type: str,
        volume_added_mL: float,
    ) -> None:
        """Append a row to the water consumption log.

        Args:
            level_cm: Water level in cm.
            level_percent: Water level as a percentage.
            event_type: 'reading' or 'topoff'.
            volume_added_mL: Volume added (0 for readings).
        """
        try:
            with open(self._log_path, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    time.strftime('%Y-%m-%dT%H:%M:%S'),
                    f'{level_cm:.2f}',
                    f'{level_percent:.2f}',
                    event_type,
                    f'{volume_added_mL:.1f}',
                    '',  # probe_ec_after — filled by dosing node in V0.2
                    '',  # probe_ph_after
                ])
        except Exception as exc:
            self.get_logger().warn(f'Failed to write water log: {exc}')


def main(args: Optional[list[str]] = None) -> None:
    """Initialise rclpy, spin the WaterLevelNode, and shut down cleanly."""
    rclpy.init(args=args)
    node = WaterLevelNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info('WaterLevelNode interrupted')
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
