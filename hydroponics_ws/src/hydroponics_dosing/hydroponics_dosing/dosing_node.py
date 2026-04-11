# MIT License
# Copyright (c) 2026 AIdroponics Project

"""ROS2 auto-dosing node for AIdroponics V0.1 single-plant platform.

Purpose
-------
Closes the loop between probe readings and nutrient/pH adjustment using
explicit chemistry calculations (not PID). Doses pH-first, then nutrients
A+B, with verify-after-dose loops and mandatory safety scaffolding.

Subscriptions
-------------
/probe/reading      (hydroponics_msgs/ProbeReading)
/water/level        (hydroponics_msgs/WaterLevel)
/water/topoff_event (hydroponics_msgs/TopOffEvent)

Publications
------------
/dosing/event  (hydroponics_msgs/DosingEvent)
/dosing/error  (std_msgs/String)

Services called
---------------
/probe/trigger  (hydroponics_msgs/srv/TriggerProbe)

Parameters
----------
All loaded from v01_system.yaml under the 'dosing' key, plus plant library
thresholds injected at launch as parameters:
  plant_ph_ideal_min, plant_ph_ideal_max
  plant_ec_ideal_min, plant_ec_ideal_max
  plant_nutrient_ab_ratio

Dosing chemistry math
---------------------
pH dose (linear approximation, conservative — safe to undershoot):
  dose_mL = |pH_error| × volume_L × (1.0 / adjuster_molarity)
  capped at max_dose_mL

EC dose (linear, reliable in hydroponics concentration range):
  total_dose_mL = ec_deficit /
    ((nutrient_a_ec_per_mL_per_L + nutrient_b_ec_per_mL_per_L / ab_ratio)
     / current_volume_L)
  split by A:B ratio, each capped at max_dose_mL
"""

from __future__ import annotations

import time
from typing import Optional
from collections import deque

import rclpy
from rclpy.node import Node
from rclpy.callback_group import ReentrantCallbackGroup
from std_msgs.msg import Int32, String

from hydroponics_msgs.msg import ProbeReading, DosingEvent, WaterLevel, TopOffEvent
from hydroponics_msgs.srv import TriggerProbe


# Pump identifiers
PUMP_PH_DOWN = 'ph_down'
PUMP_PH_UP = 'ph_up'
PUMP_NUTRIENT_A = 'nutrient_a'
PUMP_NUTRIENT_B = 'nutrient_b'


