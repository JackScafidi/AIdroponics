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

"""mock_esp32.py — Simulated ESP32 micro-ROS node for hardware-free testing.

Publishes realistic sensor values with small random noise and responds to
pump/light/stepper commands by updating internal simulated state.
"""

import json
import math
import random
import time
from typing import List

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy

from std_msgs.msg import String
from hydroponics_msgs.msg import TransportStatus


class MockEsp32Node(Node):
    """Simulates the ESP32 sensor/actuator interface for hardware-free testing."""

    def __init__(self) -> None:
        super().__init__("mock_esp32_node")

        # Parameters
        self.declare_parameter("initial_ph", 6.2)
        self.declare_parameter("initial_ec", 1.8)
        self.declare_parameter("initial_temp_c", 22.5)
        self.declare_parameter("noise_enabled", True)

        self._ph       = float(self.get_parameter("initial_ph").value)
        self._ec       = float(self.get_parameter("initial_ec").value)
        self._temp     = float(self.get_parameter("initial_temp_c").value)
        self._noise    = bool(self.get_parameter("noise_enabled").value)
        self._water_ok = True

        # Simulated hardware state
        self._grow_intensity: int = 0
        self._inspection_on: bool = False
        self._pump_active: List[bool] = [False, False, False, False]
        self._pump_end_times: List[float] = [0.0, 0.0, 0.0, 0.0]
        self._rail_pos_mm: float = 0.0
        self._z_pos_mm: float = 0.0
        self._rail_moving: bool = False
        self._z_moving: bool = False
        self._rail_target_mm: float = 0.0
        self._z_target_mm: float = 0.0
        self._rail_move_start: float = 0.0
        self._move_speed_mm_s: float = 50.0

        sensor_qos = QoSProfile(reliability=ReliabilityPolicy.BEST_EFFORT, depth=5)
        reliable_qos = QoSProfile(reliability=ReliabilityPolicy.RELIABLE, depth=10)

        # Publisher: sensor telemetry
        self._sensor_pub = self.create_publisher(
            String, "/hydroponics/esp32/sensors", sensor_qos)

        # Publisher: transport status
        self._transport_pub = self.create_publisher(
            TransportStatus, "/hydroponics/transport_status", sensor_qos)

        # Subscriptions: hardware commands
        self.create_subscription(
            String, "/hydroponics/esp32/pump_cmd",
            self._on_pump_cmd, reliable_qos)
        self.create_subscription(
            String, "/hydroponics/esp32/light_cmd",
            self._on_light_cmd, reliable_qos)
        self.create_subscription(
            String, "/hydroponics/esp32/stepper_cmd",
            self._on_stepper_cmd, reliable_qos)

        # Publish at 1 Hz
        self.create_timer(1.0, self._publish_sensors)
        # Simulate slow drift every 10 s
        self.create_timer(10.0, self._drift_sensors)
        # Update simulated motion at 10 Hz
        self.create_timer(0.1, self._update_motion)

        self.get_logger().info(
            f"MockEsp32Node started — pH={self._ph:.2f}, EC={self._ec:.2f}, "
            f"T={self._temp:.1f}°C, noise={'on' if self._noise else 'off'}"
        )

    # ---------------------------------------------------------------------- #
    # Sensor simulation
    # ---------------------------------------------------------------------- #

    def _noise_val(self, scale: float) -> float:
        return random.gauss(0, scale) if self._noise else 0.0

    def _drift_sensors(self) -> None:
        """Slowly drift pH and EC to simulate real nutrient consumption."""
        self._ph  += random.gauss(-0.02, 0.01)   # pH tends to drift down
        self._ec  += random.gauss(-0.01, 0.005)  # EC decreases as plants absorb
        self._temp += random.gauss(0.0, 0.05)
        # Clamp to physically plausible ranges
        self._ph   = max(4.5, min(8.5, self._ph))
        self._ec   = max(0.2, min(4.0, self._ec))
        self._temp = max(15.0, min(32.0, self._temp))

    def _publish_sensors(self) -> None:
        """Publish current simulated sensor state as JSON."""
        now = time.time()
        # Update pump active states
        for i in range(4):
            if self._pump_active[i] and now >= self._pump_end_times[i]:
                self._pump_active[i] = False

        data = {
            "ph":           round(self._ph + self._noise_val(0.02), 3),
            "ec":           round(self._ec + self._noise_val(0.01), 3),
            "temp_c":       round(self._temp + self._noise_val(0.05), 2),
            "water_level_ok": self._water_ok,
            "rail_pos_mm":  round(self._rail_pos_mm, 1),
            "z_pos_mm":     round(self._z_pos_mm, 1),
            "rail_moving":  self._rail_moving,
            "z_moving":     self._z_moving,
            "grow_intensity": self._grow_intensity,
            "inspection_on": self._inspection_on,
            "pump_active":  self._pump_active.copy(),
        }
        msg = String()
        msg.data = json.dumps(data)
        self._sensor_pub.publish(msg)

        # Also publish TransportStatus
        ts = TransportStatus()
        ts.header.stamp = self.get_clock().now().to_msg()
        ts.position_mm  = self._rail_pos_mm
        ts.is_moving    = self._rail_moving
        ts.velocity_mm_s = self._move_speed_mm_s if self._rail_moving else 0.0
        self._transport_pub.publish(ts)

    # ---------------------------------------------------------------------- #
    # Motion simulation
    # ---------------------------------------------------------------------- #

    def _update_motion(self) -> None:
        """Move simulated axes toward their targets at 50 mm/s."""
        dt = 0.1
        if self._rail_moving:
            step = self._move_speed_mm_s * dt
            diff = self._rail_target_mm - self._rail_pos_mm
            if abs(diff) <= step:
                self._rail_pos_mm = self._rail_target_mm
                self._rail_moving = False
            else:
                self._rail_pos_mm += math.copysign(step, diff)

        if self._z_moving:
            step = (self._move_speed_mm_s / 2) * dt
            diff = self._z_target_mm - self._z_pos_mm
            if abs(diff) <= step:
                self._z_pos_mm = self._z_target_mm
                self._z_moving = False
            else:
                self._z_pos_mm += math.copysign(step, diff)

    # ---------------------------------------------------------------------- #
    # Command callbacks
    # ---------------------------------------------------------------------- #

    def _on_pump_cmd(self, msg: String) -> None:
        try:
            payload = json.loads(msg.data)
        except json.JSONDecodeError:
            return

        pump_id    = int(payload.get("pump_id", -1))
        duration   = float(payload.get("duration_ms", 0)) / 1000.0
        amount_ml  = float(payload.get("amount_ml", -1.0))
        flow_rate  = 1.0  # mL/s default

        if pump_id < 0 or pump_id >= 4:
            return

        if amount_ml > 0:
            duration = amount_ml / flow_rate

        if duration > 0:
            self._pump_active[pump_id]    = True
            self._pump_end_times[pump_id] = time.time() + duration

            # Simulate pH/EC response after dosing
            self._simulate_dose_effect(pump_id, amount_ml if amount_ml > 0 else duration * flow_rate)

            self.get_logger().info(
                f"[mock_esp32] Pump {pump_id} dosed for {duration:.1f}s "
                f"(≈{duration * flow_rate:.1f} mL)"
            )

    def _simulate_dose_effect(self, pump_id: int, ml: float) -> None:
        """Crudely simulate sensor changes after a pump dose."""
        effect = ml * 0.05
        if pump_id == 0:   # pH up
            self._ph = min(8.5, self._ph + effect * 0.3)
        elif pump_id == 1: # pH down
            self._ph = max(4.5, self._ph - effect * 0.3)
        elif pump_id == 2: # nutrient A
            self._ec = min(4.0, self._ec + effect * 0.1)
        elif pump_id == 3: # nutrient B
            self._ec = min(4.0, self._ec + effect * 0.1)

    def _on_light_cmd(self, msg: String) -> None:
        try:
            payload = json.loads(msg.data)
        except json.JSONDecodeError:
            return

        if "grow_intensity" in payload:
            self._grow_intensity = max(0, min(100, int(payload["grow_intensity"])))
            self.get_logger().info(f"[mock_esp32] Grow intensity → {self._grow_intensity}%")

        if "inspection_on" in payload:
            self._inspection_on = bool(payload["inspection_on"])
            self.get_logger().info(
                f"[mock_esp32] Inspection light → {'ON' if self._inspection_on else 'OFF'}")

    def _on_stepper_cmd(self, msg: String) -> None:
        try:
            payload = json.loads(msg.data)
        except json.JSONDecodeError:
            return

        target_mm = float(payload.get("target_mm", -1.0))
        if target_mm < 0:
            return

        axis = str(payload.get("axis", "rail"))
        if axis == "rail":
            self._rail_target_mm = target_mm
            self._rail_moving    = True
            self.get_logger().info(
                f"[mock_esp32] Rail → {target_mm:.1f} mm "
                f"(current={self._rail_pos_mm:.1f})"
            )
        elif axis == "z":
            self._z_target_mm = target_mm
            self._z_moving    = True
            self.get_logger().info(
                f"[mock_esp32] Z → {target_mm:.1f} mm (current={self._z_pos_mm:.1f})")


def main(args=None) -> None:
    rclpy.init(args=args)
    node = MockEsp32Node()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
