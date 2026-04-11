# MIT License
# Copyright (c) 2026 AIdroponics Project

"""ROS2 probe arm node for AIdroponics V0.1 single-plant platform.

Purpose
-------
Controls a servo-driven arm that inserts pH, EC, and temperature probes
into the nutrient solution, waits for sensor stabilization, reads the
sensors, then retracts the arm. Publishes readings to /probe/reading.

Single fixed bin position — all multi-bin targeting logic from the original
work station design has been removed.

Subscriptions
-------------
None at steady state. The node self-triggers on a timer.

Publications
------------
/probe/reading  (hydroponics_msgs/ProbeReading)

Services provided
-----------------
/probe/trigger        (hydroponics_msgs/srv/TriggerProbe)   — on-demand cycle
/probe/set_interval   (hydroponics_msgs/srv/SetProbeInterval) — change timer interval

Parameters
----------
All loaded from v01_system.yaml under the 'probe' key:
  interval_seconds           — default probe cycle period
  min_interval_seconds       — floor for set_interval requests
  stabilization_delay_seconds — wait after servo extends before reading
  servo_channel              — ESP32 servo channel index
  servo_extended_angle       — angle when probes submerged
  servo_retracted_angle      — angle when probes retracted
"""

from __future__ import annotations

import time
from typing import Optional

import rclpy
from rclpy.node import Node
from rclpy.callback_group import ReentrantCallbackGroup
from std_msgs.msg import Float32, Int32

from hydroponics_msgs.msg import ProbeReading
from hydroponics_msgs.srv import TriggerProbe, SetProbeInterval


