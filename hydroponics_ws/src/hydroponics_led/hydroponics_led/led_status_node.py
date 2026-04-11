# MIT License
# Copyright (c) 2026 AIdroponics Project

"""ROS2 LED status indicator node for AIdroponics V0.1.

Purpose
-------
Subscribes to /bin/status and drives a GPIO-connected RGB LED to indicate
plant health. Simple GPIO writes — no PWM or animation.

Status mapping
--------------
  GREEN  — severity info    (plant healthy, all parameters in range)
  YELLOW — severity warning (drifting or NDVI declining)
  RED    — severity critical (intervention needed or dosing lockout)
  BLUE   — analysis in progress (probe cycle or vision capture active)

Subscriptions
-------------
/bin/status  (hydroponics_msgs/PlantStatus)

Publications
------------
/led/state  (std_msgs/String) — current LED colour string (for dashboard)

Parameters
----------
All loaded from v01_system.yaml under the 'led' key:
  led.gpio_red, led.gpio_green, led.gpio_blue
  led.active_high
"""

from __future__ import annotations

from typing import Optional

import rclpy
from rclpy.node import Node
from rclpy.callback_group import ReentrantCallbackGroup
from std_msgs.msg import String

from hydroponics_msgs.msg import PlantStatus

# PlantStatus severity codes (mirror diagnostics node constants)
SEVERITY_INFO = 0
SEVERITY_WARNING = 1
SEVERITY_CRITICAL = 2

# LED colour definitions: (red_on, green_on, blue_on)
LED_GREEN = (False, True, False)
LED_YELLOW = (True, True, False)
LED_RED = (True, False, False)
LED_BLUE = (False, False, True)
LED_OFF = (False, False, False)


class LedStatusNode(Node):
    """GPIO LED driver that maps PlantStatus severity to a colour."""

    def __init__(self) -> None:
        super().__init__('led_status_node')
        self._cb_group = ReentrantCallbackGroup()

        # --- Parameters ---
        self.declare_parameter('led.gpio_red', 5)
        self.declare_parameter('led.gpio_green', 6)
        self.declare_parameter('led.gpio_blue', 13)
        self.declare_parameter('led.active_high', True)

        self._gpio_red: int = (
            self.get_parameter('led.gpio_red').get_parameter_value().integer_value
        )
        self._gpio_green: int = (
            self.get_parameter('led.gpio_green').get_parameter_value().integer_value
        )
        self._gpio_blue: int = (
            self.get_parameter('led.gpio_blue').get_parameter_value().integer_value
        )
        self._active_high: bool = (
            self.get_parameter('led.active_high').get_parameter_value().bool_value
        )

        # --- GPIO initialisation ---
        # Attempt to import RPi.GPIO; fall back gracefully on non-Pi hardware
        self._gpio_available: bool = False
        try:
            import RPi.GPIO as GPIO
            self._GPIO = GPIO
            GPIO.setmode(GPIO.BCM)
            for pin in (self._gpio_red, self._gpio_green, self._gpio_blue):
                GPIO.setup(pin, GPIO.OUT)
                GPIO.output(pin, not self._active_high)  # start off
            self._gpio_available = True
            self.get_logger().info('RPi.GPIO initialised successfully')
        except ImportError:
            self.get_logger().warn(
                'RPi.GPIO not available — LED control will be simulated (log only)'
            )
        except Exception as exc:
            self.get_logger().warn(f'GPIO init failed: {exc} — LED control simulated')

        self._current_colour: str = 'off'

        # --- Publisher (LED state for dashboard) ---
        self._pub_led_state = self.create_publisher(String, '/led/state', 10)

        # --- Subscriber ---
        self._sub_status = self.create_subscription(
            PlantStatus, '/bin/status', self._on_bin_status, 10,
            callback_group=self._cb_group
        )

        # Set initial LED colour to GREEN (no data yet — assume safe)
        self._set_led(LED_GREEN, 'green')

        self.get_logger().info(
            f'LedStatusNode ready — pins: R={self._gpio_red} G={self._gpio_green} '
            f'B={self._gpio_blue}, active_high={self._active_high}'
        )

    # -------------------------------------------------------------------------
    # Status callback
    # -------------------------------------------------------------------------

    def _on_bin_status(self, msg: PlantStatus) -> None:
        """Map severity code to LED colour and actuate.

        Args:
            msg: PlantStatus message from /bin/status.
        """
        severity = msg.status_code

        if severity == SEVERITY_INFO:
            self._set_led(LED_GREEN, 'green')
        elif severity == SEVERITY_WARNING:
            self._set_led(LED_YELLOW, 'yellow')
        elif severity == SEVERITY_CRITICAL:
            self._set_led(LED_RED, 'red')
        else:
            self.get_logger().warn(f'Unknown status_code {severity} — setting RED')
            self._set_led(LED_RED, 'red')

    # -------------------------------------------------------------------------
    # GPIO helpers
    # -------------------------------------------------------------------------

    def _set_led(self, colour_tuple: tuple[bool, bool, bool], colour_name: str) -> None:
        """Write GPIO pins to display the given colour.

        Args:
            colour_tuple: (red_on, green_on, blue_on) booleans.
            colour_name: Human-readable colour name for logging.
        """
        if colour_name == self._current_colour:
            return  # No change

        red_on, green_on, blue_on = colour_tuple
        self._write_pin(self._gpio_red, red_on)
        self._write_pin(self._gpio_green, green_on)
        self._write_pin(self._gpio_blue, blue_on)

        self._current_colour = colour_name
        self.get_logger().info(f'LED → {colour_name.upper()}')

        state_msg = String()
        state_msg.data = colour_name
        self._pub_led_state.publish(state_msg)

    def _write_pin(self, pin: int, on: bool) -> None:
        """Write a single GPIO pin.

        Args:
            pin: BCM GPIO pin number.
            on: True to turn on, False to turn off.
        """
        if self._gpio_available:
            value = on if self._active_high else not on
            self._GPIO.output(pin, value)

    def destroy_node(self) -> None:
        """Clean up GPIO on shutdown."""
        if self._gpio_available:
            try:
                self._write_pin(self._gpio_red, False)
                self._write_pin(self._gpio_green, False)
                self._write_pin(self._gpio_blue, False)
                self._GPIO.cleanup()
            except Exception:
                pass
        super().destroy_node()


def main(args: Optional[list[str]] = None) -> None:
    """Initialise rclpy, spin the LedStatusNode, and shut down cleanly."""
    rclpy.init(args=args)
    node = LedStatusNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info('LedStatusNode interrupted')
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
