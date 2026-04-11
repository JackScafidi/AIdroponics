# MIT License
# Copyright (c) 2024 Claudroponics Project

"""Unit tests for harvest manager decision logic."""

import pytest
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# Standalone copies of types under test (decoupled from ROS for unit testing)
class PlantStatus(str, Enum):
    EMPTY = "EMPTY"
    SEEDLING = "SEEDLING"
    VEGETATIVE = "VEGETATIVE"
    MATURE = "MATURE"
    HARVESTED = "HARVESTED"
    SPENT = "SPENT"


@dataclass
class PlantState:
    position_index: int
    status: PlantStatus = PlantStatus.EMPTY
    health_state: str = "healthy"
    canopy_area_cm2: float = 0.0
    maturity_state: str = "immature"
    days_since_planted: int = 0
    days_since_last_cut: int = 0
    cut_cycle_number: int = 0


@dataclass
class HarvestConfig:
    maturity_canopy_area_cm2: float = 80.0
    min_days_between_cuts: int = 14
    cut_height_mm: float = 50.0
    max_cut_cycles: int = 3


def should_cut(plant: PlantState, config: HarvestConfig) -> bool:
    """Determine if a plant should be cut-and-regrown."""
    if plant.status not in (PlantStatus.MATURE, PlantStatus.VEGETATIVE):
        return False
    if plant.maturity_state != "mature":
        return False
    if plant.canopy_area_cm2 < config.maturity_canopy_area_cm2:
        return False
    if plant.days_since_last_cut < config.min_days_between_cuts:
        return False
    return True


def should_replace(plant: PlantState, config: HarvestConfig) -> bool:
    """Determine if a plant should be end-of-life replaced."""
    if plant.cut_cycle_number >= config.max_cut_cycles:
        return True
    if plant.health_state in ("disease_fungal", "disease_bacterial"):
        return True
    if plant.status == PlantStatus.SPENT:
        return True
    return False


def build_harvest_plan(plants: list[PlantState], config: HarvestConfig) -> list[dict[str, Any]]:
    """Build ordered list of harvest actions."""
    actions = []
    for plant in plants:
        if should_replace(plant, config):
            actions.append({"position_index": plant.position_index,
                             "action_type": "replace",
                             "cut_height_mm": 0.0})
        elif should_cut(plant, config):
            actions.append({"position_index": plant.position_index,
                             "action_type": "cut",
                             "cut_height_mm": config.cut_height_mm})
    return actions


class TestMaturityDetection:
    def test_mature_plant_ready_for_cut(self) -> None:
        cfg = HarvestConfig()
        plant = PlantState(
            position_index=0,
            status=PlantStatus.MATURE,
            maturity_state="mature",
            canopy_area_cm2=90.0,
            days_since_last_cut=15,
        )
        assert should_cut(plant, cfg) is True

    def test_immature_plant_not_cut(self) -> None:
        cfg = HarvestConfig()
        plant = PlantState(
            position_index=0,
            status=PlantStatus.VEGETATIVE,
            maturity_state="vegetative",
            canopy_area_cm2=90.0,
            days_since_last_cut=20,
        )
        assert should_cut(plant, cfg) is False

    def test_too_small_canopy_not_cut(self) -> None:
        cfg = HarvestConfig(maturity_canopy_area_cm2=80.0)
        plant = PlantState(
            position_index=0,
            status=PlantStatus.MATURE,
            maturity_state="mature",
            canopy_area_cm2=50.0,  # below threshold
            days_since_last_cut=20,
        )
        assert should_cut(plant, cfg) is False

    def test_min_days_between_cuts_enforced(self) -> None:
        cfg = HarvestConfig(min_days_between_cuts=14)
        plant = PlantState(
            position_index=0,
            status=PlantStatus.MATURE,
            maturity_state="mature",
            canopy_area_cm2=90.0,
            days_since_last_cut=10,  # too soon
        )
        assert should_cut(plant, cfg) is False

    def test_exactly_at_min_days_boundary(self) -> None:
        cfg = HarvestConfig(min_days_between_cuts=14)
        plant = PlantState(
            position_index=0,
            status=PlantStatus.MATURE,
            maturity_state="mature",
            canopy_area_cm2=90.0,
            days_since_last_cut=14,  # exactly at boundary
        )
        assert should_cut(plant, cfg) is True


