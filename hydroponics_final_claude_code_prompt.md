# Autonomous Hydroponics Farm — Complete System Specification

## Project Overview

Build the complete ROS2 codebase for a station-based autonomous hydroponics farming system. The architecture mirrors commercial vertical farming facilities (Iron Ox, Bowery, Plenty): plants grow in removable trays that transport along a linear rail to specialized stations for inspection, harvesting, and replanting. This is a single-module prototype designed to prove every subsystem, built on a ~$400 budget using a Raspberry Pi 5, ESP32 MCU, stepper-driven transport, and free 3D printing.

The prototype manages a 4-position DWC grow channel with automated tray transport, fixed-camera YOLOv8 machine vision inspection, cut-and-regrow harvesting, channel-level PID nutrient management, and a full data pipeline tracking per-plant growth curves and yield economics.

All code must be production-grade, well-documented, type-hinted (Python), and ready to deploy on real hardware. The system should launch with zero manual configuration for a parsley crop using sensible defaults.

---

## Physical Layout

```
[Seedling Rack]  [Work Station]  [========= DWC Grow Channel =========]  [Inspection Station]
                  (2-DOF cutter   (4 plant positions in removable tray,   (2 fixed cameras +
                   + gripper on    tray floats on nutrient solution,       dedicated LEDs,
                   rotating        air stones, grow LED panel above)       hard stop position)
                   turret)

|<---------------------------- ~4 ft linear rail ------------------------------>|
```

Total footprint: ~4ft × 1ft × 2ft tall on a workbench.

### Core Workflow (Station-Based Processing)
Plants do NOT move during growth. The tray only moves for inspection or harvest:
1. Tray sits in grow channel (95% of time) — nutrients, aeration, lighting are continuous
2. On schedule (default 48 hours), tray transports RIGHT to inspection station
3. Fixed cameras image all 4 plants under controlled lighting
4. Vision pipeline analyzes: health, deficiency, growth measurements, maturity
5. If harvest needed: tray transports LEFT to work station
6. Work station performs cut-and-regrow harvest or end-of-life plant replacement
7. Tray returns to grow channel. Data logged. Cycle repeats.

---

## Hardware Specification

### Compute
- **Raspberry Pi 5 (8GB)**: Ubuntu 24.04 + ROS2 Humble. Runs all ROS2 nodes, YOLO inference, dashboard, MQTT
- **YOLOv8-nano on CPU**: Ultralytics Python package. ~200–400ms per image at 640px. No accelerator HAT needed — inspection takes one photo every 48 hours
- **ESP32 DevKit V1**: micro-ROS client over USB serial. Handles all real-time I/O: steppers, servos, ADC, sensors, pumps, lighting

### Frame
- **1×2 pine/poplar lumber**: ~$9 for 3× 8ft boards. Cut to length for base, verticals, and top rails
- **3D printed joints**: Corner brackets, motor mounts, rod holders, clamps. Bolt or screw to wood. No aluminum extrusions

