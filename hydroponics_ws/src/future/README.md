# src/future/ — Archived Components

These packages are out of scope for V0.1 and have been moved here for future reintegration. **Nothing has been deleted.** Every file is preserved exactly as it was.

V0.1 is a minimal single-plant platform to validate four subsystems: probe/aeration cycle, dual-camera NDVI vision, A/B auto-dosing, and water management. The components below require a stationary multi-bin conveyor or harvesting mechanism that does not exist in the V0.1 hardware.

---

## hydroponics_transport

**What it does:** C++ ROS2 action server controlling a linear rail transport system (stepper motor + TMC2209 driver). Moves DWC bins between positions along a rail. Exposes a `TransportTo` action and publishes `TransportStatus`.

**V0.1 mapping:** Not needed — V0.1 has a single stationary bin. No rail, no bin movement.

**V0.2+ reintegration:** When multi-bin support is added, this node drives the rail. It will need to subscribe to a bin scheduler (not yet written) and coordinate with the probe arm and work station. Dependencies on V0.1: none — it is self-contained. The `TransportTo.action` message is already preserved in `hydroponics_msgs`.

---

## hydroponics_bt

**What it does:** C++ BehaviorTree.CPP orchestrator that sequences the full grow cycle: transport → work station → vision inspection → nutrient dosing → harvest. Contains the main `bt_manager` node and five BT node files (harvest, nutrient, safety, transport, work_station, vision). Tree definition in `trees/main_tree.xml`.

**V0.1 mapping:** In V0.1, the orchestration role is replaced by individual timed loops in each node (probe timer, aeration timer, vision capture timer) and event-driven dosing. There is no need for a central behavior tree when all nodes manage their own cycles.

**V0.2+ reintegration:** The BT will be needed once the system has multiple bins requiring coordinated scheduling (transport → position → inspect → dose → harvest). The `bt_manager` will need to be updated to call V0.1's new service interfaces (`/probe/trigger`, `/aeration/trigger`, `/vision/capture`). The existing `nutrient_nodes.cpp` and `vision_nodes.cpp` will need updating for the new topic names.

---

## hydroponics_harvest

**What it does:** Python harvest manager tracking cut-and-regrow cycles. Monitors plant maturity via vision, decides when to cut, coordinates with the work station's cutter servo, records yield data. Publishes `HarvestPlan` and `HarvestResult`.

**V0.1 mapping:** No cutting mechanism in V0.1 hardware. Harvest is manual.

**V0.2+ reintegration:** When the work station is added back, the harvest manager plugs in with minimal changes. It depends on: `InspectionResult` from the vision node (still exists), `ExecuteHarvest.action` from the work station (work_station is in `future/`), and plant profile day ranges. The V0.1 `plant_library.yaml` already includes harvest parameters per herb to ease reintegration.

---

## hydroponics_work_station

**What it does:** C++ ROS2 action server driving the harvest work station hardware via ESP32 micro-ROS: Z-axis stepper (vertical positioning), turret servo (tool selection: CUTTER or GRIPPER), cutter servo (blade actuation), gripper servo (open/close/force grip). Exposes `MoveZ` and `ExecuteHarvest` actions, `GetWorkStationStatus` service.

**V0.1 mapping:** The probe arm in V0.1 is a simpler servo mechanism (extend/retract, no Z-axis stepper, no tool selection). The probe arm logic lives in the new `hydroponics_probe` package. The full harvest work station (Z-axis + cutter + gripper) is not needed until V0.2.

**V0.2+ reintegration:** This node is self-contained and can be re-enabled by adding it back to the launch file and re-enabling the `ExecuteHarvest` action path in the harvest manager. It depends on the ESP32 firmware's servo and stepper modules (unchanged). The `MoveZ.action` and `ExecuteHarvest.action` messages are preserved in `hydroponics_msgs`.

---

## How to Re-enable a Package

1. Move the package directory from `src/future/` back to `src/`
2. Add it to the launch file (`v01_single_plant.launch.py` or a new multi-bin launch)
3. Run `colcon build --packages-select <package_name>`
4. Update topic/service names if V0.1 interfaces changed (see V0.1 node docstrings for current interface contracts)
