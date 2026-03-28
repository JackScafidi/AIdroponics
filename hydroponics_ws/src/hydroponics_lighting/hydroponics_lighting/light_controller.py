# MIT License
# Copyright (c) 2024 Claudroponics Project

"""ROS2 lighting controller node for grow panel PWM and inspection LEDs."""

from __future__ import annotations

import math
from datetime import datetime, time as dt_time, timedelta
from typing import Any

import rclpy
from rclpy.node import Node
from rclpy.callback_group import ReentrantCallbackGroup
from std_msgs.msg import Bool, Float32

from hydroponics_msgs.msg import LightStatus, NutrientStatus
from hydroponics_msgs.srv import SetGrowLightIntensity, SetInspectionLight


# ---------------------------------------------------------------------------
# Growth stage light profiles
# ---------------------------------------------------------------------------

STAGE_PROFILES: dict[str, dict[str, float]] = {
    'seedling': {
        'light_hours': 14.0,
        'intensity_percent': 40.0,
    },
    'vegetative': {
        'light_hours': 16.0,
        'intensity_percent': 80.0,
    },
    'mature': {
        'light_hours': 16.0,
        'intensity_percent': 90.0,
    },
}

# Schedule states
STATE_OFF = 'off'
STATE_ON = 'on'
STATE_RAMPING_UP = 'ramping_up'
STATE_RAMPING_DOWN = 'ramping_down'


