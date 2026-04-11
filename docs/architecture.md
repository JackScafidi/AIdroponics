# AIdroponics — System Architecture (V0.1)

## Overview

AIdroponics V0.1 is a single-plant deep-water-culture (DWC) validation platform
with dual-camera NDVI+RGB vision, explicit-chemistry A/B auto-dosing, servo-driven
probe/aeration cycling, and reactive water management. It runs on a Raspberry Pi
CM4 with an ESP32 co-processor handling all hardware I/O via micro-ROS.

There is no BehaviorTree orchestrator in V0.1 — each node manages its own timed
loop independently, reacting to sensor readings and ROS2 topics.

```
┌───────────────────────────────────────────────────────────────────────────┐
│                     Raspberry Pi CM4 (ROS2 Humble)                        │
│                                                                           │
│  ┌─────────────────┐   ┌─────────────────┐   ┌────────────────────────┐  │
│  │  probe_arm_node │   │  aeration_node  │   │  plant_vision_node     │  │
│  │  (servo cycle)  │   │  (servo cycle)  │   │  (dual-cam NDVI+RGB)   │  │
│  └────────┬────────┘   └────────┬────────┘   └───────────┬────────────┘  │
│           │                     │                         │               │
│  ┌────────▼────────┐   ┌────────▼────────┐   ┌───────────▼────────────┐  │
│  │  dosing_node    │   │  water_level    │   │ plant_health_analyzer  │  │
│  │  (explicit pH/  │   │  _node          │   │ (YAML rule engine)     │  │
│  │   EC chemistry) │   │  (auto top-off) │   └───────────┬────────────┘  │
│  └─────────────────┘   └─────────────────┘               │               │
│                                                           │               │
│  ┌─────────────────┐   ┌─────────────────┐   ┌───────────▼────────────┐  │
│  │  data_pipeline  │   │  mqtt_bridge    │   │  led_status_node       │  │
│  │  (SQLite)       │   │  (HiveMQ TLS)   │   │  (GPIO LED indicator)  │  │
│  └─────────────────┘   └─────────────────┘   └────────────────────────┘  │
│                                                                           │
│  ┌────────────────────┐   ┌──────────────────────────────────────────┐   │
│  │ lighting_node      │   │  dashboard_server                        │   │
│  │ (schedule + PWM)   │   │  (FastAPI :8080 + WebSocket + React UI)  │   │
│  └────────────────────┘   └──────────────────────────────────────────┘   │
│                                                                           │
│  ┌───────────────────────────────────────────────────────────────────┐   │
│  │              micro_ros_bridge (C++ USB watchdog)                   │   │
│  └────────────────────────────┬──────────────────────────────────────┘   │
└───────────────────────────────┼───────────────────────────────────────────┘
                                │ USB (micro-ROS serial transport)
┌───────────────────────────────▼───────────────────────────────────────────┐
│                      ESP32 Firmware (PlatformIO + micro-ROS)               │
│   Pumps ×4 (MOSFET) │ Probe servo │ Aeration servo │ Water level sensor   │
│   pH / EC / Temp ADC │ Lighting PWM (LEDC)                                │
└───────────────────────────────────────────────────────────────────────────┘
```

## ROS2 Node Inventory

| Node | Language | Package | Role |
|---|---|---|---|
| `probe_arm_node` | Python | hydroponics_probe | Servo arm lowers probe into reservoir on timed cycle; triggers dosing |
| `aeration_node` | Python | hydroponics_probe | Servo-driven aeration diffuser cycle |
| `plant_vision_node` | Python | hydroponics_vision | Dual-camera NDVI+RGB pipeline; AprilTag scale, HSV segmentation, temporal tracking |
| `dosing_node` | Python | hydroponics_dosing | Explicit-chemistry pH/EC correction; sliding-window safety limits |
| `water_level_node` | Python | hydroponics_water | Ultrasonic water level sensing; auto top-off pump control |
| `plant_health_analyzer` | Python | hydroponics_diagnostics | YAML rule engine; emits DiagnosticReport and SystemAlert |
| `led_status_node` | Python | hydroponics_led | GPIO LED status indicator (green/yellow/red) |
| `light_controller` | Python | hydroponics_lighting | Schedule-based grow light; intensity via ESP32 PWM |
| `data_pipeline` | Python | hydroponics_data | SQLite writer + analytics queries |
| `mqtt_bridge` | Python | hydroponics_mqtt | HiveMQ Cloud TLS bridge; Home Assistant MQTT discovery |
| `micro_ros_bridge` | C++ | hydroponics_micro_ros_bridge | ESP32 USB watchdog + topic relay |
| `dashboard_server` | Python | hydroponics_dashboard | FastAPI REST + WebSocket + React static server |

## Key Topics

