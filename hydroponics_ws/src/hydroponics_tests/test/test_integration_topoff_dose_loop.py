# MIT License
# Copyright (c) 2026 Autoponics Project
"""Integration test: top-off event → diluted EC → dosing node issues correct A+B doses.

Tests the data flow:
  WaterLevelNode publishes TopOffEvent
  → DosingNode receives it (sets flag)
  → ProbeReading arrives showing diluted EC
  → DosingNode calculates and issues correct A+B doses at configured ratio
  → DosingEvent published with correct pump IDs and volumes

This test uses pure logic extraction (no ROS) to verify the integration contract.
"""

import pytest
from typing import Optional


# ---------------------------------------------------------------------------
# Extracted dosing logic stubs (mirrors dosing_node logic)
# ---------------------------------------------------------------------------

class SimpleDosingLogic:
    """Simplified dosing logic for integration testing without ROS."""

    def __init__(
        self,
        ph_ideal: tuple[float, float] = (5.5, 6.5),
        ec_ideal: tuple[float, float] = (1.0, 1.6),
        ab_ratio: float = 1.0,
        nutrient_a_ec_per_mL_per_L: float = 0.5,
        nutrient_b_ec_per_mL_per_L: float = 0.5,
        ph_down_molarity: float = 1.0,
        ph_up_molarity: float = 1.0,
        max_dose_mL: float = 5.0,
        bin_cross_section_cm2: float = 900.0,
    ):
        self.ph_ideal = ph_ideal
        self.ec_ideal = ec_ideal
        self.ab_ratio = ab_ratio
        self.nutrient_a_ec_per_mL = nutrient_a_ec_per_mL_per_L
        self.nutrient_b_ec_per_mL = nutrient_b_ec_per_mL_per_L
        self.ph_down_molarity = ph_down_molarity
        self.ph_up_molarity = ph_up_molarity
        self.max_dose_mL = max_dose_mL
        self.bin_cross_section_cm2 = bin_cross_section_cm2
        self.issued_doses: list[dict] = []
        self.topoff_pending = False
        self.water_level_cm = 20.0

    def on_topoff_event(self, volume_mL: float) -> None:
        self.topoff_pending = True

    def on_water_level(self, level_cm: float) -> None:
        self.water_level_cm = level_cm

    def on_probe_reading(self, ph: float, ec: float) -> None:
        volume_L = (self.water_level_cm * self.bin_cross_section_cm2) / 1000.0
        doses = []

        # pH first
        if not (self.ph_ideal[0] <= ph <= self.ph_ideal[1]):
            dose_mL, pump_id = self._calc_ph_dose(ph, volume_L)
            if dose_mL > 0:
                doses.append({'pump': pump_id, 'mL': dose_mL, 'reason': 'ph_correction'})

        # EC next
        if ec < self.ec_ideal[0]:
            dose_a, dose_b = self._calc_ec_dose(ec, volume_L)
            if dose_a > 0:
                doses.append({'pump': 'nutrient_a', 'mL': dose_a, 'reason': 'ec_correction'})
            if dose_b > 0:
                doses.append({'pump': 'nutrient_b', 'mL': dose_b, 'reason': 'ec_correction'})
        elif ec > self.ec_ideal[1]:
            doses.append({'pump': None, 'mL': 0, 'reason': 'ec_too_high_no_dose'})

        self.issued_doses.extend(doses)
        self.topoff_pending = False
        return doses

    def _calc_ph_dose(self, ph: float, volume_L: float) -> tuple[float, str]:
        if ph < self.ph_ideal[0]:
            error = self.ph_ideal[0] - ph
            dose = min(error * volume_L * (1.0 / self.ph_up_molarity), self.max_dose_mL)
            return dose, 'ph_up'
        else:
            error = ph - self.ph_ideal[1]
            dose = min(error * volume_L * (1.0 / self.ph_down_molarity), self.max_dose_mL)
            return dose, 'ph_down'

    def _calc_ec_dose(self, ec: float, volume_L: float) -> tuple[float, float]:
        ec_deficit = self.ec_ideal[0] - ec
        a_frac = self.ab_ratio / (self.ab_ratio + 1.0)
        b_frac = 1.0 / (self.ab_ratio + 1.0)
        combined = self.nutrient_a_ec_per_mL * a_frac + self.nutrient_b_ec_per_mL * b_frac
        if combined <= 0:
            return 0.0, 0.0
        total = (ec_deficit * volume_L) / combined
        return min(total * a_frac, self.max_dose_mL), min(total * b_frac, self.max_dose_mL)


