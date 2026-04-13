# MIT License
# Copyright (c) 2026 Autoponics Project
"""Unit tests for water level distance-to-level conversion math."""

import pytest


def distance_to_water_level(
    distance_cm: float,
    bin_depth_cm: float,
    sensor_mount_height_cm: float,
) -> tuple[float, float]:
    """Mirror of WaterLevelNode._get_water_level math.

    Returns:
        Tuple of (level_cm, level_percent).
    """
    total_depth = sensor_mount_height_cm + bin_depth_cm
    water_cm = total_depth - distance_cm
    water_cm = max(0.0, min(water_cm, bin_depth_cm))
    level_percent = (water_cm / bin_depth_cm) * 100.0
    return water_cm, level_percent


def estimate_volume_mL(
    level_before_percent: float,
    level_after_percent: float,
    bin_depth_cm: float,
    bin_cross_section_cm2: float,
) -> float:
    """Estimate volume added from level change."""
    fill_cm = max(0.0, (level_after_percent - level_before_percent) / 100.0 * bin_depth_cm)
    return fill_cm * bin_cross_section_cm2 * 10.0  # cm³ → mL


class TestDistanceToLevel:
    """Tests for ultrasonic distance → water level conversion."""

    def test_full_bin(self):
        """Sensor at mount height (water at rim) → 100% level."""
        # sensor_mount_height=10, bin_depth=25
        # Full = sensor reads exactly mount height = 10cm
        level_cm, level_pct = distance_to_water_level(
            distance_cm=10.0, bin_depth_cm=25.0, sensor_mount_height_cm=10.0
        )
        assert level_cm == pytest.approx(25.0, rel=0.01)
        assert level_pct == pytest.approx(100.0, rel=0.01)

    def test_empty_bin(self):
        """Sensor reads full depth + mount height → 0% level."""
        level_cm, level_pct = distance_to_water_level(
            distance_cm=35.0, bin_depth_cm=25.0, sensor_mount_height_cm=10.0
        )
        assert level_cm == pytest.approx(0.0, abs=0.01)
        assert level_pct == pytest.approx(0.0, abs=0.01)

    def test_half_full(self):
        """Sensor at mid-depth position → 50% level."""
        # mid = mount_height + bin_depth/2 = 10 + 12.5 = 22.5
        level_cm, level_pct = distance_to_water_level(
            distance_cm=22.5, bin_depth_cm=25.0, sensor_mount_height_cm=10.0
        )
        assert level_cm == pytest.approx(12.5, rel=0.01)
        assert level_pct == pytest.approx(50.0, rel=0.01)

    def test_clamped_to_zero_on_large_distance(self):
        """Distance beyond bin bottom clamps to 0%."""
        _, level_pct = distance_to_water_level(
            distance_cm=100.0, bin_depth_cm=25.0, sensor_mount_height_cm=10.0
        )
        assert level_pct == 0.0

    def test_clamped_to_100_on_tiny_distance(self):
        """Distance less than mount height clamps to 100%."""
        _, level_pct = distance_to_water_level(
            distance_cm=2.0, bin_depth_cm=25.0, sensor_mount_height_cm=10.0
        )
        assert level_pct == pytest.approx(100.0, rel=0.01)

    def test_known_geometry_30x30_bin(self):
        """Standard 30x30cm bin, sensor at 10cm above rim.

        Water at 20cm level → distance = 10 + (25 - 20) = 15cm.
        """
        level_cm, level_pct = distance_to_water_level(
            distance_cm=15.0, bin_depth_cm=25.0, sensor_mount_height_cm=10.0
        )
        assert level_cm == pytest.approx(20.0, rel=0.01)
        assert level_pct == pytest.approx(80.0, rel=0.01)


class TestVolumeEstimation:
    """Tests for fill volume estimation from level change."""

    def test_known_fill_volume(self):
        """60% → 85% in a 30x30cm, 25cm bin.

        Fill = 0.25 × 25cm × 900cm² × 10 = 56,250 mL = 56.25L
        """
        vol = estimate_volume_mL(
            level_before_percent=60.0,
            level_after_percent=85.0,
            bin_depth_cm=25.0,
            bin_cross_section_cm2=900.0,
        )
        expected = 0.25 * 25.0 * 900.0 * 10.0
        assert vol == pytest.approx(expected, rel=0.01)

    def test_no_fill_zero_volume(self):
        vol = estimate_volume_mL(
            level_before_percent=85.0,
            level_after_percent=85.0,
            bin_depth_cm=25.0,
            bin_cross_section_cm2=900.0,
        )
        assert vol == 0.0

    def test_volume_scales_with_cross_section(self):
        """Wider bin → more volume for same level change."""
        vol_small = estimate_volume_mL(60.0, 85.0, 25.0, 400.0)
        vol_large = estimate_volume_mL(60.0, 85.0, 25.0, 900.0)
        assert vol_large == pytest.approx(vol_small * (900.0 / 400.0), rel=0.01)