| Topic | Message Type | Publisher → Subscriber |
|---|---|---|
| `/probe/reading` | `ProbeReading` | probe_arm_node → dosing_node, dashboard, data_pipeline |
| `/ndvi/reading` | `NDVIReading` | plant_vision_node → plant_health_analyzer, dashboard, data_pipeline |
| `/ndvi/alert` | `NDVIAlert` | plant_vision_node → probe_arm_node (interval override), dashboard |
| `/plant/measurement` | `PlantMeasurement` | plant_vision_node → plant_health_analyzer, dashboard |
| `/plant/status` | `PlantStatus` | plant_health_analyzer → dashboard, mqtt_bridge |
| `/water/level` | `WaterLevel` | water_level_node → plant_health_analyzer, dashboard |
| `/water/topoff_event` | `TopOffEvent` | water_level_node → data_pipeline, dashboard |
| `/dosing/event` | `DosingEvent` | dosing_node → data_pipeline, dashboard |
| `/dosing/manual_command` | `DosingEvent` | dashboard → dosing_node |
| `/diagnostics/report` | `DiagnosticReport` | plant_health_analyzer → dashboard, mqtt_bridge |
| `/system_alert` | `SystemAlert` | all nodes → dashboard, mqtt_bridge |
| `/lighting/set_intensity` | `Float32` | dashboard → light_controller |

## Key Services

| Service | Message Type | Server |
|---|---|---|
| `/probe/trigger` | `TriggerProbe` | probe_arm_node |
| `/aeration/trigger` | `TriggerAeration` | aeration_node |
| `/probe/set_interval` | `SetProbeInterval` | probe_arm_node |
| `/vision/capture` | `CaptureVision` | plant_vision_node |

## NDVI Vision Pipeline

```
IMX477 (RGB) ──┐
               ├── plant_vision_node
V2 NoIR        ┘
  + blue gel

1. Capture RGB + NoIR frames (dual CSI)
2. AprilTag detection → pixel-to-cm scale factor
3. HSV segmentation → plant ROI mask
4. NDVI = (NIR - visible) / (NIR + visible)
     NIR     = red channel of NoIR image
     visible = blue channel of NoIR image
5. Per-pixel NDVI → mean, median, std_dev over plant ROI
6. Temporal slope (linear regression over trend_window readings)
7. Declining slope → early-warning mode
     probe interval: 15 min → 5 min
     vision interval: 30 min → 10 min
8. Publish NDVIReading + PlantMeasurement
```

## Dosing Chemistry

The dosing node uses explicit stoichiometry, not PID:

```
pH dose (mL) = |pH_error| × reservoir_volume_L × (1 / molarity)
EC dose (mL) = |EC_error| × reservoir_volume_L × dose_factor
A:B split    = nutrient_ab_ratio (from plant_library.yaml, default 1.0)
```

Safety constraints (all enforced per pump):
- `max_dose_mL` cap per single dose
- `min_dose_interval_s` between doses on same pump
- Sliding window: max doses per hour
- pH corrected before nutrients (affects nutrient solubility)
- Verify-after-dose loop; emergency lockout after 3 consecutive failed verify cycles

## Diagnostic Rule Engine

`plant_health_analyzer` evaluates 10 YAML rules from `diagnostic_rules.yaml` every
tick. Each rule specifies:
- `condition`: sensor field + operator + threshold (e.g. `ph > 7.5`)
- `severity`: 0 (info), 1 (warning), 2 (critical)
- `symptom`: human-readable description
- `recommendation`: action string
- `dosing_action`: optional pump command to trigger

The node publishes `DiagnosticReport` (overall_severity, active_rules,
detected_symptoms, recommendations, dosing_action) and emits `SystemAlert` for
any rule at severity ≥ 1.

## Data Flow

1. **ESP32** samples pH/EC/temp at 1 Hz, water level at 0.5 Hz; publishes via micro-ROS
2. **probe_arm_node** lowers servo arm on timed cycle (default 15 min); reads probe; publishes `ProbeReading`
3. **dosing_node** receives `ProbeReading`; if pH or EC outside target computes dose; publishes `DosingEvent`
4. **plant_vision_node** runs dual-camera NDVI pipeline on schedule (default 30 min); publishes `NDVIReading` + `PlantMeasurement`
5. **plant_health_analyzer** evaluates rules against latest readings; publishes `DiagnosticReport`; issues `NDVIAlert` if NDVI declining
6. **probe_arm_node** listens to `NDVIAlert` — if declining NDVI, tightens probe interval to 5 min
7. **data_pipeline** records all readings and events to SQLite
8. **dashboard_server** serves REST analytics and streams live data to browser via WebSocket at ~1 Hz
9. **mqtt_bridge** forwards readings and alerts to HiveMQ Cloud for Home Assistant integration

## Database Schema

Tables: `probe_readings`, `ndvi_readings`, `dosing_events`, `topoff_events`, `alerts_log`.

See `hydroponics_data/` for schema and analytics queries.

## Network Ports

| Port | Service |
|---|---|
| 8080 | FastAPI dashboard (HTTP + WebSocket `/ws/stream`) |
| 8883 | MQTT TLS (HiveMQ Cloud) |