class DosingNode(Node):
    """Explicit-chemistry auto-dosing node with full safety scaffolding."""

    def __init__(self) -> None:
        super().__init__('dosing_node')
        self._cb_group = ReentrantCallbackGroup()

        # --- Parameters ---
        self.declare_parameter('dosing.ph_down_molarity', 1.0)
        self.declare_parameter('dosing.ph_up_molarity', 1.0)
        self.declare_parameter('dosing.nutrient_a_ec_per_mL_per_L', 0.5)
        self.declare_parameter('dosing.nutrient_b_ec_per_mL_per_L', 0.5)
        self.declare_parameter('dosing.nutrient_ab_ratio', 1.0)
        self.declare_parameter('dosing.mL_per_second_ph_down', 1.0)
        self.declare_parameter('dosing.mL_per_second_ph_up', 1.0)
        self.declare_parameter('dosing.mL_per_second_nutrient_a', 1.0)
        self.declare_parameter('dosing.mL_per_second_nutrient_b', 1.0)
        self.declare_parameter('dosing.max_dose_mL', 5.0)
        self.declare_parameter('dosing.min_dose_interval_seconds', 300.0)
        self.declare_parameter('dosing.max_doses_per_hour', 8)
        self.declare_parameter('dosing.emergency_lockout_threshold', 3)
        self.declare_parameter('dosing.ph_mixing_wait_seconds', 90.0)
        self.declare_parameter('dosing.nutrient_mixing_wait_seconds', 90.0)
        self.declare_parameter('bin.cross_section_cm2', 900.0)

        # Plant thresholds (injected by launch file from plant_library.yaml)
        self.declare_parameter('plant_ph_ideal_min', 5.5)
        self.declare_parameter('plant_ph_ideal_max', 6.5)
        self.declare_parameter('plant_ec_ideal_min', 1.0)
        self.declare_parameter('plant_ec_ideal_max', 1.6)
        self.declare_parameter('plant_nutrient_ab_ratio', 1.0)

        def get_float(name: str) -> float:
            return self.get_parameter(name).get_parameter_value().double_value

        def get_int(name: str) -> int:
            return self.get_parameter(name).get_parameter_value().integer_value

        self._ph_down_molarity: float = get_float('dosing.ph_down_molarity')
        self._ph_up_molarity: float = get_float('dosing.ph_up_molarity')
        self._nutrient_a_ec_per_mL_per_L: float = get_float('dosing.nutrient_a_ec_per_mL_per_L')
        self._nutrient_b_ec_per_mL_per_L: float = get_float('dosing.nutrient_b_ec_per_mL_per_L')
        self._default_ab_ratio: float = get_float('dosing.nutrient_ab_ratio')
        self._flow_rates: dict[str, float] = {
            PUMP_PH_DOWN: get_float('dosing.mL_per_second_ph_down'),
            PUMP_PH_UP: get_float('dosing.mL_per_second_ph_up'),
            PUMP_NUTRIENT_A: get_float('dosing.mL_per_second_nutrient_a'),
            PUMP_NUTRIENT_B: get_float('dosing.mL_per_second_nutrient_b'),
        }
        self._max_dose_mL: float = get_float('dosing.max_dose_mL')
        self._min_dose_interval: float = get_float('dosing.min_dose_interval_seconds')
        self._max_doses_per_hour: int = get_int('dosing.max_doses_per_hour')
        self._emergency_lockout_threshold: int = get_int('dosing.emergency_lockout_threshold')
        self._ph_mixing_wait: float = get_float('dosing.ph_mixing_wait_seconds')
        self._nutrient_mixing_wait: float = get_float('dosing.nutrient_mixing_wait_seconds')
        self._bin_cross_section_cm2: float = get_float('bin.cross_section_cm2')

        self._ph_ideal_min: float = get_float('plant_ph_ideal_min')
        self._ph_ideal_max: float = get_float('plant_ph_ideal_max')
        self._ec_ideal_min: float = get_float('plant_ec_ideal_min')
        self._ec_ideal_max: float = get_float('plant_ec_ideal_max')
        # Active A:B ratio — plant library value takes precedence over config default
        self._ab_ratio: float = get_float('plant_nutrient_ab_ratio')
        if self._ab_ratio <= 0:
            self._ab_ratio = self._default_ab_ratio

        # --- State ---
        self._current_water_level_cm: float = 20.0  # default until first reading
        self._last_dose_times: dict[str, float] = {p: 0.0 for p in [
            PUMP_PH_DOWN, PUMP_PH_UP, PUMP_NUTRIENT_A, PUMP_NUTRIENT_B
        ]}
        # Sliding window of dose event timestamps for max_doses_per_hour check
        self._dose_event_timestamps: deque = deque()
        self._consecutive_failed_verify: int = 0
        self._emergency_lockout: bool = False
        self._topoff_pending_probe: bool = False

        # --- Publishers ---
        self._pub_dosing_event = self.create_publisher(DosingEvent, '/dosing/event', 10)
        self._pub_error = self.create_publisher(String, '/dosing/error', 10)
        # Pump command (pump_id encoding: see _actuate_pump)
        self._pub_pump = self.create_publisher(Int32, 'pump_cmd', 10)

        # --- Subscribers ---
        self._sub_probe = self.create_subscription(
            ProbeReading, '/probe/reading', self._on_probe_reading, 10,
            callback_group=self._cb_group
        )
        self._sub_water_level = self.create_subscription(
            WaterLevel, '/water/level', self._on_water_level, 10,
            callback_group=self._cb_group
        )
        self._sub_topoff = self.create_subscription(
            TopOffEvent, '/water/topoff_event', self._on_topoff_event, 10,
            callback_group=self._cb_group
        )

        # --- Service client ---
        self._probe_trigger_client = self.create_client(TriggerProbe, '/probe/trigger')

        self.get_logger().info(
            f'DosingNode ready — '
            f'pH ideal=[{self._ph_ideal_min}, {self._ph_ideal_max}], '
            f'EC ideal=[{self._ec_ideal_min}, {self._ec_ideal_max}], '
            f'A:B ratio={self._ab_ratio}'
        )

    # -------------------------------------------------------------------------
    # Subscriptions
    # -------------------------------------------------------------------------

    def _on_water_level(self, msg: WaterLevel) -> None:
        """Update stored water level for volume calculations."""
        self._current_water_level_cm = msg.level_cm

    def _on_topoff_event(self, msg: TopOffEvent) -> None:
        """Note that a top-off occurred — next probe reading will trigger dosing."""
        self.get_logger().info(
            f'Top-off event received ({msg.volume_added_mL:.0f} mL) — '
            f'will dose after next probe reading'
        )
        self._topoff_pending_probe = True

    def _on_probe_reading(self, msg: ProbeReading) -> None:
        """Process a new probe reading and dose if needed."""
        if self._emergency_lockout:
            self.get_logger().warn(
                f'Emergency lockout active — ignoring probe reading '
                f'(pH={msg.ph:.2f}, EC={msg.ec_mS_cm:.3f})'
            )
            return

        self.get_logger().info(
            f'Probe reading: pH={msg.ph:.2f}, EC={msg.ec_mS_cm:.3f} mS/cm, '
            f'temp={msg.temperature_C:.1f}°C'
        )
        self._run_dosing_sequence(msg.ph, msg.ec_mS_cm)
        self._topoff_pending_probe = False

    # -------------------------------------------------------------------------
    # Dosing sequence
    # -------------------------------------------------------------------------

    def _run_dosing_sequence(self, current_ph: float, current_ec: float) -> None:
        """Execute the pH-first then EC dosing sequence with verify loops.

        Order:
          1. Correct pH if out of ideal range
          2. Wait for mixing and re-probe
          3. Correct EC if below ideal range (never dose if EC too high)
          4. Wait for mixing and re-probe to verify

        Args:
            current_ph: Current pH reading.
            current_ec: Current EC reading in mS/cm.
        """
        volume_L = self._compute_solution_volume_L()

        # --- Step 1: pH correction ---
        ph_needs_dose = not (self._ph_ideal_min <= current_ph <= self._ph_ideal_max)
        if ph_needs_dose:
            self.get_logger().info(
                f'pH {current_ph:.2f} outside ideal [{self._ph_ideal_min}, {self._ph_ideal_max}] '
                f'— calculating pH dose'
            )
            ph_success = self._dose_ph_with_verify(current_ph, volume_L)
            if not ph_success:
                return  # Emergency lockout was triggered or max doses exceeded

        # --- Step 2: EC correction ---
        if current_ec < self._ec_ideal_min:
            self.get_logger().info(
                f'EC {current_ec:.3f} below ideal min {self._ec_ideal_min} '
                f'— calculating nutrient dose'
            )
            self._dose_ec_with_verify(current_ec, volume_L)
        elif current_ec > self._ec_ideal_max:
            self.get_logger().warn(
                f'EC {current_ec:.3f} above ideal max {self._ec_ideal_max} '
                f'— DO NOT dose. Dilute by adding fresh water.'
            )

    def _dose_ph_with_verify(self, current_ph: float, volume_L: float) -> bool:
        """Dose to correct pH, then verify after mixing.

        Returns:
            True if pH corrected or within range, False if emergency lockout triggered.
        """
        failed_count = 0
        ph = current_ph

        for attempt in range(self._emergency_lockout_threshold + 1):
            if not (self._ph_ideal_min <= ph <= self._ph_ideal_max):
                if not self._can_dose(PUMP_PH_UP if ph < self._ph_ideal_min else PUMP_PH_DOWN):
                    self.get_logger().warn('pH dose blocked by safety limits — waiting')
                    return True

                dose_mL, pump_id = self._calculate_ph_dose(ph, volume_L)
                if dose_mL <= 0:
                    break

                self._actuate_pump(pump_id, dose_mL, ph, 0.0, volume_L, reason='ph_correction')

                self.get_logger().info(
                    f'Waiting {self._ph_mixing_wait}s for pH mixing'
                )
                time.sleep(self._ph_mixing_wait)

                new_reading = self._trigger_probe_and_get_reading()
                if new_reading is None:
                    self.get_logger().warn('Could not get probe reading after pH dose')
                    break

                ph = new_reading.ph
                if self._ph_ideal_min <= ph <= self._ph_ideal_max:
                    self.get_logger().info(f'pH corrected to {ph:.2f} after {attempt + 1} dose(s)')
                    self._consecutive_failed_verify = 0
                    return True

                failed_count += 1
                self._consecutive_failed_verify += 1
            else:
                self._consecutive_failed_verify = 0
                return True

            if self._consecutive_failed_verify >= self._emergency_lockout_threshold:
                self._trigger_emergency_lockout(
                    f'pH not responding after {self._consecutive_failed_verify} doses '
                    f'(current pH={ph:.2f}) — check probe calibration or perform full solution change'
                )
                return False

        return True

    def _dose_ec_with_verify(self, current_ec: float, volume_L: float) -> None:
        """Dose A+B nutrients to raise EC, then verify after mixing."""
        for attempt in range(self._emergency_lockout_threshold + 1):
            if current_ec < self._ec_ideal_min:
                if not self._can_dose(PUMP_NUTRIENT_A) or not self._can_dose(PUMP_NUTRIENT_B):
                    self.get_logger().warn('Nutrient dose blocked by safety limits — waiting')
                    return

                dose_a_mL, dose_b_mL = self._calculate_ec_dose(current_ec, volume_L)
                if dose_a_mL <= 0 and dose_b_mL <= 0:
                    break

                if dose_a_mL > 0:
                    self._actuate_pump(
                        PUMP_NUTRIENT_A, dose_a_mL, 0.0, current_ec, volume_L,
                        reason='ec_correction'
                    )
                if dose_b_mL > 0:
                    self._actuate_pump(
                        PUMP_NUTRIENT_B, dose_b_mL, 0.0, current_ec, volume_L,
                        reason='ec_correction'
                    )

                self.get_logger().info(
                    f'Waiting {self._nutrient_mixing_wait}s for nutrient mixing'
                )
                time.sleep(self._nutrient_mixing_wait)

                new_reading = self._trigger_probe_and_get_reading()
                if new_reading is None:
                    self.get_logger().warn('Could not get probe reading after nutrient dose')
                    return

                current_ec = new_reading.ec_mS_cm
                if current_ec >= self._ec_ideal_min:
                    self.get_logger().info(
                        f'EC raised to {current_ec:.3f} after {attempt + 1} dose(s)'
                    )
                    self._consecutive_failed_verify = 0
                    return

                self._consecutive_failed_verify += 1
                if self._consecutive_failed_verify >= self._emergency_lockout_threshold:
                    self._trigger_emergency_lockout(
                        f'EC not responding after {self._consecutive_failed_verify} doses '
                        f'(current EC={current_ec:.3f}) — check nutrient concentrates'
                    )
                    return
            else:
                self._consecutive_failed_verify = 0
                return

    # -------------------------------------------------------------------------
    # Dose calculation (explicit chemistry math)
    # -------------------------------------------------------------------------

    def _calculate_ph_dose(
        self, current_ph: float, volume_L: float
    ) -> tuple[float, str]:
        """Calculate pH adjustment dose using linear approximation.

        Linear approximation (conservative — safe to undershoot for large errors):
          dose_mL = |pH_error| × volume_L × (1.0 / adjuster_molarity)

        The verify-after-dose loop handles any undershoot.

        Args:
            current_ph: Current pH.
            volume_L: Current solution volume in litres.

        Returns:
            Tuple of (dose_mL, pump_id). dose_mL is capped at max_dose_mL.
        """
        if current_ph < self._ph_ideal_min:
            # pH too low — need pH up
            ph_error = self._ph_ideal_min - current_ph
            molarity = self._ph_up_molarity
            pump_id = PUMP_PH_UP
        else:
            # pH too high — need pH down
            ph_error = current_ph - self._ph_ideal_max
            molarity = self._ph_down_molarity
            pump_id = PUMP_PH_DOWN

        dose_mL = ph_error * volume_L * (1.0 / molarity)
        dose_mL = min(dose_mL, self._max_dose_mL)

        self.get_logger().info(
            f'pH dose calculation: error={ph_error:.3f}, volume={volume_L:.2f}L, '
            f'molarity={molarity}, dose={dose_mL:.3f} mL ({pump_id})'
        )
        return dose_mL, pump_id

    def _calculate_ec_dose(
        self, current_ec: float, volume_L: float
    ) -> tuple[float, float]:
        """Calculate A+B nutrient dose to raise EC to ideal minimum.

        EC response is linear in the hydroponics concentration range.
        The ec_per_mL_per_L values must be calibrated per nutrient brand.

        Args:
            current_ec: Current EC in mS/cm.
            volume_L: Current solution volume in litres.

        Returns:
            Tuple of (dose_a_mL, dose_b_mL), each capped at max_dose_mL.
        """
        ec_deficit = self._ec_ideal_min - current_ec

        ab_ratio = self._ab_ratio
        # A fraction of total dose
        a_fraction = ab_ratio / (ab_ratio + 1.0)
        b_fraction = 1.0 / (ab_ratio + 1.0)

        # Combined EC contribution rate (mS/cm per mL per L)
        combined_ec_rate = (
            self._nutrient_a_ec_per_mL_per_L * a_fraction +
            self._nutrient_b_ec_per_mL_per_L * b_fraction
        )

        if combined_ec_rate <= 0:
            return 0.0, 0.0

        # Total mL of combined concentrate needed for the full solution volume
        total_dose_mL = (ec_deficit * volume_L) / combined_ec_rate

        dose_a_mL = min(total_dose_mL * a_fraction, self._max_dose_mL)
        dose_b_mL = min(total_dose_mL * b_fraction, self._max_dose_mL)

        self.get_logger().info(
            f'EC dose calculation: deficit={ec_deficit:.3f} mS/cm, '
            f'volume={volume_L:.2f}L, A:B={ab_ratio:.1f}, '
            f'dose_a={dose_a_mL:.3f} mL, dose_b={dose_b_mL:.3f} mL'
        )
        return dose_a_mL, dose_b_mL

    def _compute_solution_volume_L(self) -> float:
        """Compute current solution volume from water level.

        Returns:
            Volume in litres.
        """
        volume_cm3 = self._current_water_level_cm * self._bin_cross_section_cm2
        return volume_cm3 / 1000.0

    # -------------------------------------------------------------------------
    # Safety scaffolding
    # -------------------------------------------------------------------------

    def _can_dose(self, pump_id: str) -> bool:
        """Check all safety conditions before allowing a dose.

        Checks:
          1. min_dose_interval_seconds since last dose on this pump
          2. max_doses_per_hour across all pumps not exceeded

        Args:
            pump_id: Pump identifier string.

        Returns:
            True if dose is allowed, False if blocked.
        """
        now = time.monotonic()

        # Check min interval for this pump
        elapsed = now - self._last_dose_times.get(pump_id, 0.0)
        if elapsed < self._min_dose_interval:
            self.get_logger().warn(
                f'Dose rejected for {pump_id}: min interval {self._min_dose_interval}s '
                f'not elapsed (elapsed={elapsed:.0f}s)'
            )
            return False

        # Prune timestamps older than 1 hour
        one_hour_ago = now - 3600.0
        while self._dose_event_timestamps and self._dose_event_timestamps[0] < one_hour_ago:
            self._dose_event_timestamps.popleft()

        if len(self._dose_event_timestamps) >= self._max_doses_per_hour:
            msg_text = (
                f'max_doses_per_hour ({self._max_doses_per_hour}) exceeded — '
                f'halting dosing. Check system for runaway dosing conditions.'
            )
            self.get_logger().error(msg_text)
            err = String()
            err.data = msg_text
            self._pub_error.publish(err)
            return False

        return True

    def _actuate_pump(
        self,
        pump_id: str,
        dose_mL: float,
        ph_before: float,
        ec_before: float,
        solution_volume_L: float,
        reason: str,
    ) -> None:
        """Send pump command and publish DosingEvent.

        Args:
            pump_id: Pump identifier string.
            dose_mL: Volume to dose in mL.
            ph_before: pH at time of dose (0.0 if N/A).
            ec_before: EC at time of dose (0.0 if N/A).
            solution_volume_L: Current solution volume.
            reason: Human-readable reason string.
        """
        flow_rate = self._flow_rates[pump_id]
        duration_seconds = dose_mL / flow_rate if flow_rate > 0 else 0.0

        # Encode pump command as integer: pump_index * 100000 + duration_ms
        pump_index = {
            PUMP_PH_DOWN: 1,
            PUMP_PH_UP: 0,
            PUMP_NUTRIENT_A: 2,
            PUMP_NUTRIENT_B: 3,
        }[pump_id]
        duration_ms = int(duration_seconds * 1000)
        cmd = Int32()
        cmd.data = pump_index * 100000 + duration_ms
        self._pub_pump.publish(cmd)

        # Update timing state
        now = time.monotonic()
        self._last_dose_times[pump_id] = now
        self._dose_event_timestamps.append(now)

        stamp = self.get_clock().now().to_msg()
        event = DosingEvent()
        event.pump_id = pump_id
        event.dose_mL = dose_mL
        event.duration_seconds = duration_seconds
        event.reason = reason
        event.ph_before = ph_before
        event.ec_before = ec_before
        event.solution_volume_L = solution_volume_L
        event.timestamp = stamp
        self._pub_dosing_event.publish(event)

        self.get_logger().info(
            f'Dose actuated: {pump_id} {dose_mL:.3f} mL '
            f'({duration_seconds:.1f}s) — reason: {reason}'
        )

    def _trigger_emergency_lockout(self, reason: str) -> None:
        """Halt all dosing and notify operator.

        Args:
            reason: Human-readable description of the failure.
        """
        self._emergency_lockout = True
        msg_text = f'EMERGENCY LOCKOUT: {reason}'
        self.get_logger().error(msg_text)
        err = String()
        err.data = msg_text
        self._pub_error.publish(err)

    # -------------------------------------------------------------------------
    # Probe helpers
    # -------------------------------------------------------------------------

    def _trigger_probe_and_get_reading(self) -> Optional[ProbeReading]:
        """Trigger a probe cycle and block until a reading arrives.

        Returns:
            ProbeReading if successful, None on timeout or failure.
        """
        if not self._probe_trigger_client.wait_for_service(timeout_sec=2.0):
            self.get_logger().warn('/probe/trigger unavailable')
            return None

        req = TriggerProbe.Request()
        future = self._probe_trigger_client.call_async(req)
        rclpy.spin_until_future_complete(self, future, timeout_sec=30.0)

        if not future.done() or not future.result().success:
            self.get_logger().warn('Probe trigger returned failure or timed out')
            return None

        # The probe reading will arrive on /probe/reading asynchronously.
        # Block briefly to receive it via spin.
        reading_holder: list[Optional[ProbeReading]] = [None]

        def _capture_cb(msg: ProbeReading) -> None:
            reading_holder[0] = msg

        temp_sub = self.create_subscription(
            ProbeReading, '/probe/reading', _capture_cb, 1,
            callback_group=self._cb_group
        )
        deadline = time.monotonic() + 35.0
        while reading_holder[0] is None and time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.1)

        self.destroy_subscription(temp_sub)
        return reading_holder[0]


def main(args: Optional[list[str]] = None) -> None:
    """Initialise rclpy, spin the DosingNode, and shut down cleanly."""
    rclpy.init(args=args)
    node = DosingNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info('DosingNode interrupted')
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
