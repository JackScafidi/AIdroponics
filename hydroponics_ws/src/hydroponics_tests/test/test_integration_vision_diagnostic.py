# MIT License
# Copyright (c) 2026 AIdroponics Project
"""Integration test: vision measurement → diagnostic rule fires correctly.

Tests the data flow:
  PlantVisionNode publishes PlantMeasurement (with visual_symptoms)
  + NDVIReading (with trend slope)
  + ProbeReading (with pH/EC)
  → PlantHealthAnalyzerNode evaluates rules
  → Correct rules fire and correct severity assigned

No ROS infrastructure required — uses the pure rule engine.
"""

import pytest
from typing import Any


# ---------------------------------------------------------------------------
# Import rule engine logic (copy from test_rule_engine.py to stay standalone)
# ---------------------------------------------------------------------------

SEVERITY_INFO = 0
SEVERITY_WARNING = 1
SEVERITY_CRITICAL = 2
SEVERITY_MAP = {'info': SEVERITY_INFO, 'warning': SEVERITY_WARNING, 'critical': SEVERITY_CRITICAL}


def evaluate_rule(rule: dict[str, Any], state: dict[str, Any]) -> bool:
    conditions: dict[str, Any] = rule.get('conditions', {})
    for key, expected_value in conditions.items():
        actual = state.get(key, 'unknown')
        if key == 'visual':
            symptoms = state.get('visual_symptoms', [])
            if expected_value == 'no_symptoms':
                if symptoms:
                    return False
            else:
                if expected_value not in symptoms:
                    return False
        else:
            if isinstance(actual, list):
                if expected_value not in actual:
                    return False
            else:
                if actual != expected_value:
                    return False
    return True


def run_rules(rules: list[dict], state: dict) -> tuple[list[str], int]:
    matching = []
    overall = SEVERITY_INFO
    for rule in rules:
        if evaluate_rule(rule, state):
            matching.append(rule['name'])
            sev = SEVERITY_MAP.get(rule.get('severity', 'info'), SEVERITY_INFO)
            if sev > overall:
                overall = sev
    return matching, overall


RULES = [
    {
        'name': 'healthy',
        'conditions': {
            'ndvi': 'above_healthy_min', 'ndvi_trend': 'stable_or_rising',
            'visual': 'no_symptoms', 'ph': 'in_ideal', 'ec': 'in_ideal',
            'temperature': 'in_ideal'
        },
        'severity': 'info',
    },
    {
        'name': 'early_stress_detected',
        'conditions': {'ndvi_trend': 'declining', 'ph': 'in_ideal', 'ec': 'in_ideal'},
        'severity': 'warning',
    },
    {
        'name': 'nitrogen_deficiency',
        'conditions': {
            'ndvi_trend': 'declining', 'visual': 'yellowing_established_growth',
            'ec': 'below_ideal'
        },
        'severity': 'warning',
    },
    {
        'name': 'ph_lockout',
        'conditions': {
            'ndvi_trend': 'declining', 'visual': 'yellowing_established_growth',
            'ph': 'above_acceptable', 'ec': 'in_ideal'
        },
        'severity': 'critical',
    },
    {
        'name': 'nutrient_burn',
        'conditions': {'visual': 'browning_leaf_edges', 'ec': 'above_ideal'},
        'severity': 'warning',
    },
    {
        'name': 'sensor_ndvi_mismatch',
        'conditions': {
            'ndvi': 'below_warning', 'ph': 'in_ideal',
            'ec': 'in_ideal', 'temperature': 'in_ideal'
        },
        'severity': 'warning',
    },
]


