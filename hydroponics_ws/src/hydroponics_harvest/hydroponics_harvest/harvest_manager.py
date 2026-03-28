# MIT License
# Copyright (c) 2024 Claudroponics Project

"""ROS2 harvest manager node with per-plant cut-and-regrow cycle tracking."""

from __future__ import annotations

import time
import uuid
from enum import Enum
from dataclasses import dataclass, field
from typing import Any

import rclpy
from rclpy.node import Node
from rclpy.callback_group import ReentrantCallbackGroup

from hydroponics_msgs.msg import (
    HarvestAction,
    HarvestPlan,
    HarvestResult,
    InspectionResult,
    PlantPositionState,
    SystemAlert,
)
from hydroponics_msgs.srv import ResetCropCycle


# ---------------------------------------------------------------------------
# Plant state enum
# ---------------------------------------------------------------------------

class PlantState(str, Enum):
    """Lifecycle states for a single plant position."""
    EMPTY = 'EMPTY'
    SEEDLING = 'SEEDLING'
    VEGETATIVE = 'VEGETATIVE'
    MATURE = 'MATURE'
    HARVESTED = 'HARVESTED'
    SPENT = 'SPENT'


# Health states that indicate end-of-life eligibility
_DISEASE_STATES = {
    'disease_fungal',
    'disease_bacterial',
}

# ---------------------------------------------------------------------------
# Per-plant runtime record
# ---------------------------------------------------------------------------

@dataclass
class PlantRecord:
    """Mutable runtime state for one grow position."""
    position_index: int
    plant_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    plant_profile: str = 'parsley'
    state: PlantState = PlantState.EMPTY
    health_state: str = 'healthy'
    canopy_area_cm2: float = 0.0
    height_cm: float = 0.0
    leaf_count: int = 0
    days_since_planted: int = 0
    cut_cycle_number: int = 0
    last_inspection_stamp: Any = None   # builtin_interfaces/Time
    last_harvest_stamp: Any = None      # builtin_interfaces/Time
    last_harvest_wall_time: float = 0.0  # time.time() seconds for day-delta calc
    plant_wall_time: float = field(default_factory=time.time)  # when planted


# ---------------------------------------------------------------------------
# Plant profiles
# ---------------------------------------------------------------------------

PLANT_PROFILES: dict[str, dict[str, Any]] = {
    'parsley': {
        'maturity_canopy_area_cm2': 80.0,
        'min_days_between_cuts': 14,
        'cut_height_mm': 50.0,
        'max_cut_cycles': 3,
        'mature_status': 'mature',
    },
    'basil': {
        'maturity_canopy_area_cm2': 60.0,
        'min_days_between_cuts': 10,
        'cut_height_mm': 40.0,
        'max_cut_cycles': 4,
        'mature_status': 'mature',
    },
    'lettuce': {
        'maturity_canopy_area_cm2': 120.0,
        'min_days_between_cuts': 21,
        'cut_height_mm': 30.0,
        'max_cut_cycles': 2,
        'mature_status': 'mature',
    },
}

NUM_POSITIONS = 4


