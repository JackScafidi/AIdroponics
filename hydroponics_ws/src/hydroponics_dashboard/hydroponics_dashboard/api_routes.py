# MIT License
# Copyright (c) 2024 Claudroponics Project
#
# FastAPI router: all REST endpoints and the /ws/stream WebSocket.
# The RosBridge instance is injected via set_ros_bridge() before the app
# starts receiving requests.

from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from hydroponics_dashboard.auth import create_token, revoke_token, verify_password, verify_token
from hydroponics_dashboard.ros_bridge import RosBridge

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Dependency injection – set by app.py before the server starts
# ---------------------------------------------------------------------------

_bridge: Optional[RosBridge] = None


def set_ros_bridge(bridge: RosBridge) -> None:
    global _bridge
    _bridge = bridge


def get_bridge() -> RosBridge:
    if _bridge is None:
        raise HTTPException(status_code=503, detail="ROS bridge not initialised")
    return _bridge


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class DoseRequest(BaseModel):
    pump_id: str = Field(..., description="ph_up | ph_down | nutrient_a | nutrient_b")
    amount_ml: float = Field(..., gt=0.0, description="Volume to dose in millilitres")


class TransportRequest(BaseModel):
    position: str = Field(
        ...,
        description="WORK | GROW | INSPECT | WORK_PLANT_0 .. WORK_PLANT_3",
    )


class EStopRequest(BaseModel):
    reason: str = Field(default="Manual E-STOP from dashboard")


class LoginRequest(BaseModel):
    password: str


# ---------------------------------------------------------------------------
# Auth dependency — protects control endpoints
# ---------------------------------------------------------------------------


async def require_auth(authorization: str = Header(None)) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    token = authorization[7:]
    if not verify_token(token):
        raise HTTPException(status_code=401, detail="Invalid or expired token")


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter()

# ---------------------------------------------------------------------------
# Plant profiles (static catalogue – extend as new profiles are added)
# ---------------------------------------------------------------------------

_PLANT_PROFILES: List[Dict[str, Any]] = [
    {
        "name": "basil",
        "display_name": "Basil (Ocimum basilicum)",
        "stages": {
            "seedling": {"ph_target": 6.0, "ec_target": 0.8, "duration_days": 7},
            "vegetative": {"ph_target": 6.0, "ec_target": 1.4, "duration_days": 21},
            "mature": {"ph_target": 6.0, "ec_target": 1.6, "duration_days": 14},
        },
        "harvest_canopy_cm2": 250.0,
    },
    {
        "name": "parsley",
        "display_name": "Parsley (Petroselinum crispum)",
        "stages": {
            "seedling": {"ph_target": 6.0, "ec_target": 0.6, "duration_days": 14},
            "vegetative": {"ph_target": 6.2, "ec_target": 1.2, "duration_days": 28},
            "mature": {"ph_target": 6.2, "ec_target": 1.4, "duration_days": 21},
        },
        "harvest_canopy_cm2": 300.0,
    },
    {
        "name": "lettuce",
        "display_name": "Lettuce (Lactuca sativa)",
        "stages": {
            "seedling": {"ph_target": 6.0, "ec_target": 0.8, "duration_days": 7},
            "vegetative": {"ph_target": 6.0, "ec_target": 1.2, "duration_days": 21},
            "mature": {"ph_target": 6.0, "ec_target": 1.4, "duration_days": 14},
        },
        "harvest_canopy_cm2": 400.0,
    },
    {
        "name": "spinach",
        "display_name": "Spinach (Spinacia oleracea)",
        "stages": {
            "seedling": {"ph_target": 6.2, "ec_target": 0.8, "duration_days": 7},
            "vegetative": {"ph_target": 6.2, "ec_target": 1.6, "duration_days": 21},
            "mature": {"ph_target": 6.2, "ec_target": 2.0, "duration_days": 14},
        },
        "harvest_canopy_cm2": 280.0,
    },
    {
        "name": "mint",
        "display_name": "Mint (Mentha spicata)",
        "stages": {
            "seedling": {"ph_target": 6.5, "ec_target": 0.8, "duration_days": 10},
            "vegetative": {"ph_target": 6.5, "ec_target": 1.6, "duration_days": 21},
            "mature": {"ph_target": 6.5, "ec_target": 2.0, "duration_days": 14},
        },
        "harvest_canopy_cm2": 220.0,
    },
]


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------