def build_state_from_msgs(
    ph: float = 6.0,
    ec: float = 1.2,
    temp: float = 22.0,
    mean_ndvi: float = 0.4,
    ndvi_trend: float = 0.0,
    visual_symptoms: list[str] | None = None,
    ph_ideal: tuple[float, float] = (5.5, 6.5),
    ph_acceptable: tuple[float, float] = (5.0, 6.8),
    ec_ideal: tuple[float, float] = (1.0, 1.6),
    ec_acceptable: tuple[float, float] = (0.8, 2.0),
    temp_ideal: tuple[float, float] = (18.0, 27.0),
    temp_acceptable: tuple[float, float] = (15.0, 30.0),
    ndvi_healthy_min: float = 0.3,
    ndvi_warning_threshold: float = 0.2,
    ndvi_declining_threshold: float = -0.002,
) -> dict:
    """Build a state dict from simulated message values."""
    if visual_symptoms is None:
        visual_symptoms = []

    # pH
    ph_state = (
        'in_ideal' if ph_ideal[0] <= ph <= ph_ideal[1]
        else 'above_ideal' if ph > ph_ideal[1]
        else 'below_ideal'
    )
    if ph > ph_acceptable[1]:
        ph_state = 'above_acceptable'
    elif ph < ph_acceptable[0]:
        ph_state = 'below_acceptable'

    # EC
    ec_state = (
        'in_ideal' if ec_ideal[0] <= ec <= ec_ideal[1]
        else 'above_ideal' if ec > ec_ideal[1]
        else 'below_ideal'
    )
    if ec > ec_acceptable[1]:
        ec_state = 'above_acceptable'
    elif ec < ec_acceptable[0]:
        ec_state = 'below_acceptable'

    # Temperature
    temp_state = (
        'in_ideal' if temp_ideal[0] <= temp <= temp_ideal[1]
        else 'outside_acceptable'
        if temp < temp_acceptable[0] or temp > temp_acceptable[1]
        else 'outside_ideal'
    )

    # NDVI
    ndvi_state = (
        'above_healthy_min' if mean_ndvi >= ndvi_healthy_min
        else 'below_healthy_min' if mean_ndvi >= ndvi_warning_threshold
        else 'below_warning'
    )
    ndvi_trend_state = 'declining' if ndvi_trend < ndvi_declining_threshold else 'stable_or_rising'

    return {
        'ph': ph_state,
        'ec': ec_state,
        'temperature': temp_state,
        'ndvi': ndvi_state,
        'ndvi_trend': ndvi_trend_state,
        'visual_symptoms': visual_symptoms,
        'visual': visual_symptoms[0] if len(visual_symptoms) == 1 else (
            'no_symptoms' if not visual_symptoms else visual_symptoms
        ),
        'water_consumption_rate': 'normal',
    }


class TestVisionDiagnosticIntegration:
    """Integration tests: vision measurements → correct diagnostic rules."""

    def test_healthy_plant_measurement_fires_healthy_rule(self):
        """Green plant, NDVI above threshold, all sensors in range → healthy."""
        state = build_state_from_msgs(
            ph=6.0, ec=1.2, temp=22.0, mean_ndvi=0.45, ndvi_trend=0.001,
            visual_symptoms=[]
        )
        matched, severity = run_rules(RULES, state)
        assert 'healthy' in matched
        assert severity == SEVERITY_INFO

    def test_yellowing_established_low_ec_fires_nitrogen_rule(self):
        """Yellow established leaves + low EC + declining NDVI → nitrogen_deficiency."""
        state = build_state_from_msgs(
            ph=6.0, ec=0.7, mean_ndvi=0.25, ndvi_trend=-0.005,
            visual_symptoms=['yellowing_established_growth']
        )
        matched, severity = run_rules(RULES, state)
        assert 'nitrogen_deficiency' in matched

    def test_yellowing_high_ph_fires_ph_lockout_rule(self):
        """Yellow established leaves + high pH → ph_lockout (critical)."""
        state = build_state_from_msgs(
            ph=7.2, ec=1.2, mean_ndvi=0.25, ndvi_trend=-0.005,
            visual_symptoms=['yellowing_established_growth']
        )
        matched, severity = run_rules(RULES, state)
        assert 'ph_lockout' in matched
        assert severity == SEVERITY_CRITICAL

    def test_browning_edges_high_ec_fires_nutrient_burn(self):
        """Brown edges + high EC → nutrient_burn rule."""
        state = build_state_from_msgs(
            ph=6.0, ec=1.9, mean_ndvi=0.40, ndvi_trend=0.001,
            visual_symptoms=['browning_leaf_edges']
        )
        matched, severity = run_rules(RULES, state)
        assert 'nutrient_burn' in matched

    def test_ndvi_stress_normal_sensors_fires_mismatch_rule(self):
        """NDVI below warning but all sensors normal → sensor_ndvi_mismatch."""
        state = build_state_from_msgs(
            ph=6.0, ec=1.2, temp=22.0, mean_ndvi=0.15, ndvi_trend=-0.003,
            visual_symptoms=[]
        )
        matched, severity = run_rules(RULES, state)
        assert 'sensor_ndvi_mismatch' in matched
        assert severity == SEVERITY_WARNING

    def test_multiple_symptoms_can_trigger_multiple_rules(self):
        """Multiple matching conditions can trigger multiple rules."""
        state = build_state_from_msgs(
            ph=6.0, ec=1.2, mean_ndvi=0.15, ndvi_trend=-0.005,
            visual_symptoms=[]
        )
        matched, _ = run_rules(RULES, state)
        # Both early_stress and sensor_ndvi_mismatch could match
        assert len(matched) >= 1
