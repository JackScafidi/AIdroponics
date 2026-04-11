# AIdroponics V0.1 Refactor — Progress Tracker

Resume here if generation is interrupted. Check task status and pick up from the first incomplete item.

## Status Legend
- [x] Complete
- [~] In progress / partially done
- [ ] Not started

---

## Phase 1 — Setup
- [x] Read PROJECT_UPDATE.txt
- [x] Add PROJECT_UPDATE.txt to .gitignore
- [x] Create this progress file
- [x] Explore existing codebase structure

## Phase 2 — Archive Out-of-Scope Code
- [x] Create `src/future/` directory structure
- [x] Move `hydroponics_transport/` → `src/future/hydroponics_transport/`
- [x] Move `hydroponics_bt/` → `src/future/hydroponics_bt/`
- [x] Move `hydroponics_harvest/` → `src/future/hydroponics_harvest/`
- [x] Move `hydroponics_work_station/` → `src/future/hydroponics_work_station/`
- [x] Write `src/future/README.md`

## Phase 3 — Custom Message Types
Add to `hydroponics_msgs/`:
- [x] `msg/ProbeReading.msg`
- [x] `msg/NDVIReading.msg`
- [x] `msg/PlantMeasurement.msg`
- [x] `msg/WaterLevel.msg`
- [x] `msg/TopOffEvent.msg`
- [x] `msg/DosingEvent.msg`
- [x] `msg/PlantStatus.msg`
- [x] `msg/DiagnosticReport.msg`
- [x] `msg/NDVIAlert.msg`
- [x] Update `CMakeLists.txt` with new msg files
- [x] Add new service files:
  - [x] `srv/TriggerProbe.srv`
  - [x] `srv/TriggerAeration.srv`
  - [x] `srv/SetProbeInterval.srv`
  - [x] `srv/CaptureVision.srv`

## Phase 4 — Config Files
In `hydroponics_bringup/config/`:
- [x] `plant_library.yaml` (basil, mint, parsley, rosemary with NDVI thresholds)
- [x] `diagnostic_rules.yaml` (10 rules)
- [x] `v01_system.yaml` (all tunable parameters)

## Phase 5 — New Python Packages/Nodes
### hydroponics_probe (new package)
- [x] Package structure (setup.py, package.xml, __init__.py)
- [x] `probe_arm_node.py` — single-bin probe cycle, /probe/trigger, /probe/set_interval
- [x] `aeration_node.py` — single-bin aeration cycle, /aeration/trigger

### hydroponics_vision (replace existing)
- [x] `plant_vision_node.py` — dual CSI cameras, NDVI, AprilTag, HSV segmentation, temporal tracking

### hydroponics_dosing (new package, replaces nutrient_controller)
- [x] Package structure
- [x] `dosing_node.py` — pH-first dosing, A/B EC dosing, verify loop, safety scaffolding

### hydroponics_water (new package)
- [x] Package structure
- [x] `water_level_node.py` — ultrasonic sensor, auto top-off, consumption logging

### hydroponics_diagnostics (new package)
- [x] Package structure
- [x] `plant_health_analyzer_node.py` — YAML rule engine, DiagnosticReport publisher

### hydroponics_led (new package)
- [x] Package structure
- [x] `led_status_node.py` — GPIO LED driver

## Phase 6 — Launch File
- [x] `hydroponics_bringup/launch/v01_single_plant.launch.py`

## Phase 7 — Tests
### Unit Tests
- [x] `test_ndvi_computation.py`
- [x] `test_dosing_math.py`
- [x] `test_rule_engine.py` (10 scenarios)
- [x] `test_dosing_safety.py`
- [x] `test_water_level_conversion.py`
- [x] `test_temporal_tracking.py`

### Integration Tests
- [x] `test_topoff_dose_loop.py`
- [x] `test_ndvi_early_warning.py`
- [x] `test_vision_diagnostic.py`

## Phase 8 — Documentation & Git
- [x] Update project README to reflect V0.1 architecture
- [x] Update CLAUDE.md
- [ ] `git add -A && git commit -m "refactor: V0.1 — single-plant analysis platform with NDVI + RGB vision, A/B auto-dosing, and water management"`
- [ ] `git push`

---

## Key Architecture Decisions
- **Archive list**: hydroponics_transport, hydroponics_bt, hydroponics_harvest, hydroponics_work_station
- **Keep as-is**: hydroponics_micro_ros_bridge, hydroponics_lighting, hydroponics_data, hydroponics_mqtt, hydroponics_dashboard, hydroponics_mocks
- **Replace**: hydroponics_vision (new dual-cam NDVI node), hydroponics_nutrients → hydroponics_dosing
- **New packages**: hydroponics_probe, hydroponics_dosing, hydroponics_water, hydroponics_diagnostics, hydroponics_led
- **New msgs**: ProbeReading, NDVIReading, PlantMeasurement, WaterLevel, TopOffEvent, DosingEvent, PlantStatus, DiagnosticReport, NDVIAlert

## Notes
- Work station controller (C++) is harvest-specific (Z-axis + cutter/gripper) → archived
- Probe arm in V0.1 is a new Python node commanding servo via ESP32 GPIO
- Aeration cycle is a new Python node  
- Existing nutrient_controller uses PID — replaced by explicit chemistry-based dosing_node
- Existing vision_node uses YOLO multi-plant ROI — fully replaced by NDVI dual-camera pipeline