@router.post("/api/auth/login", tags=["auth"])
async def login(body: LoginRequest) -> Dict[str, Any]:
    """Authenticate with password to obtain a bearer token for control access."""
    if verify_password(body.password):
        token = create_token()
        return {"authenticated": True, "token": token}
    raise HTTPException(status_code=401, detail="Invalid password")


@router.get("/api/auth/check", tags=["auth"])
async def check_auth(authorization: str = Header(None)) -> Dict[str, Any]:
    """Check whether the current bearer token is valid."""
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
        if verify_token(token):
            return {"authenticated": True}
    return {"authenticated": False}


@router.post("/api/auth/logout", tags=["auth"])
async def logout(authorization: str = Header(None)) -> Dict[str, Any]:
    """Revoke the current bearer token."""
    if authorization and authorization.startswith("Bearer "):
        revoke_token(authorization[7:])
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Status endpoints (public — no auth required)
# ---------------------------------------------------------------------------


@router.get("/api/status", tags=["status"])
async def get_status(bridge: RosBridge = Depends(get_bridge)) -> Dict[str, Any]:
    """Return system state, transport position, and active BT node."""
    bt = bridge.bt_status
    transport = bridge.transport_status
    light = bridge.light_status
    return {
        "system_state": bt["system_state"] if bt else "UNKNOWN",
        "active_node_path": bt["active_node_path"] if bt else "",
        "transport_position": transport["current_position"] if transport else "UNKNOWN",
        "transport_moving": transport["is_moving"] if transport else False,
        "light_intensity_percent": light["grow_intensity_percent"] if light else 0.0,
        "light_schedule_state": light["schedule_state"] if light else "unknown",
    }


@router.get("/api/nutrients", tags=["sensors"])
async def get_nutrients(bridge: RosBridge = Depends(get_bridge)) -> Dict[str, Any]:
    """Return current pH, EC, temperature, targets, and PID state."""
    data = bridge.nutrient_status
    if data is None:
        raise HTTPException(status_code=503, detail="No nutrient data available yet")
    return data


@router.get("/api/plants", tags=["plants"])
async def get_plants(bridge: RosBridge = Depends(get_bridge)) -> List[Dict[str, Any]]:
    """Return per-position plant status, growth stage, and health."""
    return bridge.plant_status


@router.get("/api/harvests", tags=["plants"])
async def get_harvests(bridge: RosBridge = Depends(get_bridge)) -> Dict[str, Any]:
    """Return harvest log derived from cached yield metrics and plant data."""
    metrics = bridge.yield_metrics
    plants = bridge.plant_status
    harvest_summary = []
    for plant in plants:
        if plant.get("cut_cycle_number", 0) > 0:
            harvest_summary.append(
                {
                    "position_index": plant["position_index"],
                    "plant_id": plant["plant_id"],
                    "plant_profile": plant["plant_profile"],
                    "cut_cycles_completed": plant["cut_cycle_number"],
                    "last_harvest": plant["last_harvest"],
                }
            )
    return {
        "harvest_log": harvest_summary,
        "yield_totals": metrics,
    }


@router.get("/api/analytics", tags=["analytics"])
async def get_analytics(bridge: RosBridge = Depends(get_bridge)) -> Dict[str, Any]:
    """Return yield metrics."""
    data = bridge.yield_metrics
    if data is None:
        return {
            "total_yield_grams": 0.0,
            "yield_per_watt_hour": 0.0,
            "yield_per_liter_nutrient": 0.0,
            "cost_per_gram": 0.0,
            "total_harvests": 0,
            "total_crop_cycles": 0,
            "timestamp": None,
        }
    return data


@router.get("/api/inspections/latest", tags=["inspection"])
async def get_latest_inspection(
    bridge: RosBridge = Depends(get_bridge),
) -> Dict[str, Any]:
    """Return the most recent inspection result."""
    data = bridge.inspection_result
    if data is None:
        raise HTTPException(
            status_code=404, detail="No inspection data available yet"
        )
    return data


