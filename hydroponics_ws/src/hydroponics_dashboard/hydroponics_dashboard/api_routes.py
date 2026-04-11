# MIT License
# Copyright (c) 2026 AIdroponics Project
#
# FastAPI router: all REST endpoints and the /ws/stream WebSocket.
# The RosBridge instance is injected via set_ros_bridge() before the app
# starts receiving requests.

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from hydroponics_dashboard.auth import create_token, revoke_token, verify_password, verify_token
from hydroponics_dashboard.ros_bridge import RosBridge

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Dependency injection
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


class ProbeIntervalRequest(BaseModel):
    interval_seconds: float = Field(..., gt=0.0, description="Probe cycle interval in seconds")


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
# Plant profiles (V0.1 — NDVI thresholds, no harvest fields)
# ---------------------------------------------------------------------------

_PLANT_PROFILES: List[Dict[str, Any]] = [
    {
        "name": "basil",
        "display_name": "Basil (Ocimum basilicum)",
        "ph": {"ideal": [5.5, 6.5], "acceptable": [5.0, 6.8]},
        "ec_mS_cm": {"ideal": [1.0, 1.6], "acceptable": [0.8, 2.0]},
        "temperature_C": {"ideal": [18, 27], "acceptable": [15, 30]},
        "ndvi": {"healthy_min": 0.3, "warning_threshold": 0.2, "critical_threshold": 0.1},
        "nutrient_ab_ratio": 1.0,
    },
    {
        "name": "mint",
        "display_name": "Mint (Mentha spicata)",
        "ph": {"ideal": [6.0, 7.0], "acceptable": [5.5, 7.5]},
        "ec_mS_cm": {"ideal": [1.2, 1.6], "acceptable": [0.9, 2.0]},
        "temperature_C": {"ideal": [18, 25], "acceptable": [15, 28]},
        "ndvi": {"healthy_min": 0.32, "warning_threshold": 0.22, "critical_threshold": 0.12},
        "nutrient_ab_ratio": 1.0,
    },
    {
        "name": "parsley",
        "display_name": "Parsley (Petroselinum crispum)",
        "ph": {"ideal": [5.5, 6.5], "acceptable": [5.0, 7.0]},
        "ec_mS_cm": {"ideal": [0.8, 1.8], "acceptable": [0.6, 2.2]},
        "temperature_C": {"ideal": [15, 24], "acceptable": [10, 28]},
        "ndvi": {"healthy_min": 0.28, "warning_threshold": 0.18, "critical_threshold": 0.08},
        "nutrient_ab_ratio": 1.0,
    },
    {
        "name": "rosemary",
        "display_name": "Rosemary (Salvia rosmarinus)",
        "ph": {"ideal": [5.5, 6.5], "acceptable": [5.0, 7.0]},
        "ec_mS_cm": {"ideal": [1.0, 1.6], "acceptable": [0.8, 2.0]},
        "temperature_C": {"ideal": [18, 27], "acceptable": [15, 30]},
        "ndvi": {"healthy_min": 0.30, "warning_threshold": 0.20, "critical_threshold": 0.10},
        "nutrient_ab_ratio": 1.0,
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
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
        if verify_token(token):
            return {"authenticated": True}
    return {"authenticated": False}


@router.post("/api/auth/logout", tags=["auth"])
async def logout(authorization: str = Header(None)) -> Dict[str, Any]:
    if authorization and authorization.startswith("Bearer "):
        revoke_token(authorization[7:])
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Status / sensor endpoints (public)
# ---------------------------------------------------------------------------


@router.get("/api/status", tags=["status"])
async def get_status(bridge: RosBridge = Depends(get_bridge)) -> Dict[str, Any]:
    probe = bridge.probe_reading
    water = bridge.water_level
    plant = bridge.plant_status
    return {
        "ph": probe["ph"] if probe else None,
        "ec_mS_cm": probe["ec_mS_cm"] if probe else None,
        "temperature_C": probe["temperature_C"] if probe else None,
        "water_level_percent": water["level_percent"] if water else None,
        "plant_status_code": plant["status_code"] if plant else None,
        "plant_summary": plant["summary"] if plant else "Unknown",
    }


@router.get("/api/probe/latest", tags=["sensors"])
async def get_probe_latest(bridge: RosBridge = Depends(get_bridge)) -> Dict[str, Any]:
    data = bridge.probe_reading
    if data is None:
        raise HTTPException(status_code=503, detail="No probe data available yet")
    return data


@router.get("/api/ndvi/latest", tags=["sensors"])
async def get_ndvi_latest(bridge: RosBridge = Depends(get_bridge)) -> Dict[str, Any]:
    data = bridge.ndvi_reading
    if data is None:
        raise HTTPException(status_code=503, detail="No NDVI data available yet")
    return data


@router.get("/api/water/latest", tags=["sensors"])
async def get_water_latest(bridge: RosBridge = Depends(get_bridge)) -> Dict[str, Any]:
    data = bridge.water_level
    if data is None:
        raise HTTPException(status_code=503, detail="No water level data available yet")
    return data


@router.get("/api/plant/measurement/latest", tags=["sensors"])
async def get_plant_measurement(bridge: RosBridge = Depends(get_bridge)) -> Dict[str, Any]:
    data = bridge.plant_measurement
    if data is None:
        raise HTTPException(status_code=503, detail="No plant measurement available yet")
    return data


@router.get("/api/diagnostics/latest", tags=["diagnostics"])
async def get_diagnostic_latest(bridge: RosBridge = Depends(get_bridge)) -> Dict[str, Any]:
    data = bridge.diagnostic_report
    if data is None:
        raise HTTPException(status_code=503, detail="No diagnostic report available yet")
    return data


# ---------------------------------------------------------------------------
# History endpoints (public) — range param filters in memory
# ---------------------------------------------------------------------------

_RANGE_SECONDS = {"1h": 3600, "24h": 86400, "7d": 604800, "30d": 2592000, "all": None}


def _filter_by_range(records: list, range_str: str) -> list:
    from datetime import datetime, timezone
    secs = _RANGE_SECONDS.get(range_str)
    if secs is None:
        return records
    now = datetime.now(timezone.utc).timestamp()
    cutoff = now - secs
    result = []
    for r in records:
        try:
            ts = datetime.fromisoformat(r["timestamp"].replace("Z", "+00:00")).timestamp()
            if ts >= cutoff:
                result.append(r)
        except Exception:
            result.append(r)
    return result


@router.get("/api/probe_history", tags=["history"])
async def get_probe_history(
    range: str = "24h", bridge: RosBridge = Depends(get_bridge)
) -> Dict[str, Any]:
    return {"readings": _filter_by_range(bridge.probe_history, range)}


@router.get("/api/dosing_history", tags=["history"])
async def get_dosing_history(
    range: str = "24h", bridge: RosBridge = Depends(get_bridge)
) -> Dict[str, Any]:
    return {"events": _filter_by_range(bridge.dosing_history, range)}


@router.get("/api/ndvi_history", tags=["history"])
async def get_ndvi_history(
    range: str = "7d", bridge: RosBridge = Depends(get_bridge)
) -> Dict[str, Any]:
    return {"readings": _filter_by_range(bridge.ndvi_history, range)}


@router.get("/api/water/topoff_history", tags=["history"])
async def get_topoff_history(bridge: RosBridge = Depends(get_bridge)) -> Dict[str, Any]:
    return {"events": bridge.topoff_history}


# ---------------------------------------------------------------------------
# Plant profiles
# ---------------------------------------------------------------------------


@router.get("/api/profiles", tags=["profiles"])
async def get_profiles() -> List[Dict[str, Any]]:
    return _PLANT_PROFILES


@router.get("/api/profiles/{name}", tags=["profiles"])
async def get_profile(name: str) -> Dict[str, Any]:
    for profile in _PLANT_PROFILES:
        if profile["name"] == name.lower():
            return profile
    raise HTTPException(status_code=404, detail=f"Profile '{name}' not found")


# ---------------------------------------------------------------------------
# Control endpoints (auth required)
# ---------------------------------------------------------------------------


@router.post("/api/controls/trigger_probe", tags=["controls"], dependencies=[Depends(require_auth)])
async def control_trigger_probe(bridge: RosBridge = Depends(get_bridge)) -> Dict[str, Any]:
    """Trigger an immediate probe cycle."""
    success = await asyncio.get_event_loop().run_in_executor(
        None, bridge.call_trigger_probe
    )
    if not success:
        raise HTTPException(status_code=503, detail="TriggerProbe service failed or timed out")
    return {"status": "ok"}


@router.post("/api/controls/trigger_aeration", tags=["controls"], dependencies=[Depends(require_auth)])
async def control_trigger_aeration(bridge: RosBridge = Depends(get_bridge)) -> Dict[str, Any]:
    """Trigger an immediate aeration cycle."""
    success = await asyncio.get_event_loop().run_in_executor(
        None, bridge.call_trigger_aeration
    )
    if not success:
        raise HTTPException(status_code=503, detail="TriggerAeration service failed or timed out")
    return {"status": "ok"}


@router.post("/api/controls/set_probe_interval", tags=["controls"], dependencies=[Depends(require_auth)])
async def control_set_probe_interval(
    body: ProbeIntervalRequest, bridge: RosBridge = Depends(get_bridge)
) -> Dict[str, Any]:
    """Set probe cycle interval in seconds (minimum enforced by node)."""
    applied = await asyncio.get_event_loop().run_in_executor(
        None, lambda: bridge.call_set_probe_interval(body.interval_seconds)
    )
    return {"status": "ok", "applied_interval_seconds": applied}


@router.post("/api/controls/capture_vision", tags=["controls"], dependencies=[Depends(require_auth)])
async def control_capture_vision(bridge: RosBridge = Depends(get_bridge)) -> Dict[str, Any]:
    """Trigger an immediate vision capture cycle."""
    success = await asyncio.get_event_loop().run_in_executor(
        None, bridge.call_capture_vision
    )
    if not success:
        raise HTTPException(status_code=503, detail="CaptureVision service failed or timed out")
    return {"status": "ok"}


@router.post("/api/controls/dose", tags=["controls"], dependencies=[Depends(require_auth)])
async def control_dose(
    body: DoseRequest, bridge: RosBridge = Depends(get_bridge)
) -> Dict[str, Any]:
    """Publish a manual dose command.  The dosing node honours safety limits."""
    valid_pumps = {"ph_up", "ph_down", "nutrient_a", "nutrient_b"}
    if body.pump_id not in valid_pumps:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid pump_id '{body.pump_id}'. Valid: {sorted(valid_pumps)}",
        )
    # Publish a DosingEvent command on a control topic (dosing_node subscribes)
    from hydroponics_msgs.msg import DosingEvent  # type: ignore
    pub = bridge.create_publisher(DosingEvent, "/dosing/manual_command", 10)
    msg = DosingEvent()
    msg.pump_id = body.pump_id
    msg.dose_mL = body.amount_ml
    msg.reason = "manual_dashboard"
    pub.publish(msg)
    bridge.destroy_publisher(pub)
    return {"status": "ok", "pump_id": body.pump_id, "amount_ml": body.amount_ml}


@router.post("/api/controls/light/{intensity}", tags=["controls"], dependencies=[Depends(require_auth)])
async def control_light(
    intensity: float, bridge: RosBridge = Depends(get_bridge)
) -> Dict[str, Any]:
    """Override grow light intensity (0–100 %)."""
    if not 0.0 <= intensity <= 100.0:
        raise HTTPException(status_code=400, detail="Intensity must be between 0 and 100")
    # hydroponics_lighting subscribes to /lighting/set_intensity (Float32)
    from std_msgs.msg import Float32  # type: ignore
    pub = bridge.create_publisher(Float32, "/lighting/set_intensity", 10)
    msg = Float32()
    msg.data = float(intensity)
    pub.publish(msg)
    bridge.destroy_publisher(pub)
    return {"status": "ok", "intensity_percent": intensity}


@router.post("/api/controls/estop", tags=["controls"], dependencies=[Depends(require_auth)])
async def control_estop(
    bridge: RosBridge = Depends(get_bridge),
) -> Dict[str, Any]:
    """Publish a critical emergency-stop alert."""
    from hydroponics_msgs.msg import SystemAlert  # type: ignore
    pub = bridge.create_publisher(SystemAlert, "/system_alert", 10)
    msg = SystemAlert()
    msg.header.stamp = bridge.get_clock().now().to_msg()
    msg.alert_type = "estop"
    msg.severity = "critical"
    msg.message = "Manual E-STOP from dashboard"
    msg.recommended_action = "Inspect system immediately. Reset when safe."
    pub.publish(msg)
    bridge.destroy_publisher(pub)
    logger.warning("E-STOP published from dashboard")
    return {"status": "estop_published"}


# ---------------------------------------------------------------------------
# WebSocket stream
# ---------------------------------------------------------------------------


@router.websocket("/ws/stream")
async def ws_stream(websocket: WebSocket, bridge: RosBridge = Depends(get_bridge)) -> None:
    """Stream sensor data to the client at ~1 Hz, plus immediate event pushes."""
    await websocket.accept()
    logger.info("WebSocket client connected: %s", websocket.client)

    queue: asyncio.Queue[str] = asyncio.Queue(maxsize=256)
    loop = asyncio.get_event_loop()

    def _sender(text: str) -> None:
        try:
            loop.call_soon_threadsafe(queue.put_nowait, text)
        except Exception:
            pass

    bridge.register_ws_sender(_sender)
    bridge.broadcast_snapshot()

    try:
        while True:
            try:
                message = await asyncio.wait_for(queue.get(), timeout=1.0)
                await websocket.send_text(message)
            except asyncio.TimeoutError:
                heartbeat = json.dumps(
                    {
                        "type": "heartbeat",
                        "data": {
                            "probe_reading": bridge.probe_reading,
                            "ndvi_reading": bridge.ndvi_reading,
                            "water_level": bridge.water_level,
                            "plant_status": bridge.plant_status,
                            "diagnostic_report": bridge.diagnostic_report,
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
