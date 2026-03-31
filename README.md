# AIdroponics

**Autonomous deep-water-culture hydroponics system** with AI-powered plant health monitoring, real-time PID nutrient control, and behavior tree orchestration — built on ROS2 Humble, running on a Raspberry Pi 5 with an ESP32 co-processor.

A single linear rail transports plants between a grow station and an inspection/harvest station. The system handles everything autonomously: pH/EC dosing, growth-stage lighting schedules, machine vision inspections, harvest decisions, yield analytics, and cloud reporting — all coordinated by a reactive behavior tree that enforces safety invariants on every tick.

---

## Tech Stack

| Layer | Technologies |
|---|---|
| **Orchestration** | BehaviorTree.CPP v4, 25+ custom nodes, reactive safety guards |
| **Machine Vision** | YOLOv8 segmentation, dual-camera pipeline, pixel-to-mm calibration |
| **Control Systems** | Dual-loop PID (pH + EC) with anti-windup, derivative-on-measurement |
| **Embedded** | ESP32-S3 micro-ROS, TMC2209 UART stepper drivers, ISR motion profiles |
| **Middleware** | ROS2 Humble (C++ & Python), 14 custom msgs, 9 services, 3 actions |
| **Web** | FastAPI + React, WebSocket streaming, real-time sensor gauges |
| **Data** | SQLite analytics pipeline, down-sampled time-series, yield economics |
| **Cloud** | HiveMQ MQTT TLS bridge, Home Assistant auto-discovery |
| **Infrastructure** | Docker, PlatformIO, colcon build system |

**Languages:** C++ (BT orchestrator, transport, work station, micro-ROS bridge) / Python (vision, nutrients, harvest, lighting, data, MQTT, dashboard) / JavaScript/React (frontend) / Arduino C++ (ESP32 firmware)

---

## System Architecture

```
                          ┌──────────────────────────────────┐
                          │   BehaviorTree.CPP Orchestrator  │
                          │   (10 Hz reactive safety guard)  │
                          └────────┬──────────┬──────────────┘
                                   │          │
                    ROS2 Actions    │          │   ROS2 Services
               ┌───────────────────┤          ├──────────────────────┐
               │                   │          │                      │
     ┌─────────▼──────┐  ┌────────▼────┐  ┌──▼──────────┐  ┌───────▼────────┐
     │   Transport    │  │  Work Stn   │  │   Vision    │  │   Nutrients    │
     │  (C++ Action)  │  │ (C++ Action)│  │  (YOLOv8)   │  │  (Dual PID)   │
     │  Linear Rail   │  │ Z-Axis+Servo│  │ 2 Cameras   │  │  4 Pumps      │
     └───────┬────────┘  └──────┬──────┘  └──────┬──────┘  └───────┬───────┘
             │                  │                 │                  │
             └──────────┬───────┘                 │          ┌──────┘
                        │                         │          │
              ┌─────────▼─────────┐      ┌────────▼──┐  ┌───▼────────────┐
              │  micro-ROS Bridge │      │  Harvest  │  │   Lighting     │
              │  (ESP32 Watchdog) │      │  Manager  │  │  (PWM Sched)   │
              └─────────┬─────────┘      └─────┬─────┘  └───┬────────────┘
                        │                      │            │
    ┌───────────────────┤              ┌───────▼────────────▼──┐
    │                   │              │    Data Pipeline      │
    │  ┌────────────┐   │              │  SQLite + Analytics   │
    │  │   ESP32    │   │              └───────────┬───────────┘
    │  │ micro-ROS  │◄──┘                         │
    │  │ firmware   │                 ┌────────────┼────────────┐
    │  └────────────┘                 │            │            │
    │   2 steppers                ┌───▼───┐  ┌────▼────┐  ┌────▼────┐
    │   4 pumps                  │ MQTT  │  │ FastAPI │  │ React  │
    │   5 sensors                │ Bridge│  │ Backend │  │ Dash   │
    │   3 servos                 └───┬───┘  └────┬────┘  └────────┘
    │   2 light channels             │           │
    │   1 load cell              HiveMQ      :8080
    └────────────────────────────  Cloud
```

---

## Engineering Highlights

### Reactive Behavior Tree Orchestration
The system is coordinated by a BehaviorTree.CPP v4 tree with 25+ custom nodes across 6 domains. A `ReactiveSequence` root re-evaluates safety conditions (system health, disease flags) on every 10 Hz tick, providing immediate abort capability mid-operation. Long-running operations (transport, harvest, inspection) use `StatefulActionNode` for async handling with timeout protection.

### Machine Vision Pipeline
Dual-camera YOLOv8 segmentation pipeline classifies plant health across 8 categories. A `PlantMeasurer` module converts pixel-space metrics (canopy area, height, leaf count) to calibrated real-world measurements (cm², cm). A `DeficiencyClassifier` aggregates per-plant health state and detects nutrient deficiency trends (nitrogen, potassium, phosphorus) across the channel.