class LightController(Node):
    """Controls the grow panel (PWM-dimmable) and inspection LEDs (on/off).

    The grow panel follows a configurable daily schedule derived from on_time
    and light_hours parameters.  Transitions are smoothed by configurable
    ramp-up/down periods.  The growth stage — received from /nutrient_status —
    adjusts both light_hours and intensity from the built-in stage profile.

    Inspection LEDs are toggled on demand via the SetInspectionLight service
    (called by vision_node) and exposed as std_msgs/Bool on /inspect_light_cmd.

    Topics published:
        /grow_light_cmd  (std_msgs/Float32)  — duty cycle 0.0–1.0 for ESP32 PWM
        /inspect_light_cmd (std_msgs/Bool)   — inspection LED on/off
        /light_status    (hydroponics_msgs/LightStatus) — 1 Hz status

    Subscribed topics:
        /nutrient_status (hydroponics_msgs/NutrientStatus) — growth stage

    Services:
        /set_grow_light_intensity (SetGrowLightIntensity) — override intensity
        /set_inspection_light     (SetInspectionLight)    — toggle inspection LEDs
    """

    def __init__(self) -> None:
        super().__init__('light_controller')
        self._cb_group = ReentrantCallbackGroup()

        self._declare_parameters()

        # Cached parameter values
        self._on_time_str: str = self.get_parameter('on_time').value
        self._light_hours: float = self.get_parameter('light_hours').value
        self._ramp_up_minutes: float = self.get_parameter('ramp_up_minutes').value
        self._ramp_down_minutes: float = self.get_parameter('ramp_down_minutes').value
        self._default_intensity_pct: float = self.get_parameter(
            'default_intensity_percent').value

        # Runtime state
        self._current_intensity_pct: float = 0.0   # what is currently commanded
        self._target_intensity_pct: float = 0.0    # what the schedule wants
        self._inspection_light_on: bool = False
        self._schedule_state: str = STATE_OFF
        self._manual_intensity_override: float | None = None  # set by service

        # Growth stage profile (updated from /nutrient_status)
        self._growth_stage: str = 'vegetative'
        self._apply_stage_profile(self._growth_stage)

        # --- Publishers ---
        self._pub_grow_cmd = self.create_publisher(
            Float32, 'grow_light_cmd', 10)
        self._pub_inspect_cmd = self.create_publisher(
            Bool, 'inspect_light_cmd', 10)
        self._pub_status = self.create_publisher(
            LightStatus, 'light_status', 10)

        # --- Subscribers ---
        self._sub_nutrients = self.create_subscription(
            NutrientStatus, 'nutrient_status',
            self._nutrient_status_callback, 10,
            callback_group=self._cb_group)

        # --- Services ---
        self._srv_set_intensity = self.create_service(
            SetGrowLightIntensity, 'set_grow_light_intensity',
            self._set_grow_intensity_callback,
            callback_group=self._cb_group)
        self._srv_set_inspection = self.create_service(
            SetInspectionLight, 'set_inspection_light',
            self._set_inspection_callback,
            callback_group=self._cb_group)

        # --- 1 Hz schedule + status timer ---
        self._schedule_timer = self.create_timer(
            1.0, self._schedule_tick, callback_group=self._cb_group)

        self.get_logger().info(
            f'Light controller initialized — on_time={self._on_time_str}, '
            f'light_hours={self._light_hours:.1f}, '
            f'intensity={self._default_intensity_pct:.0f}%, '
            f'ramp_up={self._ramp_up_minutes:.0f}min, '
            f'ramp_down={self._ramp_down_minutes:.0f}min')

    # ------------------------------------------------------------------
    # Parameter declaration
    # ------------------------------------------------------------------

    def _declare_parameters(self) -> None:
        """Declare all ROS2 parameters with production-safe defaults."""
        self.declare_parameter('on_time', '06:00')
        self.declare_parameter('light_hours', 16.0)
        self.declare_parameter('ramp_up_minutes', 30.0)
        self.declare_parameter('ramp_down_minutes', 30.0)
        self.declare_parameter('default_intensity_percent', 80.0)

    # ------------------------------------------------------------------
    # Profile helpers
    # ------------------------------------------------------------------

    def _apply_stage_profile(self, stage: str) -> None:
        """Update light_hours and default intensity from growth stage profile."""
        profile = STAGE_PROFILES.get(stage, STAGE_PROFILES['vegetative'])
        self._light_hours = profile['light_hours']
        self._default_intensity_pct = profile['intensity_percent']
        self.get_logger().debug(
            f'Stage profile applied: {stage} — '
            f'light_hours={self._light_hours}, '
            f'intensity={self._default_intensity_pct:.0f}%')

    # ------------------------------------------------------------------
    # Schedule helpers
    # ------------------------------------------------------------------

    def _parse_on_time(self) -> dt_time:
        """Parse HH:MM string parameter into a datetime.time object."""
        try:
            parts = self._on_time_str.split(':')
            return dt_time(int(parts[0]), int(parts[1]))
        except (ValueError, IndexError):
            self.get_logger().warn(
                f'Invalid on_time "{self._on_time_str}", defaulting to 06:00')
            return dt_time(6, 0)

    def _get_schedule_window(self, now: datetime) -> tuple[datetime, datetime, datetime, datetime]:
        """Compute today's schedule: ramp-start, lights-on, lights-off, ramp-end.

        Returns:
            Tuple of (ramp_up_start, on_start, off_start, ramp_down_end) as
            datetime objects anchored to today's date.
        """
        on_time = self._parse_on_time()
        today = now.date()

        on_start = datetime.combine(today, on_time)
        off_start = on_start + timedelta(hours=self._light_hours)
        ramp_up_start = on_start - timedelta(minutes=self._ramp_up_minutes)
        ramp_down_end = off_start + timedelta(minutes=self._ramp_down_minutes)

        return ramp_up_start, on_start, off_start, ramp_down_end

    def _compute_target_intensity(self, now: datetime) -> tuple[float, str]:
        """Compute the target intensity (0-100) and schedule state for *now*.

        Returns:
            (target_intensity_percent, schedule_state)
        """
        ramp_up_start, on_start, off_start, ramp_down_end = (
            self._get_schedule_window(now))

        max_intensity = (
            self._manual_intensity_override
            if self._manual_intensity_override is not None
            else self._default_intensity_pct
        )

        if now < ramp_up_start or now >= ramp_down_end:
            return 0.0, STATE_OFF

        if ramp_up_start <= now < on_start:
            # Ramping up
            elapsed = (now - ramp_up_start).total_seconds()
            total = (on_start - ramp_up_start).total_seconds()
            fraction = elapsed / total if total > 0 else 1.0
            return max_intensity * fraction, STATE_RAMPING_UP

        if on_start <= now < off_start:
            return max_intensity, STATE_ON

        # off_start <= now < ramp_down_end: ramping down
        elapsed = (now - off_start).total_seconds()
        total = (ramp_down_end - off_start).total_seconds()
        fraction = elapsed / total if total > 0 else 1.0
        return max_intensity * (1.0 - fraction), STATE_RAMPING_DOWN

    def _next_transition_str(self, now: datetime) -> str:
        """Return ISO-8601 string of the next schedule transition time."""
        ramp_up_start, on_start, off_start, ramp_down_end = (
            self._get_schedule_window(now))

        transitions = [ramp_up_start, on_start, off_start, ramp_down_end]
        future = [t for t in transitions if t > now]

        if not future:
            # All transitions today have passed — next is tomorrow's ramp_up_start
            next_t = ramp_up_start + timedelta(days=1)
        else:
            next_t = min(future)

        return next_t.isoformat()

    # ------------------------------------------------------------------
    # Schedule tick (1 Hz)
    # ------------------------------------------------------------------

    def _schedule_tick(self) -> None:
        """Called at 1 Hz: compute target intensity, apply smooth step, publish."""
        now = datetime.now()

        target_pct, schedule_state = self._compute_target_intensity(now)
        self._target_intensity_pct = target_pct
        self._schedule_state = schedule_state

        # Clamp and apply
        self._current_intensity_pct = max(0.0, min(100.0, target_pct))

        # Publish PWM command to ESP32 as 0.0–1.0 duty cycle
        grow_cmd = Float32()
        grow_cmd.data = self._current_intensity_pct / 100.0
        self._pub_grow_cmd.publish(grow_cmd)

        # Publish inspection LED state
        inspect_cmd = Bool()
        inspect_cmd.data = self._inspection_light_on
        self._pub_inspect_cmd.publish(inspect_cmd)

        # Publish LightStatus
        self._publish_status(now)

    def _publish_status(self, now: datetime) -> None:
        """Publish current lighting status at 1 Hz."""
        msg = LightStatus()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.grow_intensity_percent = self._current_intensity_pct
        msg.schedule_state = self._schedule_state
        msg.inspection_light_on = self._inspection_light_on
        msg.next_transition_time = self._next_transition_str(now)
        self._pub_status.publish(msg)

    # ------------------------------------------------------------------
    # Subscriber callbacks
    # ------------------------------------------------------------------

    def _nutrient_status_callback(self, msg: NutrientStatus) -> None:
        """Update light profile when growth stage changes."""
        new_stage = msg.growth_stage
        if new_stage and new_stage != self._growth_stage:
            old_stage = self._growth_stage
            self._growth_stage = new_stage
            self._apply_stage_profile(new_stage)
            # Clear manual override on stage change so profile takes effect
            self._manual_intensity_override = None
            self.get_logger().info(
                f'Growth stage change: {old_stage} → {new_stage}, '
                f'updating light schedule')

    # ------------------------------------------------------------------
    # Service callbacks
    # ------------------------------------------------------------------

    def _set_grow_intensity_callback(
        self,
        request: SetGrowLightIntensity.Request,
        response: SetGrowLightIntensity.Response,
    ) -> SetGrowLightIntensity.Response:
        """Override grow light intensity (0–100%).

        Setting to a negative value clears the override and restores
        schedule-driven intensity.
        """
        pct = request.intensity_percent
        if pct < 0.0:
            # Clear override
            self._manual_intensity_override = None
            self.get_logger().info(
                'Grow light intensity override cleared — reverting to schedule')
            response.success = True
            return response

        if pct > 100.0:
            self.get_logger().warn(
                f'SetGrowLightIntensity: clamping {pct:.1f}% to 100%')
            pct = 100.0

        self._manual_intensity_override = pct
        self.get_logger().info(
            f'Grow light intensity manually set to {pct:.1f}%')
        response.success = True
        return response

    def _set_inspection_callback(
        self,
        request: SetInspectionLight.Request,
        response: SetInspectionLight.Response,
    ) -> SetInspectionLight.Response:
        """Toggle inspection LEDs on or off."""
        self._inspection_light_on = request.on

        # Publish immediately (do not wait for the 1 Hz tick)
        inspect_cmd = Bool()
        inspect_cmd.data = self._inspection_light_on
        self._pub_inspect_cmd.publish(inspect_cmd)

        self.get_logger().info(
            f'Inspection light {"ON" if request.on else "OFF"}')
        response.success = True
        return response


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = LightController()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
