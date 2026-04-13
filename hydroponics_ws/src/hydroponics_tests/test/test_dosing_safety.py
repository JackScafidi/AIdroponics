# MIT License
# Copyright (c) 2026 Autoponics Project
"""Unit tests for dosing safety scaffolding logic."""

import time
from collections import deque

import pytest


# ---------------------------------------------------------------------------
# Extracted safety logic for testing without ROS
# ---------------------------------------------------------------------------

class DosingSafetyChecker:
    """Mirrors the safety check logic from dosing_node."""

    def __init__(
        self,
        max_dose_mL: float = 5.0,
        min_dose_interval_seconds: float = 300.0,
        max_doses_per_hour: int = 8,
        emergency_lockout_threshold: int = 3,
        ab_ratio: float = 1.0,
    ) -> None:
        self.max_dose_mL = max_dose_mL
        self.min_dose_interval = min_dose_interval_seconds
        self.max_doses_per_hour = max_doses_per_hour
        self.emergency_lockout_threshold = emergency_lockout_threshold
        self.ab_ratio = ab_ratio
        self._last_dose_times: dict[str, float] = {}
        self._dose_event_timestamps: deque = deque()
        self.consecutive_failed_verify: int = 0
        self.emergency_lockout: bool = False

    def can_dose(self, pump_id: str, now: float = None) -> tuple[bool, str]:
        if now is None:
            now = time.monotonic()

        if self.emergency_lockout:
            return False, 'emergency_lockout'

        elapsed = now - self._last_dose_times.get(pump_id, 0.0)
        if elapsed < self.min_dose_interval:
            return False, f'min_interval_not_elapsed ({elapsed:.0f}s < {self.min_dose_interval}s)'

        one_hour_ago = now - 3600.0
        while self._dose_event_timestamps and self._dose_event_timestamps[0] < one_hour_ago:
            self._dose_event_timestamps.popleft()

        if len(self._dose_event_timestamps) >= self.max_doses_per_hour:
            return False, 'max_doses_per_hour_exceeded'

        return True, 'ok'

    def record_dose(self, pump_id: str, now: float = None) -> None:
        if now is None:
            now = time.monotonic()
        self._last_dose_times[pump_id] = now
        self._dose_event_timestamps.append(now)

    def record_failed_verify(self) -> bool:
        """Returns True if emergency lockout should be triggered."""
        self.consecutive_failed_verify += 1
        if self.consecutive_failed_verify >= self.emergency_lockout_threshold:
            self.emergency_lockout = True
            return True
        return False

    def cap_dose(self, calculated_mL: float) -> float:
        return min(calculated_mL, self.max_dose_mL)

    def split_ab(self, total_mL: float) -> tuple[float, float]:
        ab_ratio = self.ab_ratio
        a_fraction = ab_ratio / (ab_ratio + 1.0)
        b_fraction = 1.0 / (ab_ratio + 1.0)
        dose_a = min(total_mL * a_fraction, self.max_dose_mL)
        dose_b = min(total_mL * b_fraction, self.max_dose_mL)
        return dose_a, dose_b


class TestMaxDoseCap:
    def test_dose_within_limit_unchanged(self):
        checker = DosingSafetyChecker(max_dose_mL=5.0)
        assert checker.cap_dose(3.0) == 3.0

    def test_dose_above_limit_is_capped(self):
        checker = DosingSafetyChecker(max_dose_mL=5.0)
        assert checker.cap_dose(10.0) == 5.0

    def test_dose_exactly_at_limit(self):
        checker = DosingSafetyChecker(max_dose_mL=5.0)
        assert checker.cap_dose(5.0) == 5.0


class TestMinDoseInterval:
    def test_first_dose_allowed(self):
        checker = DosingSafetyChecker(min_dose_interval_seconds=300.0)
        ok, reason = checker.can_dose('ph_down', now=1000.0)
        assert ok

    def test_rapid_re_dose_blocked(self):
        checker = DosingSafetyChecker(min_dose_interval_seconds=300.0)
        checker.record_dose('ph_down', now=1000.0)
        ok, reason = checker.can_dose('ph_down', now=1060.0)  # only 60s elapsed
        assert not ok
        assert 'min_interval' in reason

    def test_dose_allowed_after_interval(self):
        checker = DosingSafetyChecker(min_dose_interval_seconds=300.0)
        checker.record_dose('ph_down', now=1000.0)
        ok, reason = checker.can_dose('ph_down', now=1400.0)  # 400s elapsed
        assert ok

    def test_different_pumps_have_independent_intervals(self):
        checker = DosingSafetyChecker(min_dose_interval_seconds=300.0)
        checker.record_dose('ph_down', now=1000.0)
        ok, _ = checker.can_dose('ph_up', now=1060.0)
        assert ok  # ph_up was never dosed — should be allowed


class TestMaxDosesPerHour:
    def test_max_doses_per_hour_triggers_lockout(self):
        checker = DosingSafetyChecker(
            max_doses_per_hour=3, min_dose_interval_seconds=0.0
        )
        base = 1000.0
        for i in range(3):
            checker.record_dose('ph_down', now=base + i * 10)
        ok, reason = checker.can_dose('ph_down', now=base + 40.0)
        assert not ok
        assert 'max_doses_per_hour' in reason

    def test_doses_from_previous_hour_expire(self):
        checker = DosingSafetyChecker(
            max_doses_per_hour=3, min_dose_interval_seconds=0.0
        )
        base = 1000.0
        for i in range(3):
            checker.record_dose('ph_down', now=base + i * 10)
        # After 1 hour, old doses expire
        ok, _ = checker.can_dose('ph_down', now=base + 3700.0)
        assert ok


class TestEmergencyLockout:
    def test_lockout_after_3_failed_verifies(self):
        checker = DosingSafetyChecker(emergency_lockout_threshold=3)
        assert not checker.record_failed_verify()
        assert not checker.record_failed_verify()
        assert checker.record_failed_verify()  # 3rd failure triggers lockout
        assert checker.emergency_lockout

    def test_lockout_blocks_all_dosing(self):
        checker = DosingSafetyChecker(emergency_lockout_threshold=3)
        checker.emergency_lockout = True
        ok, reason = checker.can_dose('ph_down', now=1000.0)
        assert not ok
        assert 'emergency_lockout' in reason


class TestABRatioMaintained:
    def test_1_to_1_ratio(self):
        checker = DosingSafetyChecker(ab_ratio=1.0, max_dose_mL=100.0)
        dose_a, dose_b = checker.split_ab(total_mL=10.0)
        assert dose_a == pytest.approx(5.0, rel=0.01)
        assert dose_b == pytest.approx(5.0, rel=0.01)

    def test_2_to_1_ratio(self):
        checker = DosingSafetyChecker(ab_ratio=2.0, max_dose_mL=100.0)
        dose_a, dose_b = checker.split_ab(total_mL=9.0)
        assert dose_a == pytest.approx(6.0, rel=0.01)
        assert dose_b == pytest.approx(3.0, rel=0.01)

    def test_ratio_capped_independently(self):
        checker = DosingSafetyChecker(ab_ratio=1.0, max_dose_mL=5.0)
        dose_a, dose_b = checker.split_ab(total_mL=20.0)
        assert dose_a <= 5.0
        assert dose_b <= 5.0
