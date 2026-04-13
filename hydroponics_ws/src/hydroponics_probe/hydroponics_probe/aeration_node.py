# MIT License
# Copyright (c) 2026 Autoponics Project

"""ROS2 aeration cycle node for Autoponics V0.1 single-plant platform.

Purpose
-------
Controls a servo-driven mechanism that lowers an airstone into the nutrient
solution, runs the air pump for a configurable duration, then retracts the
airstone. Single fixed bin position.

Subscriptions
-------------
None at steady state. The node self-triggers on a timer.

Publications
------------
None. (Future: could publish AerationEvent for data logging.)

Services provided
-----------------
/aeration/trigger  (hydroponics_msgs/srv/TriggerAeration) — on-demand cycle

Parameters
----------
All loaded from v01_system.yaml under the 'aeration' key:
  cycle_duration_seconds  — how long air pump runs per cycle
  cycle_interval_seconds  — period between automatic cycles
  servo_channel           — ESP32 servo channel for airstone arm
  servo_submerged_angle   — angle when airstone is submerged
  servo_retracted_angle   — angle when airstone is retracted
  air_pump_gpio_pin       — GPIO pin for air pump relay
"""

from __future__ import annotations

import time
from typing import Optional

import rclpy
from rclpy.node import Node
from rclpy.callback_group import ReentrantCallbackGroup
from std_msgs.msg import Int32, Bool

from hydroponics_msgs.srv import TriggerAeration


class AerationNode(Node):
    """Airstone servo and air pump controller for single-bin V0.1 operation."""

    def __init__(self) -> None:
        super().__init__('aeration_node')
        self._cb_group = ReentrantCallbackGroup()

        # --- Parameters ---
        self.declare_parameter('aeration.cycle_duration_seconds', 600.0)
        self.declare_parameter('aeration.cycle_interval_seconds', 1800.0)
        self.declare_parameter('aeration.servo_channel', 1)
        self.declare_parameter('aeration.servo_submerged_angle', 90)
        self.declare_parameter('aeration.servo_retracted_angle', 0)
        self.declare_parameter('aeration.air_pump_gpio_pin', 17)

        self._cycle_duration: float = (
            self.get_parameter('aeration.cycle_duration_seconds')
            .get_parameter_value().double_value
        )
        self._cycle_interval: float = (
            self.get_parameter('aeration.cycle_interval_seconds')
            .get_parameter_value().double_value
        )
        self._servo_channel: int = (
            self.get_parameter('aeration.servo_channel')
            .get_parameter_value().integer_value
        )
        self._servo_submerged_angle: int = (
            self.get_parameter('aeration.servo_submerged_angle')
            .get_parameter_value().integer_value
        )
        self._servo_retracted_angle: int = (
            self.get_parameter('aeration.servo_retracted_angle')
            .get_parameter_value().integer_value
        )
        self._air_pump_gpio_pin: int = (
            self.get_parameter('aeration.air_pump_gpio_pin')
            .get_parameter_value().integer_value
        )

        # Guard against concurrent cycles
        self._cycle_running: bool = False

        # --- Publishers ---
        # Servo command to ESP32 (channel * 1000 + angle)
        self._pub_servo = self.create_publisher(Int32, '/servo_cmd_raw', 10)
        # Air pump GPIO control (True = on, False = off)
        self._pub_pump = self.create_publisher(Bool, '/air_pump_cmd', 10)

        # --- Services ---
        self._srv_trigger = self.create_service(
            TriggerAeration, '/aeration/trigger', self._handle_trigger,
            callback_group=self._cb_group
        )

        # --- Aeration cycle timer ---
        self._aeration_timer = self.create_timer(
            self._cycle_interval, self._run_aeration_cycle,
            callback_group=self._cb_group
        )

        self.get_logger().info(
            f'AerationNode ready — interval={self._cycle_interval}s, '
            f'duration={self._cycle_duration}s, '
            f'servo_channel={self._servo_channel}, '
            f'air_pump_gpio={self._air_pump_gpio_pin}'
        )

    # -------------------------------------------------------------------------
    # Core aeration cycle
    # -------------------------------------------------------------------------

    def _run_aeration_cycle(self) -> None:
        """Execute one aeration cycle: submerge airstone → run pump → retract."""
        if self._cycle_running:
            self.get_logger().warn(
                'Aeration cycle requested but previous cycle still running — skipping'
            )
            return

        self._cycle_running = True
        self.get_logger().info('Aeration cycle starting')

        try:
            self._set_servo(self._servo_submerged_angle)
            self.get_logger().info(
                f'Airstone submerged (angle={self._servo_submerged_angle}). '
                f'Air pump ON for {self._cycle_duration}s.'
            )

            self._set_pump(on=True)
            time.sleep(self._cycle_duration)
            self._set_pump(on=False)

            self._set_servo(self._servo_retracted_angle)
            self.get_logger().info('Aeration cycle complete — airstone retracted, pump OFF')

        except Exception as exc:
            self.get_logger().error(f'Aeration cycle failed: {exc}')
            try:
                self._set_pump(on=False)
                self._set_servo(self._servo_retracted_angle)
            except Exception:
                pass
        finally:
            self._cycle_running = False

    # -------------------------------------------------------------------------
    # Service handler
    # -------------------------------------------------------------------------

    def _handle_trigger(
        self,
        request: TriggerAeration.Request,
        response: TriggerAeration.Response,
    ) -> TriggerAeration.Response:
        """Handle on-demand aeration cycle request."""
        self.get_logger().info('/aeration/trigger received — running on-demand cycle')
        try:
            self._run_aeration_cycle()
            response.success = True
            response.message = 'Aeration cycle completed successfully'
        except Exception as exc:
            self.get_logger().error(f'On-demand aeration cycle failed: {exc}')
            response.success = False
            response.message = str(exc)
        return response

    # -------------------------------------------------------------------------
    # Hardware helpers
    # -------------------------------------------------------------------------

    def _set_servo(self, angle: int) -> None:
        """Send servo position command to ESP32.

        Args:
            angle: Target servo angle in degrees.
        """
        msg = Int32()
        msg.data = self._servo_channel * 1000 + angle
        self._pub_servo.publish(msg)

    def _set_pump(self, on: bool) -> None:
        """Send air pump on/off command.

        Args:
            on: True to turn pump on, False to turn off.
        """
        msg = Bool()
        msg.data = on
        self._pub_pump.publish(msg)


def main(args: Optional[list[str]] = None) -> None:
    """Initialise rclpy, spin the AerationNode, and shut down cleanly."""
    rclpy.init(args=args)
    node = AerationNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info('AerationNode interrupted')
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
