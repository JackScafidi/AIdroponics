# MIT License
# Copyright (c) 2026 Autoponics Project
"""Unit tests for the diagnostic rule engine — 10 defined scenarios."""

import pytest
from typing import Any


# ---------------------------------------------------------------------------
# Minimal rule engine extracted from plant_health_analyzer_node for testing
# ---------------------------------------------------------------------------

SEVERITY_INFO = 0
SEVERITY_WARNING = 1
SEVERITY_CRITICAL = 2
SEVERITY_MAP = {'info': SEVERITY_INFO, 'warning': SEVERITY_WARNING, 'critical': SEVERITY_CRITICAL}


def evaluate_rule(rule: dict[str, Any], state: dict[str, Any]) -> bool:
    """Mirror of PlantHealthAnalyzerNode._evaluate_rule."""
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
    """Evaluate all rules and return (matched_rule_names, overall_severity)."""
    matching = []
    overall_severity = SEVERITY_INFO
    for rule in rules:
        if evaluate_rule(rule, state):
            matching.append(rule['name'])
            severity = SEVERITY_MAP.get(rule.get('severity', 'info'), SEVERITY_INFO)
            if severity > overall_severity:
                overall_severity = severity
    return matching, overall_severity


# ---------------------------------------------------------------------------
# Rules (subset matching diagnostic_rules.yaml for testing)
# ---------------------------------------------------------------------------

RULES = [
    {
        'name': 'healthy',
        'conditions': {
            'ndvi': 'above_healthy_min', 'ndvi_trend': 'stable_or_rising',
            'visual': 'no_symptoms', 'ph': 'in_ideal', 'ec': 'in_ideal',
            'temperature': 'in_ideal'
        },
        'severity': 'info', 'dosing_action': 'none',
        'recommendation': 'Plant is healthy.',
    },
    {
        'name': 'early_stress_detected',
        'conditions': {'ndvi_trend': 'declining', 'ph': 'in_ideal', 'ec': 'in_ideal'},
        'severity': 'warning', 'dosing_action': 'none',
        'recommendation': 'NDVI declining but sensors in range.',
    },
    {
        'name': 'nitrogen_deficiency',
        'conditions': {
            'ndvi_trend': 'declining', 'visual': 'yellowing_established_growth',
            'ec': 'below_ideal'
        },
        'severity': 'warning', 'dosing_action': 'increase_ec',
        'recommendation': 'Likely nitrogen deficiency.',
    },
    {
        'name': 'ph_lockout',
        'conditions': {
            'ndvi_trend': 'declining', 'visual': 'yellowing_established_growth',
            'ph': 'above_acceptable', 'ec': 'in_ideal'
        },
        'severity': 'critical', 'dosing_action': 'decrease_ph',
        'recommendation': 'pH too high — nutrient lockout.',
    },
    {
        'name': 'iron_deficiency',
        'conditions': {
            'ndvi_trend': 'declining', 'visual': 'symptomatic_new_growth',
            'ph': 'above_ideal'
        },
        'severity': 'warning', 'dosing_action': 'decrease_ph',
        'recommendation': 'Iron deficiency suspected.',
    },
    {
        'name': 'nutrient_burn',
        'conditions': {'visual': 'browning_leaf_edges', 'ec': 'above_ideal'},
        'severity': 'warning', 'dosing_action': 'none',
        'recommendation': 'Possible nutrient burn.',
    },
    {
        'name': 'temperature_stress',
        'conditions': {'temperature': 'outside_acceptable'},
        'severity': 'critical', 'dosing_action': 'none',
        'recommendation': 'Solution temperature outside acceptable range.',
    },
    {
        'name': 'growth_stall',
        'conditions': {
            'visual': 'growth_stall', 'ndvi': 'above_healthy_min',
            'ec': 'in_ideal', 'ph': 'in_ideal'
        },
        'severity': 'warning', 'dosing_action': 'none',
        'recommendation': 'Plant growth has stalled.',
    },
    {
        'name': 'rapid_water_consumption',
        'conditions': {'water_consumption_rate': 'above_normal'},
        'severity': 'info', 'dosing_action': 'none',
        'recommendation': 'Water consumption increased significantly.',
    },
    {
        'name': 'sensor_ndvi_mismatch',
        'conditions': {
            'ndvi': 'below_warning', 'ph': 'in_ideal',
            'ec': 'in_ideal', 'temperature': 'in_ideal'
        },
        'severity': 'warning', 'dosing_action': 'none',
        'recommendation': 'NDVI stressed but sensors normal.',
    },
]


