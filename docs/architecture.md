# Claudroponics — System Architecture

## Overview

Claudroponics is a single-channel, station-based deep-water-culture (DWC)
hydroponics system with autonomous grow / inspect / harvest / dose cycles
orchestrated by a BehaviorTree.CPP state machine running on a Raspberry Pi 5.

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Raspberry Pi 5 (ROS2 Humble)                 │
│                                                                     │
│  ┌──────────────┐   ┌──────────────┐   ┌───────────────────────┐   │
│  │  BT Manager  │──▶│  Transport   │   │     Vision Node       │   │
│  │ (bt_manager) │   │  Controller  │   │  (YOLOv8 + measurer)  │   │
│  └──────┬───────┘   └──────────────┘   └───────────────────────┘   │
│         │                                                           │
│  ┌──────▼───────┐   ┌──────────────┐   ┌───────────────────────┐   │
│  │  Harvest Mgr │   │  Nutrient    │   │   Light Controller    │   │
│  │              │   │  Controller  │   │                       │   │
│  └──────────────┘   └──────────────┘   └───────────────────────┘   │
│                                                                     │
│  ┌──────────────┐   ┌──────────────┐   ┌───────────────────────┐   │
│  │ Data Pipeline│   │  MQTT Bridge │   │  Dashboard (FastAPI)  │   │
│  │  (SQLite)    │   │  (HiveMQ)    │   │  + React frontend     │   │
│  └──────────────┘   └──────────────┘   └───────────────────────┘   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │           micro-ROS Bridge (USB serial watchdog)            │   │
│  └──────────────────────────┬────────────────────────────────┘    │
└─────────────────────────────┼───────────────────────────────────────┘
                              │ USB (micro-ROS serial transport)
┌─────────────────────────────▼───────────────────────────────────────┐
│                     ESP32 Firmware (Arduino + micro-ROS)             │
│  Steppers (TMC2209) │ Pumps (MOSFET) │ Sensors (pH/EC/Temp/Weight)  │
│  Lighting (LEDC PWM)│ Load Cell (HX711)                             │
└─────────────────────────────────────────────────────────────────────┘
```

## ROS2 Node Inventory

| Node | Language | Package | Role |
|---|---|---|---|
| `bt_manager` | C++ | hydroponics_bt | BehaviorTree.CPP orchestrator, master controller |
| `transport_controller` | C++ | hydroponics_transport | Linear rail ROS2 action server |
| `work_station_controller` | C++ | hydroponics_work_station | Z-axis + servo ROS2 action server |
| `micro_ros_bridge` | C++ | hydroponics_micro_ros_bridge | ESP32 USB watchdog + topic relay |
| `vision_node` | Python | hydroponics_vision | YOLOv8 inference, canopy measurement |
| `nutrient_controller` | Python | hydroponics_nutrients | Dual PID pH/EC control, pump dosing |
| `light_controller` | Python | hydroponics_lighting | Schedule-based lighting + photoperiod |
| `harvest_manager` | Python | hydroponics_harvest | Harvest readiness logic, cut cycles |
| `data_pipeline` | Python | hydroponics_data | SQLite writer, REST analytics |
| `mqtt_bridge` | Python | hydroponics_mqtt | HiveMQ Cloud TLS bridge, HA discovery |
| `dashboard_server` | Python | hydroponics_dashboard | FastAPI + WebSocket + React static server |

## Key Topics

| Topic | Type | Publisher → Subscriber |
|---|---|---|
| `/system/status` | `BehaviorTreeStatus` | bt_manager → dashboard |
| `/nutrients/status` | `NutrientStatus` | nutrient_controller → bt_manager, dashboard |
| `/vision/inspection_result` | `InspectionResult` | vision_node → bt_manager, harvest_manager |
| `/vision/channel_health` | `ChannelHealthSummary` | vision_node → dashboard |
| `/transport/status` | `TransportStatus` | transport_controller → bt_manager, dashboard |
| `/harvest/plan` | `HarvestPlan` | harvest_manager → bt_manager |
| `/harvest/result` | `HarvestResult` | harvest_manager → data_pipeline, mqtt_bridge |
| `/system/alerts` | `SystemAlert` | all nodes → dashboard |
| `/sensors/raw` | `String` (JSON) | ESP32/micro_ros → nutrient_ctrl, data_pipeline |
| `/lighting/status` | `LightStatus` | light_controller → dashboard |

## Key Services

| Service | Type | Server |
|---|---|---|
| `/vision/trigger_inspection` | `TriggerInspection` | vision_node |
| `/nutrients/force_dose` | `ForceDose` | nutrient_controller |
| `/lighting/set_inspection_light` | `SetInspectionLight` | light_controller |
| `/transport/reset_crop_cycle` | — | harvest_manager |

## Key Actions

| Action | Type | Server |
|---|---|---|
| `/transport/move` | `MoveToPosition` | transport_controller |
| `/work_station/move` | `MoveZAxis` | work_station_controller |
| `/harvest/execute` | `ExecuteHarvest` | harvest_manager |

## BehaviorTree Structure

```
HydroponicsMain (Sequence)
├── PublishSystemStatus (Action)
└── SafetyGuard (ReactiveSequence)
    ├── CheckSystemSafe (Condition)
    ├── CheckNoDiseaseDetected (Condition)
    └── Operations (Sequence)
        ├── MaybeInspect (Fallback)
        │   └── InspectionCycle (Sequence)
        │       ├── TransportTo(INSPECT)
        │       ├── SetInspectionLight(on)
        │       ├── TriggerInspection
        │       ├── SetInspectionLight(off)
        │       ├── TransportTo(GROW)
        │       └── HarvestCycle (SubTree)
        └── NutrientCheck (SubTree)
            ├── CheckNutrientStatus(water)
            ├── PhControl (Fallback)
            ├── EcControl (Fallback)
            └── TempCheck (Fallback)
```

The tree runs at ~2 Hz. ReactiveSequence re-evaluates conditions every tick,
so a sudden safety failure aborts the current operation immediately.

## Data Flow

1. **ESP32** samples pH/EC/temp at 1 Hz, publishes JSON to `/sensors/raw`
2. **nutrient_controller** reads `/sensors/raw`, runs PID, publishes `/nutrients/status`, calls `/nutrients/force_dose` when corrections are needed
3. **bt_manager** reads `/nutrients/status` via blackboard; if pH/EC out of range the NutrientCheck subtree triggers dosing
4. **vision_node** is called via `/vision/trigger_inspection` service during each InspectionCycle; results go to blackboard and `/vision/inspection_result`
5. **harvest_manager** watches inspection results, emits `/harvest/plan` when a plant is ready; bt_manager calls `/harvest/execute`
6. **data_pipeline** records all growth data to SQLite; **dashboard_server** serves analytics over REST
7. **mqtt_bridge** forwards key readings to HiveMQ Cloud for Home Assistant integration and remote monitoring

## Database Schema

See `hydroponics_data/migrations/001_initial_schema.sql`.

Tables: `growth_data`, `harvest_log`, `nutrient_log`, `alerts_log`.

## Network Ports

| Port | Service |
|---|---|
| 8080 | FastAPI dashboard (HTTP + WebSocket) |
| 1883 | MQTT (local, unencrypted) |
| 8883 | MQTT TLS (HiveMQ Cloud) |
