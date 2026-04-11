# MIT License
# Copyright (c) 2026 AIdroponics Project
"""Integration test: declining NDVI sequence → probe interval decreased."""

import pytest
import numpy as np
from typing import Optional


# ---------------------------------------------------------------------------
# Extracted NDVI trend + early warning logic stubs
# ---------------------------------------------------------------------------

class NDVITrendMonitor:
    """Mirrors NDVI trend and early warning logic from PlantVisionNode."""

    def __init__(
        self,
        buffer_size: int = 48,
        declining_slope_threshold: float = -0.002,
        normal_capture_interval: float = 1800.0,
        alert_capture_interval: float = 600.0,
        alert_probe_interval: float = 300.0,
    ):
        self.buffer_size = buffer_size
        self.declining_slope_threshold = declining_slope_threshold
        self.normal_capture_interval = normal_capture_interval
        self.alert_capture_interval = alert_capture_interval
        self.alert_probe_interval = alert_probe_interval

        self._ndvi_buffer: list[float] = []
        self.in_alert_mode: bool = False
        self.probe_interval_requested: Optional[float] = None
        self.capture_interval: float = normal_capture_interval
        self.ndvi_alerts_published: list[dict] = []

    def add_ndvi_reading(self, mean_ndvi: float) -> None:
        self._ndvi_buffer.append(mean_ndvi)
        if len(self._ndvi_buffer) > self.buffer_size:
            self._ndvi_buffer.pop(0)

        trend_slope = self._compute_trend()
        self._check_early_warning(mean_ndvi, trend_slope)

    def _compute_trend(self) -> float:
        if len(self._ndvi_buffer) < 3:
            return 0.0
        values = np.array(self._ndvi_buffer, dtype=np.float64)
        indices = np.arange(len(values), dtype=np.float64)
        slope = float(np.polyfit(indices, values, 1)[0])
        return slope

    def _check_early_warning(self, mean_ndvi: float, trend_slope: float) -> None:
        is_declining = trend_slope < self.declining_slope_threshold

        if is_declining and not self.in_alert_mode:
            self.in_alert_mode = True
            self.probe_interval_requested = self.alert_probe_interval
            self.capture_interval = self.alert_capture_interval
            self.ndvi_alerts_published.append({
                'mean_ndvi': mean_ndvi,
                'slope': trend_slope,
            })
        elif not is_declining and self.in_alert_mode:
            self.in_alert_mode = False
            self.probe_interval_requested = None
            self.capture_interval = self.normal_capture_interval


class TestNDVIEarlyWarning:
    """Integration tests for NDVI declining → probe frequency increase."""

    def test_stable_ndvi_no_alert(self):
        """Stable NDVI readings produce no alert."""
        monitor = NDVITrendMonitor()
        for _ in range(20):
            monitor.add_ndvi_reading(0.45)
        assert not monitor.in_alert_mode
        assert monitor.probe_interval_requested is None

    def test_declining_ndvi_triggers_alert(self):
        """Steadily declining NDVI should trigger early-warning mode."""
        monitor = NDVITrendMonitor(declining_slope_threshold=-0.002)
        # Simulate 10 readings with slope of -0.01 per reading
        for i in range(10):
            monitor.add_ndvi_reading(0.50 - i * 0.01)
        assert monitor.in_alert_mode

    def test_declining_ndvi_decreases_probe_interval(self):
        """When NDVI alert fires, probe interval should be set to alert value."""
        monitor = NDVITrendMonitor(
            alert_probe_interval=300.0,
            declining_slope_threshold=-0.002,
        )
        for i in range(10):
            monitor.add_ndvi_reading(0.50 - i * 0.01)
        assert monitor.probe_interval_requested == pytest.approx(300.0)

    def test_declining_ndvi_increases_capture_frequency(self):
        """When NDVI alert fires, capture interval should switch to alert value."""
        monitor = NDVITrendMonitor(
            normal_capture_interval=1800.0,
            alert_capture_interval=600.0,
            declining_slope_threshold=-0.002,
        )
        for i in range(10):
            monitor.add_ndvi_reading(0.50 - i * 0.01)
        assert monitor.capture_interval == pytest.approx(600.0)
        assert monitor.capture_interval < 1800.0

    def test_ndvi_alert_message_published(self):
        """NDVIAlert should be published when early-warning triggered."""
        monitor = NDVITrendMonitor(declining_slope_threshold=-0.002)
        for i in range(10):
            monitor.add_ndvi_reading(0.50 - i * 0.01)
        assert len(monitor.ndvi_alerts_published) >= 1

    def test_ndvi_recovery_restores_normal_intervals(self):
        """When NDVI recovers, intervals should return to normal."""
        monitor = NDVITrendMonitor(
            normal_capture_interval=1800.0,
            alert_capture_interval=600.0,
            declining_slope_threshold=-0.002,
        )
        # First trigger alert
        for i in range(10):
            monitor.add_ndvi_reading(0.50 - i * 0.01)
        assert monitor.in_alert_mode

        # Then recover — add many stable readings to flatten slope
        for _ in range(50):
            monitor.add_ndvi_reading(0.35)  # stable at low but not declining

        assert not monitor.in_alert_mode
        assert monitor.capture_interval == pytest.approx(1800.0)

    def test_short_buffer_no_false_alert(self):
        """With less than 3 readings, no trend can be computed — no alert."""
        monitor = NDVITrendMonitor()
        monitor.add_ndvi_reading(0.5)
        monitor.add_ndvi_reading(0.4)
        assert not monitor.in_alert_mode