class TestRuleEngine:
    """10 scenarios matching the diagnostic_rules.yaml rule set."""

    def test_01_healthy(self):
        state = {
            'ndvi': 'above_healthy_min', 'ndvi_trend': 'stable_or_rising',
            'visual_symptoms': [], 'visual': 'no_symptoms',
            'ph': 'in_ideal', 'ec': 'in_ideal', 'temperature': 'in_ideal',
            'water_consumption_rate': 'normal',
        }
        matched, severity = run_rules(RULES, state)
        assert 'healthy' in matched
        assert severity == SEVERITY_INFO

    def test_02_early_stress_ndvi_only(self):
        state = {
            'ndvi': 'above_healthy_min', 'ndvi_trend': 'declining',
            'visual_symptoms': [], 'visual': 'no_symptoms',
            'ph': 'in_ideal', 'ec': 'in_ideal', 'temperature': 'in_ideal',
            'water_consumption_rate': 'normal',
        }
        matched, severity = run_rules(RULES, state)
        assert 'early_stress_detected' in matched
        assert severity == SEVERITY_WARNING

    def test_03_nitrogen_deficiency(self):
        state = {
            'ndvi': 'below_healthy_min', 'ndvi_trend': 'declining',
            'visual_symptoms': ['yellowing_established_growth'],
            'visual': 'yellowing_established_growth',
            'ph': 'in_ideal', 'ec': 'below_ideal', 'temperature': 'in_ideal',
            'water_consumption_rate': 'normal',
        }
        matched, severity = run_rules(RULES, state)
        assert 'nitrogen_deficiency' in matched
        assert severity == SEVERITY_WARNING

    def test_04_ph_lockout(self):
        state = {
            'ndvi': 'below_healthy_min', 'ndvi_trend': 'declining',
            'visual_symptoms': ['yellowing_established_growth'],
            'visual': 'yellowing_established_growth',
            'ph': 'above_acceptable', 'ec': 'in_ideal', 'temperature': 'in_ideal',
            'water_consumption_rate': 'normal',
        }
        matched, severity = run_rules(RULES, state)
        assert 'ph_lockout' in matched
        assert severity == SEVERITY_CRITICAL

    def test_05_iron_deficiency(self):
        state = {
            'ndvi': 'below_healthy_min', 'ndvi_trend': 'declining',
            'visual_symptoms': ['symptomatic_new_growth'],
            'visual': 'symptomatic_new_growth',
            'ph': 'above_ideal', 'ec': 'in_ideal', 'temperature': 'in_ideal',
            'water_consumption_rate': 'normal',
        }
        matched, severity = run_rules(RULES, state)
        assert 'iron_deficiency' in matched

    def test_06_nutrient_burn(self):
        state = {
            'ndvi': 'above_healthy_min', 'ndvi_trend': 'stable_or_rising',
            'visual_symptoms': ['browning_leaf_edges'],
            'visual': 'browning_leaf_edges',
            'ph': 'in_ideal', 'ec': 'above_ideal', 'temperature': 'in_ideal',
            'water_consumption_rate': 'normal',
        }
        matched, severity = run_rules(RULES, state)
        assert 'nutrient_burn' in matched
        assert severity == SEVERITY_WARNING

    def test_07_temperature_stress(self):
        state = {
            'ndvi': 'above_healthy_min', 'ndvi_trend': 'stable_or_rising',
            'visual_symptoms': [], 'visual': 'no_symptoms',
            'ph': 'in_ideal', 'ec': 'in_ideal', 'temperature': 'outside_acceptable',
            'water_consumption_rate': 'normal',
        }
        matched, severity = run_rules(RULES, state)
        assert 'temperature_stress' in matched
        assert severity == SEVERITY_CRITICAL

    def test_08_growth_stall(self):
        state = {
            'ndvi': 'above_healthy_min', 'ndvi_trend': 'stable_or_rising',
            'visual_symptoms': ['growth_stall'],
            'visual': 'growth_stall',
            'ph': 'in_ideal', 'ec': 'in_ideal', 'temperature': 'in_ideal',
            'water_consumption_rate': 'normal',
        }
        matched, severity = run_rules(RULES, state)
        assert 'growth_stall' in matched
        assert severity == SEVERITY_WARNING

    def test_09_rapid_water_consumption(self):
        state = {
            'ndvi': 'above_healthy_min', 'ndvi_trend': 'stable_or_rising',
            'visual_symptoms': [], 'visual': 'no_symptoms',
            'ph': 'in_ideal', 'ec': 'in_ideal', 'temperature': 'in_ideal',
            'water_consumption_rate': 'above_normal',
        }
        matched, severity = run_rules(RULES, state)
        assert 'rapid_water_consumption' in matched

    def test_10_sensor_ndvi_mismatch(self):
        state = {
            'ndvi': 'below_warning', 'ndvi_trend': 'declining',
            'visual_symptoms': [], 'visual': 'no_symptoms',
            'ph': 'in_ideal', 'ec': 'in_ideal', 'temperature': 'in_ideal',
            'water_consumption_rate': 'normal',
        }
        matched, severity = run_rules(RULES, state)
        assert 'sensor_ndvi_mismatch' in matched
        assert severity == SEVERITY_WARNING
