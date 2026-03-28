# MIT License
# Copyright (c) 2024 Claudroponics Project
#
# ROS2 bridge node: subscribes to all hydroponics topics, exposes latest
# values thread-safely, holds service/action clients for control endpoints,
# and broadcasts JSON updates to connected WebSocket clients.

from __future__ import annotations

import json
import threading
import time
from typing import Any, Callable, Dict, List, Optional

import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy

from hydroponics_msgs.msg import (
    BehaviorTreeStatus,
    InspectionResult,
    LightStatus,
    NutrientStatus,
    PlantPositionState,
    SystemAlert,
    TransportStatus,
    YieldMetrics,
)
from hydroponics_msgs.srv import (
    ForceDose,
    ResetCropCycle,
    SetGrowLightIntensity,
    SetGrowthStage,
    SetInspectionLight,
    TriggerInspection,
)
from hydroponics_msgs.action import ExecuteHarvest, TransportTo

# ---------------------------------------------------------------------------
# Helpers
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


def _ros_time_to_iso(t: Any) -> str:
    """Convert a builtin_interfaces/Time to an ISO-8601 string."""
    import datetime
    sec = getattr(t, "sec", 0)
    nanosec = getattr(t, "nanosec", 0)
    ts = sec + nanosec * 1e-9
    return datetime.datetime.utcfromtimestamp(ts).isoformat() + "Z"


def _nutrient_status_to_dict(msg: NutrientStatus) -> Dict[str, Any]:
    return {
        "ph_current": msg.ph_current,
        "ec_current": msg.ec_current,
        "temperature_c": msg.temperature_c,
        "ph_target": msg.ph_target,
        "ec_target": msg.ec_target,
        "ph_pid_output": msg.ph_pid_output,
        "ec_pid_output": msg.ec_pid_output,
        "a_b_ratio": msg.a_b_ratio,
        "growth_stage": msg.growth_stage,
        "days_since_planting": msg.days_since_planting,
        "pump_active": list(msg.pump_active),
        "timestamp": _ros_time_to_iso(msg.header.stamp),
    }


def _transport_status_to_dict(msg: TransportStatus) -> Dict[str, Any]:
    return {
        "current_position": msg.current_position,
        "target_position": msg.target_position,
        "is_moving": msg.is_moving,
        "position_mm": msg.position_mm,
        "velocity_mm_s": msg.velocity_mm_s,
        "timestamp": _ros_time_to_iso(msg.header.stamp),
    }


def _light_status_to_dict(msg: LightStatus) -> Dict[str, Any]:
    return {
        "grow_intensity_percent": msg.grow_intensity_percent,
        "schedule_state": msg.schedule_state,
        "inspection_light_on": msg.inspection_light_on,
        "next_transition_time": msg.next_transition_time,
        "timestamp": _ros_time_to_iso(msg.header.stamp),
    }


def _bt_status_to_dict(msg: BehaviorTreeStatus) -> Dict[str, Any]:
    return {
        "system_state": msg.system_state,
        "active_node_path": msg.active_node_path,
        "running_nodes": list(msg.running_nodes),
        "failed_nodes": list(msg.failed_nodes),
        "timestamp": _ros_time_to_iso(msg.header.stamp),
    }


def _plant_state_to_dict(msg: PlantPositionState) -> Dict[str, Any]:
    return {
        "position_index": msg.position_index,
        "plant_id": msg.plant_id,
        "plant_profile": msg.plant_profile,
        "status": msg.status,
        "health_state": msg.health_state,
        "canopy_area_cm2": msg.canopy_area_cm2,
        "height_cm": msg.height_cm,
        "leaf_count": msg.leaf_count,
        "days_since_planted": msg.days_since_planted,
        "cut_cycle_number": msg.cut_cycle_number,
        "last_inspection": _ros_time_to_iso(msg.last_inspection),
        "last_harvest": _ros_time_to_iso(msg.last_harvest),
    }


def _yield_metrics_to_dict(msg: YieldMetrics) -> Dict[str, Any]:
    return {
        "total_yield_grams": msg.total_yield_grams,
        "yield_per_watt_hour": msg.yield_per_watt_hour,
        "yield_per_liter_nutrient": msg.yield_per_liter_nutrient,
        "cost_per_gram": msg.cost_per_gram,
        "total_harvests": msg.total_harvests,
        "total_crop_cycles": msg.total_crop_cycles,
        "timestamp": _ros_time_to_iso(msg.header.stamp),
    }


