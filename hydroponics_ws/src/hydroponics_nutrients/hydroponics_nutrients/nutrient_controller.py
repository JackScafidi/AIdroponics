# MIT License
# Copyright (c) 2024 Claudroponics Project

"""ROS2 nutrient controller node with dual PID loops for pH and EC management."""

from __future__ import annotations

import time
from typing import Any

import rclpy
from rclpy.node import Node
from rclpy.callback_group import ReentrantCallbackGroup
from std_msgs.msg import Float32, Int32

from hydroponics_msgs.msg import (
    NutrientStatus,
    ChannelHealthSummary,
    SystemAlert,
)
from hydroponics_msgs.srv import ForceDose, SetGrowthStage, ResetCropCycle

from hydroponics_nutrients.pid import PIDController, PIDConfig


class NutrientController(Node):
    """Dual PID nutrient controller for pH and EC with growth stage management.

    Reads pH, EC, temperature from ESP32 ADC/OneWire via micro-ROS topics.
    Runs two independent PID loops at 1Hz. Handles growth stage transitions,
    deficiency response from vision, and water level safety.
    """

    # Pump IDs
    PUMP_PH_UP = 0
    PUMP_PH_DOWN = 1
    PUMP_NUTRIENT_A = 2
    PUMP_NUTRIENT_B = 3
    PUMP_NAMES = ['ph_up', 'ph_down', 'nutrient_a', 'nutrient_b']

    def __init__(self) -> None:
        super().__init__('nutrient_controller')
        self._cb_group = ReentrantCallbackGroup()

        # Declare parameters
        self._declare_parameters()

        # Load plant profile
        self._plant_profile: dict[str, Any] = {}
        self._growth_stage: str = 'seedling'
        self._days_since_planting: int = 0
        self._planting_time: float = time.time()
        self._a_b_ratio: float = 1.0

        # PID controllers
        ph_cfg = PIDConfig(
            kp=self.get_parameter('ph_pid.kp').value,
            ki=self.get_parameter('ph_pid.ki').value,
            kd=self.get_parameter('ph_pid.kd').value,
            dead_band=self.get_parameter('ph_pid.dead_band').value,
            integral_clamp=self.get_parameter('ph_pid.integral_clamp').value,
            output_min=self.get_parameter('ph_pid.output_min').value,
            output_max=self.get_parameter('ph_pid.output_max').value,
        )
        ec_cfg = PIDConfig(
            kp=self.get_parameter('ec_pid.kp').value,
            ki=self.get_parameter('ec_pid.ki').value,
            kd=self.get_parameter('ec_pid.kd').value,
            dead_band=self.get_parameter('ec_pid.dead_band').value,
            integral_clamp=self.get_parameter('ec_pid.integral_clamp').value,
            output_min=self.get_parameter('ec_pid.output_min').value,
            output_max=self.get_parameter('ec_pid.output_max').value,
        )
        self._ph_pid = PIDController(ph_cfg)
        self._ec_pid = PIDController(ec_cfg)

        # Set default targets (parsley seedling defaults)
        self._ph_target: float = 6.0
        self._ec_target: float = 0.8
        self._ph_pid.setpoint = self._ph_target
        self._ec_pid.setpoint = self._ec_target

        # Sensor readings
        self._current_ph: float = 7.0
        self._current_ec: float = 0.0
        self._current_temp: float = 20.0
        self._water_level_ok: bool = True

        # Pump state
        self._pump_active: list[bool] = [False, False, False, False]
        self._last_dose_time: float = 0.0
        self._mixing_wait: float = self.get_parameter('mixing_wait_seconds').value
        self._min_dose_ml: float = self.get_parameter('minimum_dose_ml').value

        # Pump flow rates (mL/s)
        self._flow_rates: dict[str, float] = {
            'ph_up': self.get_parameter('pump_flow_rates.ph_up').value,
            'ph_down': self.get_parameter('pump_flow_rates.ph_down').value,
            'nutrient_a': self.get_parameter('pump_flow_rates.nutrient_a').value,
            'nutrient_b': self.get_parameter('pump_flow_rates.nutrient_b').value,
        }

        # Deficiency response
        self._deficiency_threshold: float = self.get_parameter(
            'deficiency_prevalence_threshold').value

        # --- Subscribers ---
        self._sub_ph = self.create_subscription(
            Float32, 'ph_raw', self._ph_callback, 10,
            callback_group=self._cb_group)
        self._sub_ec = self.create_subscription(
            Float32, 'ec_raw', self._ec_callback, 10,
            callback_group=self._cb_group)
        self._sub_temp = self.create_subscription(
            Float32, 'temperature', self._temp_callback, 10,
            callback_group=self._cb_group)
        self._sub_water = self.create_subscription(
            Float32, 'water_level', self._water_callback, 10,
            callback_group=self._cb_group)
        self._sub_health = self.create_subscription(
            ChannelHealthSummary, 'channel_health_summary',
            self._health_callback, 10,
            callback_group=self._cb_group)

        # --- Publishers ---
        self._pub_status = self.create_publisher(NutrientStatus, 'nutrient_status', 10)
        self._pub_alert = self.create_publisher(SystemAlert, 'system_alert', 10)
        self._pub_pump = self.create_publisher(Int32, 'pump_cmd', 10)

        # --- Services ---
        self._srv_dose = self.create_service(
            ForceDose, 'force_dose', self._force_dose_callback,
            callback_group=self._cb_group)
        self._srv_stage = self.create_service(
            SetGrowthStage, 'set_growth_stage', self._set_stage_callback,
            callback_group=self._cb_group)
        self._srv_reset = self.create_service(
            ResetCropCycle, 'reset_crop_cycle', self._reset_cycle_callback,
            callback_group=self._cb_group)

        # --- Control loop timer ---
        control_rate = self.get_parameter('control_rate_hz').value
        period = 1.0 / control_rate
        self._control_timer = self.create_timer(
            period, self._control_loop, callback_group=self._cb_group)

        # --- Growth stage check timer (every 60s) ---
        self._stage_timer = self.create_timer(
            60.0, self._check_growth_stage, callback_group=self._cb_group)

        self.get_logger().info(
            f'Nutrient controller initialized — pH target: {self._ph_target}, '
            f'EC target: {self._ec_target}, stage: {self._growth_stage}')

    def _declare_parameters(self) -> None:
        """Declare all ROS2 parameters with defaults."""
        self.declare_parameter('ph_pid.kp', 2.0)
        self.declare_parameter('ph_pid.ki', 0.1)
        self.declare_parameter('ph_pid.kd', 0.5)
        self.declare_parameter('ph_pid.dead_band', 0.1)
        self.declare_parameter('ph_pid.integral_clamp', 10.0)
        self.declare_parameter('ph_pid.output_min', 0.0)
        self.declare_parameter('ph_pid.output_max', 5000.0)

        self.declare_parameter('ec_pid.kp', 3.0)
        self.declare_parameter('ec_pid.ki', 0.2)
        self.declare_parameter('ec_pid.kd', 0.3)
        self.declare_parameter('ec_pid.dead_band', 0.1)
        self.declare_parameter('ec_pid.integral_clamp', 10.0)
        self.declare_parameter('ec_pid.output_min', 0.0)
        self.declare_parameter('ec_pid.output_max', 5000.0)

        self.declare_parameter('pump_flow_rates.ph_up', 1.0)
        self.declare_parameter('pump_flow_rates.ph_down', 1.0)
        self.declare_parameter('pump_flow_rates.nutrient_a', 1.5)
        self.declare_parameter('pump_flow_rates.nutrient_b', 1.5)

        self.declare_parameter('minimum_dose_ml', 0.1)
        self.declare_parameter('mixing_wait_seconds', 60.0)
        self.declare_parameter('control_rate_hz', 1.0)
        self.declare_parameter('deficiency_prevalence_threshold', 0.5)
        self.declare_parameter('publish_rate_hz', 1.0)

    # --- Sensor callbacks ---

    def _ph_callback(self, msg: Float32) -> None:
        self._current_ph = msg.data

    def _ec_callback(self, msg: Float32) -> None:
        self._current_ec = msg.data

    def _temp_callback(self, msg: Float32) -> None:
        self._current_temp = msg.data

    def _water_callback(self, msg: Float32) -> None:
        self._water_level_ok = msg.data > 0.5

    def _health_callback(self, msg: ChannelHealthSummary) -> None:
        """Handle channel health summary from vision — adjust A/B ratio for deficiencies."""
        if msg.deficiency_prevalence > self._deficiency_threshold:
            deficiency = msg.primary_deficiency
            if deficiency != 'none':
                self.get_logger().warn(
                    f'Deficiency detected: {deficiency} '
                    f'(prevalence: {msg.deficiency_prevalence:.0%})')
                self._apply_deficiency_response(deficiency)

        if msg.diseased_count > 0:
            alert = SystemAlert()
            alert.header.stamp = self.get_clock().now().to_msg()
            alert.alert_type = 'disease'
            alert.severity = 'critical'
            alert.message = f'Disease detected in {msg.diseased_count} plants'
            alert.recommended_action = 'Pause operations and inspect manually'
            self._pub_alert.publish(alert)

    def _apply_deficiency_response(self, deficiency: str) -> None:
        """Adjust A/B ratio based on detected deficiency type."""
        # Default responses (can be overridden by plant profile)
        responses: dict[str, dict[str, float]] = {
            'nitrogen': {'a_b_ratio': 1.3, 'ec_boost': 0.2},
            'phosphorus': {'a_b_ratio': 0.7, 'ec_boost': 0.1},
            'potassium': {'a_b_ratio': 0.8, 'ec_boost': 0.15},
            'iron': {'a_b_ratio': 1.0, 'ec_boost': 0.1},
        }

        # Strip _deficiency suffix if present
        key = deficiency.replace('_deficiency', '')
        if key in responses:
            resp = responses[key]
            self._a_b_ratio = resp['a_b_ratio']
            self._ec_target += resp['ec_boost']
            self._ec_pid.setpoint = self._ec_target
            self.get_logger().info(
                f'Deficiency response: A/B ratio → {self._a_b_ratio}, '
                f'EC target → {self._ec_target}')

    # --- Control loop ---

    def _control_loop(self) -> None:
        """Main PID control loop running at control_rate_hz."""
        now = time.monotonic()

        # Safety: pause dosing if water level is low
        if not self._water_level_ok:
            self._publish_status()
            return

        # Check mixing wait period
        elapsed_since_dose = now - self._last_dose_time
        if elapsed_since_dose < self._mixing_wait:
            self.get_logger().debug(
                f'Mixing wait: {self._mixing_wait - elapsed_since_dose:.0f}s remaining')
            self._publish_status()
            return

        # pH PID
        ph_output = self._ph_pid.compute(self._current_ph, now)
        if ph_output > 0:
            self._dose_ph(ph_output)

        # EC PID
        ec_output = self._ec_pid.compute(self._current_ec, now)
        if ec_output > 0:
            self._dose_ec(ec_output)

        # Publish status
        self._publish_status()

    def _dose_ph(self, pid_output_ms: float) -> None:
        """Convert PID output to pump command for pH adjustment."""
        error = self._ph_target - self._current_ph

        if error > 0:
            # pH too low, need pH up
            pump_name = 'ph_up'
            pump_id = self.PUMP_PH_UP
        else:
            # pH too high, need pH down
            pump_name = 'ph_down'
            pump_id = self.PUMP_PH_DOWN

        dose_ml = (pid_output_ms / 1000.0) * self._flow_rates[pump_name]
        if dose_ml < self._min_dose_ml:
            return

        self.get_logger().info(
            f'pH dose: {pump_name} {dose_ml:.2f} mL '
            f'(pH={self._current_ph:.2f}, target={self._ph_target:.2f})')

        self._send_pump_cmd(pump_id, int(pid_output_ms))
        self._last_dose_time = time.monotonic()

    def _dose_ec(self, pid_output_ms: float) -> None:
        """Convert PID output to pump commands for EC adjustment (A+B nutrients)."""
        dose_a_ms = pid_output_ms * self._a_b_ratio / (1.0 + self._a_b_ratio)
        dose_b_ms = pid_output_ms / (1.0 + self._a_b_ratio)

        dose_a_ml = (dose_a_ms / 1000.0) * self._flow_rates['nutrient_a']
        dose_b_ml = (dose_b_ms / 1000.0) * self._flow_rates['nutrient_b']

        if dose_a_ml < self._min_dose_ml and dose_b_ml < self._min_dose_ml:
            return

        self.get_logger().info(
            f'EC dose: A={dose_a_ml:.2f}mL B={dose_b_ml:.2f}mL '
            f'(EC={self._current_ec:.2f}, target={self._ec_target:.2f}, '
            f'A/B={self._a_b_ratio:.2f})')

        if dose_a_ml >= self._min_dose_ml:
            self._send_pump_cmd(self.PUMP_NUTRIENT_A, int(dose_a_ms))
        if dose_b_ml >= self._min_dose_ml:
            self._send_pump_cmd(self.PUMP_NUTRIENT_B, int(dose_b_ms))

        self._last_dose_time = time.monotonic()

    def _send_pump_cmd(self, pump_id: int, duration_ms: int) -> None:
        """Send pump command to ESP32. Encodes pump_id and duration."""
        # Encoding: pump_id * 100000 + duration_ms
        msg = Int32()
        msg.data = pump_id * 100000 + duration_ms
        self._pub_pump.publish(msg)
        self._pump_active[pump_id] = True

    # --- Growth stage management ---

    def _check_growth_stage(self) -> None:
        """Check if growth stage should transition based on days since planting."""
        self._days_since_planting = int(
            (time.time() - self._planting_time) / 86400)

        # Stage transitions would be driven by plant profile day ranges
        # For default parsley: seedling 0-14, vegetative 15-40, mature 41+
        new_stage = self._growth_stage
        if self._days_since_planting <= 14:
            new_stage = 'seedling'
        elif self._days_since_planting <= 40:
            new_stage = 'vegetative'
        else:
            new_stage = 'mature'

        if new_stage != self._growth_stage:
            old_stage = self._growth_stage
            self._growth_stage = new_stage
            self._update_targets_for_stage()
            self.get_logger().info(
                f'Growth stage transition: {old_stage} → {new_stage} '
                f'(day {self._days_since_planting})')

    def _update_targets_for_stage(self) -> None:
        """Update pH/EC targets and A/B ratio based on current growth stage."""
        # Default parsley targets by stage
        stage_targets: dict[str, dict[str, float]] = {
            'seedling': {'ph': 6.0, 'ec': 0.8, 'a_b': 1.0},
            'vegetative': {'ph': 6.0, 'ec': 1.2, 'a_b': 1.0},
            'mature': {'ph': 6.0, 'ec': 1.4, 'a_b': 1.0},
        }
        targets = stage_targets.get(self._growth_stage, stage_targets['vegetative'])
        self._ph_target = targets['ph']
        self._ec_target = targets['ec']
        self._a_b_ratio = targets['a_b']
        self._ph_pid.setpoint = self._ph_target
        self._ec_pid.setpoint = self._ec_target

    # --- Status publishing ---

    def _publish_status(self) -> None:
        """Publish current nutrient controller status."""
        msg = NutrientStatus()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.ph_current = self._current_ph
        msg.ec_current = self._current_ec
        msg.temperature_c = self._current_temp
        msg.ph_target = self._ph_target
        msg.ec_target = self._ec_target
        msg.ph_pid_output = self._ph_pid.compute(self._current_ph)
        msg.ec_pid_output = self._ec_pid.compute(self._current_ec)
        msg.a_b_ratio = self._a_b_ratio
        msg.growth_stage = self._growth_stage
        msg.days_since_planting = self._days_since_planting
        msg.pump_active = self._pump_active
        self._pub_status.publish(msg)

        # Reset pump active flags
        self._pump_active = [False, False, False, False]

    # --- Service callbacks ---

    def _force_dose_callback(
        self, request: ForceDose.Request, response: ForceDose.Response
    ) -> ForceDose.Response:
        """Handle manual force dose request."""
        pump_names = {name: idx for idx, name in enumerate(self.PUMP_NAMES)}
        if request.pump_id not in pump_names:
            response.success = False
            self.get_logger().warn(f'Invalid pump_id: {request.pump_id}')
            return response

        pump_idx = pump_names[request.pump_id]
        flow_rate = self._flow_rates[request.pump_id]
        duration_ms = int((request.amount_ml / flow_rate) * 1000)

        self.get_logger().info(
            f'Force dose: {request.pump_id} {request.amount_ml:.2f}mL '
            f'({duration_ms}ms)')
        self._send_pump_cmd(pump_idx, duration_ms)
        self._last_dose_time = time.monotonic()
        response.success = True
        return response

    def _set_stage_callback(
        self, request: SetGrowthStage.Request, response: SetGrowthStage.Response
    ) -> SetGrowthStage.Response:
        """Handle manual growth stage override."""
        valid_stages = {'seedling', 'vegetative', 'mature'}
        if request.stage not in valid_stages:
            response.success = False
            response.previous_stage = self._growth_stage
            return response

        response.previous_stage = self._growth_stage
        self._growth_stage = request.stage
        self._update_targets_for_stage()
        response.success = True
        self.get_logger().info(
            f'Growth stage manually set: {response.previous_stage} → {request.stage}')
        return response

    def _reset_cycle_callback(
        self, request: ResetCropCycle.Request, response: ResetCropCycle.Response
    ) -> ResetCropCycle.Response:
        """Reset crop cycle — resets planting time and growth stage."""
        self._planting_time = time.time()
        self._days_since_planting = 0
        self._growth_stage = 'seedling'
        self._a_b_ratio = 1.0
        self._update_targets_for_stage()
        self._ph_pid.reset()
        self._ec_pid.reset()
        response.success = True
        self.get_logger().info('Crop cycle reset — stage=seedling, day=0')
        return response


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = NutrientController()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
