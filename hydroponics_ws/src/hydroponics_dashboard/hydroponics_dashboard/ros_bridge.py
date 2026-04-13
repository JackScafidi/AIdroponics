# MIT License
# Copyright (c) 2026 Autoponics Project
#
# ROS2 bridge node: subscribes to all V0.1 hydroponics topics, exposes latest
# values thread-safely, holds service clients for control endpoints,
# and broadcasts JSON updates to connected WebSocket clients.

from __future__ import annotations

import json
import threading
from typing import Any, Callable, Dict, List, Optional

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy

from hydroponics_msgs.msg import (
    ProbeReading,
    NDVIReading,
    PlantMeasurement,
    WaterLevel,
    TopOffEvent,
    DosingEvent,
    PlantStatus,
    DiagnosticReport,
    NDVIAlert,
    SystemAlert,
)
from hydroponics_msgs.srv import (
    TriggerProbe,
    TriggerAeration,
    SetProbeInterval,
    CaptureVision,
)

# ---------------------------------------------------------------------------
# QoS profiles
# ---------------------------------------------------------------------------

_BEST_EFFORT_QOS = QoSProfile(
    reliability=ReliabilityPolicy.BEST_EFFORT,
    history=HistoryPolicy.KEEP_LAST,
    depth=1,
)

_RELIABLE_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
)

MAX_ALERTS: int = 50
MAX_DOSING_HISTORY: int = 200
MAX_TOPOFF_HISTORY: int = 50


# ---------------------------------------------------------------------------
# Message → dict helpers
# ---------------------------------------------------------------------------

def _ros_time_to_iso(t: Any) -> str:
    import datetime
    sec = getattr(t, "sec", 0)
    nanosec = getattr(t, "nanosec", 0)
    ts = sec + nanosec * 1e-9
    return datetime.datetime.utcfromtimestamp(ts).isoformat() + "Z"


def _probe_reading_to_dict(msg: ProbeReading) -> Dict[str, Any]:
    return {
        "ph": msg.ph,
        "ec_mS_cm": msg.ec_mS_cm,
        "temperature_C": msg.temperature_C,
        "timestamp": _ros_time_to_iso(msg.timestamp),
    }


def _ndvi_reading_to_dict(msg: NDVIReading) -> Dict[str, Any]:
    return {
        "mean_ndvi": msg.mean_ndvi,
        "median_ndvi": msg.median_ndvi,
        "std_dev_ndvi": msg.std_dev_ndvi,
        "ndvi_trend_slope": msg.ndvi_trend_slope,
        "trend_window_size": msg.trend_window_size,
        "timestamp": _ros_time_to_iso(msg.timestamp),
    }


def _plant_measurement_to_dict(msg: PlantMeasurement) -> Dict[str, Any]:
    return {
        "height_cm": msg.height_cm,
        "canopy_width_cm": msg.canopy_width_cm,
        "canopy_area_cm2": msg.canopy_area_cm2,
        "visual_symptoms": list(msg.visual_symptoms),
        "timestamp": _ros_time_to_iso(msg.timestamp),
    }


def _water_level_to_dict(msg: WaterLevel) -> Dict[str, Any]:
    return {
        "level_cm": msg.level_cm,
        "level_percent": msg.level_percent,
        "timestamp": _ros_time_to_iso(msg.timestamp),
    }


def _topoff_event_to_dict(msg: TopOffEvent) -> Dict[str, Any]:
    return {
        "volume_added_mL": msg.volume_added_mL,
        "level_before_percent": msg.level_before_percent,
        "level_after_percent": msg.level_after_percent,
        "timestamp": _ros_time_to_iso(msg.timestamp),
    }


def _dosing_event_to_dict(msg: DosingEvent) -> Dict[str, Any]:
    return {
        "pump_id": msg.pump_id,
        "dose_mL": msg.dose_mL,
        "duration_seconds": msg.duration_seconds,
        "reason": msg.reason,
        "ph_before": msg.ph_before,
        "ec_before": msg.ec_before,
        "solution_volume_L": msg.solution_volume_L,
        "timestamp": _ros_time_to_iso(msg.timestamp),
    }


def _plant_status_to_dict(msg: PlantStatus) -> Dict[str, Any]:
    return {
        "status_code": msg.status_code,
        "summary": msg.summary,
        "active_warnings": list(msg.active_warnings),
        "recommendations": list(msg.recommendations),
        "last_analysis": _ros_time_to_iso(msg.last_analysis),
    }