### Dual-Loop PID Nutrient Control
Independent pH and EC PID controllers run at 1 Hz with derivative-on-measurement (avoids setpoint kick), integral anti-windup clamping, and configurable dead-band tolerance to prevent actuator chatter. Growth-stage-aware setpoints automatically adjust targets as plants progress from seedling to mature. Four peristaltic pumps (pH up/down, Nutrient A/B) are flow-rate calibrated with enforced mixing wait periods between doses.

### ESP32 Real-Time Firmware
Custom Arduino/micro-ROS firmware manages all hardware I/O: ISR-driven stepper motion profiles on two axes (rail transport + Z-axis), TMC2209 register-level UART configuration for StallGuard4 load detection, non-blocking sensor acquisition loops (pH ADC with 10-sample moving average, EC probe, DS18B20 OneWire, HX711 load cell), PWM-controlled lighting, and MOSFET-gated pump actuation — all without blocking the micro-ROS executor or triggering WDT resets.

### Full-Stack Dashboard
FastAPI backend bridges ROS2 topics into a REST API with 11+ endpoints covering system status, manual controls (transport, dosing, lighting, e-stop), and analytics queries. A multi-threaded ROS executor runs alongside the ASGI server. The React frontend provides live sensor gauges, behavior tree visualization, nutrient history charts, plant profile management, and harvest tracking with glassmorphism UI.

### Data Pipeline & Economics
SQLite-backed analytics pipeline down-samples high-frequency sensor data (10 Hz from ESP32) to 0.1 Hz for storage efficiency. Computes growth rates (cm²/day) from consecutive inspections and yield economics (yield per watt-hour, cost per gram) from configurable energy/nutrient cost rates. Publishes aggregated `YieldMetrics` every 60 seconds.

---

## Project Metrics

| Metric | Count |
|---|---|
| ROS2 Nodes | 11 (4 C++ / 7 Python) |
| Custom Message Types | 14 |
| Custom Services / Actions | 9 / 3 |
| Behavior Tree Nodes | 25+ |
| Hardware Integrations | 12 peripherals across 2 MCU axes |
| Communication Layers | 3 (ROS2 DDS, micro-ROS serial, MQTT TLS) |
| Dashboard API Endpoints | 11+ |
| Plant Profiles | 5 (parsley, basil, cilantro, mint, lettuce) |

---

## Workspace Layout

```
hydroponics_ws/src/
  hydroponics_msgs/             Custom msg/srv/action definitions
  hydroponics_bt/               C++ BehaviorTree.CPP orchestrator + 25 custom nodes
  hydroponics_transport/        C++ linear rail action server (TransportTo)
  hydroponics_work_station/     C++ Z-axis + servo action server (MoveZ)
  hydroponics_micro_ros_bridge/ C++ ESP32 watchdog and connectivity monitor
  hydroponics_vision/           Python YOLOv8 vision pipeline (4 modules)
  hydroponics_nutrients/        Python dual-PID nutrient controller
  hydroponics_lighting/         Python photoperiod schedule controller
  hydroponics_harvest/          Python harvest manager + decision logic
  hydroponics_data/             Python SQLite analytics pipeline (4 modules)
  hydroponics_mqtt/             Python HiveMQ Cloud MQTT bridge
  hydroponics_dashboard/        FastAPI backend + React frontend (14 components)
  hydroponics_bringup/          6 launch files + URDF xacro model
  hydroponics_mocks/            Mock ESP32 + cameras for simulation mode
esp32_firmware/                 PlatformIO micro-ROS firmware (7 source modules)
training/                       YOLOv8 training + data collection scripts
docs/                           Architecture, wiring, calibration, scaling guides
docker/                         Dockerfile + entrypoint
```

---

## Quick Start

```bash
# Build
cd hydroponics_ws
rosdep install --from-paths src --ignore-src -r -y
colcon build --symlink-install
source install/setup.bash

# Launch (simulation — no hardware required)
ros2 launch hydroponics_bringup simulation.launch.py

# Launch (full system with hardware)
ros2 launch hydroponics_bringup full_system.launch.py plant_profile:=parsley

# Dashboard at http://localhost:8080
```

### ESP32 Firmware
```bash
cd esp32_firmware
pio run --target upload    # See esp32_firmware/README.md for pin wiring
```

### Docker
```bash
docker build -t aidroponics:latest .
docker run --rm -it -p 8080:8080 aidroponics:latest simulation
```

---

## Documentation

- [Architecture](docs/architecture.md) — Node inventory, topic graph, data flow
- [Wiring Diagram](docs/wiring_diagram.md) — ESP32 pin assignments, schematic
- [Calibration Guide](docs/calibration_guide.md) — Stepper, pH, EC, load cell procedures
- [Scaling Guide](docs/scaling_guide.md) — Multi-channel, multi-computer, commercial

---

## License

MIT
