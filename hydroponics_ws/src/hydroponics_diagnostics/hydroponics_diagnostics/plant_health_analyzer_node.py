# MIT License
# Copyright (c) 2026 AIdroponics Project

"""ROS2 plant health analyzer node for AIdroponics V0.1.

Purpose
-------
Synthesizes all sensor, vision, and NDVI data streams into actionable
diagnostics using a YAML-driven rule engine. Publishes a DiagnosticReport
and a PlantStatus (for the LED node) on every analysis cycle.

The rule engine evaluates all configured rules against the latest cached
state and collects every matching rule. The first matching rule that has a
non-none dosing_action determines the overall dosing recommendation. All
matching rules contribute to the recommendations list.

Subscriptions
-------------
/probe/reading      (hydroponics_msgs/ProbeReading)
/vision/measurement (hydroponics_msgs/PlantMeasurement)
/vision/ndvi        (hydroponics_msgs/NDVIReading)
/vision/ndvi_alert  (hydroponics_msgs/NDVIAlert)
/water/level        (hydroponics_msgs/WaterLevel)
/water/topoff_event (hydroponics_msgs/TopOffEvent)
/dosing/event       (hydroponics_msgs/DosingEvent)

Publications
------------
/diagnostics/report  (hydroponics_msgs/DiagnosticReport)
/bin/status          (hydroponics_msgs/PlantStatus)

Parameters
----------
  rules_config_path     — path to diagnostic_rules.yaml
  plant_ph_ideal_min/max, plant_ec_ideal_min/max, plant_temp_ideal_min/max
  plant_ph_acceptable_min/max, plant_ec_acceptable_min/max,
  plant_temp_acceptable_min/max
  plant_ndvi_healthy_min, plant_ndvi_warning_threshold
  ndvi.declining_slope_threshold
  water.consumption_alert_multiplier
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Any

import yaml

import rclpy
from rclpy.node import Node
from rclpy.callback_group import ReentrantCallbackGroup

from hydroponics_msgs.msg import (
    ProbeReading,
    PlantMeasurement,
    NDVIReading,
    NDVIAlert,
    WaterLevel,
    TopOffEvent,
    DosingEvent,
    DiagnosticReport,
    PlantStatus,
)

# Severity codes for PlantStatus.status_code
SEVERITY_INFO = 0
SEVERITY_WARNING = 1
SEVERITY_CRITICAL = 2

SEVERITY_MAP = {'info': SEVERITY_INFO, 'warning': SEVERITY_WARNING, 'critical': SEVERITY_CRITICAL}


class PlantHealthAnalyzerNode(Node):
    """YAML rule engine that synthesizes all data into plant health diagnostics."""

    def __init__(self) -> None:
        super().__init__('plant_health_analyzer_node')
        self._cb_group = ReentrantCallbackGroup()

        # --- Parameters ---
        self.declare_parameter('rules_config_path', '')
        self.declare_parameter('plant_ph_ideal_min', 5.5)
        self.declare_parameter('plant_ph_ideal_max', 6.5)
        self.declare_parameter('plant_ph_acceptable_min', 5.0)
        self.declare_parameter('plant_ph_acceptable_max', 6.8)
        self.declare_parameter('plant_ec_ideal_min', 1.0)
        self.declare_parameter('plant_ec_ideal_max', 1.6)
        self.declare_parameter('plant_ec_acceptable_min', 0.8)
        self.declare_parameter('plant_ec_acceptable_max', 2.0)
        self.declare_parameter('plant_temp_ideal_min', 18.0)
        self.declare_parameter('plant_temp_ideal_max', 27.0)
        self.declare_parameter('plant_temp_acceptable_min', 15.0)
        self.declare_parameter('plant_temp_acceptable_max', 30.0)
        self.declare_parameter('plant_ndvi_healthy_min', 0.3)
        self.declare_parameter('plant_ndvi_warning_threshold', 0.2)
        self.declare_parameter('ndvi.declining_slope_threshold', -0.002)
        self.declare_parameter('water.consumption_alert_multiplier', 1.5)

        def get_float(n: str) -> float:
            return self.get_parameter(n).get_parameter_value().double_value

        self._ph_ideal_min: float = get_float('plant_ph_ideal_min')
        self._ph_ideal_max: float = get_float('plant_ph_ideal_max')
        self._ph_acceptable_min: float = get_float('plant_ph_acceptable_min')
        self._ph_acceptable_max: float = get_float('plant_ph_acceptable_max')
        self._ec_ideal_min: float = get_float('plant_ec_ideal_min')
        self._ec_ideal_max: float = get_float('plant_ec_ideal_max')
        self._ec_acceptable_min: float = get_float('plant_ec_acceptable_min')
        self._ec_acceptable_max: float = get_float('plant_ec_acceptable_max')
        self._temp_ideal_min: float = get_float('plant_temp_ideal_min')
        self._temp_ideal_max: float = get_float('plant_temp_ideal_max')
        self._temp_acceptable_min: float = get_float('plant_temp_acceptable_min')
        self._temp_acceptable_max: float = get_float('plant_temp_acceptable_max')
        self._ndvi_healthy_min: float = get_float('plant_ndvi_healthy_min')
        self._ndvi_warning_threshold: float = get_float('plant_ndvi_warning_threshold')
        self._ndvi_declining_threshold: float = get_float('ndvi.declining_slope_threshold')
        self._consumption_alert_multiplier: float = get_float('water.consumption_alert_multiplier')

        # --- Load rules ---
        rules_path_param = (
            self.get_parameter('rules_config_path').get_parameter_value().string_value
        )
        self._rules: list[dict[str, Any]] = self._load_rules(rules_path_param)

        # --- Cached state (updated by subscriptions) ---
        self._latest_probe: Optional[ProbeReading] = None
        self._latest_measurement: Optional[PlantMeasurement] = None
        self._latest_ndvi: Optional[NDVIReading] = None
        self._latest_ndvi_alert: Optional[NDVIAlert] = None
        self._latest_water: Optional[WaterLevel] = None
        self._topoff_volume_history: list[float] = []

        # --- Publishers ---
        self._pub_report = self.create_publisher(DiagnosticReport, '/diagnostics/report', 10)
        self._pub_status = self.create_publisher(PlantStatus, '/bin/status', 10)

        # --- Subscriptions ---
        self._sub_probe = self.create_subscription(
            ProbeReading, '/probe/reading', self._on_probe, 10,
            callback_group=self._cb_group
        )
        self._sub_measurement = self.create_subscription(
            PlantMeasurement, '/vision/measurement', self._on_measurement, 10,
            callback_group=self._cb_group
        )
        self._sub_ndvi = self.create_subscription(
            NDVIReading, '/vision/ndvi', self._on_ndvi, 10,
            callback_group=self._cb_group
        )
        self._sub_ndvi_alert = self.create_subscription(
            NDVIAlert, '/vision/ndvi_alert', self._on_ndvi_alert, 10,
            callback_group=self._cb_group
        )
        self._sub_water = self.create_subscription(
            WaterLevel, '/water/level', self._on_water, 10,
            callback_group=self._cb_group
        )
        self._sub_topoff = self.create_subscription(
            TopOffEvent, '/water/topoff_event', self._on_topoff, 10,
            callback_group=self._cb_group
        )
        self._sub_dosing = self.create_subscription(
            DosingEvent, '/dosing/event', self._on_dosing, 10,
            callback_group=self._cb_group
        )

        self.get_logger().info(
            f'PlantHealthAnalyzerNode ready — {len(self._rules)} rules loaded'
        )

    # -------------------------------------------------------------------------
    # Subscriptions
    # -------------------------------------------------------------------------

    def _on_probe(self, msg: ProbeReading) -> None:
        self._latest_probe = msg
        self._run_analysis()

    def _on_measurement(self, msg: PlantMeasurement) -> None:
        self._latest_measurement = msg
        self._run_analysis()

    def _on_ndvi(self, msg: NDVIReading) -> None:
        self._latest_ndvi = msg
        self._run_analysis()

    def _on_ndvi_alert(self, msg: NDVIAlert) -> None:
        self._latest_ndvi_alert = msg

    def _on_water(self, msg: WaterLevel) -> None:
        self._latest_water = msg

    def _on_topoff(self, msg: TopOffEvent) -> None:
        self._topoff_volume_history.append(msg.volume_added_mL)

    def _on_dosing(self, msg: DosingEvent) -> None:
        # Log dosing for future correlation — not used in rule evaluation currently
        self.get_logger().debug(
            f'Dosing event: {msg.pump_id} {msg.dose_mL:.2f} mL — {msg.reason}'
        )

    # -------------------------------------------------------------------------
    # Analysis
    # -------------------------------------------------------------------------

    def _run_analysis(self) -> None:
        """Evaluate all rules against current state and publish results."""
        if self._latest_probe is None:
            return  # Need at minimum a probe reading

        state = self._build_state()
        matching_rules = []
        all_recommendations = []
        all_symptoms = list(state.get('visual_symptoms', []))
        overall_severity = SEVERITY_INFO

        for rule in self._rules:
            if self._evaluate_rule(rule, state):
                matching_rules.append(rule['name'])
                all_recommendations.append(rule['recommendation'])
                rule_severity = SEVERITY_MAP.get(rule.get('severity', 'info'), SEVERITY_INFO)
                if rule_severity > overall_severity:
                    overall_severity = rule_severity

        if not matching_rules:
            # No rules matched — default to healthy
            matching_rules = ['no_matching_rule']
            all_recommendations = ['No diagnostic rule matched current state. System monitoring.']

        stamp = self.get_clock().now().to_msg()

        # Build DiagnosticReport
        report = DiagnosticReport()
        report.detected_symptoms = all_symptoms
        report.active_rules = matching_rules
        report.recommendations = all_recommendations
        report.overall_severity = overall_severity
        report.probe_ph = self._latest_probe.ph if self._latest_probe else 0.0
        report.probe_ec = self._latest_probe.ec_mS_cm if self._latest_probe else 0.0
        report.probe_temp = self._latest_probe.temperature_C if self._latest_probe else 0.0
        report.plant_height_cm = (
            self._latest_measurement.height_cm if self._latest_measurement else 0.0
        )
        report.plant_area_cm2 = (
            self._latest_measurement.canopy_area_cm2 if self._latest_measurement else 0.0
        )
        report.mean_ndvi = self._latest_ndvi.mean_ndvi if self._latest_ndvi else 0.0
        report.ndvi_trend_slope = (
            self._latest_ndvi.ndvi_trend_slope if self._latest_ndvi else 0.0
        )
        report.water_level_percent = (
            self._latest_water.level_percent if self._latest_water else 0.0
        )
        report.timestamp = stamp
        self._pub_report.publish(report)

        # Build PlantStatus for LED node
        severity_to_summary = {
            SEVERITY_INFO: 'HEALTHY',
            SEVERITY_WARNING: 'WARNING',
            SEVERITY_CRITICAL: 'CRITICAL',
        }
        status = PlantStatus()
        status.status_code = overall_severity
        status.summary = severity_to_summary.get(overall_severity, 'UNKNOWN')
        status.active_warnings = [
            r['name'] for r in self._rules
            if r['name'] in matching_rules and
            SEVERITY_MAP.get(r.get('severity', 'info'), 0) >= SEVERITY_WARNING
        ]
        status.recommendations = all_recommendations
        status.last_analysis = stamp
        self._pub_status.publish(status)

        self.get_logger().info(
            f'Analysis: severity={status.summary}, '
            f'rules={matching_rules}, '
            f'pH={report.probe_ph:.2f}, EC={report.probe_ec:.3f}, '
            f'NDVI={report.mean_ndvi:.3f}'
        )

    # -------------------------------------------------------------------------
    # State builder
    # -------------------------------------------------------------------------

    def _build_state(self) -> dict[str, Any]:
        """Build a flat state dict from all cached topic data.

        Returns:
            Dict with keys for each condition predicate used by rules.
        """
        state: dict[str, Any] = {}

        # pH predicates
        if self._latest_probe:
            ph = self._latest_probe.ph
            ec = self._latest_probe.ec_mS_cm
            temp = self._latest_probe.temperature_C

            state['ph'] = (
                'in_ideal' if self._ph_ideal_min <= ph <= self._ph_ideal_max
                else 'above_ideal' if ph > self._ph_ideal_max
                else 'below_ideal'
            )
            if ph > self._ph_acceptable_max:
                state['ph'] = 'above_acceptable'
            elif ph < self._ph_acceptable_min:
                state['ph'] = 'below_acceptable'

            state['ec'] = (
                'in_ideal' if self._ec_ideal_min <= ec <= self._ec_ideal_max
                else 'above_ideal' if ec > self._ec_ideal_max
                else 'below_ideal'
            )
            if ec > self._ec_acceptable_max:
                state['ec'] = 'above_acceptable'
            elif ec < self._ec_acceptable_min:
                state['ec'] = 'below_acceptable'

            state['temperature'] = (
                'in_ideal' if self._temp_ideal_min <= temp <= self._temp_ideal_max
                else 'outside_acceptable'
                if temp < self._temp_acceptable_min or temp > self._temp_acceptable_max
                else 'outside_ideal'
            )
        else:
            state['ph'] = 'unknown'
            state['ec'] = 'unknown'
            state['temperature'] = 'unknown'

        # NDVI predicates
        if self._latest_ndvi:
            ndvi = self._latest_ndvi.mean_ndvi
            slope = self._latest_ndvi.ndvi_trend_slope
            state['ndvi'] = (
                'above_healthy_min' if ndvi >= self._ndvi_healthy_min
                else 'below_healthy_min' if ndvi >= self._ndvi_warning_threshold
                else 'below_warning'
            )
            state['ndvi_trend'] = (
                'declining' if slope < self._ndvi_declining_threshold
                else 'stable_or_rising'
            )
        else:
            state['ndvi'] = 'unknown'
            state['ndvi_trend'] = 'unknown'

        # Visual symptoms
        symptoms: list[str] = []
        if self._latest_measurement:
            symptoms = list(self._latest_measurement.visual_symptoms)
        state['visual_symptoms'] = symptoms

        if symptoms:
            # Map to predicate form for rule evaluation
            state['visual'] = symptoms[0] if len(symptoms) == 1 else symptoms
        else:
            state['visual'] = 'no_symptoms'

        # Water consumption rate
        if len(self._topoff_volume_history) >= 3:
            recent = self._topoff_volume_history[-1]
            avg = sum(self._topoff_volume_history[:-1]) / len(self._topoff_volume_history[:-1])
            state['water_consumption_rate'] = (
                'above_normal'
                if recent > avg * self._consumption_alert_multiplier
                else 'normal'
            )
        else:
            state['water_consumption_rate'] = 'normal'

        return state

    # -------------------------------------------------------------------------
    # Rule evaluation
    # -------------------------------------------------------------------------

    def _evaluate_rule(self, rule: dict[str, Any], state: dict[str, Any]) -> bool:
        """Check if all conditions in a rule match the current state.

        Args:
            rule: Rule dict from diagnostic_rules.yaml.
            state: Current state dict from _build_state.

        Returns:
            True if all conditions match, False otherwise.
        """
        conditions: dict[str, Any] = rule.get('conditions', {})
        for key, expected_value in conditions.items():
            actual = state.get(key, 'unknown')

            if key == 'visual':
                # Visual can be a list — check if expected value is in the symptom list
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

    # -------------------------------------------------------------------------
    # Rule loading
    # -------------------------------------------------------------------------

    def _load_rules(self, config_path: str) -> list[dict[str, Any]]:
        """Load diagnostic rules from YAML file.

        Falls back to an empty list with a warning if the file is missing.

        Args:
            config_path: Path to diagnostic_rules.yaml.

        Returns:
            List of rule dicts.
        """
        if not config_path:
            self.get_logger().warn(
                'rules_config_path not set — no diagnostic rules loaded'
            )
            return []

        path = Path(os.path.expanduser(config_path))
        if not path.exists():
            self.get_logger().warn(
                f'Diagnostic rules file not found: {path} — no rules loaded'
            )
            return []

        with open(path, 'r') as f:
            data = yaml.safe_load(f)

        rules = data.get('rules', [])
        self.get_logger().info(f'Loaded {len(rules)} diagnostic rules from {path}')
        return rules


def main(args: Optional[list[str]] = None) -> None:
    """Initialise rclpy, spin the PlantHealthAnalyzerNode, and shut down cleanly."""
    rclpy.init(args=args)
    node = PlantHealthAnalyzerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info('PlantHealthAnalyzerNode interrupted')
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
