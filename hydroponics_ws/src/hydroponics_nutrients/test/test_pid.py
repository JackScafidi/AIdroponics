# MIT License
# Copyright (c) 2024 Claudroponics Project

"""Unit tests for the PID controller."""

import math
import time
import pytest

from hydroponics_nutrients.pid import PIDController, PIDConfig


def make_pid(kp=1.0, ki=0.0, kd=0.0, dead_band=0.0,
             integral_clamp=100.0, output_min=0.0, output_max=1000.0) -> PIDController:
    cfg = PIDConfig(kp=kp, ki=ki, kd=kd, dead_band=dead_band,
                    integral_clamp=integral_clamp,
                    output_min=output_min, output_max=output_max)
    pid = PIDController(cfg)
    pid.setpoint = 6.0
    return pid


class TestPIDStepResponse:
    def test_proportional_only_positive_error(self) -> None:
        """P-only controller: output = kp * error."""
        pid = make_pid(kp=2.0)
        output = pid.compute(5.0, current_time=0.0)
        # error = 6.0 - 5.0 = 1.0, kp=2 → output=2.0
        assert math.isclose(output, 2.0, rel_tol=1e-6)

    def test_proportional_only_negative_error(self) -> None:
        pid = make_pid(kp=2.0)
        output = pid.compute(7.0, current_time=0.0)
        # error = 6.0 - 7.0 = -1.0, kp=2 → -2.0 → clamped to output_min=0.0
        assert math.isclose(output, 0.0, rel_tol=1e-6)

    def test_integral_accumulates_over_time(self) -> None:
        """Integral term should grow with sustained error over time."""
        pid = make_pid(ki=1.0)
        pid.compute(5.0, current_time=0.0)   # error=1.0, dt=0 → no accumulation
        output1 = pid.compute(5.0, current_time=1.0)  # error=1.0, dt=1 → integral=1.0
        output2 = pid.compute(5.0, current_time=2.0)  # error=1.0, dt=1 → integral=2.0
        assert output2 > output1, "Integral should make output grow with sustained error"

    def test_derivative_on_measurement_no_setpoint_kick(self) -> None:
        """Derivative-on-measurement: changing setpoint should not cause spike."""
        pid = make_pid(kd=10.0)
        pid.compute(5.5, current_time=0.0)
        pid.setpoint = 7.0   # Big setpoint change
        # Measurement doesn't jump → derivative-on-measurement keeps output smooth
        output = pid.compute(5.5, current_time=1.0)
        # With kp=1, error=1.5, output=1.5. No kd spike since measurement unchanged
        assert output < 10.0, "Setpoint change should not cause large derivative spike"


class TestAntiWindup:
    def test_integral_clamped_at_limit(self) -> None:
        """Integral should not exceed integral_clamp."""
        pid = make_pid(ki=1.0, integral_clamp=5.0)
        for i in range(100):
            pid.compute(0.0, current_time=float(i))  # error=6.0 every second
        assert abs(pid.integral) <= 5.0 + 1e-6

    def test_integral_clamp_both_directions(self) -> None:
        """Clamp applies to both positive and negative accumulation."""
        pid = make_pid(ki=1.0, integral_clamp=3.0, output_min=-1000.0)
        pid.setpoint = 0.0
        for i in range(100):
            pid.compute(10.0, current_time=float(i))  # error=-10 every second
        assert pid.integral >= -3.0 - 1e-6


class TestDeadBand:
    def test_no_actuation_within_dead_band(self) -> None:
        """Output must be exactly 0.0 if error is within dead_band."""
        pid = make_pid(kp=10.0, ki=1.0, dead_band=0.1)
        # error = 6.05 - 6.0 = 0.05 < dead_band
        output = pid.compute(6.05, current_time=0.0)
        assert output == 0.0

    def test_actuation_outside_dead_band(self) -> None:
        """Output must be non-zero if error exceeds dead_band."""
        pid = make_pid(kp=2.0, dead_band=0.1)
        output = pid.compute(5.5, current_time=0.0)  # error=0.5 > dead_band=0.1
        assert output > 0.0

    def test_dead_band_boundary_at_edge(self) -> None:
        """Exactly at dead_band boundary: no actuation."""
        pid = make_pid(kp=2.0, dead_band=0.1)
        output = pid.compute(6.1, current_time=0.0)  # error=-0.1, within dead_band
        assert output == 0.0

    def test_integral_not_accumulated_in_dead_band(self) -> None:
        """Integral should not accumulate while in dead band."""
        pid = make_pid(ki=1.0, dead_band=0.5)
        initial_integral = pid.integral
        for i in range(10):
            pid.compute(6.1, current_time=float(i))  # error=0.1 < dead_band=0.5
        assert pid.integral == initial_integral


class TestOutputClamping:
    def test_output_clamped_to_max(self) -> None:
        pid = make_pid(kp=1000.0, output_max=500.0)
        output = pid.compute(0.0, current_time=0.0)
        assert output <= 500.0

    def test_output_not_below_min(self) -> None:
        pid = make_pid(kp=1.0, output_min=10.0)
        # error=6-6=0 → in dead_band... use small dead_band
        pid2 = make_pid(kp=0.0001, output_min=10.0)
        output = pid2.compute(5.9, current_time=0.0)
        # P term tiny, but output_min=10.0 → BUT only if non-zero output
        # Actually if error > 0 and kp is tiny, P ≈ 0 which is < output_min
        # The clamp applies after: max(output_min, min(output_max, raw_output))
        # So output = 10.0 (clamped up from tiny positive value)
        assert output >= 10.0


class TestReset:
    def test_reset_clears_integral(self) -> None:
        pid = make_pid(ki=1.0)
        for i in range(5):
            pid.compute(0.0, current_time=float(i))
        assert pid.integral != 0.0
        pid.reset()
        assert pid.integral == 0.0

    def test_setpoint_change_triggers_reset(self) -> None:
        pid = make_pid(ki=1.0)
        for i in range(5):
            pid.compute(0.0, current_time=float(i))
        assert pid.integral != 0.0
        pid.setpoint = 7.0  # Should reset integral
        assert pid.integral == 0.0

    def test_same_setpoint_does_not_reset(self) -> None:
        pid = make_pid(ki=1.0)
        for i in range(5):
            pid.compute(0.0, current_time=float(i))
        integral_before = pid.integral
        pid.setpoint = 6.0  # Same value — no reset
        assert pid.integral == integral_before