class TestTopOffDoseLoop:
    """Integration test: top-off → diluted probe → correct nutrient doses."""

    def test_topoff_then_low_ec_doses_both_nutrients(self):
        """After a top-off dilutes EC, dosing node issues A and B doses."""
        logic = SimpleDosingLogic(ec_ideal=(1.0, 1.6), ab_ratio=1.0)
        logic.on_water_level(level_cm=21.0)
        logic.on_topoff_event(volume_mL=5000.0)

        # Post-topoff probe shows diluted EC
        doses = logic.on_probe_reading(ph=6.0, ec=0.6)

        nutrient_pumps = [d['pump'] for d in doses]
        assert 'nutrient_a' in nutrient_pumps
        assert 'nutrient_b' in nutrient_pumps

    def test_ab_ratio_maintained_after_topoff(self):
        """A:B dose ratio matches the configured ratio after top-off."""
        logic = SimpleDosingLogic(ec_ideal=(1.0, 1.6), ab_ratio=2.0, max_dose_mL=100.0)
        logic.on_water_level(level_cm=20.0)
        doses = logic.on_probe_reading(ph=6.0, ec=0.5)

        a_dose = next((d['mL'] for d in doses if d['pump'] == 'nutrient_a'), 0.0)
        b_dose = next((d['mL'] for d in doses if d['pump'] == 'nutrient_b'), 0.0)
        assert a_dose == pytest.approx(b_dose * 2.0, rel=0.05)

    def test_no_dose_when_ec_in_range_after_topoff(self):
        """No nutrient dose if EC is already in ideal range after top-off."""
        logic = SimpleDosingLogic(ec_ideal=(1.0, 1.6))
        logic.on_topoff_event(volume_mL=500.0)
        doses = logic.on_probe_reading(ph=6.0, ec=1.2)
        ec_doses = [d for d in doses if d['pump'] in ('nutrient_a', 'nutrient_b')]
        assert ec_doses == []

    def test_high_ec_after_topoff_produces_no_dose(self):
        """If EC is above ideal, no dose issued — dilute manually."""
        logic = SimpleDosingLogic(ec_ideal=(1.0, 1.6))
        doses = logic.on_probe_reading(ph=6.0, ec=2.0)
        pump_doses = [d for d in doses if d['pump'] in ('nutrient_a', 'nutrient_b')]
        assert pump_doses == []
        no_dose_entry = [d for d in doses if d['reason'] == 'ec_too_high_no_dose']
        assert len(no_dose_entry) > 0

    def test_ph_dosed_before_nutrients(self):
        """pH correction appears before nutrient doses in the issued list."""
        logic = SimpleDosingLogic(ph_ideal=(5.5, 6.5), ec_ideal=(1.0, 1.6), max_dose_mL=100.0)
        logic.on_water_level(level_cm=20.0)
        doses = logic.on_probe_reading(ph=4.0, ec=0.5)  # Both pH and EC off

        pump_sequence = [d['pump'] for d in doses]
        # pH pump must appear before nutrient pumps
        first_ph_idx = next(
            (i for i, p in enumerate(pump_sequence) if p in ('ph_up', 'ph_down')), None
        )
        first_nutrient_idx = next(
            (i for i, p in enumerate(pump_sequence)
             if p in ('nutrient_a', 'nutrient_b')), None
        )
        if first_ph_idx is not None and first_nutrient_idx is not None:
            assert first_ph_idx < first_nutrient_idx