# ---------------------------------------------------------------------------
# Control endpoints
# ---------------------------------------------------------------------------


@router.post("/api/controls/transport/{position}", tags=["controls"], dependencies=[Depends(require_auth)])
async def control_transport(
    position: str, bridge: RosBridge = Depends(get_bridge)
) -> Dict[str, Any]:
    """Trigger a TransportTo action goal."""
    valid_positions = {
        "WORK",
        "GROW",
        "INSPECT",
        "WORK_PLANT_0",
        "WORK_PLANT_1",
        "WORK_PLANT_2",
        "WORK_PLANT_3",
    }
    pos_upper = position.upper()
    if pos_upper not in valid_positions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid position '{position}'. Valid: {sorted(valid_positions)}",
        )
    goal_future = bridge.send_transport_goal(pos_upper)
    if goal_future is None:
        raise HTTPException(
            status_code=503, detail="TransportTo action server not available"
        )
    return {"status": "accepted", "target_position": pos_upper}


@router.post("/api/controls/inspect", tags=["controls"], dependencies=[Depends(require_auth)])
async def control_inspect(bridge: RosBridge = Depends(get_bridge)) -> Dict[str, Any]:
    """Trigger a manual inspection cycle."""
    result = await asyncio.get_event_loop().run_in_executor(
        None, bridge.call_trigger_inspection
    )
    if not result["success"]:
        raise HTTPException(
            status_code=503, detail="Inspection service call failed or timed out"
        )
    return {"status": "ok", "scan_number": result["scan_number"]}


@router.post("/api/controls/harvest", tags=["controls"], dependencies=[Depends(require_auth)])
async def control_harvest(bridge: RosBridge = Depends(get_bridge)) -> Dict[str, Any]:
    """Trigger a manual harvest cycle (sends ExecuteHarvest action with empty plan)."""
    from hydroponics_msgs.msg import HarvestPlan  # type: ignore

    plan = HarvestPlan()
    goal_future = bridge.send_harvest_goal(plan)
    if goal_future is None:
        raise HTTPException(
            status_code=503, detail="ExecuteHarvest action server not available"
        )
    return {"status": "accepted"}


@router.post("/api/controls/dose", tags=["controls"], dependencies=[Depends(require_auth)])
async def control_dose(
    body: DoseRequest, bridge: RosBridge = Depends(get_bridge)
) -> Dict[str, Any]:
    """Manually dose a specific pump."""
    valid_pumps = {"ph_up", "ph_down", "nutrient_a", "nutrient_b"}
    if body.pump_id not in valid_pumps:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid pump_id '{body.pump_id}'. Valid: {sorted(valid_pumps)}",
        )
    success = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: bridge.call_force_dose(body.pump_id, body.amount_ml),
    )
    if not success:
        raise HTTPException(
            status_code=503, detail="ForceDose service call failed or timed out"
        )
    return {"status": "ok", "pump_id": body.pump_id, "amount_ml": body.amount_ml}


@router.post("/api/controls/light/{intensity}", tags=["controls"], dependencies=[Depends(require_auth)])
async def control_light(
    intensity: float, bridge: RosBridge = Depends(get_bridge)
) -> Dict[str, Any]:
    """Override grow light intensity (0–100 %)."""
    if not 0.0 <= intensity <= 100.0:
        raise HTTPException(
            status_code=400, detail="Intensity must be between 0 and 100"
        )
    success = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: bridge.call_set_grow_light_intensity(intensity),
    )
    if not success:
        raise HTTPException(
            status_code=503,
            detail="SetGrowLightIntensity service call failed or timed out",
        )
    return {"status": "ok", "intensity_percent": intensity}