class HarvestManager(Node):
    """Manages per-plant harvest decisions and crop cycle bookkeeping.

    Tracks all four grow positions through their full lifecycle.  After every
    InspectionResult the node evaluates each plant against harvest criteria
    and, if any plants are ready, builds and publishes a HarvestPlan.

    After a HarvestResult arrives the corresponding position state is updated
    and crop-cycle events are emitted on /system_alert.

    Topics subscribed:
        /inspection_result (InspectionResult)  — vision assessment of all plants
        /harvest_result    (HarvestResult)      — outcome of one harvest action

    Topics published:
        /harvest_plan   (HarvestPlan)           — ordered harvest actions to execute
        /plant_status   (PlantPositionState[])  — 1 Hz per-plant state array (4 msgs)
        /system_alert   (SystemAlert)           — crop cycle events

    Services:
        /reset_crop_cycle (ResetCropCycle)      — reset one or all positions
    """

    def __init__(self) -> None:
        super().__init__('harvest_manager')
        self._cb_group = ReentrantCallbackGroup()

        self._declare_parameters()

        # Load default profile thresholds from parameters
        self._default_profile: str = self.get_parameter('plant_profile').value
        self._maturity_canopy_area_cm2: float = self.get_parameter(
            'maturity_canopy_area_cm2').value
        self._min_days_between_cuts: int = int(
            self.get_parameter('min_days_between_cuts').value)
        self._cut_height_mm: float = self.get_parameter('cut_height_mm').value
        self._max_cut_cycles: int = int(
            self.get_parameter('max_cut_cycles').value)

        # Per-position state
        self._plants: list[PlantRecord] = [
            PlantRecord(
                position_index=i,
                plant_profile=self._default_profile,
                state=PlantState.EMPTY,
            )
            for i in range(NUM_POSITIONS)
        ]

        # --- Publishers ---
        self._pub_harvest_plan = self.create_publisher(
            HarvestPlan, 'harvest_plan', 10)
        self._pub_plant_status = self.create_publisher(
            PlantPositionState, 'plant_status', 10)
        self._pub_alert = self.create_publisher(
            SystemAlert, 'system_alert', 10)

        # --- Subscribers ---
        self._sub_inspection = self.create_subscription(
            InspectionResult, 'inspection_result',
            self._inspection_result_callback, 10,
            callback_group=self._cb_group)
        self._sub_harvest_result = self.create_subscription(
            HarvestResult, 'harvest_result',
            self._harvest_result_callback, 10,
            callback_group=self._cb_group)

        # --- Services ---
        self._srv_reset = self.create_service(
            ResetCropCycle, 'reset_crop_cycle',
            self._reset_crop_cycle_callback,
            callback_group=self._cb_group)

        # --- 1 Hz status publisher ---
        self._status_timer = self.create_timer(
            1.0, self._publish_plant_status, callback_group=self._cb_group)

        self.get_logger().info(
            f'Harvest manager initialized — profile={self._default_profile}, '
            f'maturity_canopy={self._maturity_canopy_area_cm2}cm2, '
            f'min_days_between_cuts={self._min_days_between_cuts}, '
            f'max_cut_cycles={self._max_cut_cycles}')

    # ------------------------------------------------------------------
    # Parameter declaration
    # ------------------------------------------------------------------

    def _declare_parameters(self) -> None:
        """Declare all ROS2 parameters with production-safe defaults."""
        self.declare_parameter('plant_profile', 'parsley')
        self.declare_parameter('maturity_canopy_area_cm2', 80.0)
        self.declare_parameter('min_days_between_cuts', 14)
        self.declare_parameter('cut_height_mm', 50.0)
        self.declare_parameter('max_cut_cycles', 3)

    # ------------------------------------------------------------------
    # Profile helpers
    # ------------------------------------------------------------------

    def _profile_for(self, plant_profile: str) -> dict[str, Any]:
        """Return thresholds for a plant profile, falling back to parameters."""
        if plant_profile in PLANT_PROFILES:
            return PLANT_PROFILES[plant_profile]
        # Fall back to parameter-driven thresholds
        return {
            'maturity_canopy_area_cm2': self._maturity_canopy_area_cm2,
            'min_days_between_cuts': self._min_days_between_cuts,
            'cut_height_mm': self._cut_height_mm,
            'max_cut_cycles': self._max_cut_cycles,
            'mature_status': 'mature',
        }

    def _days_since_last_cut(self, plant: PlantRecord) -> int:
        """Return days elapsed since last harvest, or days since planting."""
        if plant.last_harvest_wall_time > 0:
            return int((time.time() - plant.last_harvest_wall_time) / 86400)
        return plant.days_since_planted

    # ------------------------------------------------------------------
    # Inspection result handling
    # ------------------------------------------------------------------

    def _inspection_result_callback(self, msg: InspectionResult) -> None:
        """Process vision inspection — update plant states, build harvest plan."""
        self.get_logger().info(
            f'InspectionResult received (scan #{msg.scan_number}, '
            f'{len(msg.plants)} plants)')

        # Update per-plant state from vision data
        for plant_state_msg in msg.plants:
            idx = plant_state_msg.position_index
            if idx >= NUM_POSITIONS:
                self.get_logger().warn(
                    f'InspectionResult: invalid position_index {idx}, skipping')
                continue
            self._update_plant_from_vision(self._plants[idx], plant_state_msg)

        # Handle system-level disease alert
        if msg.disease_detected:
            self._publish_alert(
                alert_type='disease',
                severity='critical',
                message=f'Disease detected: {msg.disease_type}',
                recommended_action='Isolate affected plants and inspect manually',
            )

        # Evaluate harvest criteria and build plan
        actions = self._evaluate_harvest_criteria()
        if actions:
            self._build_and_publish_harvest_plan(actions)

    def _update_plant_from_vision(
        self,
        plant: PlantRecord,
        vision: PlantPositionState,
    ) -> None:
        """Merge latest vision data into a PlantRecord."""
        plant.health_state = vision.health_state
        plant.canopy_area_cm2 = vision.canopy_area_cm2
        plant.height_cm = vision.height_cm
        plant.leaf_count = vision.leaf_count
        plant.days_since_planted = vision.days_since_planted
        plant.last_inspection_stamp = vision.last_inspection

        # Sync status string back to enum where possible
        try:
            plant.state = PlantState(vision.status)
        except ValueError:
            self.get_logger().debug(
                f'Position {plant.position_index}: unknown status '
                f'"{vision.status}", keeping {plant.state.value}')

    # ------------------------------------------------------------------
    # Harvest criteria evaluation
    # ------------------------------------------------------------------

    def _evaluate_harvest_criteria(self) -> list[HarvestAction]:
        """Assess all four plants and return ordered list of HarvestActions."""
        actions: list[HarvestAction] = []

        for plant in self._plants:
            if plant.state == PlantState.EMPTY:
                continue

            profile = self._profile_for(plant.plant_profile)
            action = self._classify_plant_action(plant, profile)
            if action is not None:
                actions.append(action)

        # Order: cuts first (by position index), then replacements
        cuts = [a for a in actions if a.action_type == 'cut']
        replacements = [a for a in actions if a.action_type == 'replace']
        return cuts + replacements

    def _classify_plant_action(
        self,
        plant: PlantRecord,
        profile: dict[str, Any],
    ) -> HarvestAction | None:
        """Determine whether a plant needs a cut, replacement, or nothing.

        Returns a HarvestAction or None.
        """
        # End-of-life conditions → replace
        is_diseased = plant.health_state in _DISEASE_STATES
        exceeded_max_cycles = plant.cut_cycle_number >= profile['max_cut_cycles']

        if is_diseased or exceeded_max_cycles:
            plant.state = PlantState.SPENT
            reason = 'diseased' if is_diseased else f'max cycles ({profile["max_cut_cycles"]}) reached'
            self.get_logger().info(
                f'Position {plant.position_index}: end-of-life ({reason}) — scheduling replace')
            action = HarvestAction()
            action.position_index = plant.position_index
            action.action_type = 'replace'
            action.cut_height_mm = 0.0
            return action

        # Cut-and-regrow conditions
        is_mature_status = plant.state == PlantState.MATURE
        canopy_ready = plant.canopy_area_cm2 >= profile['maturity_canopy_area_cm2']
        days_ok = self._days_since_last_cut(plant) >= profile['min_days_between_cuts']

        if is_mature_status and canopy_ready and days_ok:
            self.get_logger().info(
                f'Position {plant.position_index}: ready for cut '
                f'(canopy={plant.canopy_area_cm2:.1f}cm2, '
                f'days_since_cut={self._days_since_last_cut(plant)})')
            action = HarvestAction()
            action.position_index = plant.position_index
            action.action_type = 'cut'
            action.cut_height_mm = profile['cut_height_mm']
            return action

        return None

    def _build_and_publish_harvest_plan(self, actions: list[HarvestAction]) -> None:
        """Construct a HarvestPlan message and publish it."""
        plan = HarvestPlan()
        plan.header.stamp = self.get_clock().now().to_msg()
        plan.actions = actions
        plan.total_cuts = sum(1 for a in actions if a.action_type == 'cut')
        plan.total_replacements = sum(
            1 for a in actions if a.action_type == 'replace')

        self._pub_harvest_plan.publish(plan)
        self.get_logger().info(
            f'HarvestPlan published: {plan.total_cuts} cuts, '
            f'{plan.total_replacements} replacements')

    # ------------------------------------------------------------------
    # Harvest result handling
    # ------------------------------------------------------------------

    def _harvest_result_callback(self, msg: HarvestResult) -> None:
        """Update plant state after a harvest action completes."""
        idx = msg.position_index
        if idx >= NUM_POSITIONS:
            self.get_logger().warn(
                f'HarvestResult: invalid position_index {idx}')
            return

        plant = self._plants[idx]

        if not msg.success:
            self.get_logger().warn(
                f'HarvestResult: action "{msg.action_type}" failed at '
                f'position {idx}')
            return

        now_stamp = self.get_clock().now().to_msg()

        if msg.action_type == 'cut':
            plant.cut_cycle_number += 1
            plant.state = PlantState.HARVESTED
            plant.last_harvest_stamp = now_stamp
            plant.last_harvest_wall_time = time.time()
            self.get_logger().info(
                f'Position {idx}: cut complete '
                f'(weight={msg.weight_grams:.1f}g, '
                f'cycle #{plant.cut_cycle_number})')
            self._publish_alert(
                alert_type='cycle_complete',
                severity='info',
                message=(
                    f'Position {idx} harvested '
                    f'({msg.weight_grams:.1f}g, cycle {plant.cut_cycle_number})'
                ),
                recommended_action='Monitor regrowth over next 14 days',
            )

        elif msg.action_type == 'replace':
            old_id = plant.plant_id
            # Reset position to fresh seedling
            plant.plant_id = str(uuid.uuid4())
            plant.state = PlantState.SEEDLING
            plant.health_state = 'healthy'
            plant.canopy_area_cm2 = 0.0
            plant.height_cm = 0.0
            plant.leaf_count = 0
            plant.days_since_planted = 0
            plant.cut_cycle_number = 0
            plant.last_harvest_stamp = now_stamp
            plant.last_harvest_wall_time = time.time()
            plant.plant_wall_time = time.time()
            self.get_logger().info(
                f'Position {idx}: plant replaced '
                f'(old_id={old_id[:8]}, new_id={plant.plant_id[:8]})')
            self._publish_alert(
                alert_type='cycle_complete',
                severity='info',
                message=f'Position {idx} replanted with {plant.plant_profile}',
                recommended_action='Check seedling tray stock level',
            )

    # ------------------------------------------------------------------
    # Status publishing
    # ------------------------------------------------------------------

    def _publish_plant_status(self) -> None:
        """Publish one PlantPositionState message per position at 1 Hz."""
        now_stamp = self.get_clock().now().to_msg()
        for plant in self._plants:
            msg = PlantPositionState()
            msg.position_index = plant.position_index
            msg.plant_id = plant.plant_id
            msg.plant_profile = plant.plant_profile
            msg.status = plant.state.value
            msg.health_state = plant.health_state
            msg.canopy_area_cm2 = plant.canopy_area_cm2
            msg.height_cm = plant.height_cm
            msg.leaf_count = plant.leaf_count
            msg.days_since_planted = plant.days_since_planted
            msg.cut_cycle_number = plant.cut_cycle_number
            if plant.last_inspection_stamp is not None:
                msg.last_inspection = plant.last_inspection_stamp
            if plant.last_harvest_stamp is not None:
                msg.last_harvest = plant.last_harvest_stamp
            self._pub_plant_status.publish(msg)

    # ------------------------------------------------------------------
    # Alert helper
    # ------------------------------------------------------------------

    def _publish_alert(
        self,
        alert_type: str,
        severity: str,
        message: str,
        recommended_action: str,
    ) -> None:
        """Publish a SystemAlert message."""
        msg = SystemAlert()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.alert_type = alert_type
        msg.severity = severity
        msg.message = message
        msg.recommended_action = recommended_action
        self._pub_alert.publish(msg)

    # ------------------------------------------------------------------
    # Service callbacks
    # ------------------------------------------------------------------

    def _reset_crop_cycle_callback(
        self,
        request: ResetCropCycle.Request,
        response: ResetCropCycle.Response,
    ) -> ResetCropCycle.Response:
        """Reset one position (by index) or all positions (index == 255)."""
        profile = request.plant_profile or self._default_profile

        def _reset_one(plant: PlantRecord) -> None:
            plant.plant_id = str(uuid.uuid4())
            plant.plant_profile = profile
            plant.state = PlantState.SEEDLING
            plant.health_state = 'healthy'
            plant.canopy_area_cm2 = 0.0
            plant.height_cm = 0.0
            plant.leaf_count = 0
            plant.days_since_planted = 0
            plant.cut_cycle_number = 0
            plant.last_inspection_stamp = None
            plant.last_harvest_stamp = None
            plant.last_harvest_wall_time = 0.0
            plant.plant_wall_time = time.time()

        if request.position_index == 255:
            for plant in self._plants:
                _reset_one(plant)
            self.get_logger().info(
                f'All positions reset to SEEDLING (profile={profile})')
            self._publish_alert(
                alert_type='cycle_complete',
                severity='info',
                message=f'All positions reset to {profile} seedling',
                recommended_action='Ensure seedling rack is stocked',
            )
        else:
            idx = request.position_index
            if idx >= NUM_POSITIONS:
                self.get_logger().warn(
                    f'ResetCropCycle: invalid position_index {idx}')
                response.success = False
                return response
            _reset_one(self._plants[idx])
            self.get_logger().info(
                f'Position {idx} reset to SEEDLING (profile={profile})')
            self._publish_alert(
                alert_type='cycle_complete',
                severity='info',
                message=f'Position {idx} reset to {profile} seedling',
                recommended_action='Place new seedling in position',
            )

        response.success = True
        return response


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = HarvestManager()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
