# MIT License
# Copyright (c) 2024 Claudroponics Project

"""PID controller with anti-windup, derivative-on-measurement, and dead band."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class PIDConfig:
    """Configuration for a PID controller."""
    kp: float = 1.0
    ki: float = 0.0
    kd: float = 0.0
    dead_band: float = 0.0
    integral_clamp: float = 100.0
    output_min: float = 0.0
    output_max: float = 5000.0


class PIDController:
    """PID controller with anti-windup integral clamp and derivative-on-measurement.

    Features:
        - Proportional + Integral (clamped) + Derivative (on measurement, not error)
        - Dead band: no actuation within +/- dead_band of setpoint
        - Anti-windup: integral term clamped to [-integral_clamp, +integral_clamp]
        - Output clamping: output restricted to [output_min, output_max]
        - Reset method for setpoint changes
    """

    def __init__(self, config: PIDConfig) -> None:
        self._config = config
        self._integral: float = 0.0
        self._prev_measurement: float | None = None
        self._prev_time: float | None = None
        self._setpoint: float = 0.0

    @property
    def config(self) -> PIDConfig:
        return self._config

    @config.setter
    def config(self, value: PIDConfig) -> None:
        self._config = value

    @property
    def setpoint(self) -> float:
        return self._setpoint

    @setpoint.setter
    def setpoint(self, value: float) -> None:
        if value != self._setpoint:
            self._setpoint = value
            self.reset()

    @property
    def integral(self) -> float:
        return self._integral

    def reset(self) -> None:
        """Reset integral accumulator and derivative state."""
        self._integral = 0.0
        self._prev_measurement = None
        self._prev_time = None

    def compute(self, measurement: float, current_time: float | None = None) -> float:
        """Compute PID output given current measurement.

        Args:
            measurement: Current sensor reading.
            current_time: Current time in seconds. Uses time.monotonic() if None.

        Returns:
            PID output clamped to [output_min, output_max].
            Returns 0.0 if error is within dead band.
        """
        if current_time is None:
            current_time = time.monotonic()

        error = self._setpoint - measurement

        # Dead band: no actuation if within tolerance
        if abs(error) <= self._config.dead_band:
            self._prev_measurement = measurement
            self._prev_time = current_time
            return 0.0

        # Time delta
        if self._prev_time is None:
            dt = 0.0
        else:
            dt = current_time - self._prev_time
            if dt <= 0.0:
                dt = 0.0

        # Proportional term
        p_term = self._config.kp * error

        # Integral term with anti-windup clamp
        if dt > 0.0:
            self._integral += error * dt
            self._integral = max(
                -self._config.integral_clamp,
                min(self._config.integral_clamp, self._integral)
            )
        i_term = self._config.ki * self._integral

        # Derivative term on measurement (not error) to avoid setpoint kick
        d_term = 0.0
        if self._prev_measurement is not None and dt > 0.0:
            d_measurement = (measurement - self._prev_measurement) / dt
            d_term = -self._config.kd * d_measurement

        # Store state
        self._prev_measurement = measurement
        self._prev_time = current_time

        # Compute and clamp output
        output = p_term + i_term + d_term
        output = max(self._config.output_min, min(self._config.output_max, output))

        return output
