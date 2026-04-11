# AIdroponics

**Autonomous deep-water-culture hydroponics system** with AI-powered plant health monitoring, explicit-chemistry auto-dosing, dual-camera NDVI vision, and water management — built on ROS2 Humble, running on a Raspberry Pi CM4 with an ESP32 co-processor.

V0.1 is a minimal single-plant validation platform. It validates four tightly coupled subsystems before scaling: the probe/aeration mechanical cycle, the dual-camera NDVI+RGB vision pipeline, closed-loop A/B nutrient dosing, and reactive water level management.

---

## V0.1 — What It Validates

| Subsystem | Key Capability |
|---|---|
| **Probe Arm** | Servo-driven pH/EC/temp probe cycle, configurable interval, /probe/set_interval service |
| **Aeration** | Servo-driven airstone cycle, configurable on/off schedule |
| **Dual-Camera Vision** | RGB (IMX477) + NoIR (V2 + blue gel) CSI cameras; NDVI computation; AprilTag scale calibration; HSV plant segmentation; temporal change tracking |
| **Auto-Dosing** | Explicit chemistry math (not PID); pH-first dosing order; A/B nutrient split; verify-after-dose loop; full safety scaffolding |
| **Water Management** | Ultrasonic distance sensing; reactive auto top-off with feedback; consumption CSV logging |
| **Diagnostics** | YAML rule engine combining NDVI trends + RGB visual symptoms + sensor data into actionable DiagnosticReport |
| **LED Status** | GPIO RGB LED: green/yellow/red/blue mapped to system severity |

---

## How the NDVI Early-Warning Pipeline Works

```
Normal operation:
  NDVI stable & healthy → RGB captures at 30-min interval → routine monitoring

Early warning (NDVI declining):
  NDVI trend slope < threshold
  → probe interval drops 15 min → 5 min
  → capture interval drops 30 min → 10 min
  → NDVIAlert published
  → RGB camera analyzes for specific visual symptoms

Diagnosis:
  Diagnostic engine combines:
    NDVI trend (chlorophyll stress, days-early warning)
    + RGB symptoms (yellowing_established, symptomatic_new_growth, browning_edges)
    + probe readings (pH, EC, temperature)
  → matches YAML diagnostic rules
  → identifies probable cause
  → auto-doser acts, or flags for manual intervention

Key insight: NDVI detects ALL plant stress regardless of species or cause.
RGB + sensors then disambiguate the specific problem.
The sensor_ndvi_mismatch rule handles the case where NDVI is stressed but
EC/pH look fine — this means selective nutrient depletion or root disease,
which the system cannot auto-fix, and correctly recommends manual inspection.
```

---

## Dosing Chemistry

Dosing uses explicit physical math, not PID. Every dose calculation traces back to configurable parameters in `v01_system.yaml`.

**pH dose (linear approximation — safe to undershoot, verify loop corrects remainder):**
```
dose_mL = |pH_error| × solution_volume_L × (1.0 / adjuster_molarity)
dose_mL = min(dose_mL, max_dose_mL)
```

**EC dose (linear — reliable in hydroponic concentration range):**
```
ec_deficit = target_EC_min - current_EC
total_dose_mL = (ec_deficit × volume_L) / combined_ec_rate_per_mL_per_L
dose_A = total × (A_ratio / (A_ratio + 1))
dose_B = total × (1 / (A_ratio + 1))
each capped at max_dose_mL
```

**Safety scaffolding (mandatory, non-negotiable):**
- `max_dose_mL`: cap per pump per dose (default 5 mL)
- `min_dose_interval_seconds`: floor between consecutive doses of same pump (default 300s)
- `max_doses_per_hour`: total dose events allowed per hour (default 8)
- Verify-after-dose loop: re-probe after mixing wait; re-dose only if still out of range and safety limits allow
- Emergency lockout: 3 consecutive failed verify cycles → halt all dosing + RED LED + error message

**Calibrate `ec_per_mL_per_L`:** Add 1 mL of concentrate to 1 L of RO water, measure EC increase, record the value per brand.

---

## Plant Parameter Library

`config/plant_library.yaml` contains per-herb growing parameters. Set active plant at launch with `plant_type:=basil`.

```yaml
plants:
  basil:
    ph:        { ideal: [5.5, 6.5], acceptable: [5.0, 6.8] }
    ec_mS_cm:  { ideal: [1.0, 1.6], acceptable: [0.8, 2.0] }
    temperature_C: { ideal: [18, 27], acceptable: [15, 30] }
    ndvi:      { healthy_min: 0.3, warning_threshold: 0.2, critical_threshold: 0.1 }
    nutrient_ab_ratio: 1.0
```