def _diagnostic_report_to_dict(msg: DiagnosticReport) -> Dict[str, Any]:
    return {
        "detected_symptoms": list(msg.detected_symptoms),
        "active_rules": list(msg.active_rules),
        "recommendations": list(msg.recommendations),
        "overall_severity": msg.overall_severity,
        "probe_ph": msg.probe_ph,
        "probe_ec": msg.probe_ec,
        "probe_temp": msg.probe_temp,
        "mean_ndvi": msg.mean_ndvi,
        "ndvi_trend_slope": msg.ndvi_trend_slope,
        "plant_area_cm2": msg.plant_area_cm2,
        "plant_height_cm": msg.plant_height_cm,
        "water_level_percent": msg.water_level_percent,
        "timestamp": _ros_time_to_iso(msg.timestamp),
    }


def _ndvi_alert_to_dict(msg: NDVIAlert) -> Dict[str, Any]:
    return {
        "current_ndvi": msg.current_ndvi,
        "ndvi_trend_slope": msg.ndvi_trend_slope,
        "ndvi_48h_ago": msg.ndvi_48h_ago,
        "alert_level": msg.alert_level,
        "timestamp": _ros_time_to_iso(msg.timestamp),
    }


def _alert_to_dict(msg: SystemAlert) -> Dict[str, Any]:
    return {
        "alert_type": msg.alert_type,
        "severity": msg.severity,
        "message": msg.message,
        "recommended_action": msg.recommended_action,
        "timestamp": _ros_time_to_iso(msg.header.stamp),
    }


# ---------------------------------------------------------------------------
# RosBridge
# ---------------------------------------------------------------------------


