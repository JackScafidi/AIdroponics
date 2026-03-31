# AIdroponics Project

## Overview
Autonomous hydroponics farming system — ROS2 Humble, station-based architecture with linear rail transport, YOLOv8 machine vision, automated harvesting, PID nutrient management, and full data pipeline. See `hydroponics_final_claude_code_prompt.md` for full specification.

## Build
```bash
cd hydroponics_ws
colcon build --symlink-install
source install/setup.bash
ros2 launch hydroponics_bringup full_system.launch.py plant_profile:=parsley
ros2 launch hydroponics_bringup simulation.launch.py   # no hardware
```

## Frontend Dev Server
```bash
cd hydroponics_ws/src/hydroponics_dashboard/frontend
npm install
npx vite   # serves on :3000, proxies /api to :8080
```

## Architecture
- 11 ROS2 nodes: 4 C++ + 7 Python
- ESP32 micro-ROS firmware for all hardware I/O
- BehaviorTree.CPP master orchestrator
- FastAPI + React web dashboard on port 8080
- SQLite local database
- HiveMQ Cloud MQTT bridge

## Dashboard Auth
- Control endpoints (`/api/controls/*`) require bearer token auth
- Read-only endpoints (status, sensors, analytics) are public for shared viewer access
- Auth module: `hydroponics_dashboard/auth.py` — salted SHA-256 hash, never plain text
- Vite dev server includes a mock auth plugin so login works without the FastAPI backend

## Leaf Animation
- `FallingLeaves.jsx` — physics-based rAF animation (not CSS keyframes)
- 20 leaves with sinusoidal sway, aerodynamic Z-rotation coupled to sway direction, parallax depth via scale-based opacity
- Recycled on completion with re-randomized properties

## Workspace Layout
```
hydroponics_ws/src/
  hydroponics_msgs/             Custom msg/srv/action (13 msg, 9 srv, 3 action)
  hydroponics_transport/        C++ rail transport controller (ROS2 action server)
  hydroponics_work_station/     C++ Z-axis + servo work station controller
  hydroponics_micro_ros_bridge/ C++ ESP32 watchdog/connectivity monitor
  hydroponics_bt/               C++ BT manager + 4 node files + main_tree.xml
  hydroponics_vision/           Python YOLOv8 vision node (5 files)
  hydroponics_nutrients/        Python PID nutrient controller (pid.py + controller)
  hydroponics_lighting/         Python light schedule controller
  hydroponics_harvest/          Python harvest manager + decision logic
  hydroponics_data/             Python SQLite data pipeline + analytics (4 files)
  hydroponics_mqtt/             Python MQTT bridge (mqtt_bridge.py)
  hydroponics_dashboard/        FastAPI backend + React frontend + auth module
  hydroponics_bringup/          6 launch files + URDF xacro
  hydroponics_mocks/            mock_esp32.py + mock_cameras.py
esp32_firmware/                 PlatformIO micro-ROS firmware (7 source modules)
training/                       YOLOv8 training + data collection scripts
docs/                           Architecture, wiring, calibration, scaling guides
docker/                         Dockerfile + entrypoint
```

## Key Config Files
- `hydroponics_bringup/config/plant_profiles/` — parsley, basil, cilantro, mint
- `hydroponics_nutrients/config/pid_params.yaml` — PID tuning
- `hydroponics_transport/config/transport_params.yaml` — rail positions (mm), steps/mm
- `hydroponics_vision/config/vision_params.yaml` — camera IDs, ROI coords, YOLO config
- `hydroponics_data/config/economics.yaml` — energy/nutrient cost rates
