# MIT License
# Copyright (c) 2024 Claudroponics Project

"""Growth curve analytics for individual hydroponic plants."""

from __future__ import annotations

from collections import Counter
from typing import Any

from hydroponics_data.database import Database


class GrowthAnalytics:
    """Computes growth curves and predictive analytics from inspection history.

    All computations are performed on data retrieved from the Database instance
    provided at construction time.  No state is cached between calls so that
    results always reflect the latest persisted data.
    """

    # Minimum number of inspections required for linear-regression calculations.
    _MIN_REGRESSION_POINTS: int = 2

    def __init__(self, database: Database) -> None:
        """Initialise with a shared Database instance.

        Args:
            database: Open Database instance used for all queries.
        """
        self._db = database

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compute_growth_curve(self, plant_id: str) -> list[dict[str, Any]]:
        """Return a time-ordered growth curve for the given plant.

        Each element contains the timestamp and the core morphometric
        measurements recorded at that inspection.

        Args:
            plant_id: UUID of the plant to analyse.

        Returns:
            List of dicts with keys:
                timestamp (float), canopy_area_cm2 (float | None),
                height_cm (float | None), leaf_count (int | None).
            Empty list if no inspections exist.
        """
        inspections = self._db.get_plant_inspections(plant_id)
        return [
            {
                'timestamp': row['timestamp'],
                'canopy_area_cm2': row['canopy_area_cm2'],
                'height_cm': row['height_cm'],
                'leaf_count': row['leaf_count'],
            }
            for row in inspections
        ]

    def compute_growth_rate(self, plant_id: str, last_n: int = 10) -> float:
        """Estimate canopy growth rate via linear regression over recent inspections.

        Performs ordinary least-squares regression of canopy_area_cm2 against
        elapsed days.  Only inspections with a valid (non-None) canopy area
        measurement are included.

        Args:
            plant_id: UUID of the plant to analyse.
            last_n: Maximum number of most-recent inspections to include.

        Returns:
            Growth rate in cm²/day.  Returns 0.0 when fewer than
            _MIN_REGRESSION_POINTS valid readings are available.
        """
        inspections = self._db.get_plant_inspections(plant_id)

        # Keep only entries with a valid canopy area, then take the last N.
        valid: list[tuple[float, float]] = [
            (row['timestamp'], row['canopy_area_cm2'])
            for row in inspections
            if row['canopy_area_cm2'] is not None
        ]
        valid = valid[-last_n:]

        if len(valid) < self._MIN_REGRESSION_POINTS:
            return 0.0

        # Convert timestamps to elapsed days from the first point.
        t0 = valid[0][0]
        xs = [(ts - t0) / 86400.0 for ts, _ in valid]
        ys = [area for _, area in valid]

        return _linear_regression_slope(xs, ys)

    def estimate_time_to_maturity(
        self, plant_id: str, target_area_cm2: float
    ) -> float | None:
        """Estimate how many days remain until the plant reaches target_area_cm2.

        Uses the current growth rate and the most-recent canopy area
        measurement to project forward.

        Args:
            plant_id: UUID of the plant to analyse.
            target_area_cm2: Canopy area threshold that defines maturity.

        Returns:
            Estimated days to maturity as a float, or None if the estimate
            cannot be computed (insufficient data, zero/negative growth rate,
            or current area already exceeds the target).
        """
        rate = self.compute_growth_rate(plant_id)
        if rate <= 0.0:
            return None

        # Find the most recent valid canopy area.
        inspections = self._db.get_plant_inspections(plant_id)
        current_area: float | None = None
        for row in reversed(inspections):
            if row['canopy_area_cm2'] is not None:
                current_area = row['canopy_area_cm2']
                break

        if current_area is None:
            return None

        remaining = target_area_cm2 - current_area
        if remaining <= 0.0:
            return 0.0

        return remaining / rate

    def compute_average_health(self, plant_id: str, last_n: int = 5) -> str:
        """Return the most frequently observed health_class over recent inspections.

        Args:
            plant_id: UUID of the plant to analyse.
            last_n: Number of most-recent inspections to consider.

        Returns:
            Most common health_class string, or "unknown" when no valid
            health classifications are available.
        """
        inspections = self._db.get_plant_inspections(plant_id)
        recent = inspections[-last_n:]

        classes = [
            row['health_class']
            for row in recent
            if row['health_class'] is not None
        ]

        if not classes:
            return 'unknown'

        most_common, _ = Counter(classes).most_common(1)[0]
        return most_common


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _linear_regression_slope(xs: list[float], ys: list[float]) -> float:
    """Return the slope of the ordinary least-squares line through (xs, ys).

    Args:
        xs: Independent variable values (must have the same length as ys).
        ys: Dependent variable values.

    Returns:
        Slope (rise/run).  Returns 0.0 if the denominator is zero (all x
        values identical).
    """
    n = len(xs)
    sum_x = sum(xs)
    sum_y = sum(ys)
    sum_xy = sum(x * y for x, y in zip(xs, ys))
    sum_xx = sum(x * x for x in xs)

    denom = n * sum_xx - sum_x * sum_x
    if denom == 0.0:
        return 0.0

    return (n * sum_xy - sum_x * sum_y) / denom
