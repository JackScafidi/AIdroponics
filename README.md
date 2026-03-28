# Claudroponics

Autonomous deep-water-culture (DWC) hydroponics system powered by ROS2 Humble,
BehaviorTree.CPP orchestration, YOLOv8 machine vision, PID nutrient control,
and a React dashboard.

A single linear rail transports plants between a **grow station** and an
**inspection/harvest station**. Everything from dosing pH/EC, triggering
inspections, deciding when to harvest, and logging yield data is fully automated.

---

## Feature Highlights

- **Station-based transport** — NEMA 17 stepper on linear rail, TMC2209 driver,
  BehaviorTree-driven move sequences
- **Machine vision** — YOLOv8 plant health classification (8 classes),
  canopy area measurement, deficiency detection
- **Dual-loop PID nutrient control** — independent pH and EC controllers with
  anti-windup, 4-pump dosing rig
- **Automated harvest** — weight-based yield measurement (HX711 load cell),
  harvest history, cut-cycle tracking
- **React dashboard** — live sensor gauges, behavior tree visualiser, nutrient
  history charts, plant profile editor, system controls
- **MQTT bridge** — HiveMQ Cloud TLS, Home Assistant auto-discovery
- **Docker support** — Python nodes + dashboard containerised for easy deployment

---

## Hardware Bill of Materials

| Component | Model / Spec | Qty | Cost (USD) |
|---|---|---|---|
| Single-board computer | Raspberry Pi 5 (8 GB) | 1 | $80 |
| Microcontroller | ESP32-S3 DevKit-C (38-pin) | 1 | $8 |
| Rail stepper | NEMA 17 (48 mm, 1.7 A) | 1 | $12 |
| Z-axis stepper | NEMA 17 (40 mm, 1.5 A) | 1 | $10 |
| Stepper driver | TMC2209 SilentStepStick | 2 | $16 |
| Harvest servo | Futaba S3003 or MG996R | 1 | $8 |
| Peristaltic pump 12 V | 1–5 mL/min flow | 4 | $40 |
| Pump MOSFET | IRF520 or IRLZ44N | 4 | $4 |
| pH electrode | BNC + analog module | 1 | $20 |
| EC probe | conductivity cell | 1 | $15 |
| Temperature sensor | DS18B20 waterproof | 1 | $5 |
| Load cell | 1 kg bar + HX711 module | 1 | $8 |
| Overhead camera | RPi Camera Module 3 | 1 | $25 |
| Side camera | USB webcam (1080p) | 1 | $20 |
| Grow light | 12 V LED strip (full spectrum) | 1 m | $12 |
| Inspection LEDs | 6500 K white LED ring | 1 | $6 |
| Linear rail | 1.2 m aluminium extrusion + belt | 1 | $25 |
| Power supply | 12 V 5 A | 1 | $18 |
| DWC channel | 4-pot PVC or foam board | 1 | $30 |
| Reservoir | 10 L food-grade tub | 1 | $10 |
| Misc (tubing, nuts, wiring) | — | — | $20 |
| **Total** | | | **~$392** |

---

## Quick Start

### Prerequisites

- Raspberry Pi 5 running Ubuntu 22.04 (64-bit)
- ROS2 Humble installed (`ros-humble-desktop`)
- PlatformIO CLI (for ESP32 firmware)
- Node.js 20+ (for React frontend build)

### 1. Clone & build

```bash
git clone https://github.com/your-org/claudroponics.git
cd claudroponics/hydroponics_ws

# Install ROS2 dependencies
rosdep install --from-paths src --ignore-src -r -y

# Build
colcon build --symlink-install
source install/setup.bash
```

### 2. Flash ESP32 firmware

```bash
cd esp32_firmware
pio run --target upload
```

See `esp32_firmware/README.md` for pin wiring and calibration.

### 3. Build the React frontend

```bash
cd hydroponics_ws/src/hydroponics_dashboard/frontend
npm install
npm run build
```

### 4. Launch

```bash
# Full system (parsley profile, real hardware)
ros2 launch hydroponics_bringup full_system.launch.py plant_profile:=parsley

# Simulation (no hardware required)
ros2 launch hydroponics_bringup simulation.launch.py

# Access dashboard
xdg-open http://localhost:8080
```

### 5. Train / update the vision model

```bash
cd training

# Collect frames from the running system
python collect_training_data.py collect --limit 500

# Label and train
python collect_training_data.py label
python collect_training_data.py split
python train_yolo.py --model yolov8s.pt --epochs 150
```

---

## Docker (Python nodes + dashboard)

```bash
docker build -t claudroponics:latest .

# Simulation mode
docker run --rm -it -p 8080:8080 claudroponics:latest simulation

# Dashboard only (connect to external ROS2 DDS)
docker run --rm -it --network host \
  -e ROS_DOMAIN_ID=0 \
  claudroponics:latest dashboard
```

---

## Workspace Layout

```
hydroponics_ws/src/
  hydroponics_msgs/          Custom msg/srv/action (13 msg, 9 srv, 3 action)
  hydroponics_transport/     C++ rail transport controller (ROS2 action server)
  hydroponics_work_station/  C++ Z-axis + servo controller (ROS2 action server)
  hydroponics_micro_ros_bridge/ C++ ESP32 watchdog / topic relay
  hydroponics_bt/            C++ BehaviorTree.CPP master orchestrator
  hydroponics_vision/        Python YOLOv8 vision node
  hydroponics_nutrients/     Python PID nutrient controller
  hydroponics_lighting/      Python light schedule controller
  hydroponics_harvest/       Python harvest manager
  hydroponics_data/          Python SQLite data pipeline + analytics
  hydroponics_mqtt/          Python MQTT bridge (HiveMQ Cloud)
  hydroponics_dashboard/     FastAPI + React web dashboard
  hydroponics_mocks/         Mock ESP32 + cameras for simulation
esp32_firmware/              PlatformIO Arduino + micro-ROS firmware
training/                    YOLOv8 training scripts
docs/                        Architecture, wiring, calibration, scaling guides
docker/                      Dockerfile + entrypoint
```

---

## Configuration

| File | Purpose |
|---|---|
| `hydroponics_bringup/config/plant_profiles/parsley.yaml` | pH/EC targets, harvest thresholds by growth stage |
| `hydroponics_nutrients/config/pid_params.yaml` | PID gains, anti-windup limits |
| `hydroponics_transport/config/transport_params.yaml` | Rail positions (mm), steps/mm |
| `hydroponics_vision/config/vision_params.yaml` | Camera IDs, ROI, YOLO model path |
| `hydroponics_mqtt/config/mqtt_config.yaml` | Broker host, TLS certs, topic map |
| `hydroponics_data/config/economics.yaml` | Energy/nutrient cost rates |

---

## Documentation

- [Architecture](docs/architecture.md) — node inventory, topic list, data flow
- [Wiring Diagram](docs/wiring_diagram.md) — ESP32 pin assignments, schematic
- [Calibration Guide](docs/calibration_guide.md) — stepper, pH, EC, load cell
- [Scaling Guide](docs/scaling_guide.md) — multi-channel, multi-computer, commercial

---

## License

MIT