### Linear Rail Transport
- **Structure**: Two 8mm smooth rods (1200mm) in 3D printed rod holders bolted to lumber frame
- **Bearings**: 4× LM8UU linear bearings pressed into 3D printed carriage plate
- **Drive**: NEMA 17 stepper + TMC2209 driver + GT2 belt (6mm) + 20-tooth pulleys
- **Carriage**: 3D printed plate on LM8UU bearings, carries grow tray with 3D printed alignment pins for repeatable registration
- **Positions** (in YAML config as mm from home): `WORK_POSITION`, `GROW_POSITION`, `INSPECT_POSITION`, `WORK_PLANT_0` through `WORK_PLANT_3` (indexed by 5" plant spacing)
- **Homing**: Limit switch at one end + step counting for position tracking. Must home on every power-up
- **Speed**: Conservative ~50mm/s max with soft trapezoidal acceleration (200ms+ ramp) to prevent nutrient sloshing
- **TMC2209 StallGuard**: Optional stall detection provides basic feedback without encoders

### Inspection Station
- **2× USB cameras** (1080p, manual focus locked): Camera 1 overhead, Camera 2 at ~30° side angle. Connected directly to Pi USB (no hub needed)
- **LED strip** (5000K daylight, 12V): Dedicated inspection illumination, on/off via ESP32 GPIO + MOSFET. Turns on only during image capture
- **Mounting**: 3D printed rigid bracket bolted to frame lumber. Rigidity is critical — any flex degrades imaging consistency
- **Hard stop**: 3D printed bumper + microswitch at rail end. Tray always stops at exactly the same position
- **Capture sequence**: Tray at hard stop → LEDs on → wait 200ms → both cameras capture sequentially → LEDs off → publish images

### Work Station (Harvest + Replant)
- **Z axis**: NEMA 17 stepper + TMC2209 + 8mm lead screw (250mm, 2mm pitch) + anti-backlash nut. Two 8mm guide rods with LM8UU bearings. ~200mm vertical travel. 3D printed carriage
- **Turret rotation**: MG996R servo rotates 3D printed turret body 180° between two tool positions
- **Tool 1 — Cutter**: SG90 servo actuates a blade mechanism (3D printed housing). Performs horizontal cut at configurable height (~50mm above net pot rim)
- **Tool 2 — Gripper**: SG90 servo drives 2-finger parallel jaw (3D printed body + jaws + silicone pads). 0–25mm opening. Grips 2" net pots for plant removal and replanting
- **Work position indexing**: Rail moves tray in 5" increments to align each plant under the work station sequentially
- **Collection tray**: 3D printed, sits on HX711 + 1kg beam load cell below the cutter to weigh each harvest
- **Seedling rack**: 3D printed 5–8 slot vertical magazine with spring feed. Holds pre-planted net pots (rockwool + seedling). Manually restocked by operator
- **Waste bin**: Container for spent plants removed at end-of-life

### DWC Grow Channel
- **Container**: Black plastic storage tote (~24" × 8" inner), ~$5. Light-proof (black or spray-painted)
- **Tray/raft**: 3D printed rigid panel holding 4× 2" net pots at fixed 5" spacing. Floats on nutrient solution surface
- **Aeration**: 4" bar air stone along bottom, always-on air pump (2–4 LPM), airline tubing + check valve
- **Sensors in reservoir**: Gravity analog pH probe, Gravity analog EC probe, DS18B20 waterproof temp probe, vertical float switch (water level)
- **Tray handoff**: Channel has open top. Carriage holds tray above solution at work/inspect positions. Tray settles into solution at grow position (passive — ramped channel entry or carriage drops below channel lip)

### Nutrient Management
- **4 peristaltic pumps** (12V dosing type): pH up, pH down, Nutrient A, Nutrient B. Driven via MOSFET modules from ESP32 GPIO
- **PID control**: Two independent loops (pH and EC) at 1Hz
  - Targets vary by growth stage (from plant profile YAML)
  - A/B dosing ratio: default 1:1, adjusted by growth stage and deficiency response
  - Dead band: ±0.1 pH, ±0.1 mS/cm EC — don't actuate within dead band
  - After any dose, wait 60 seconds mixing time before next reading
  - Anti-windup (integral clamp), derivative-on-measurement
  - PID output → pump run duration in milliseconds per cycle
  - Minimum dose: 0.1 mL (based on pump flow rate calibration)
- **Growth stage transitions**: Automatic based on days since planting per plant profile
- **Deficiency response**: Vision detects channel-wide trend (>50% plants affected) → adjust A/B ratio per plant profile lookup
- **Disease response**: Vision detects disease → pause ALL operations → alert user for manual intervention
- **Temperature monitoring**: DS18B20. Alert if out of range (no active cooling in prototype)
- **Water change alerting**: Track reservoir age, alert when due (default 14 days). After manual drain/refill, system auto-re-doses to target

### Grow Lighting
- **Panel**: PWM-dimmable full-spectrum LED (~25W), controlled via MOSFET from ESP32 PWM
- **Schedule**: Per plant profile per growth stage: hours on/off, ramp-up/down duration, intensity percentage
- **Inspection light**: Separate LED strip, on/off only, controlled independently

---

## Software Architecture

### Overview
- **ROS2 Humble** on Raspberry Pi 5 (Ubuntu 24.04)
- **Python** for high-level logic: vision, nutrients, harvest, data, lighting, dashboard, MQTT
- **C++** for real-time: transport controller, work station controller, behavior tree manager
- **ESP32 Arduino/PlatformIO firmware** with micro-ROS for all hardware I/O
- **BehaviorTree.CPP** for master orchestration
- **FastAPI + React** for web dashboard
- **SQLite** for local growth/yield database
- **HiveMQ Cloud** (free tier MQTT) for cloud logging + Home Assistant phone alerts
- **colcon** build system, MIT license

### Node List (11 nodes)

#### 1. `transport_controller` (C++)
- Sends step/direction commands to ESP32 via micro-ROS for the rail stepper
- Exposes ROS2 actions: `TransportTo(position_name)` where position_name is `WORK`, `GROW`, `INSPECT`, or `WORK_PLANT_0..3`
- Handles homing sequence: drive to limit switch → zero step counter
- Trapezoidal acceleration profiles: configurable max speed (~50mm/s), acceleration, deceleration
- Publishes: `TransportStatus` (current_position, target_position, is_moving, position_mm)
- Rail positions loaded from YAML config (positions in mm from home, steps/mm calibration)
- Software travel limits to prevent overrun

#### 2. `work_station_controller` (C++)
- Sends commands to ESP32 for Z-axis stepper and work station servos via micro-ROS
- Exposes ROS2 actions:
  - `MoveZ(height_mm)` — move Z to absolute height
  - `SelectTool(tool_id)` — rotate turret to `CUTTER` or `GRIPPER`
  - `ExecuteCut()` — actuate cutter blade at current Z height
  - `GripperAction(action)` — `OPEN`, `CLOSE`, or `GRIP_WITH_FORCE`
  - `HomeZ()` — home Z axis via limit switch
- Exposes ROS2 services:
  - `GetWorkStationStatus()` — current Z position, selected tool, gripper state
- Z cut height configurable per plant profile (`cut_height_mm`, typically 50mm above net pot rim)
- Gripper: simple open/close with timeout

#### 3. `vision_node` (Python)
- Manages 2 inspection cameras + inspection light
- **Image capture**: Tray at hard stop → set inspection LED on via ESP32 → wait 200ms stabilize → capture Camera 1 (overhead) → capture Camera 2 (side) → LED off → publish
- **YOLOv8-nano inference on Pi 5 CPU** using `ultralytics` Python package (standard PyTorch `.pt` weights)
  - Instance segmentation: detect individual plants, segment canopy area per plant
  - Classification: `healthy`, `nitrogen_deficiency`, `phosphorus_deficiency`, `potassium_deficiency`, `iron_deficiency`, `disease_fungal`, `disease_bacterial`
  - Maturity estimation: `immature`, `vegetative`, `mature`, `overmature`
  - Inference time: ~200–400ms per image at 640px. Two images per inspection = under 1 second
- **Per-plant measurements** from overhead camera (calibrated to real units at known camera height):
  - Canopy area (pixels → cm² via calibration factor)
  - Plant height (from side camera, calibrated)
  - Color histogram (HSV distribution for health tracking)
  - Leaf count estimate (from instance segmentation)
- **Consistent imaging**: Fixed cameras + fixed lighting = directly comparable across scans without normalization
- **Plant position registration**: Hard stop ensures tray at same position every time. Per-plant ROIs (pixel coordinates) configured in YAML
- Publishes: `InspectionResult`, `ChannelHealthSummary`, `RawInspectionImages`
- Config: camera intrinsics, ROI coordinates per plant position, detection confidence thresholds

#### 4. `nutrient_controller` (Python)
- Reads pH, EC, temperature from ESP32 ADC / OneWire via micro-ROS topics
- Two independent PID loops (pH and EC) at 1Hz
  - PID class: proportional + integral (clamped anti-windup) + derivative-on-measurement
  - Output → pump run duration (ms) per control cycle
  - Dead band: don't actuate within ±0.1 pH or ±0.1 mS/cm
  - After dosing: 60s mixing wait before next actuation
- **Growth stage management**: Tracks days since planting. Auto-transitions seedling → vegetative → mature per plant profile day ranges. Adjusts pH/EC targets and A/B ratio on transition
- **Deficiency response**: Subscribes to `ChannelHealthSummary`. If deficiency prevalence > 50%, adjusts A/B ratio per plant profile deficiency_response table
- Water level sensor: if low → pause dosing → publish alert
- Temperature: if out of range → publish alert
- Publishes: `NutrientStatus` (pH, EC, temp, targets, PID outputs, pump states, growth_stage, A/B ratio, days_since_planting)
- Services: `ForceDose(pump_id, amount_ml)`, `SetGrowthStage(stage)`, `ResetCropCycle()`

#### 5. `light_controller` (Python)
- Controls two lighting systems via ESP32:
  - **Grow panel**: PWM-dimmable, follows schedule from plant profile (varies by growth stage). Ramp-up/down over configurable minutes
  - **Inspection LEDs**: On/off, triggered by vision_node during inspection capture
- Services: `SetGrowLightIntensity(percent)`, `SetGrowLightSchedule(schedule)`, `SetInspectionLight(on_off)`
- Publishes: `LightStatus` (grow_intensity, schedule_state, inspection_light_state, next_transition_time)

#### 6. `harvest_manager` (Python)
- Implements harvest decision logic and orchestrates the harvest sequence
- **Harvest types**:
  - **Cut-and-regrow**: Vision detects plant mature → cutter descends to cut_height → blade actuates → foliage falls to collection tray → load cell weighs. Plant regrows from crown
  - **End-of-life replacement**: After N cut cycles (default 3, from plant profile) OR plant health degrades → gripper removes entire plant (net pot) → deposits in waste → picks new seedling from rack → places in tray
- **Per-plant state tracking**: Each of 4 tray positions has state: `EMPTY`, `SEEDLING`, `VEGETATIVE`, `MATURE`, `HARVESTED` (regrowing), `SPENT`
- **Channel-level scheduling**: After each inspection, evaluates all 4 plants and builds a complete harvest plan for one work session
- **Maturity detection**: Plant is ready for cut when vision maturity == "mature" AND canopy_area >= threshold (from profile) AND days since last cut >= minimum (from profile)
- Publishes: `HarvestPlan` (ordered list of per-position actions), `PlantPositionStatus` (state array for all 4 positions), `CropCycleEvent` (harvests, replants, stage transitions)
- Subscribes to: `InspectionResult`, `HarvestResult`

#### 7. `data_pipeline` (Python)
- **This node is critical for portfolio value** — transforms the robot into a data-driven agricultural system
- **SQLite database** (local, no external server):
  - Table `plants`: plant_id (UUID), position_index, plant_profile, planted_date, current_stage, status
  - Table `inspections`: inspection_id, plant_id, timestamp, canopy_area_cm2, height_cm, leaf_count, health_class, deficiency_type, maturity_state, raw_image_paths (JSON array)
  - Table `harvests`: harvest_id, plant_id, timestamp, harvest_type (cut/removal), weight_grams, cut_cycle_number
  - Table `nutrient_readings`: timestamp, ph, ec, temperature_c, growth_stage, a_b_ratio
  - Table `system_events`: timestamp, event_type, severity, details
- **Growth curve computation**: For each plant, query inspection history and compute: canopy area over time, height over time, growth rate (cm²/day), time to maturity
- **Yield analytics**:
  - Grams per harvest per plant position
  - Cumulative yield per crop cycle
  - Yield per watt-hour of light energy (integrate light intensity × hours)
  - Yield per liter of nutrient consumed (integrate pump runtimes × flow rates)
  - Cost per gram (energy + nutrient + water costs, rates configurable in `economics.yaml`)
- **Data export**: REST API endpoints for CSV and JSON export
- Publishes: `GrowthCurveUpdate` (per-plant metrics, emitted after each inspection), `YieldMetrics`
- Subscribes to: `InspectionResult`, `HarvestResult`, `NutrientStatus`, `CropCycleEvent`, `LightStatus`
- Database schema migrations versioned in `migrations/` directory

#### 8. `behavior_tree_manager` (C++)
- Master orchestrator using **BehaviorTree.CPP** library
- Tree loaded from XML file (`trees/main_tree.xml`) — modifiable without recompilation
- Behavior tree structure:

```
Root (ReactiveSequence)
├── SafetyMonitor (condition, always checked first)
│   ├── CheckWaterLevel
│   ├── CheckTemperatureRange
│   └── CheckDiseaseAlert → PauseAndNotify
│
├── MainSequence (Sequence)
│   ├── StartupSequence
│   │   ├── HomeRail (drive to limit switch, zero position)
│   │   ├── HomeWorkStationZ
│   │   ├── InitializeSensors (wait for pH/EC/temp readings)
│   │   └── TransportTo(GROW)
│   │
│   ├── ContinuousMonitoring (Parallel — always running alongside main loop)
│   │   ├── NutrientPIDLoop (managed by nutrient_controller, BT just monitors health)
│   │   └── LightScheduleLoop (managed by light_controller, BT just monitors)
│   │
│   ├── ScheduledInspectionCycle (Sequence)
│   │   ├── IsInspectionDue (condition, checks configurable timer — default 48hrs)
│   │   ├── TransportTo(INSPECT)
│   │   ├── WaitForTransportComplete
│   │   ├── TriggerInspection (calls vision_node capture + inference)
│   │   ├── WaitForInspectionResult
│   │   ├── AnalyzeResults (Fallback — first matching branch executes)
│   │   │   ├── DiseaseDetected (Sequence)
│   │   │   │   ├── TransportTo(GROW)
│   │   │   │   └── PauseAndAlert (MQTT + dashboard critical alert)
│   │   │   ├── HarvestNeeded (Sequence)
│   │   │   │   ├── BuildHarvestPlan (harvest_manager computes plan)
│   │   │   │   ├── TransportTo(WORK)
│   │   │   │   ├── WaitForTransportComplete
│   │   │   │   ├── ForEachPlantInPlan (Sequence, iterates harvest actions)
│   │   │   │   │   ├── TransportToPlantIndex(N) (rail indexes tray by 5" spacing)
│   │   │   │   │   ├── SelectTool (CUTTER or GRIPPER based on action type)
│   │   │   │   │   ├── ExecuteHarvestAction (Fallback with retry)
│   │   │   │   │   │   ├── CutHarvest (Sequence)
│   │   │   │   │   │   │   ├── MoveZ(cut_height)
│   │   │   │   │   │   │   ├── ExecuteCut
│   │   │   │   │   │   │   ├── WaitForCutComplete
│   │   │   │   │   │   │   ├── ReadHarvestWeight (from load cell)
│   │   │   │   │   │   │   └── MoveZ(home)
│   │   │   │   │   │   ├── PlantReplacement (Sequence)
│   │   │   │   │   │   │   ├── SelectTool(GRIPPER)
│   │   │   │   │   │   │   ├── MoveZ(grip_height)
│   │   │   │   │   │   │   ├── GripNetPot
│   │   │   │   │   │   │   ├── MoveZ(home)
│   │   │   │   │   │   │   ├── DepositInWasteBin
│   │   │   │   │   │   │   ├── PickSeedlingFromRack
│   │   │   │   │   │   │   ├── MoveZ(place_height)
│   │   │   │   │   │   │   ├── PlaceInTray
│   │   │   │   │   │   │   └── MoveZ(home)
│   │   │   │   │   │   └── RetryHandler (max 3 retries → skip plant + alert)
│   │   │   │   │   └── LogHarvestEvent (to data_pipeline)
│   │   │   │   └── TransportTo(GROW)
│   │   │   ├── DeficiencyDetected → AdjustNutrientRatio (non-blocking)
│   │   │   └── AllHealthy → TransportTo(GROW)
│   │   └── ResetInspectionTimer
```

- Publishes: `BehaviorTreeStatus` (current active node path, node states, overall system state)
- Custom BT nodes organized into source files: `transport_nodes.cpp`, `work_station_nodes.cpp`, `vision_nodes.cpp`, `harvest_nodes.cpp`, `nutrient_nodes.cpp`, `safety_nodes.cpp`

#### 9. `web_dashboard` (Python FastAPI + React SPA)

**Backend (FastAPI):**
- Runs as a ROS2 node (rclpy spinning in background thread)
- REST API endpoints:
  - `GET /api/status` — system state, transport position, active BT node
  - `GET /api/nutrients` — current pH, EC, temp, targets, PID state
  - `GET /api/plants` — per-position plant status, growth stage, health
  - `GET /api/plants/{id}/growth-curve` — historical growth data
  - `GET /api/harvests` — harvest log with weights
  - `GET /api/analytics` — yield metrics: cost-per-gram, efficiency stats
  - `GET /api/inspections/latest` — most recent inspection images
  - `POST /api/controls/transport/{position}` — manual tray move
  - `POST /api/controls/inspect` — trigger manual inspection
  - `POST /api/controls/harvest` — trigger manual harvest cycle
  - `POST /api/controls/dose` — manual nutrient dose (pump_id, amount_ml)
  - `POST /api/controls/light/{intensity}` — manual light override
  - `POST /api/controls/estop` — emergency stop all motion
  - `GET /api/export/data?format=csv` — export growth + nutrient data
  - `GET /api/profiles` — list plant profiles
  - `PUT /api/profiles/{id}` — update plant profile parameters
- WebSocket: streams sensor data (1Hz), camera frames during inspection, BT status (1Hz)

**Frontend (React SPA, served as static files at `http://<pi-ip>:8080`):**
1. **ChannelOverview** — 4 plant position cards: thumbnail, health badge, stage, days planted, canopy sparkline
2. **SensorGauges** — Circular gauges for pH, EC, water temp, water level. Color-coded green/yellow/red vs targets
3. **InspectionViewer** — Latest images from both cameras. Click plant to see image history timeline. Side-by-side comparison
4. **GrowthCurves** — Per-plant Recharts timeseries: canopy area, height, leaf count over time. Overlay nutrient conditions. Mark harvest events
5. **YieldAnalytics** — Cumulative yield (grams), yield/watt-hour, yield/liter nutrient, cost/gram. Bar charts across crop cycles
6. **NutrientHistory** — Time-series: pH, EC, temperature. Show PID setpoint changes at stage transitions. Highlight dosing events
7. **BehaviorTreeStatus** — Tree diagram: node states (idle/running/success/failure), active execution path highlighted
8. **SystemControls** — Transport buttons (WORK/GROW/INSPECT), trigger inspection, trigger harvest, force dose, light slider, E-STOP
9. **AlertPanel** — Active + historical alerts: severity, timestamp, recommended action
10. **PlantProfileEditor** — Select profile, view/edit parameters
- Responsive design — functional on phone/tablet

#### 10. `mqtt_bridge` (Python)
- Bridges ROS2 topics to HiveMQ Cloud (free tier) MQTT broker
- Publishes at 0.1Hz (every 10 seconds) for sensors, on-change for events:
  - `hydroponics/sensors/ph`, `hydroponics/sensors/ec`, `hydroponics/sensors/temperature`, `hydroponics/sensors/water_level`
  - `hydroponics/system/state`, `hydroponics/system/transport_position`
  - `hydroponics/plants/{position}/status`, `hydroponics/plants/{position}/canopy_area`
  - `hydroponics/harvests/latest` (event + weight)
  - `hydroponics/alerts/#` (disease, water_low, retry_failed, water_change_due, temp alerts)
- Home Assistant MQTT integration: alert topics formatted for HA automation → phone push notifications
- Broker URL + credentials from environment variables

#### 11. `micro_ros_bridge` (C++)
- Manages serial USB communication with ESP32 via micro-ROS agent
- ESP32 publishes: `ph_raw`, `ec_raw`, `temperature`, `water_level`, `limit_switch_states`, `z_position`, `harvest_weight`, `rail_position` (step count)
- ESP32 subscribes to: `rail_stepper_cmd`, `z_stepper_cmd`, `servo_cmd` (turret/cutter/gripper), `pump_cmd` (4 pumps), `grow_light_cmd` (PWM), `inspect_light_cmd` (on/off)
- Handles connection, reconnection, watchdog monitoring

---

## ESP32 Firmware (micro-ROS, Arduino/PlatformIO, C++)

### Stepper Control (2 axes)
- **Rail axis**: STEP/DIR/EN → TMC2209 #1 → NEMA 17. Trapezoidal acceleration. Configurable steps/mm, max speed, acceleration
- **Z axis**: STEP/DIR/EN → TMC2209 #2 → NEMA 17. Same acceleration profile
- Both axes: homing via limit switch (configurable direction, speed, backoff distance)
- TMC2209 UART (optional): single-wire UART per driver for StallGuard stall detection on rail axis

### Servo Control (3 channels via ESP32 LEDC)
- Turret rotation (MG996R), cutter blade (SG90), gripper (SG90)
- Map commanded position (degrees or microseconds) to LEDC duty cycle

### Pump Control
- 4 GPIO → MOSFET modules → 12V peristaltic pumps
- Timed dosing: run pump for N milliseconds with 1ms precision
- Flyback protection: MOSFET modules include flyback diodes

### Analog Sensors (ESP32 ADC1 — ADC2 conflicts with WiFi)
- pH sensor + EC sensor on ADC1 pins (12-bit)
- **Noise mitigation** (ESP32 ADC is noisier than dedicated ADC chips):
  - Oversample: 64 raw readings per measurement
  - Discard top/bottom 10% (trimmed mean)
  - Apply ESP32 ADC nonlinearity correction (`esp_adc_cal` eFuse calibration or lookup table)
  - Median filter over last 5 averaged readings before publishing
  - 1Hz publish rate after filtering
  - **Quiet period**: only sample pH/EC when stepper motors are idle (EMI from step pulses causes ADC noise). Firmware sets a `motors_active` flag

### Digital Sensors
- DS18B20 temperature: OneWire protocol, DallasTemperature library. 4.7kΩ pullup on data line
- HX711 load cell amplifier: CLK + DAT on two GPIO. Tare on startup, calibrated to grams
- Limit switches: rail home, rail end, Z home (3 total). NC wiring with pullup resistors
- Float switch: water level. NC wiring with pullup

### Lighting Control
- Grow light: LEDC PWM channel → MOSFET → 24V LED panel
- Inspection LED: GPIO → MOSFET → 12V LED strip (on/off)

### Safety
- Watchdog: if no micro-ROS heartbeat from Pi for 5 seconds → stop all steppers and pumps
- Limit switch interrupts: immediate stop on trigger

### Communication
- micro-ROS transport: serial over USB to Pi (primary) or WiFi UDP (backup, configurable)

---

## Plant Profiles

YAML files in `config/plant_profiles/`. Each defines the complete lifecycle for a crop type.

```yaml
# config/plant_profiles/parsley.yaml
name: "Italian Flat-Leaf Parsley"
plant_id: "parsley"

growth_stages:
  seedling:
    day_range: [0, 14]
    ph_target: 6.0
    ph_tolerance: 0.3
    ec_target: 0.8
    ec_tolerance: 0.2
    a_b_ratio: 1.0
    light_hours: 16
    light_intensity_percent: 60
  vegetative:
    day_range: [15, 40]
    ph_target: 6.0
    ph_tolerance: 0.3
    ec_target: 1.2
    ec_tolerance: 0.3
    a_b_ratio: 1.0
    light_hours: 14
    light_intensity_percent: 80
  mature:
    day_range: [41, 999]
    ph_target: 6.0
    ph_tolerance: 0.3
    ec_target: 1.4
    ec_tolerance: 0.3
    a_b_ratio: 1.0
    light_hours: 14
    light_intensity_percent: 85

light_schedule:
  on_time: "06:00"
  ramp_up_minutes: 30
  ramp_down_minutes: 30

deficiency_response:
  nitrogen:    { a_b_ratio: 1.3, ec_boost: 0.2 }
  phosphorus:  { a_b_ratio: 0.7, ec_boost: 0.1 }
  potassium:   { a_b_ratio: 0.8, ec_boost: 0.15 }
  iron:        { a_b_ratio: 1.0, ec_boost: 0.1 }

harvest:
  maturity_canopy_area_cm2: 80
  min_days_between_cuts: 14
  cut_height_mm: 50
  max_cut_cycles: 3
  regrow_days_expected: 14

temperature:
  target_c: 20
  max_c: 24
  min_c: 15

water_change_interval_days: 14
expected_yield_grams_per_cut: 15
```

Create additional profiles for: `basil.yaml`, `cilantro.yaml`, `mint.yaml` with appropriate hydroponic parameters (research typical values for each herb).

---

## ROS2 Custom Interface Definitions

### Messages (`hydroponics_msgs/msg/`)

```
# PlantPositionState.msg
uint8 position_index              # 0-3
string plant_id                   # unique plant instance ID (UUID)
string plant_profile              # "parsley", "basil", etc.
string status                     # EMPTY, SEEDLING, VEGETATIVE, MATURE, HARVESTED, SPENT
string health_state               # healthy, nitrogen_deficiency, phosphorus_deficiency, potassium_deficiency, iron_deficiency, disease_fungal, disease_bacterial
float64 canopy_area_cm2
float64 height_cm
uint32 leaf_count
uint32 days_since_planted
uint32 cut_cycle_number
builtin_interfaces/Time last_inspection
builtin_interfaces/Time last_harvest

# InspectionResult.msg
std_msgs/Header header
PlantPositionState[] plants       # array of 4 plant states
uint32 scan_number
bool disease_detected
string disease_type
string[] deficiency_trends        # channel-level: ["nitrogen"] if >50% show it

# ChannelHealthSummary.msg
std_msgs/Header header
float64 avg_canopy_area_cm2
uint8 healthy_count
uint8 deficient_count
uint8 diseased_count
string primary_deficiency         # most common, or "none"
float64 deficiency_prevalence     # fraction affected

# HarvestAction.msg
uint8 position_index
string action_type                # "cut" or "replace"
float64 cut_height_mm

# HarvestPlan.msg
std_msgs/Header header
HarvestAction[] actions
uint8 total_cuts
uint8 total_replacements

# HarvestResult.msg
std_msgs/Header header
uint8 position_index
string action_type
float64 weight_grams              # from load cell (0 for replacements)
bool success

# NutrientStatus.msg
std_msgs/Header header
float64 ph_current
float64 ec_current
float64 temperature_c
float64 ph_target
float64 ec_target
float64 ph_pid_output
float64 ec_pid_output
float64 a_b_ratio
string growth_stage
uint32 days_since_planting
bool[4] pump_active               # [ph_up, ph_down, nutrient_a, nutrient_b]

# TransportStatus.msg
std_msgs/Header header
string current_position           # WORK, GROW, INSPECT, TRANSIT, WORK_PLANT_0..3
string target_position
bool is_moving
float64 position_mm
float64 velocity_mm_s

# GrowthDataPoint.msg
std_msgs/Header header
string plant_id
uint8 position_index
float64 canopy_area_cm2
float64 height_cm
uint32 leaf_count
float64 growth_rate_cm2_per_day
float64 ph_at_reading
float64 ec_at_reading
float64 temp_at_reading

# SystemAlert.msg
std_msgs/Header header
string alert_type                 # disease, water_low, temp_high, temp_low, retry_failed, water_change_due, seedling_rack_low, cycle_complete
string severity                   # info, warning, critical
string message
string recommended_action

# YieldMetrics.msg
std_msgs/Header header
float64 total_yield_grams
float64 yield_per_watt_hour
float64 yield_per_liter_nutrient
float64 cost_per_gram
uint32 total_harvests
uint32 total_crop_cycles

# LightStatus.msg
std_msgs/Header header
float64 grow_intensity_percent
string schedule_state             # on, off, ramping_up, ramping_down
bool inspection_light_on
string next_transition_time

# BehaviorTreeStatus.msg
std_msgs/Header header
string system_state               # STARTUP, RUNNING, PAUSED, ERROR
string active_node_path           # e.g. "MainSequence/ScheduledInspection/TriggerInspection"
string[] running_nodes
string[] failed_nodes
```

### Services (`hydroponics_msgs/srv/`)

```
# TriggerInspection.srv
---
bool success
uint32 scan_number

# ForceDose.srv
string pump_id                    # ph_up, ph_down, nutrient_a, nutrient_b
float64 amount_ml
---
bool success

# SetGrowthStage.srv
string stage                      # seedling, vegetative, mature
---
bool success
string previous_stage

# ResetCropCycle.srv
uint8 position_index              # which position (255 = all)
string plant_profile
---
bool success

# GetYieldAnalytics.srv
---
float64 total_yield_grams
float64 avg_yield_per_cut
float64 yield_per_watt_hour
float64 yield_per_liter
float64 cost_per_gram
uint32 total_crop_cycles

# GetPlantHistory.srv
string plant_id
---
GrowthDataPoint[] growth_history
float64[] harvest_weights
uint32 total_inspections

# GetWorkStationStatus.srv
---
float64 z_position_mm
string selected_tool              # CUTTER, GRIPPER, NONE
string gripper_state              # OPEN, CLOSED, UNKNOWN

# SetGrowLightIntensity.srv
float64 intensity_percent
---
bool success

# SetInspectionLight.srv
bool on
---
bool success
```

### Actions (`hydroponics_msgs/action/`)

```
# TransportTo.action
# Goal
string target_position            # WORK, GROW, INSPECT, WORK_PLANT_0..3
---
# Result
bool success
string final_position
string message
---
# Feedback
float64 progress_percent
float64 current_position_mm

# MoveZ.action
# Goal
float64 target_height_mm
---
# Result
bool success
float64 final_height_mm
---
# Feedback
float64 current_height_mm

# ExecuteHarvest.action
# Goal
HarvestPlan plan
---
# Result
bool success
HarvestResult[] results
float64 total_weight_grams
---
# Feedback
uint8 current_action_index
uint8 total_actions
string current_action_description
```

---

## ROS2 Package Structure

```
hydroponics_ws/
├── src/
│   ├── hydroponics_msgs/                # Custom message/service/action definitions
│   │   ├── msg/                         # All .msg files listed above
│   │   ├── srv/                         # All .srv files listed above
│   │   ├── action/                      # All .action files listed above
│   │   ├── CMakeLists.txt
│   │   └── package.xml
│   │
│   ├── hydroponics_transport/           # C++ — transport_controller
│   │   ├── src/
│   │   │   └── transport_controller.cpp
│   │   ├── config/
│   │   │   └── transport_params.yaml    # steps/mm, positions, speeds, accel
│   │   ├── CMakeLists.txt
│   │   └── package.xml
│   │
│   ├── hydroponics_work_station/        # C++ — work_station_controller
│   │   ├── src/
│   │   │   └── work_station_controller.cpp
│   │   ├── config/
│   │   │   └── work_station_params.yaml # Z travel, cut heights, servo angles, turret positions
│   │   ├── CMakeLists.txt
│   │   └── package.xml
│   │
│   ├── hydroponics_vision/              # Python — vision_node
│   │   ├── hydroponics_vision/
│   │   │   ├── __init__.py
│   │   │   ├── vision_node.py           # Main: capture sequence, orchestrate inference, publish
│   │   │   ├── yolo_inference.py        # CPU Ultralytics wrapper: load model, predict, parse results
│   │   │   ├── plant_measurer.py        # Canopy area (px→cm²), height from side cam, color histogram
│   │   │   ├── deficiency_classifier.py # Map YOLO classes → deficiency types, aggregate channel health
│   │   │   └── camera_manager.py        # 2-camera sequential capture, device enumeration, settings lock
│   │   ├── models/                      # YOLOv8-nano weights (.pt files)
│   │   ├── config/
│   │   │   └── vision_params.yaml       # Camera device IDs, intrinsics, ROI coords, thresholds
│   │   ├── setup.py
│   │   └── package.xml
│   │
│   ├── hydroponics_nutrients/           # Python — nutrient_controller
│   │   ├── hydroponics_nutrients/
│   │   │   ├── __init__.py
│   │   │   ├── nutrient_controller.py   # Main: PID loops, stage management, deficiency response
│   │   │   └── pid.py                   # PID class: P+I(clamped)+D(on measurement), dead band, reset
│   │   ├── config/
│   │   │   └── pid_params.yaml          # Kp, Ki, Kd for pH and EC, dead bands, mixing time
│   │   ├── setup.py
│   │   └── package.xml
│   │
│   ├── hydroponics_lighting/            # Python — light_controller
│   │   ├── hydroponics_lighting/
│   │   │   ├── __init__.py
│   │   │   └── light_controller.py
│   │   ├── setup.py
│   │   └── package.xml
│   │
│   ├── hydroponics_harvest/             # Python — harvest_manager
│   │   ├── hydroponics_harvest/
│   │   │   ├── __init__.py
│   │   │   └── harvest_manager.py
│   │   ├── setup.py
│   │   └── package.xml
│   │
│   ├── hydroponics_data/                # Python — data_pipeline
│   │   ├── hydroponics_data/
│   │   │   ├── __init__.py
│   │   │   ├── data_pipeline.py         # Main: subscribe to topics, store, compute, publish
│   │   │   ├── database.py              # SQLite schema, connection, queries, migrations runner
│   │   │   ├── growth_analytics.py      # Growth curves, rates, time-to-maturity estimates
│   │   │   └── yield_economics.py       # Cost-per-gram, yield-per-watt, yield-per-liter
│   │   ├── config/
│   │   │   └── economics.yaml           # Energy cost $/kWh, nutrient cost $/L, water cost $/L
│   │   ├── migrations/
│   │   │   └── 001_initial_schema.sql
│   │   ├── setup.py
│   │   └── package.xml
│   │
│   ├── hydroponics_bt/                  # C++ — behavior_tree_manager
│   │   ├── src/
│   │   │   ├── bt_manager.cpp           # Load XML, tick tree, publish status
│   │   │   └── bt_nodes/
│   │   │       ├── transport_nodes.cpp  # TransportTo, WaitForTransport, TransportToPlantIndex
│   │   │       ├── work_station_nodes.cpp # MoveZ, SelectTool, ExecuteCut, GripperAction
│   │   │       ├── vision_nodes.cpp     # TriggerInspection, WaitForResult, AnalyzeResults
│   │   │       ├── harvest_nodes.cpp    # BuildPlan, ForEachPlant, LogHarvestEvent
│   │   │       ├── nutrient_nodes.cpp   # AdjustRatio, CheckDeficiency
│   │   │       └── safety_nodes.cpp     # CheckWaterLevel, CheckTemp, CheckDisease, PauseAndAlert
│   │   ├── trees/
│   │   │   └── main_tree.xml            # BehaviorTree.CPP XML definition (matches tree above)
│   │   ├── CMakeLists.txt
│   │   └── package.xml
│   │
│   ├── hydroponics_mqtt/                # Python — mqtt_bridge
│   │   ├── hydroponics_mqtt/
│   │   │   ├── __init__.py
│   │   │   └── mqtt_bridge.py
│   │   ├── config/
│   │   │   └── mqtt_config.yaml         # Broker URL, topic prefix, publish rates, HA format
│   │   ├── setup.py
│   │   └── package.xml
│   │
│   ├── hydroponics_dashboard/           # Python (FastAPI) + React frontend
│   │   ├── hydroponics_dashboard/
│   │   │   ├── __init__.py
│   │   │   ├── app.py                   # FastAPI app, static file serving, CORS
│   │   │   ├── ros_bridge.py            # rclpy subscribers → WebSocket forwarder
│   │   │   └── api_routes.py            # All REST endpoints + WebSocket handler
│   │   ├── frontend/
│   │   │   ├── src/
│   │   │   │   ├── App.jsx
│   │   │   │   ├── components/
│   │   │   │   │   ├── ChannelOverview.jsx
│   │   │   │   │   ├── SensorGauges.jsx
│   │   │   │   │   ├── InspectionViewer.jsx
│   │   │   │   │   ├── GrowthCurves.jsx       # Recharts timeseries
│   │   │   │   │   ├── YieldAnalytics.jsx
│   │   │   │   │   ├── NutrientHistory.jsx
│   │   │   │   │   ├── BehaviorTreeStatus.jsx
│   │   │   │   │   ├── SystemControls.jsx
│   │   │   │   │   ├── AlertPanel.jsx
│   │   │   │   │   └── PlantProfileEditor.jsx
│   │   │   │   └── index.js
│   │   │   ├── package.json
│   │   │   └── public/
│   │   ├── setup.py
│   │   └── package.xml
│   │
│   ├── hydroponics_bringup/             # Launch files + top-level config
│   │   ├── launch/
│   │   │   ├── full_system.launch.py
│   │   │   ├── transport_test.launch.py
│   │   │   ├── vision_test.launch.py
│   │   │   ├── work_station_test.launch.py
│   │   │   ├── nutrient_test.launch.py
│   │   │   └── simulation.launch.py     # All nodes with mock hardware
│   │   ├── config/
│   │   │   ├── plant_profiles/
│   │   │   │   ├── parsley.yaml
│   │   │   │   ├── basil.yaml
│   │   │   │   ├── cilantro.yaml
│   │   │   │   └── mint.yaml
│   │   │   └── system_config.yaml       # Global: inspection interval, retry count, etc.
│   │   ├── urdf/
│   │   │   └── hydroponics_module.urdf.xacro
│   │   ├── CMakeLists.txt
│   │   └── package.xml
│   │
│   └── esp32_firmware/                  # ESP32 micro-ROS firmware (PlatformIO/Arduino)
│       ├── src/
│       │   ├── main.cpp                 # Setup, loop, micro-ROS init
│       │   ├── stepper.cpp / stepper.h  # Dual axis stepper control (rail + Z), trapezoidal accel
│       │   ├── tmc2209.cpp / tmc2209.h  # TMC2209 UART config, StallGuard setup
│       │   ├── servo.cpp / servo.h      # 3-channel LEDC servo (turret, cutter, gripper)
│       │   ├── pumps.cpp / pumps.h      # 4 pump MOSFET control, timed dosing
│       │   ├── sensors.cpp / sensors.h  # ADC (pH, EC with oversampling), DS18B20, float, limits
│       │   ├── load_cell.cpp / load_cell.h # HX711 driver, tare, calibration
│       │   ├── lighting.cpp / lighting.h   # Grow PWM + inspect on/off
│       │   └── micro_ros_app.cpp        # All micro-ROS publishers/subscribers
│       ├── platformio.ini               # ESP32 DevKit V1 target, micro-ROS lib deps
│       └── README.md
│
├── training/                            # YOLOv8 training pipeline
│   ├── train_yolo.py                    # Fine-tune YOLOv8n-seg on plant datasets
│   ├── dataset_config.yaml              # Ultralytics dataset format config
│   ├── collect_training_data.py         # Capture + auto-save images from inspection station
│   └── README.md                        # Instructions: datasets (PlantVillage, PlantDoc), labeling (Roboflow/LabelStudio), training, evaluation
│
├── README.md                            # Project overview, BOM, architecture diagram, setup, calibration, run guide
├── docker/
│   └── Dockerfile                       # Ubuntu 24.04 + ROS2 Humble + Python deps for containerized build
└── docs/
    ├── architecture.md                  # Full system architecture with diagrams
    ├── wiring_diagram.md                # ESP32 GPIO pin assignments, power distribution, all connections
    ├── calibration_guide.md             # Step-by-step: homing, steps/mm, pH cal, EC cal, camera ROIs, pump flow rates
    └── scaling_guide.md                 # Tier 1→2→3 scaling path: multi-channel rack, shared stations, distributed ROS2
```

---

## URDF Robot Description

URDF/xacro for the prototype module (`hydroponics_module.urdf.xacro`):
- **world**: Fixed frame (world origin)
- **rail_base**: Fixed frame at the start of the linear rail
- **tray_carriage**: Prismatic joint along rail X axis (0 to ~1200mm)
- **grow_channel**: Fixed frame where DWC tote sits (center of rail)
- **inspection_station**: Fixed frame at inspection end (cameras + lights as child links)
- **work_station_base**: Fixed frame at work end
- **work_z_carriage**: Prismatic joint (0 to ~200mm vertical)
- **tool_turret**: Revolute joint (0° to 180° for tool selection)
- **cutter_tool**: Fixed link on turret
- **gripper_tool**: Fixed link on turret (opposite side, 180° from cutter)
- Include simple box/cylinder collision geometries for joint limit and safety checking
- Joint limits measured from actual built frame (calibration step documents this)

---

## Testing and Simulation

### Mock Hardware Nodes
- `mock_esp32`: Simulates all ESP32 sensor data (pH, EC, temp, water level, limit switches, load cell) and responds to actuator commands (steppers, servos, pumps). Configurable noise levels on sensor readings
- `mock_cameras`: Publishes test images of plants at various growth stages (healthy, deficient, diseased, various maturity levels). Uses a library of sample images
- Mock nodes are separate Python ROS2 packages in a `hydroponics_mocks/` directory

### Launch Files
- `simulation.launch.py`: Launches all real nodes + mock hardware. Simulates a grow cycle at configurable time acceleration (e.g., 1 simulated day = 1 real minute)
- `transport_test.launch.py`: Transport + mock ESP32 only. For testing rail motion
- `vision_test.launch.py`: Vision + mock cameras. For testing inference pipeline
- `work_station_test.launch.py`: Work station + mock ESP32. For testing Z + tools
- `nutrient_test.launch.py`: Nutrients + mock ESP32. For testing PID tuning

### Unit Tests
- PID controller: step response, anti-windup clamp, dead band no-actuation zone, setpoint change reset
- Growth stage transitions: verify target changes at correct day boundaries
- Harvest policy: maturity detection logic, cut cycle counting, end-of-life trigger, edge cases (all mature, all empty, mixed)
- Yield economics: cost-per-gram calculation with known inputs
- Plant position indexing: verify rail mm positions correspond to physical plant spacing

### Integration Tests
- Full inspection cycle: transport → inspect position → capture → inference → results published
- Full harvest cycle: plan → transport to work → index to plant → cut → weigh → return to grow
- Nutrient response: inject deficiency detection → verify A/B ratio change within one PID cycle
- Disease alert: inject disease detection → verify system pauses → alert published

---

## Additional Requirements

1. All nodes: proper ROS2 logging at debug, info, warn, error levels
2. All configurable parameters: loadable from YAML config files, changeable at runtime via `ros2 param set`
3. All Python code: type hints on all functions and methods
4. All C++ code: ROS2 C++ style guide
5. Build system: `colcon build --symlink-install`
6. License: MIT
7. Database migrations versioned in `migrations/` directory
8. All config values have sensible defaults — system should launch and run a parsley grow cycle with zero manual configuration
9. README.md: system overview, hardware BOM with costs, ASCII architecture diagram, build instructions, calibration procedures, how-to-run guide

---

## Build and Run

```bash
# Build
cd hydroponics_ws
colcon build --symlink-install

# Source
source install/setup.bash

# Launch full system (real hardware)
ros2 launch hydroponics_bringup full_system.launch.py plant_profile:=parsley

# Launch simulation (no hardware, mock sensors)
ros2 launch hydroponics_bringup simulation.launch.py

# Test individual subsystems
ros2 launch hydroponics_bringup transport_test.launch.py
ros2 launch hydroponics_bringup vision_test.launch.py
ros2 launch hydroponics_bringup work_station_test.launch.py
ros2 launch hydroponics_bringup nutrient_test.launch.py
```