class RosBridge(Node):
    """ROS2 node that aggregates all V0.1 hydroponics topics and exposes them
    through thread-safe properties.  WebSocket clients registered via
    ``register_ws_sender`` receive JSON-encoded pushes whenever topics update.
    """

    def __init__(self) -> None:
        super().__init__("dashboard_ros_bridge")
        self._lock = threading.Lock()

        # ---- cached topic data ----------------------------------------
        self._probe_reading: Optional[Dict[str, Any]] = None
        self._ndvi_reading: Optional[Dict[str, Any]] = None
        self._plant_measurement: Optional[Dict[str, Any]] = None
        self._water_level: Optional[Dict[str, Any]] = None
        self._plant_status: Optional[Dict[str, Any]] = None
        self._diagnostic_report: Optional[Dict[str, Any]] = None
        self._ndvi_alert: Optional[Dict[str, Any]] = None
        self._alerts: List[Dict[str, Any]] = []

        # ---- history ring-buffers ----------------------------------------
        self._probe_history: List[Dict[str, Any]] = []
        self._probe_history_max: int = 2880       # 48 h @ ~1 Hz
        self._dosing_history: List[Dict[str, Any]] = []
        self._dosing_history_max: int = MAX_DOSING_HISTORY
        self._ndvi_history: List[Dict[str, Any]] = []
        self._ndvi_history_max: int = 2880
        self._topoff_history: List[Dict[str, Any]] = []
        self._topoff_history_max: int = MAX_TOPOFF_HISTORY

        # ---- WebSocket broadcast senders --------------------------------
        self._ws_senders: List[Callable[[str], None]] = []

        # ---- Subscriptions ----------------------------------------------
        self.create_subscription(ProbeReading, "/probe/reading", self._cb_probe, _BEST_EFFORT_QOS)
        self.create_subscription(NDVIReading, "/vision/ndvi", self._cb_ndvi, _BEST_EFFORT_QOS)
        self.create_subscription(PlantMeasurement, "/vision/measurement", self._cb_plant_measurement, _BEST_EFFORT_QOS)
        self.create_subscription(WaterLevel, "/water/level", self._cb_water_level, _BEST_EFFORT_QOS)
        self.create_subscription(TopOffEvent, "/water/topoff_event", self._cb_topoff, _RELIABLE_QOS)
        self.create_subscription(DosingEvent, "/dosing/event", self._cb_dosing, _RELIABLE_QOS)
        self.create_subscription(PlantStatus, "/bin/status", self._cb_plant_status, _BEST_EFFORT_QOS)
        self.create_subscription(DiagnosticReport, "/diagnostics/report", self._cb_diagnostic, _RELIABLE_QOS)
        self.create_subscription(NDVIAlert, "/vision/ndvi_alert", self._cb_ndvi_alert, _RELIABLE_QOS)
        self.create_subscription(SystemAlert, "/system_alert", self._cb_alert, _RELIABLE_QOS)

        # ---- Service clients --------------------------------------------
        self._srv_trigger_probe = self.create_client(TriggerProbe, "/probe/trigger")
        self._srv_trigger_aeration = self.create_client(TriggerAeration, "/aeration/trigger")
        self._srv_set_probe_interval = self.create_client(SetProbeInterval, "/probe/set_interval")
        self._srv_capture_vision = self.create_client(CaptureVision, "/vision/capture")

        self.get_logger().info("RosBridge (V0.1) node initialised.")

    # ------------------------------------------------------------------
    # Subscription callbacks
    # ------------------------------------------------------------------

    def _cb_probe(self, msg: ProbeReading) -> None:
        d = _probe_reading_to_dict(msg)
        with self._lock:
            self._probe_reading = d
            self._probe_history.append(d)
            if len(self._probe_history) > self._probe_history_max:
                self._probe_history = self._probe_history[-self._probe_history_max:]
        self._broadcast({"type": "probe_reading", "data": d})

    def _cb_ndvi(self, msg: NDVIReading) -> None:
        d = _ndvi_reading_to_dict(msg)
        with self._lock:
            self._ndvi_reading = d
            self._ndvi_history.append(d)
            if len(self._ndvi_history) > self._ndvi_history_max:
                self._ndvi_history = self._ndvi_history[-self._ndvi_history_max:]
        self._broadcast({"type": "ndvi_reading", "data": d})

    def _cb_plant_measurement(self, msg: PlantMeasurement) -> None:
        d = _plant_measurement_to_dict(msg)
        with self._lock:
            self._plant_measurement = d
        self._broadcast({"type": "plant_measurement", "data": d})

    def _cb_water_level(self, msg: WaterLevel) -> None:
        d = _water_level_to_dict(msg)
        with self._lock:
            self._water_level = d
        self._broadcast({"type": "water_level", "data": d})

    def _cb_topoff(self, msg: TopOffEvent) -> None:
        d = _topoff_event_to_dict(msg)
        with self._lock:
            self._topoff_history.insert(0, d)
            if len(self._topoff_history) > self._topoff_history_max:
                self._topoff_history = self._topoff_history[:self._topoff_history_max]
        self._broadcast({"type": "topoff_event", "data": d})

    def _cb_dosing(self, msg: DosingEvent) -> None:
        d = _dosing_event_to_dict(msg)
        with self._lock:
            self._dosing_history.insert(0, d)
            if len(self._dosing_history) > self._dosing_history_max:
                self._dosing_history = self._dosing_history[:self._dosing_history_max]
        self._broadcast({"type": "dosing_event", "data": d})

    def _cb_plant_status(self, msg: PlantStatus) -> None:
        d = _plant_status_to_dict(msg)
        with self._lock:
            self._plant_status = d
        self._broadcast({"type": "plant_status", "data": d})

    def _cb_diagnostic(self, msg: DiagnosticReport) -> None:
        d = _diagnostic_report_to_dict(msg)
        with self._lock:
            self._diagnostic_report = d
        self._broadcast({"type": "diagnostic_report", "data": d})

    def _cb_ndvi_alert(self, msg: NDVIAlert) -> None:
        d = _ndvi_alert_to_dict(msg)
        with self._lock:
            self._ndvi_alert = d
        self._broadcast({"type": "ndvi_alert", "data": d})

    def _cb_alert(self, msg: SystemAlert) -> None:
        d = _alert_to_dict(msg)
        with self._lock:
            self._alerts.insert(0, d)
            if len(self._alerts) > MAX_ALERTS:
                self._alerts = self._alerts[:MAX_ALERTS]
        self._broadcast({"type": "system_alert", "data": d})

    # ------------------------------------------------------------------
    # Thread-safe property accessors
    # ------------------------------------------------------------------

    @property
    def probe_reading(self) -> Optional[Dict[str, Any]]:
        with self._lock: return self._probe_reading

    @property
    def ndvi_reading(self) -> Optional[Dict[str, Any]]:
        with self._lock: return self._ndvi_reading

    @property
    def plant_measurement(self) -> Optional[Dict[str, Any]]:
        with self._lock: return self._plant_measurement

    @property
    def water_level(self) -> Optional[Dict[str, Any]]:
        with self._lock: return self._water_level

    @property
    def plant_status(self) -> Optional[Dict[str, Any]]:
        with self._lock: return self._plant_status

    @property
    def diagnostic_report(self) -> Optional[Dict[str, Any]]:
        with self._lock: return self._diagnostic_report

    @property
    def ndvi_alert(self) -> Optional[Dict[str, Any]]:
        with self._lock: return self._ndvi_alert

    @property
    def alerts(self) -> List[Dict[str, Any]]:
        with self._lock: return list(self._alerts)

    @property
    def probe_history(self) -> List[Dict[str, Any]]:
        with self._lock: return list(self._probe_history)

    @property
    def dosing_history(self) -> List[Dict[str, Any]]:
        with self._lock: return list(self._dosing_history)

    @property
    def ndvi_history(self) -> List[Dict[str, Any]]:
        with self._lock: return list(self._ndvi_history)

    @property
    def topoff_history(self) -> List[Dict[str, Any]]:
        with self._lock: return list(self._topoff_history)

    # ------------------------------------------------------------------
    # WebSocket broadcast
    # ------------------------------------------------------------------

    def register_ws_sender(self, sender: Callable[[str], None]) -> None:
        with self._lock:
            self._ws_senders.append(sender)

    def unregister_ws_sender(self, sender: Callable[[str], None]) -> None:
        with self._lock:
            try:
                self._ws_senders.remove(sender)
            except ValueError:
                pass

    def _broadcast(self, payload: Dict[str, Any]) -> None:
        text = json.dumps(payload, default=str)
        dead: List[Callable[[str], None]] = []
        with self._lock:
            senders = list(self._ws_senders)
        for sender in senders:
            try:
                sender(text)
            except Exception:
                dead.append(sender)
        if dead:
            with self._lock:
                for d in dead:
                    try:
                        self._ws_senders.remove(d)
                    except ValueError:
                        pass

    def broadcast_snapshot(self) -> None:
        snapshot: Dict[str, Any] = {
            "type": "snapshot",
            "data": {
                "probe_reading": self.probe_reading,
                "ndvi_reading": self.ndvi_reading,
                "plant_measurement": self.plant_measurement,
                "water_level": self.water_level,
                "plant_status": self.plant_status,
                "diagnostic_report": self.diagnostic_report,
                "ndvi_alert": self.ndvi_alert,
                "alerts": self.alerts[:20],
            },
        }
        self._broadcast(snapshot)

    # ------------------------------------------------------------------
    # Service wrappers
    # ------------------------------------------------------------------

    def call_trigger_probe(self, timeout: float = 5.0) -> bool:
        if not self._srv_trigger_probe.wait_for_service(timeout_sec=timeout):
            self.get_logger().warning("trigger_probe service not available")
            return False
        req = TriggerProbe.Request()
        future = self._srv_trigger_probe.call_async(req)
        rclpy.spin_until_future_complete(self, future, timeout_sec=timeout)
        return future.done() and future.result().success

    def call_trigger_aeration(self, timeout: float = 5.0) -> bool:
        if not self._srv_trigger_aeration.wait_for_service(timeout_sec=timeout):
            self.get_logger().warning("trigger_aeration service not available")
            return False
        req = TriggerAeration.Request()
        future = self._srv_trigger_aeration.call_async(req)
        rclpy.spin_until_future_complete(self, future, timeout_sec=timeout)
        return future.done() and future.result().success

    def call_set_probe_interval(
        self, interval_seconds: float, timeout: float = 5.0
    ) -> float:
        if not self._srv_set_probe_interval.wait_for_service(timeout_sec=timeout):
            self.get_logger().warning("set_probe_interval service not available")
            return 0.0
        req = SetProbeInterval.Request()
        req.interval_seconds = interval_seconds
        future = self._srv_set_probe_interval.call_async(req)
        rclpy.spin_until_future_complete(self, future, timeout_sec=timeout)
        if future.done():
            return future.result().applied_interval_seconds
        return 0.0

    def call_capture_vision(self, timeout: float = 10.0) -> bool:
        if not self._srv_capture_vision.wait_for_service(timeout_sec=timeout):
            self.get_logger().warning("capture_vision service not available")
            return False
        req = CaptureVision.Request()
        future = self._srv_capture_vision.call_async(req)
        rclpy.spin_until_future_complete(self, future, timeout_sec=timeout)
        return future.done() and future.result().success