def _alert_to_dict(msg: SystemAlert) -> Dict[str, Any]:
    return {
        "alert_type": msg.alert_type,
        "severity": msg.severity,
        "message": msg.message,
        "recommended_action": msg.recommended_action,
        "timestamp": _ros_time_to_iso(msg.header.stamp),
    }


def _inspection_result_to_dict(msg: InspectionResult) -> Dict[str, Any]:
    return {
        "plants": [_plant_state_to_dict(p) for p in msg.plants],
        "scan_number": msg.scan_number,
        "disease_detected": msg.disease_detected,
        "disease_type": msg.disease_type,
        "deficiency_trends": list(msg.deficiency_trends),
        "timestamp": _ros_time_to_iso(msg.header.stamp),
    }


# ---------------------------------------------------------------------------
# RosBridge
# ---------------------------------------------------------------------------


class RosBridge(Node):
    """ROS2 node that aggregates all hydroponics topics and exposes them
    through thread-safe properties.  WebSocket clients registered via
    ``register_ws_sender`` receive JSON-encoded pushes whenever topics
    update.
    """

    def __init__(self) -> None:
        super().__init__("dashboard_ros_bridge")

        self._lock = threading.Lock()

        # ---- cached topic data ----------------------------------------
        self._nutrient_status: Optional[Dict[str, Any]] = None
        self._transport_status: Optional[Dict[str, Any]] = None
        self._light_status: Optional[Dict[str, Any]] = None
        self._bt_status: Optional[Dict[str, Any]] = None
        self._plant_status: List[Dict[str, Any]] = []
        self._yield_metrics: Optional[Dict[str, Any]] = None
        self._alerts: List[Dict[str, Any]] = []
        self._inspection_result: Optional[Dict[str, Any]] = None

        # nutrient history ring-buffer (last 2880 samples @ 1 Hz = 48 h)
        self._nutrient_history: List[Dict[str, Any]] = []
        self._nutrient_history_max: int = 2880

        # ---- WebSocket broadcast senders --------------------------------
        self._ws_senders: List[Callable[[str], None]] = []

        # ---- Subscriptions ----------------------------------------------
        self.create_subscription(
            NutrientStatus,
            "/nutrient_status",
            self._cb_nutrient,
            _BEST_EFFORT_QOS,
        )
        self.create_subscription(
            TransportStatus,
            "/transport_status",
            self._cb_transport,
            _BEST_EFFORT_QOS,
        )
        self.create_subscription(
            LightStatus,
            "/light_status",
            self._cb_light,
            _BEST_EFFORT_QOS,
        )
        self.create_subscription(
            BehaviorTreeStatus,
            "/behavior_tree_status",
            self._cb_bt,
            _BEST_EFFORT_QOS,
        )
        self.create_subscription(
            InspectionResult,
            "/plant_status",
            self._cb_plant_status_from_inspection,
            _RELIABLE_QOS,
        )
        self.create_subscription(
            YieldMetrics,
            "/yield_metrics",
            self._cb_yield,
            _BEST_EFFORT_QOS,
        )
        self.create_subscription(
            SystemAlert,
            "/system_alert",
            self._cb_alert,
            _RELIABLE_QOS,
        )
        self.create_subscription(
            InspectionResult,
            "/inspection_result",
            self._cb_inspection,
            _RELIABLE_QOS,
        )

        # ---- Service clients --------------------------------------------
        self._srv_force_dose = self.create_client(ForceDose, "/force_dose")
        self._srv_set_growth_stage = self.create_client(
            SetGrowthStage, "/set_growth_stage"
        )
        self._srv_reset_crop_cycle = self.create_client(
            ResetCropCycle, "/reset_crop_cycle"
        )
        self._srv_set_inspection_light = self.create_client(
            SetInspectionLight, "/set_inspection_light"
        )
        self._srv_set_grow_light_intensity = self.create_client(
            SetGrowLightIntensity, "/set_grow_light_intensity"
        )
        self._srv_trigger_inspection = self.create_client(
            TriggerInspection, "/trigger_inspection"
        )

        # ---- Action clients ---------------------------------------------
        self._ac_transport_to = ActionClient(self, TransportTo, "/transport_to")
        self._ac_execute_harvest = ActionClient(self, ExecuteHarvest, "/execute_harvest")

        self.get_logger().info("RosBridge node initialised.")

    # ------------------------------------------------------------------
    # Subscription callbacks
    # ------------------------------------------------------------------

    def _cb_nutrient(self, msg: NutrientStatus) -> None:
        d = _nutrient_status_to_dict(msg)
        with self._lock:
            self._nutrient_status = d
            self._nutrient_history.append(d)
            if len(self._nutrient_history) > self._nutrient_history_max:
                self._nutrient_history = self._nutrient_history[
                    -self._nutrient_history_max :
                ]
        self._broadcast({"type": "nutrient_status", "data": d})

    def _cb_transport(self, msg: TransportStatus) -> None:
        d = _transport_status_to_dict(msg)
        with self._lock:
            self._transport_status = d
        self._broadcast({"type": "transport_status", "data": d})

    def _cb_light(self, msg: LightStatus) -> None:
        d = _light_status_to_dict(msg)
        with self._lock:
            self._light_status = d
        self._broadcast({"type": "light_status", "data": d})

    def _cb_bt(self, msg: BehaviorTreeStatus) -> None:
        d = _bt_status_to_dict(msg)
        with self._lock:
            self._bt_status = d
        self._broadcast({"type": "bt_status", "data": d})

    def _cb_plant_status_from_inspection(self, msg: InspectionResult) -> None:
        """Also update plant list whenever an InspectionResult arrives on
        the /plant_status topic (same message type used for live plant state)."""
        plants = [_plant_state_to_dict(p) for p in msg.plants]
        with self._lock:
            self._plant_status = plants
        self._broadcast({"type": "plant_status", "data": plants})

    def _cb_yield(self, msg: YieldMetrics) -> None:
        d = _yield_metrics_to_dict(msg)
        with self._lock:
            self._yield_metrics = d
        self._broadcast({"type": "yield_metrics", "data": d})

    def _cb_alert(self, msg: SystemAlert) -> None:
        d = _alert_to_dict(msg)
        with self._lock:
            self._alerts.insert(0, d)
            if len(self._alerts) > MAX_ALERTS:
                self._alerts = self._alerts[:MAX_ALERTS]
        self._broadcast({"type": "system_alert", "data": d})

    def _cb_inspection(self, msg: InspectionResult) -> None:
        d = _inspection_result_to_dict(msg)
        with self._lock:
            self._inspection_result = d
            # also update plant list from inspection payload
            self._plant_status = d["plants"]
        self._broadcast({"type": "inspection_result", "data": d})

    # ------------------------------------------------------------------
    # Thread-safe property accessors
    # ------------------------------------------------------------------

    @property
    def nutrient_status(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._nutrient_status

    @property
    def transport_status(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._transport_status

    @property
    def light_status(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._light_status

    @property
    def bt_status(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._bt_status

    @property
    def plant_status(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._plant_status)

    @property
    def yield_metrics(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._yield_metrics

    @property
    def alerts(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._alerts)

    @property
    def inspection_result(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._inspection_result

    @property
    def nutrient_history(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._nutrient_history)

    # ------------------------------------------------------------------
    # WebSocket broadcast
    # ------------------------------------------------------------------

    def register_ws_sender(self, sender: Callable[[str], None]) -> None:
        """Register a callable that accepts a JSON string and sends it to
        a single WebSocket client."""
        with self._lock:
            self._ws_senders.append(sender)

    def unregister_ws_sender(self, sender: Callable[[str], None]) -> None:
        with self._lock:
            try:
                self._ws_senders.remove(sender)
            except ValueError:
                pass

    def _broadcast(self, payload: Dict[str, Any]) -> None:
        """Push a JSON-serialised payload to every registered WS sender.
        Senders that raise are silently removed."""
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
        """Push a full-state snapshot to all connected WebSocket clients."""
        snapshot: Dict[str, Any] = {
            "type": "snapshot",
            "data": {
                "nutrient_status": self.nutrient_status,
                "transport_status": self.transport_status,
                "light_status": self.light_status,
                "bt_status": self.bt_status,
                "plant_status": self.plant_status,
                "yield_metrics": self.yield_metrics,
                "alerts": self.alerts[:20],
                "inspection_result": self.inspection_result,
            },
        }
        self._broadcast(snapshot)

    # ------------------------------------------------------------------
    # Service / Action wrappers
    # ------------------------------------------------------------------

    def call_force_dose(
        self, pump_id: str, amount_ml: float, timeout: float = 5.0
    ) -> bool:
        if not self._srv_force_dose.wait_for_service(timeout_sec=timeout):
            self.get_logger().warning("force_dose service not available")
            return False
        req = ForceDose.Request()
        req.pump_id = pump_id
        req.amount_ml = amount_ml
        future = self._srv_force_dose.call_async(req)
        rclpy.spin_until_future_complete(self, future, timeout_sec=timeout)
        if future.done():
            return future.result().success
        return False

    def call_set_growth_stage(self, stage: str, timeout: float = 5.0) -> bool:
        if not self._srv_set_growth_stage.wait_for_service(timeout_sec=timeout):
            self.get_logger().warning("set_growth_stage service not available")
            return False
        req = SetGrowthStage.Request()
        req.stage = stage
        future = self._srv_set_growth_stage.call_async(req)
        rclpy.spin_until_future_complete(self, future, timeout_sec=timeout)
        if future.done():
            return future.result().success
        return False

    def call_reset_crop_cycle(
        self, position_index: int, plant_profile: str, timeout: float = 5.0
    ) -> bool:
        if not self._srv_reset_crop_cycle.wait_for_service(timeout_sec=timeout):
            self.get_logger().warning("reset_crop_cycle service not available")
            return False
        req = ResetCropCycle.Request()
        req.position_index = position_index
        req.plant_profile = plant_profile
        future = self._srv_reset_crop_cycle.call_async(req)
        rclpy.spin_until_future_complete(self, future, timeout_sec=timeout)
        if future.done():
            return future.result().success
        return False

    def call_set_inspection_light(self, on: bool, timeout: float = 5.0) -> bool:
        if not self._srv_set_inspection_light.wait_for_service(timeout_sec=timeout):
            self.get_logger().warning("set_inspection_light service not available")
            return False
        req = SetInspectionLight.Request()
        req.on = on
        future = self._srv_set_inspection_light.call_async(req)
        rclpy.spin_until_future_complete(self, future, timeout_sec=timeout)
        if future.done():
            return future.result().success
        return False

    def call_set_grow_light_intensity(
        self, intensity_percent: float, timeout: float = 5.0
    ) -> bool:
        if not self._srv_set_grow_light_intensity.wait_for_service(timeout_sec=timeout):
            self.get_logger().warning(
                "set_grow_light_intensity service not available"
            )
            return False
        req = SetGrowLightIntensity.Request()
        req.intensity_percent = intensity_percent
        future = self._srv_set_grow_light_intensity.call_async(req)
        rclpy.spin_until_future_complete(self, future, timeout_sec=timeout)
        if future.done():
            return future.result().success
        return False

    def call_trigger_inspection(self, timeout: float = 10.0) -> Dict[str, Any]:
        if not self._srv_trigger_inspection.wait_for_service(timeout_sec=timeout):
            self.get_logger().warning("trigger_inspection service not available")
            return {"success": False, "scan_number": 0}
        req = TriggerInspection.Request()
        future = self._srv_trigger_inspection.call_async(req)
        rclpy.spin_until_future_complete(self, future, timeout_sec=timeout)
        if future.done():
            res = future.result()
            return {"success": res.success, "scan_number": res.scan_number}
        return {"success": False, "scan_number": 0}

    def send_transport_goal(
        self,
        target_position: str,
        feedback_cb: Optional[Callable] = None,
    ) -> Optional[Any]:
        """Send a TransportTo action goal and return the future."""
        if not self._ac_transport_to.wait_for_server(timeout_sec=5.0):
            self.get_logger().warning("TransportTo action server not available")
            return None
        goal = TransportTo.Goal()
        goal.target_position = target_position
        return self._ac_transport_to.send_goal_async(goal, feedback_callback=feedback_cb)

    def send_harvest_goal(
        self,
        plan: Any,
        feedback_cb: Optional[Callable] = None,
    ) -> Optional[Any]:
        """Send an ExecuteHarvest action goal and return the future."""
        if not self._ac_execute_harvest.wait_for_server(timeout_sec=5.0):
            self.get_logger().warning("ExecuteHarvest action server not available")
            return None
        goal = ExecuteHarvest.Goal()
        goal.plan = plan
        return self._ac_execute_harvest.send_goal_async(goal, feedback_callback=feedback_cb)