To add a new herb: add an entry to `plant_library.yaml` with the same structure, and add NDVI thresholds from published literature or calibrate empirically.

---

## Diagnostic Rule Engine

`config/diagnostic_rules.yaml` defines 10 rules combining NDVI, RGB symptoms, and sensor predicates. Rules match ALL conditions — first rule with a non-none `dosing_action` determines what the system does.

| Rule | Key Conditions | Severity | Action |
|---|---|---|---|
| healthy | NDVI stable, all in ideal | info | none |
| early_stress_detected | NDVI declining, sensors OK | warning | none |
| nitrogen_deficiency | NDVI↓ + yellowing_established + EC low | warning | increase_ec |
| ph_lockout | NDVI↓ + yellowing_established + pH high | critical | decrease_ph |
| iron_deficiency | NDVI↓ + symptomatic_new_growth + pH above ideal | warning | decrease_ph |
| nutrient_burn | brown_edges + EC high | warning | none (dilute manually) |
| temperature_stress | temp outside acceptable | critical | none |
| growth_stall | stall flag + NDVI OK + sensors OK | warning | none |
| rapid_water_consumption | consumption above normal avg | info | none |
| sensor_ndvi_mismatch | NDVI stressed + sensors normal | warning | none (manual) |

To add a new rule: add a YAML entry to `diagnostic_rules.yaml`. No code changes required.

---

## Tech Stack

| Layer | Technologies |
|---|---|
| **Vision** | Dual CSI cameras (RGB IMX477 + NoIR V2), OpenCV NDVI computation, ArUco AprilTag detection, HSV segmentation, temporal frame tracking |
| **Control** | Explicit chemistry dosing math, verify-after-dose loops, mandatory safety scaffolding |
| **Diagnostics** | YAML rule engine, multi-signal synthesis (NDVI + RGB + sensors) |
| **Embedded** | ESP32 micro-ROS, servo control, GPIO pumps/solenoid, ultrasonic sensor |
| **Middleware** | ROS2 Humble (Python), 22 custom msgs, 13 services, 3 actions |
| **Web** | FastAPI + React, WebSocket streaming, real-time sensor gauges |
| **Data** | SQLite analytics, water consumption CSV, frame pair storage |
| **Cloud** | HiveMQ MQTT TLS bridge |

---

## Project Metrics

| Metric | Count |
|---|---|
| ROS2 Nodes (V0.1 active) | 12 |
| Custom Message Types | 22 (13 legacy + 9 new) |
| Custom Services | 13 (9 legacy + 4 new) |
| Diagnostic Rules | 10 |
| Plant Profiles | 4 (basil, mint, parsley, rosemary) |
| Unit Tests | 6 test files |
| Integration Tests | 3 test files |

---

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

### What Is Archived in `src/future/`

Four packages moved to `src/future/` — none deleted, all preserved for V0.2 reintegration:

- **hydroponics_transport** — linear rail stepper controller. Not needed: V0.1 has a single stationary bin.
- **hydroponics_bt** — BehaviorTree.CPP orchestrator. Not needed: V0.1 nodes each manage their own timed loops.
- **hydroponics_harvest** — cut-and-regrow harvest manager. Not needed: no cutting mechanism in V0.1 hardware.
- **hydroponics_work_station** — Z-axis + cutter/gripper C++ node. Not needed: the V0.1 probe arm is a simpler servo mechanism handled by `hydroponics_probe`.

See `src/future/README.md` for reintegration notes per package.

---

## Quick Start

```bash
# Build
cd hydroponics_ws
rosdep install --from-paths src --ignore-src -r -y
colcon build --symlink-install
source install/setup.bash

# Launch V0.1 single-plant (no hardware)
ros2 launch hydroponics_bringup simulation.launch.py

# Launch V0.1 single-plant (with hardware)
ros2 launch hydroponics_bringup v01_single_plant.launch.py plant_type:=basil

# Dashboard at http://localhost:8080
```

### Run Tests (no ROS required)
```bash
cd hydroponics_ws/src/hydroponics_tests
python -m pytest test/ -v
```

### Frontend Dev Server
```bash
cd hydroponics_ws/src/hydroponics_dashboard/frontend
npm install
npx vite   # serves on :3000, proxies /api to :8080
```

---

## Documentation

- [Architecture](docs/architecture.md) — Node inventory, topic graph, data flow
- [Wiring Diagram](docs/wiring_diagram.md) — ESP32 pin assignments, schematic
- [Calibration Guide](docs/calibration_guide.md) — Servo, pH, EC, pump flow rate procedures
- [Scaling Guide](docs/scaling_guide.md) — Multi-plant, multi-bin, commercial

---

## License

MIT
