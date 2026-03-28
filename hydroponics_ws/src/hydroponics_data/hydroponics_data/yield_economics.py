# MIT License
# Copyright (c) 2024 Claudroponics Project

"""Yield and cost economics analytics for the Claudroponics system."""

from __future__ import annotations

from typing import Any

from hydroponics_data.database import Database


class YieldEconomics:
    """Computes yield totals and cost-efficiency metrics from persisted data.

    All monetary and physical constants are sourced from economics_config,
    which should mirror the structure of config/economics.yaml (keyed under
    the ``economics.ros__parameters`` namespace or a flat dict).

    The class is intentionally stateless between calls so that every
    invocation reflects the latest database state.
    """

    def __init__(self, database: Database, economics_config: dict[str, Any]) -> None:
        """Initialise with a shared Database and economics configuration.

        Args:
            database: Open Database instance used for all queries.
            economics_config: Flat dict of economic parameters.  Expected
                keys (with units) are documented inline below.  Missing
                keys fall back to sensible defaults so the class remains
                functional with a partial configuration.
        """
        self._db = database
        self._cfg = economics_config

    # ------------------------------------------------------------------
    # Configuration helpers
    # ------------------------------------------------------------------

    def _cfg_float(self, key: str, default: float) -> float:
        """Return a float configuration value, falling back to default."""
        val = self._cfg.get(key, default)
        try:
            return float(val)
        except (TypeError, ValueError):
            return default

    # ------------------------------------------------------------------
    # Yield analytics
    # ------------------------------------------------------------------

    def compute_total_yield(self) -> float:
        """Return the total harvested weight in grams across all harvests.

        Returns:
            Total yield in grams (0.0 if no harvests recorded).
        """
        return self._db.get_total_yield_grams()

    def compute_avg_yield_per_cut(self) -> float:
        """Return the average yield per cut-type harvest in grams.

        Only harvests with harvest_type == "cut" are included.  Returns 0.0
        when no cut harvests are recorded.

        Returns:
            Average yield per cut in grams.
        """
        harvests = self._db.get_all_harvests()
        cut_weights = [h['weight_grams'] for h in harvests if h['harvest_type'] == 'cut']
        if not cut_weights:
            return 0.0
        return sum(cut_weights) / len(cut_weights)

    def compute_yield_per_watt_hour(self) -> float:
        """Return grams of yield per watt-hour of grow-light energy consumed.

        Uses the maximum cumulative_watt_hours value from light_readings as
        the total energy consumed.  Returns 0.0 when no energy data or yield
        data are available.

        Returns:
            g/Wh ratio.
        """
        total_yield = self.compute_total_yield()
        if total_yield <= 0.0:
            return 0.0

        total_wh = self._get_total_watt_hours()
        if total_wh <= 0.0:
            return 0.0

        return total_yield / total_wh

    def compute_yield_per_liter_nutrient(self) -> float:
        """Return grams of yield per litre of nutrient solution dispensed.

        Nutrient volume is estimated from system_events records whose
        event_type is "pump_dose" and whose details field encodes a JSON
        object with a ``volume_ml`` key.  Falls back to pump runtime samples
        if that data is absent.  Returns 0.0 when no reliable volume data
        exist.

        Returns:
            g/L ratio.
        """
        total_yield = self.compute_total_yield()
        if total_yield <= 0.0:
            return 0.0

        total_liters = self._estimate_nutrient_liters()
        if total_liters <= 0.0:
            return 0.0

        return total_yield / total_liters

    def compute_cost_per_gram(self) -> float:
        """Return total operating cost divided by total yield in grams.

        Cost components:
            - Energy:   total_wh * electricity_cost_per_kwh / 1000
            - Nutrients: estimated_liters * (nutrient_a_cost + nutrient_b_cost) / 2
            - Water:    reservoir_volume_liters * water_cost_per_liter
                        (multiplied by total crop cycles as a proxy for refills)

        Returns 0.0 when total yield is zero to avoid division by zero.

        Returns:
            USD per gram.
        """
        total_yield = self.compute_total_yield()
        if total_yield <= 0.0:
            return 0.0

        energy_cost = self._compute_energy_cost()
        nutrient_cost = self._compute_nutrient_cost()
        water_cost = self._compute_water_cost()

        total_cost = energy_cost + nutrient_cost + water_cost
        return total_cost / total_yield

    def compute_total_crop_cycles(self) -> int:
        """Count distinct crop cycles from system_events.

        A crop cycle event is identified by event_type == "cycle_complete".

        Returns:
            Number of completed crop cycles (0 if none recorded).
        """
        conn = self._db._conn  # access the underlying connection directly
        sql = (
            "SELECT COUNT(*) FROM system_events WHERE event_type = 'cycle_complete'"
        )
        cursor = conn.execute(sql)
        result = cursor.fetchone()
        return int(result[0]) if result else 0

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_total_watt_hours(self) -> float:
        """Return the maximum cumulative_watt_hours from light_readings."""
        conn = self._db._conn
        sql = 'SELECT COALESCE(MAX(cumulative_watt_hours), 0.0) FROM light_readings'
        cursor = conn.execute(sql)
        result = cursor.fetchone()
        return float(result[0]) if result else 0.0

    def _estimate_nutrient_liters(self) -> float:
        """Estimate total nutrient volume dispensed in litres.

        Sums ``volume_ml`` values from system_events with event_type
        "pump_dose" whose details field is a JSON object.  If no such
        events exist, returns a reservoir-exchange estimate:
            cycles * reservoir_volume_liters.
        """
        import json

        conn = self._db._conn
        sql = "SELECT details FROM system_events WHERE event_type = 'pump_dose'"
        cursor = conn.execute(sql)
        rows = cursor.fetchall()

        total_ml = 0.0
        for row in rows:
            details = row[0]
            if details:
                try:
                    data = json.loads(details)
                    total_ml += float(data.get('volume_ml', 0.0))
                except (json.JSONDecodeError, TypeError, ValueError):
                    pass

        if total_ml > 0.0:
            return total_ml / 1000.0

        # Fallback: estimate from crop cycles × reservoir volume.
        cycles = max(self.compute_total_crop_cycles(), 1)
        reservoir_l = self._cfg_float('reservoir_volume_liters', 8.0)
        return cycles * reservoir_l

    def _compute_energy_cost(self) -> float:
        """Return estimated energy cost in USD."""
        total_wh = self._get_total_watt_hours()
        cost_per_kwh = self._cfg_float('electricity_cost_per_kwh', 0.12)
        return (total_wh / 1000.0) * cost_per_kwh

    def _compute_nutrient_cost(self) -> float:
        """Return estimated nutrient solution cost in USD."""
        liters = self._estimate_nutrient_liters()
        # Assume 50/50 A/B split; use average of A and B costs.
        cost_a = self._cfg_float('nutrient_a_cost_per_liter', 8.0)
        cost_b = self._cfg_float('nutrient_b_cost_per_liter', 8.0)
        avg_cost = (cost_a + cost_b) / 2.0
        return liters * avg_cost

    def _compute_water_cost(self) -> float:
        """Return estimated water cost in USD based on reservoir refills."""
        cycles = max(self.compute_total_crop_cycles(), 1)
        reservoir_l = self._cfg_float('reservoir_volume_liters', 8.0)
        cost_per_liter = self._cfg_float('water_cost_per_liter', 0.002)
        return cycles * reservoir_l * cost_per_liter
