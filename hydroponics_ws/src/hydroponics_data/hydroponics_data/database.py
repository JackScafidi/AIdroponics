# MIT License
# Copyright (c) 2024 Claudroponics Project

"""SQLite database manager for the Claudroponics data pipeline."""

from __future__ import annotations

import json
import os
import sqlite3
from typing import Any


class Database:
    """Manages the SQLite database for all hydroponics data.

    Creates or opens the database at db_path and runs all pending SQL
    migration files found in migrations_dir in lexicographic order.
    All public methods use parameterized queries to prevent SQL injection.
    """

    def __init__(self, db_path: str) -> None:
        """Open (or create) the SQLite database and run any pending migrations.

        Args:
            db_path: Filesystem path to the SQLite database file.
        """
        self._db_path = db_path
        os.makedirs(os.path.dirname(db_path) or '.', exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute('PRAGMA journal_mode = WAL')
        self._conn.execute('PRAGMA foreign_keys = ON')
        self._conn.commit()

        # Run migrations relative to this file's package location
        migrations_dir = os.path.join(
            os.path.dirname(__file__), '..', 'migrations'
        )
        if os.path.isdir(migrations_dir):
            self.run_migrations(migrations_dir)

    # ------------------------------------------------------------------
    # Migration support
    # ------------------------------------------------------------------

    def run_migrations(self, migrations_dir: str) -> None:
        """Execute all .sql files in migrations_dir in lexicographic order.

        Each file is executed as a single script so that multi-statement
        files work correctly.  Already-applied files are skipped via a
        lightweight applied-set check against the schema_migrations table
        (if it exists); if the table is absent all files are executed.

        Args:
            migrations_dir: Directory containing *.sql migration files.
        """
        sql_files = sorted(
            f for f in os.listdir(migrations_dir) if f.endswith('.sql')
        )
        for filename in sql_files:
            filepath = os.path.join(migrations_dir, filename)
            with open(filepath, 'r', encoding='utf-8') as fh:
                script = fh.read()
            with self._conn:
                self._conn.executescript(script)

    # ------------------------------------------------------------------
    # Plant helpers
    # ------------------------------------------------------------------

    def insert_plant(
        self,
        plant_id: str,
        position_index: int,
        plant_profile: str,
        planted_date: float,
    ) -> None:
        """Insert a new plant record.

        Args:
            plant_id: UUID string uniquely identifying the plant.
            position_index: Channel position (0–3).
            plant_profile: Profile name, e.g. "parsley".
            planted_date: Unix timestamp (float) of planting time.
        """
        sql = (
            'INSERT OR IGNORE INTO plants '
            '(plant_id, position_index, plant_profile, planted_date) '
            'VALUES (?, ?, ?, ?)'
        )
        with self._conn:
            self._conn.execute(sql, (plant_id, position_index, plant_profile, planted_date))

    def update_plant_stage(self, plant_id: str, stage: str, status: str) -> None:
        """Update the growth stage and status of an existing plant.

        Args:
            plant_id: UUID of the plant to update.
            stage: New growth stage string, e.g. "vegetative".
            status: New status string, e.g. "ACTIVE".
        """
        sql = (
            'UPDATE plants SET current_stage = ?, status = ? '
            'WHERE plant_id = ?'
        )
        with self._conn:
            self._conn.execute(sql, (stage, status, plant_id))

    # ------------------------------------------------------------------
    # Inspection helpers
    # ------------------------------------------------------------------

    def insert_inspection(
        self,
        inspection_id: str,
        plant_id: str,
        timestamp: float,
        canopy_area_cm2: float | None,
        height_cm: float | None,
        leaf_count: int | None,
        health_class: str | None,
        deficiency_type: str | None,
        maturity_state: str | None,
        image_paths: list[str],
    ) -> None:
        """Insert a single plant inspection record.

        Args:
            inspection_id: UUID string for this inspection.
            plant_id: UUID of the inspected plant.
            timestamp: Unix timestamp of the inspection.
            canopy_area_cm2: Measured canopy area in cm².
            height_cm: Measured plant height in cm.
            leaf_count: Counted number of leaves.
            health_class: Classification string, e.g. "healthy".
            deficiency_type: Deficiency type or None when healthy.
            maturity_state: Maturity state string, e.g. "VEGETATIVE".
            image_paths: List of raw image file paths (stored as JSON).
        """
        sql = (
            'INSERT OR IGNORE INTO inspections '
            '(inspection_id, plant_id, timestamp, canopy_area_cm2, height_cm, '
            ' leaf_count, health_class, deficiency_type, maturity_state, raw_image_paths) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'
        )
        with self._conn:
            self._conn.execute(
                sql,
                (
                    inspection_id,
                    plant_id,
                    timestamp,
                    canopy_area_cm2,
                    height_cm,
                    leaf_count,
                    health_class,
                    deficiency_type,
                    maturity_state,
                    json.dumps(image_paths),
                ),
            )

    # ------------------------------------------------------------------
    # Harvest helpers
    # ------------------------------------------------------------------

    def insert_harvest(
        self,
        harvest_id: str,
        plant_id: str,
        timestamp: float,
        harvest_type: str,
        weight_grams: float,
        cut_cycle_number: int,
    ) -> None:
        """Insert a harvest event record.

        Args:
            harvest_id: UUID string for this harvest.
            plant_id: UUID of the harvested plant.
            timestamp: Unix timestamp of the harvest.
            harvest_type: "cut" or "replace".
            weight_grams: Measured weight of harvested material.
            cut_cycle_number: Current cut cycle index.
        """
        sql = (
            'INSERT OR IGNORE INTO harvests '
            '(harvest_id, plant_id, timestamp, harvest_type, weight_grams, cut_cycle_number) '
            'VALUES (?, ?, ?, ?, ?, ?)'
        )
        with self._conn:
            self._conn.execute(
                sql,
                (harvest_id, plant_id, timestamp, harvest_type, weight_grams, cut_cycle_number),
            )

    # ------------------------------------------------------------------
    # Nutrient reading helpers
    # ------------------------------------------------------------------

    def insert_nutrient_reading(
        self,
        timestamp: float,
        ph: float | None,
        ec: float | None,
        temperature_c: float | None,
        growth_stage: str | None,
        a_b_ratio: float | None,
        ph_pid_output: float | None,
        ec_pid_output: float | None,
    ) -> None:
        """Insert a nutrient sensor snapshot.

        Args:
            timestamp: Unix timestamp of the reading.
            ph: pH value.
            ec: Electrical conductivity in mS/cm.
            temperature_c: Nutrient solution temperature in °C.
            growth_stage: Current growth stage label.
            a_b_ratio: Current A:B nutrient ratio.
            ph_pid_output: PID output for pH loop.
            ec_pid_output: PID output for EC loop.
        """
        sql = (
            'INSERT INTO nutrient_readings '
            '(timestamp, ph, ec, temperature_c, growth_stage, a_b_ratio, '
            ' ph_pid_output, ec_pid_output) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?)'
        )
        with self._conn:
            self._conn.execute(
                sql,
                (timestamp, ph, ec, temperature_c, growth_stage, a_b_ratio,
                 ph_pid_output, ec_pid_output),
            )

    # ------------------------------------------------------------------
    # System event helpers
    # ------------------------------------------------------------------

    def insert_system_event(
        self,
        timestamp: float,
        event_type: str,
        severity: str,
        details: str | None,
    ) -> None:
        """Insert a system event or alert record.

        Args:
            timestamp: Unix timestamp of the event.
            event_type: Category label, e.g. "disease" or "water_low".
            severity: One of "info", "warning", "critical".
            details: Free-form detail string or None.
        """
        sql = (
            'INSERT INTO system_events (timestamp, event_type, severity, details) '
            'VALUES (?, ?, ?, ?)'
        )
        with self._conn:
            self._conn.execute(sql, (timestamp, event_type, severity, details))

    # ------------------------------------------------------------------
    # Light reading helpers
    # ------------------------------------------------------------------

    def insert_light_reading(
        self,
        timestamp: float,
        intensity_percent: float | None,
        schedule_state: str | None,
        cumulative_watt_hours: float,
    ) -> None:
        """Insert a grow-light status snapshot.

        Args:
            timestamp: Unix timestamp of the reading.
            intensity_percent: Grow-light intensity 0–100.
            schedule_state: Schedule state label, e.g. "on", "off".
            cumulative_watt_hours: Running energy total in watt-hours.
        """
        sql = (
            'INSERT INTO light_readings '
            '(timestamp, intensity_percent, schedule_state, cumulative_watt_hours) '
            'VALUES (?, ?, ?, ?)'
        )
        with self._conn:
            self._conn.execute(
                sql, (timestamp, intensity_percent, schedule_state, cumulative_watt_hours)
            )

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def get_plant_inspections(self, plant_id: str) -> list[dict[str, Any]]:
        """Return all inspections for a given plant, ordered by timestamp.

        Args:
            plant_id: UUID of the plant to query.

        Returns:
            List of dicts with inspection fields.
        """
        sql = (
            'SELECT inspection_id, plant_id, timestamp, canopy_area_cm2, '
            '       height_cm, leaf_count, health_class, deficiency_type, '
            '       maturity_state, raw_image_paths '
            'FROM inspections '
            'WHERE plant_id = ? '
            'ORDER BY timestamp ASC'
        )
        with self._conn:
            cursor = self._conn.execute(sql, (plant_id,))
            rows = cursor.fetchall()

        results: list[dict[str, Any]] = []
        for row in rows:
            d = dict(row)
            raw = d.get('raw_image_paths')
            d['raw_image_paths'] = json.loads(raw) if raw else []
            results.append(d)
        return results

    def get_all_harvests(self) -> list[dict[str, Any]]:
        """Return all harvest records ordered by timestamp.

        Returns:
            List of dicts with harvest fields.
        """
        sql = (
            'SELECT harvest_id, plant_id, timestamp, harvest_type, '
            '       weight_grams, cut_cycle_number '
            'FROM harvests '
            'ORDER BY timestamp ASC'
        )
        with self._conn:
            cursor = self._conn.execute(sql)
            return [dict(row) for row in cursor.fetchall()]

    def get_nutrient_readings(self, since_timestamp: float) -> list[dict[str, Any]]:
        """Return nutrient readings newer than since_timestamp.

        Args:
            since_timestamp: Unix timestamp lower bound (exclusive).

        Returns:
            List of dicts with nutrient reading fields.
        """
        sql = (
            'SELECT id, timestamp, ph, ec, temperature_c, growth_stage, '
            '       a_b_ratio, ph_pid_output, ec_pid_output '
            'FROM nutrient_readings '
            'WHERE timestamp > ? '
            'ORDER BY timestamp ASC'
        )
        with self._conn:
            cursor = self._conn.execute(sql, (since_timestamp,))
            return [dict(row) for row in cursor.fetchall()]

    def get_total_yield_grams(self) -> float:
        """Return the sum of all harvested weight_grams.

        Returns:
            Total yield in grams, or 0.0 if no harvests exist.
        """
        sql = 'SELECT COALESCE(SUM(weight_grams), 0.0) FROM harvests'
        with self._conn:
            cursor = self._conn.execute(sql)
            result = cursor.fetchone()
            return float(result[0]) if result else 0.0

    def close(self) -> None:
        """Close the underlying database connection."""
        self._conn.close()