class TestCutCycleCounting:
    def test_end_of_life_at_max_cut_cycles(self) -> None:
        cfg = HarvestConfig(max_cut_cycles=3)
        plant = PlantState(position_index=0, cut_cycle_number=3)
        assert should_replace(plant, cfg) is True

    def test_not_end_of_life_below_max(self) -> None:
        cfg = HarvestConfig(max_cut_cycles=3)
        plant = PlantState(position_index=0, cut_cycle_number=2)
        assert should_replace(plant, cfg) is False

    def test_disease_triggers_replacement(self) -> None:
        cfg = HarvestConfig()
        plant = PlantState(position_index=0, health_state="disease_fungal")
        assert should_replace(plant, cfg) is True

    def test_bacterial_disease_triggers_replacement(self) -> None:
        cfg = HarvestConfig()
        plant = PlantState(position_index=0, health_state="disease_bacterial")
        assert should_replace(plant, cfg) is True

    def test_spent_status_triggers_replacement(self) -> None:
        cfg = HarvestConfig()
        plant = PlantState(position_index=0, status=PlantStatus.SPENT)
        assert should_replace(plant, cfg) is True


class TestHarvestPolicy:
    def test_all_empty_positions_no_actions(self) -> None:
        cfg = HarvestConfig()
        plants = [PlantState(position_index=i, status=PlantStatus.EMPTY)
                  for i in range(4)]
        plan = build_harvest_plan(plants, cfg)
        assert len(plan) == 0

    def test_all_mature_plants_all_cut(self) -> None:
        cfg = HarvestConfig()
        plants = [
            PlantState(
                position_index=i,
                status=PlantStatus.MATURE,
                maturity_state="mature",
                canopy_area_cm2=100.0,
                days_since_last_cut=20,
            )
            for i in range(4)
        ]
        plan = build_harvest_plan(plants, cfg)
        assert len(plan) == 4
        assert all(a["action_type"] == "cut" for a in plan)

    def test_mixed_positions_correct_selection(self) -> None:
        cfg = HarvestConfig()
        plants = [
            PlantState(position_index=0, status=PlantStatus.EMPTY),
            PlantState(
                position_index=1,
                status=PlantStatus.MATURE, maturity_state="mature",
                canopy_area_cm2=90.0, days_since_last_cut=15
            ),
            PlantState(
                position_index=2,
                status=PlantStatus.VEGETATIVE, maturity_state="vegetative",
                canopy_area_cm2=40.0
            ),
            PlantState(position_index=3, cut_cycle_number=3),  # end-of-life
        ]
        plan = build_harvest_plan(plants, cfg)
        assert len(plan) == 2
        cut_actions = [a for a in plan if a["action_type"] == "cut"]
        replace_actions = [a for a in plan if a["action_type"] == "replace"]
        assert len(cut_actions) == 1
        assert cut_actions[0]["position_index"] == 1
        assert len(replace_actions) == 1
        assert replace_actions[0]["position_index"] == 3

    def test_action_order_matches_position_order(self) -> None:
        """Harvest plan should process positions in order 0→3."""
        cfg = HarvestConfig()
        plants = [
            PlantState(
                position_index=i,
                status=PlantStatus.MATURE, maturity_state="mature",
                canopy_area_cm2=90.0, days_since_last_cut=20
            )
            for i in range(4)
        ]
        plan = build_harvest_plan(plants, cfg)
        positions = [a["position_index"] for a in plan]
        assert positions == sorted(positions)

    def test_cut_height_from_config(self) -> None:
        cfg = HarvestConfig(cut_height_mm=60.0)
        plants = [
            PlantState(
                position_index=0,
                status=PlantStatus.MATURE, maturity_state="mature",
                canopy_area_cm2=90.0, days_since_last_cut=20
            )
        ]
        plan = build_harvest_plan(plants, cfg)
        assert len(plan) == 1
        assert plan[0]["cut_height_mm"] == 60.0


class TestEdgeCases:
    def test_disease_overrides_mature_cut(self) -> None:
        """Diseased plant should be replaced, not cut, even if mature."""
        cfg = HarvestConfig()
        plant = PlantState(
            position_index=0,
            status=PlantStatus.MATURE,
            maturity_state="mature",
            canopy_area_cm2=100.0,
            days_since_last_cut=20,
            health_state="disease_fungal",
        )
        plan = build_harvest_plan([plant], cfg)
        assert len(plan) == 1
        assert plan[0]["action_type"] == "replace"

    def test_overmature_still_cut_if_not_end_of_life(self) -> None:
        """Overmature plant within cut cycle limit → still should cut if mature state."""
        cfg = HarvestConfig(max_cut_cycles=3)
        plant = PlantState(
            position_index=0,
            status=PlantStatus.MATURE,
            maturity_state="mature",  # overmature maps to mature for cut decision
            canopy_area_cm2=120.0,
            days_since_last_cut=20,
            cut_cycle_number=2,  # under limit
        )
        plan = build_harvest_plan([plant], cfg)
        assert len(plan) == 1
        assert plan[0]["action_type"] == "cut"
