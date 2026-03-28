# Claudroponics Project

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

## Architecture
- 11 ROS2 nodes: 4 C++ + 7 Python
- ESP32 micro-ROS firmware for all hardware I/O
- BehaviorTree.CPP master orchestrator
- FastAPI + React web dashboard on port 8080
- SQLite local database
- HiveMQ Cloud MQTT bridge

## Generation Status: COMPLETE ✅ (2026-03-26)

## Workspace Layout
```
hydroponics_ws/src/
  hydroponics_msgs/          ✅ Custom msg/srv/action (13 msg, 9 srv, 3 action)
  hydroponics_transport/     ✅ C++ rail transport controller (ROS2 action server)
  hydroponics_work_station/  ✅ C++ Z-axis + servo work station controller
  hydroponics_micro_ros_bridge/ ✅ C++ ESP32 watchdog/connectivity monitor
  hydroponics_bt/            ✅ C++ BT manager + 4 node files + main_tree.xml
  hydroponics_vision/        ✅ Python YOLOv8 vision node (5 files)
  hydroponics_nutrients/     ✅ Python PID nutrient controller (pid.py + controller)
  hydroponics_lighting/      ✅ Python light schedule controller
  hydroponics_harvest/       ✅ Python harvest manager + decision logic
  hydroponics_data/          ✅ Python SQLite data pipeline + analytics (4 files)
  hydroponics_mqtt/          ✅ Python MQTT bridge (mqtt_bridge.py)
  hydroponics_dashboard/     ✅ FastAPI backend + React frontend (14 JSX/JS files)
  hydroponics_bringup/       ✅ 6 launch files + URDF xacro
  hydroponics_mocks/         ✅ mock_esp32.py + mock_cameras.py
esp32_firmware/              ✅ main.cpp + 6 source pairs + README
training/                    ✅ train_yolo.py, dataset_config.yaml, collect_training_data.py, README
docs/                        ✅ architecture.md, wiring_diagram.md, calibration_guide.md, scaling_guide.md
docker/                      ✅ Dockerfile + entrypoint.sh
README.md                    ✅ Top-level project README with BOM
```

## Key Config Files
- `hydroponics_bringup/config/plant_profiles/` — parsley, basil, cilantro, mint
- `hydroponics_nutrients/config/pid_params.yaml` — PID tuning
- `hydroponics_transport/config/transport_params.yaml` — rail positions (mm), steps/mm
- `hydroponics_vision/config/vision_params.yaml` — camera IDs, ROI coords, YOLO config
- `hydroponics_data/config/economics.yaml` — energy/nutrient cost rates

## Generation Progress
See `GENERATION_PROGRESS.md` for detailed file-level status. Generation is COMPLETE.