class ProbeArmNode(Node):
    """Servo-driven probe arm controller for single-bin V0.1 operation."""

    def __init__(self) -> None:
        super().__init__('probe_arm_node')
        self._cb_group = ReentrantCallbackGroup()

        # --- Parameters ---
        self.declare_parameter('probe.interval_seconds', 900.0)
        self.declare_parameter('probe.min_interval_seconds', 300.0)
        self.declare_parameter('probe.stabilization_delay_seconds', 5.0)
        self.declare_parameter('probe.servo_channel', 0)
        self.declare_parameter('probe.servo_extended_angle', 90)
        self.declare_parameter('probe.servo_retracted_angle', 0)

        self._interval: float = (
            self.get_parameter('probe.interval_seconds').get_parameter_value().double_value
        )
        self._min_interval: float = (
            self.get_parameter('probe.min_interval_seconds').get_parameter_value().double_value
        )
        self._stabilization_delay: float = (
            self.get_parameter('probe.stabilization_delay_seconds')
            .get_parameter_value().double_value
        )
        self._servo_channel: int = (
            self.get_parameter('probe.servo_channel').get_parameter_value().integer_value
        )
        self._servo_extended_angle: int = (
            self.get_parameter('probe.servo_extended_angle').get_parameter_value().integer_value
        )
        self._servo_retracted_angle: int = (
            self.get_parameter('probe.servo_retracted_angle').get_parameter_value().integer_value
        )

        # --- Sensor readings (updated by ESP32 micro-ROS topics) ---
        self._current_ph: float = 7.0
        self._current_ec: float = 0.0
        self._current_temp: float = 20.0

        # --- Publisher ---
        self._pub_reading = self.create_publisher(
            ProbeReading, '/probe/reading', 10
        )

        # --- Servo command publisher (to ESP32 via micro-ROS bridge) ---
        # Encoding: channel * 1000 + angle
        self._pub_servo = self.create_publisher(Int32, '/servo_cmd_raw', 10)

        # --- Sensor subscribers ---
        self._sub_ph = self.create_subscription(
            Float32, '/ph_raw', self._ph_callback, 10,
            callback_group=self._cb_group
        )
        self._sub_ec = self.create_subscription(
            Float32, '/ec_raw', self._ec_callback, 10,
            callback_group=self._cb_group
        )
        self._sub_temp = self.create_subscription(
            Float32, '/temperature', self._temp_callback, 10,
            callback_group=self._cb_group
        )

        # --- Services ---
        self._srv_trigger = self.create_service(
            TriggerProbe, '/probe/trigger', self._handle_trigger,
            callback_group=self._cb_group
        )
        self._srv_set_interval = self.create_service(
            SetProbeInterval, '/probe/set_interval', self._handle_set_interval,
            callback_group=self._cb_group
        )

        # --- Probe cycle timer ---
        self._probe_timer = self.create_timer(
            self._interval, self._run_probe_cycle,
            callback_group=self._cb_group
        )

        self.get_logger().info(
            f'ProbeArmNode ready — interval={self._interval}s, '
            f'stabilization_delay={self._stabilization_delay}s, '
            f'servo_channel={self._servo_channel}'
        )

    # -------------------------------------------------------------------------
    # Sensor callbacks
    # -------------------------------------------------------------------------

    def _ph_callback(self, msg: Float32) -> None:
        self._current_ph = msg.data

    def _ec_callback(self, msg: Float32) -> None:
        self._current_ec = msg.data

    def _temp_callback(self, msg: Float32) -> None:
        self._current_temp = msg.data

    # -------------------------------------------------------------------------
    # Core probe cycle
    # -------------------------------------------------------------------------

    def _run_probe_cycle(self) -> None:
        """Execute one full probe cycle: extend → stabilize → read → retract → publish."""
        self.get_logger().info('Probe cycle starting')

        self._set_servo(self._servo_extended_angle)
        self.get_logger().info(
            f'Probe arm extended (angle={self._servo_extended_angle}). '
            f'Waiting {self._stabilization_delay}s for stabilization.'
        )
        time.sleep(self._stabilization_delay)

        ph = self._current_ph
        ec = self._current_ec
        temp = self._current_temp

        self._set_servo(self._servo_retracted_angle)
        self.get_logger().info(
            f'Probe arm retracted. pH={ph:.2f}  EC={ec:.3f} mS/cm  '
            f'temp={temp:.1f}°C'
        )

        msg = ProbeReading()
        msg.ph = ph
        msg.ec_mS_cm = ec
        msg.temperature_C = temp
        msg.timestamp = self.get_clock().now().to_msg()
        self._pub_reading.publish(msg)

    # -------------------------------------------------------------------------
    # Service handlers
    # -------------------------------------------------------------------------

    def _handle_trigger(
        self,
        request: TriggerProbe.Request,
        response: TriggerProbe.Response,
    ) -> TriggerProbe.Response:
        """Handle on-demand probe cycle request."""
        self.get_logger().info('/probe/trigger received — running on-demand cycle')
        try:
            self._run_probe_cycle()
            response.success = True
            response.message = 'Probe cycle completed successfully'
        except Exception as exc:
            self.get_logger().error(f'On-demand probe cycle failed: {exc}')
            response.success = False
            response.message = str(exc)
            try:
                self._set_servo(self._servo_retracted_angle)
            except Exception:
                pass
        return response

    def _handle_set_interval(
        self,
        request: SetProbeInterval.Request,
        response: SetProbeInterval.Response,
    ) -> SetProbeInterval.Response:
        """Handle request to change the probe cycle interval."""
        requested: float = float(request.interval_seconds)

        if requested < self._min_interval:
            self.get_logger().warn(
                f'/probe/set_interval: requested {requested}s is below minimum '
                f'{self._min_interval}s — clamping to minimum'
            )
            applied = self._min_interval
        else:
            applied = requested

        self._interval = applied
        self._probe_timer.cancel()
        self._probe_timer = self.create_timer(
            self._interval, self._run_probe_cycle,
            callback_group=self._cb_group
        )

        self.get_logger().info(f'Probe interval updated to {applied}s')
        response.success = True
        response.applied_interval_seconds = applied
        response.message = f'Probe interval set to {applied}s'
        return response

    # -------------------------------------------------------------------------
    # Hardware helpers
    # -------------------------------------------------------------------------

    def _set_servo(self, angle: int) -> None:
        """Send a servo position command to the ESP32.

        Encoding: channel * 1000 + angle (integer), matches ESP32 firmware
        expectation on /servo_cmd_raw.

        Args:
            angle: Target servo angle in degrees.
        """
        msg = Int32()
        msg.data = self._servo_channel * 1000 + angle
        self._pub_servo.publish(msg)


def main(args: Optional[list[str]] = None) -> None:
    """Initialise rclpy, spin the ProbeArmNode, and shut down cleanly."""
    rclpy.init(args=args)
    node = ProbeArmNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info('ProbeArmNode interrupted')
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
