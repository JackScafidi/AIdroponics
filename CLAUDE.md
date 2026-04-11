# AIdroponics Project

## Overview
Autonomous hydroponics farming system — ROS2 Humble, single-plant validation platform (V0.1) with dual-camera NDVI+RGB vision, explicit-chemistry A/B auto-dosing, servo-driven probe/aeration cycle, and reactive water management. Running on Raspberry Pi CM4 with ESP32 co-processor.

## Build
```bash
cd hydroponics_ws
rosdep install --from-paths src --ignore-src -r -y
colcon build --symlink-install
source install/setup.bash
ros2 launch hydroponics_bringup v01_single_plant.launch.py plant_type:=basil
ros2 launch hydroponics_bringup simulation.launch.py   # no hardware
```

## Tests (no ROS required)
```bash
cd hydroponics_ws/src/hydroponics_tests
python -m pytest test/ -v
```

## Frontend Dev Server
```bash
cd hydroponics_ws/src/hydroponics_dashboard/frontend
npm install
npx vite   # serves on :3000, proxies /api to :8080
```

## Architecture
- 12 ROS2 nodes, all Python except micro_ros_bridge (C++)
- ESP32 micro-ROS firmware for all hardware I/O
- Each node manages its own timed loop (no BT orchestrator in V0.1)
- FastAPI + React web dashboard on port 8080
- SQLite local database
- HiveMQ Cloud MQTT TLS bridge

## Dashboard Auth
- Control endpoints (`/api/controls/*`) require bearer token auth
- Read-only endpoints (status, sensors, analytics) are public for shared viewer access
- Auth module: `hydroponics_dashboard/auth.py` — salted SHA-256 hash, never plain text
- Vite dev server includes a mock auth plugin so login works without the FastAPI backend

## Leaf Animation
- `FallingLeaves.jsx` — physics-based rAF animation (not CSS keyframes)
- 20 leaves with sinusoidal sway, aerodynamic Z-rotation coupled to sway direction, parallax depth via scale-based opacity
- Recycled on completion with re-randomized properties

## NDVI Vision Pipeline
- Dual CSI cameras: RGB (IMX477) + NoIR (V2 + blue gel)
- NDVI = (NIR - visible) / (NIR + visible) where NIR = red channel, visible = blue channel
- AprilTag scale calibration (cv2.aruco), HSV plant segmentation, temporal change tracking
- Declining NDVI slope → early-warning mode: probe interval 15 min → 5 min, capture 30 min → 10 min

## Dosing Chemistry
- Explicit math (not PID): pH dose = |pH_error| × volume_L × (1/molarity); EC dose split by A:B ratio
- pH corrected before nutrients (affects solubility)
- Safety: max_dose_mL cap, min_dose_interval per pump, max_doses_per_hour sliding window
- Verify-after-dose loop; emergency lockout after 3 consecutive failed verify cycles

## Workspace Layout
```
hydroponics_ws/src/
  hydroponics_msgs/             Custom msg/srv/action (22 msg, 13 srv, 3 action)
  hydroponics_probe/            Python probe arm + aeration nodes
  hydroponics_vision/           Python dual-camera vision node (NDVI + RGB pipeline)
  hydroponics_dosing/           Python explicit-chemistry dosing node
  hydroponics_water/            Python water level + auto top-off node
  hydroponics_diagnostics/      Python YAML rule engine diagnostic node
  hydroponics_led/              Python GPIO LED status node
  hydroponics_micro_ros_bridge/ C++ ESP32 watchdog/connectivity monitor
  hydroponics_nutrients/        Python legacy PID controller (kept for reference)
  hydroponics_lighting/         Python light schedule controller
  hydroponics_data/             Python SQLite data pipeline + analytics (4 files)
  hydroponics_mqtt/             Python MQTT bridge
  hydroponics_dashboard/        FastAPI backend + React frontend + auth module
  hydroponics_bringup/          Launch files + config (plant_library, v01_system, diagnostic_rules)
  hydroponics_mocks/            mock_esp32.py + mock_cameras.py
  hydroponics_tests/            Unit + integration tests (no ROS required)
  future/                       Archived multi-bin code (transport, BT, harvest, work_station)
esp32_firmware/                 PlatformIO micro-ROS firmware (7 source modules)
training/                       YOLOv8 training + data collection scripts
docs/                           Architecture, wiring, calibration, scaling guides
docker/                         Dockerfile + entrypoint
```

## Key Config Files
- `hydroponics_bringup/config/plant_library.yaml` — basil, mint, parsley, rosemary with NDVI thresholds
- `hydroponics_bringup/config/v01_system.yaml` — all tunable parameters (probe, dosing, vision, water, LED)
- `hydroponics_bringup/config/diagnostic_rules.yaml` — 10 YAML rules for the diagnostic engine