@router.post("/api/controls/estop", tags=["controls"], dependencies=[Depends(require_auth)])
async def control_estop(
    body: Optional[EStopRequest] = None,
    bridge: RosBridge = Depends(get_bridge),
) -> Dict[str, Any]:
    """Publish a critical emergency-stop alert."""
    from hydroponics_msgs.msg import SystemAlert  # type: ignore
    from rclpy.qos import QoSProfile, ReliabilityPolicy

    reason = (body.reason if body else None) or "Manual E-STOP from dashboard"

    # Use a one-shot publisher on the bridge node.
    pub = bridge.create_publisher(
        SystemAlert,
        "/system_alert",
        10,
    )
    msg = SystemAlert()
    msg.header.stamp = bridge.get_clock().now().to_msg()
    msg.alert_type = "estop"
    msg.severity = "critical"
    msg.message = reason
    msg.recommended_action = "Inspect system immediately. Reset when safe."
    pub.publish(msg)
    bridge.destroy_publisher(pub)

    logger.warning("E-STOP published: %s", reason)
    return {"status": "estop_published", "reason": reason}


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


@router.get("/api/export/data", tags=["export"])
async def export_data(
    format: str = "csv", bridge: RosBridge = Depends(get_bridge)
) -> StreamingResponse:
    """Export nutrient readings as CSV (or JSON)."""
    history = bridge.nutrient_history

    if format.lower() == "json":
        content = json.dumps(history, indent=2)
        return StreamingResponse(
            iter([content]),
            media_type="application/json",
            headers={
                "Content-Disposition": "attachment; filename=nutrient_history.json"
            },
        )

    # Default: CSV
    output = io.StringIO()
    fieldnames = [
        "timestamp",
        "ph_current",
        "ec_current",
        "temperature_c",
        "ph_target",
        "ec_target",
        "ph_pid_output",
        "ec_pid_output",
        "a_b_ratio",
        "growth_stage",
        "days_since_planting",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in history:
        writer.writerow(row)
    output.seek(0)
    return StreamingResponse(
        iter([output.read()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=nutrient_history.csv"
        },
    )


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------


@router.get("/api/profiles", tags=["profiles"])
async def get_profiles() -> List[Dict[str, Any]]:
    """List all available plant profiles."""
    return _PLANT_PROFILES


@router.get("/api/profiles/{name}", tags=["profiles"])
async def get_profile(name: str) -> Dict[str, Any]:
    """Return a specific plant profile by name."""
    for profile in _PLANT_PROFILES:
        if profile["name"] == name.lower():
            return profile
    raise HTTPException(status_code=404, detail=f"Profile '{name}' not found")


# ---------------------------------------------------------------------------
# WebSocket stream
# ---------------------------------------------------------------------------


@router.websocket("/ws/stream")
async def ws_stream(websocket: WebSocket, bridge: RosBridge = Depends(get_bridge)) -> None:
    """Stream sensor data and BT status to the client at ~1 Hz.

    Additionally, the RosBridge will push event-driven updates whenever a
    topic callback fires.  The client receives both the periodic heartbeat
    and immediate event pushes.
    """
    await websocket.accept()
    logger.info("WebSocket client connected: %s", websocket.client)

    # Queue for thread-safe message delivery from ROS callbacks.
    queue: asyncio.Queue[str] = asyncio.Queue(maxsize=256)

    loop = asyncio.get_event_loop()

    def _sender(text: str) -> None:
        """Called from the ROS spin thread; schedules delivery on the event loop."""
        try:
            loop.call_soon_threadsafe(queue.put_nowait, text)
        except Exception:
            pass

    bridge.register_ws_sender(_sender)

    # Send an immediate full snapshot so the UI has data right away.
    bridge.broadcast_snapshot()

    try:
        while True:
            # Wait up to 1 second for a queued message; if none, send heartbeat.
            try:
                message = await asyncio.wait_for(queue.get(), timeout=1.0)
                await websocket.send_text(message)
            except asyncio.TimeoutError:
                # 1 Hz heartbeat with current snapshot.
                heartbeat = json.dumps(
                    {
                        "type": "heartbeat",
                        "data": {
                            "nutrient_status": bridge.nutrient_status,
                            "bt_status": bridge.bt_status,
                            "transport_status": bridge.transport_status,
                            "light_status": bridge.light_status,
                        },
                    },
                    default=str,
                )
                await websocket.send_text(heartbeat)
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected: %s", websocket.client)
    except Exception as exc:  # noqa: BLE001
        logger.error("WebSocket error: %s", exc)
    finally:
        bridge.unregister_ws_sender(_sender)
