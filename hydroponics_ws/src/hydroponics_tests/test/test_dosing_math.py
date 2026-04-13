# MIT License
# Copyright (c) 2026 Autoponics Project
"""Unit tests for dosing math in dosing_node."""

import pytest


# ---------------------------------------------------------------------------
# Extracted dosing calculation functions (pure math — no ROS dependency)
# ---------------------------------------------------------------------------

def calculate_ph_dose(
    current_ph: float,
    ph_ideal_min: float,
    ph_ideal_max: float,
    volume_L: float,
    ph_down_molarity: float,
    ph_up_molarity: float,
    max_dose_mL: float,
) -> tuple[float, str]:
    """Pure pH dose calculation logic mirrored from dosing_node."""
    if current_ph < ph_ideal_min:
        ph_error = ph_ideal_min - current_ph
        molarity = ph_up_molarity
        pump_id = 'ph_up'
    else:
        ph_error = current_ph - ph_ideal_max
        molarity = ph_down_molarity
        pump_id = 'ph_down'
    dose_mL = ph_error * volume_L * (1.0 / molarity)
    dose_mL = min(dose_mL, max_dose_mL)
    return dose_mL, pump_id


def calculate_ec_dose(
    current_ec: float,
    ec_ideal_min: float,
    volume_L: float,
    nutrient_a_ec_per_mL_per_L: float,
    nutrient_b_ec_per_mL_per_L: float,
    ab_ratio: float,
    max_dose_mL: float,
) -> tuple[float, float]:
    """Pure EC dose calculation logic mirrored from dosing_node."""
    ec_deficit = ec_ideal_min - current_ec
    a_fraction = ab_ratio / (ab_ratio + 1.0)
    b_fraction = 1.0 / (ab_ratio + 1.0)
    combined_ec_rate = (
        nutrient_a_ec_per_mL_per_L * a_fraction +
        nutrient_b_ec_per_mL_per_L * b_fraction
    )
    if combined_ec_rate <= 0:
        return 0.0, 0.0
    total_dose_mL = (ec_deficit * volume_L) / combined_ec_rate
    dose_a_mL = min(total_dose_mL * a_fraction, max_dose_mL)
    dose_b_mL = min(total_dose_mL * b_fraction, max_dose_mL)
    return dose_a_mL, dose_b_mL


def compute_solution_volume_L(
    water_level_cm: float, bin_cross_section_cm2: float
) -> float:
    volume_cm3 = water_level_cm * bin_cross_section_cm2
    return volume_cm3 / 1000.0


class TestPhDoseMath:
    """Tests for pH dose calculation correctness."""

    def test_ph_too_high_doses_ph_down(self):
        """pH above ideal maximum should trigger ph_down pump."""
        dose_mL, pump_id = calculate_ph_dose(
            current_ph=7.0, ph_ideal_min=5.5, ph_ideal_max=6.5,
            volume_L=10.0, ph_down_molarity=1.0, ph_up_molarity=1.0,
            max_dose_mL=5.0
        )
        assert pump_id == 'ph_down'
        assert dose_mL > 0

    def test_ph_too_low_doses_ph_up(self):
        """pH below ideal minimum should trigger ph_up pump."""
        dose_mL, pump_id = calculate_ph_dose(
            current_ph=4.5, ph_ideal_min=5.5, ph_ideal_max=6.5,
            volume_L=10.0, ph_down_molarity=1.0, ph_up_molarity=1.0,
            max_dose_mL=5.0
        )
        assert pump_id == 'ph_up'
        assert dose_mL > 0

    def test_ph_dose_scales_with_volume(self):
        """Larger solution volume requires larger dose."""
        dose_5L, _ = calculate_ph_dose(
            current_ph=7.0, ph_ideal_min=5.5, ph_ideal_max=6.5,
            volume_L=5.0, ph_down_molarity=1.0, ph_up_molarity=1.0,
            max_dose_mL=100.0
        )
        dose_10L, _ = calculate_ph_dose(
            current_ph=7.0, ph_ideal_min=5.5, ph_ideal_max=6.5,
            volume_L=10.0, ph_down_molarity=1.0, ph_up_molarity=1.0,
            max_dose_mL=100.0
        )
        assert dose_10L == pytest.approx(dose_5L * 2, rel=0.01)

    def test_ph_dose_capped_at_max(self):
        """Dose must never exceed max_dose_mL."""
        dose_mL, _ = calculate_ph_dose(
            current_ph=9.0, ph_ideal_min=5.5, ph_ideal_max=6.5,
            volume_L=100.0, ph_down_molarity=0.1, ph_up_molarity=1.0,
            max_dose_mL=5.0
        )
        assert dose_mL <= 5.0

    def test_ph_dose_with_higher_molarity_is_smaller(self):
        """Higher molarity adjuster requires less volume."""
        dose_1M, _ = calculate_ph_dose(
            current_ph=7.0, ph_ideal_min=5.5, ph_ideal_max=6.5,
            volume_L=10.0, ph_down_molarity=1.0, ph_up_molarity=1.0,
            max_dose_mL=100.0
        )
        dose_2M, _ = calculate_ph_dose(
            current_ph=7.0, ph_ideal_min=5.5, ph_ideal_max=6.5,
            volume_L=10.0, ph_down_molarity=2.0, ph_up_molarity=1.0,
            max_dose_mL=100.0
        )
        assert dose_2M == pytest.approx(dose_1M / 2.0, rel=0.01)


class TestECDoseMath:
    """Tests for EC dose calculation correctness."""

    def test_ec_deficit_produces_dose(self):
        """EC below ideal minimum should produce positive doses."""
        dose_a, dose_b = calculate_ec_dose(
            current_ec=0.5, ec_ideal_min=1.0, volume_L=10.0,
            nutrient_a_ec_per_mL_per_L=0.5, nutrient_b_ec_per_mL_per_L=0.5,
            ab_ratio=1.0, max_dose_mL=5.0
        )
        assert dose_a > 0
        assert dose_b > 0

    def test_ec_ab_ratio_1_to_1(self):
        """A:B ratio of 1:1 should produce equal doses."""
        dose_a, dose_b = calculate_ec_dose(
            current_ec=0.5, ec_ideal_min=1.0, volume_L=10.0,
            nutrient_a_ec_per_mL_per_L=0.5, nutrient_b_ec_per_mL_per_L=0.5,
            ab_ratio=1.0, max_dose_mL=100.0
        )
        assert dose_a == pytest.approx(dose_b, rel=0.01)

    def test_ec_ab_ratio_2_to_1(self):
        """A:B ratio of 2:1 means A dose is twice B dose."""
        dose_a, dose_b = calculate_ec_dose(
            current_ec=0.5, ec_ideal_min=1.0, volume_L=10.0,
            nutrient_a_ec_per_mL_per_L=0.5, nutrient_b_ec_per_mL_per_L=0.5,
            ab_ratio=2.0, max_dose_mL=100.0
        )
        assert dose_a == pytest.approx(dose_b * 2.0, rel=0.01)

    def test_ec_dose_capped_at_max(self):
        """Each pump dose must not exceed max_dose_mL."""
        dose_a, dose_b = calculate_ec_dose(
            current_ec=0.0, ec_ideal_min=5.0, volume_L=100.0,
            nutrient_a_ec_per_mL_per_L=0.1, nutrient_b_ec_per_mL_per_L=0.1,
            ab_ratio=1.0, max_dose_mL=5.0
        )
        assert dose_a <= 5.0
        assert dose_b <= 5.0

    def test_ec_scales_with_volume(self):
        """Larger volume needs larger dose to achieve same EC rise."""
        dose_a_5L, _ = calculate_ec_dose(
            current_ec=0.5, ec_ideal_min=1.0, volume_L=5.0,
            nutrient_a_ec_per_mL_per_L=0.5, nutrient_b_ec_per_mL_per_L=0.5,
            ab_ratio=1.0, max_dose_mL=100.0
        )
        dose_a_10L, _ = calculate_ec_dose(
            current_ec=0.5, ec_ideal_min=1.0, volume_L=10.0,
            nutrient_a_ec_per_mL_per_L=0.5, nutrient_b_ec_per_mL_per_L=0.5,
            ab_ratio=1.0, max_dose_mL=100.0
        )
        assert dose_a_10L == pytest.approx(dose_a_5L * 2, rel=0.01)


class TestSolutionVolume:
    """Tests for solution volume calculation."""

    def test_standard_bin(self):
        """30x30cm bin at 20cm water level = 18L."""
        vol = compute_solution_volume_L(water_level_cm=20.0, bin_cross_section_cm2=900.0)
        assert vol == pytest.approx(18.0, rel=0.01)

    def test_zero_level_is_zero_volume(self):
        vol = compute_solution_volume_L(water_level_cm=0.0, bin_cross_section_cm2=900.0)
        assert vol == 0.0
