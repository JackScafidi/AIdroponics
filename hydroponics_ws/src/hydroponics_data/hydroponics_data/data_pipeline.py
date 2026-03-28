# MIT License
# Copyright (c) 2024 Claudroponics Project

"""ROS2 data-pipeline node: persists all system data and publishes analytics."""

from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any

import rclpy
from rclpy.node import Node
from rclpy.callback_group import ReentrantCallbackGroup
from std_msgs.msg import Header

from hydroponics_msgs.msg import (
    GrowthDataPoint,
    HarvestResult,
    InspectionResult,
    LightStatus,
    NutrientStatus,
    SystemAlert,
    YieldMetrics,
)
from hydroponics_msgs.srv import GetPlantHistory, GetYieldAnalytics

from hydroponics_data.database import Database
from hydroponics_data.growth_analytics import GrowthAnalytics
from hydroponics_data.yield_economics import YieldEconomics


class DataPipeline(Node):
    """Central data-pipeline node for the Claudroponics system.

    Responsibilities
    ----------------
    * Persists every inspection, harvest, nutrient reading, light reading,
      and system alert to SQLite via the Database class.
    * Down-samples high-frequency NutrientStatus and LightStatus messages
      to 0.1 Hz before writing to the database.
    * Computes and publishes GrowthDataPoint messages on /growth_curve_update
      in response to each InspectionResult.
    * Publishes YieldMetrics on /yield_metrics every 60 seconds.
    * Provides GetYieldAnalytics and GetPlantHistory services.
    * Auto-creates four parsley plant records on startup when the plants
      table is empty.

    Parameters
    ----------
    database_path : str
        Filesystem path to the SQLite database file.
        Default: ``~/.ros/hydroponics/hydroponics.db``
    economics_config_path : str
        Path to the economics YAML config file.
        Default: resolved relative to this package's share directory.
    """

    # Down-sample interval for nutrient and light readings (seconds).
    _DOWNSAMPLE_INTERVAL: float = 10.0  # 0.1 Hz

    # Yield-metrics publish interval (seconds).
    _YIELD_PUBLISH_INTERVAL: float = 60.0

    # Default plant profile used for auto-created records.
    _DEFAULT_PROFILE: str = 'parsley'

    def __init__(self) -> None:
        super().__init__('data_pipeline')
        self._cb_group = ReentrantCallbackGroup()

        # ------------------------------------------------------------------
        # Parameters
        # ------------------------------------------------------------------
        self.declare_parameter(
            'database_path',
            os.path.expanduser('~/.ros/hydroponics/hydroponics.db'),
        )
        self.declare_parameter('economics_config_path', '')

        db_path: str = self.get_parameter('database_path').value
        economics_path: str = self.get_parameter('economics_config_path').value

        # ------------------------------------------------------------------
        # Database
        # ------------------------------------------------------------------
        self._db = Database(db_path)
        self.get_logger().info(f'Database opened at: {db_path}')

        # ------------------------------------------------------------------
        # Economics configuration
        # ------------------------------------------------------------------
        self._economics_cfg: dict[str, Any] = self._load_economics_config(economics_path)
        self._growth_analytics = GrowthAnalytics(self._db)
        self._yield_economics = YieldEconomics(self._db, self._economics_cfg)

        # ------------------------------------------------------------------
        # Down-sample timestamps
        # ------------------------------------------------------------------
        self._last_nutrient_write: float = 0.0
        self._last_light_write: float = 0.0

        # ------------------------------------------------------------------
        # In-memory cache (REST-queryable / for yield-metrics publishing)
        # ------------------------------------------------------------------
        self._yield_cache: dict[str, Any] = {}

        # ------------------------------------------------------------------
        # Subscriptions
        # ------------------------------------------------------------------
        self._sub_inspection = self.create_subscription(
            InspectionResult,
            '/inspection_result',
            self._on_inspection_result,
            10,
            callback_group=self._cb_group,
        )
        self._sub_harvest = self.create_subscription(
            HarvestResult,
            '/harvest_result',
            self._on_harvest_result,
            10,
            callback_group=self._cb_group,
        )
        self._sub_nutrient = self.create_subscription(
            NutrientStatus,
            '/nutrient_status',
            self._on_nutrient_status,
            10,
            callback_group=self._cb_group,
        )
        self._sub_alert = self.create_subscription(
            SystemAlert,
            '/system_alert',
            self._on_system_alert,
            10,
            callback_group=self._cb_group,
        )
        self._sub_light = self.create_subscription(
            LightStatus,
            '/light_status',
            self._on_light_status,
            10,
            callback_group=self._cb_group,
        )

        # ------------------------------------------------------------------
        # Publishers
        # ------------------------------------------------------------------
        self._pub_growth = self.create_publisher(GrowthDataPoint, '/growth_curve_update', 10)
        self._pub_yield = self.create_publisher(YieldMetrics, '/yield_metrics', 10)

        # ------------------------------------------------------------------
        # Services
        # ------------------------------------------------------------------
        self._srv_yield = self.create_service(
            GetYieldAnalytics,
            'get_yield_analytics',
            self._handle_get_yield_analytics,
            callback_group=self._cb_group,
        )
        self._srv_history = self.create_service(
            GetPlantHistory,
            'get_plant_history',
            self._handle_get_plant_history,
            callback_group=self._cb_group,
        )

        # ------------------------------------------------------------------
        # Timers
        # ------------------------------------------------------------------
        self._yield_timer = self.create_timer(
            self._YIELD_PUBLISH_INTERVAL,
            self._publish_yield_metrics,
            callback_group=self._cb_group,
        )

        # ------------------------------------------------------------------
        # Bootstrap: create default plants if the table is empty
        # ------------------------------------------------------------------
        self._ensure_default_plants()

        self.get_logger().info('DataPipeline node initialised.')

    # ------------------------------------------------------------------
    # Start-up helpers
    # ------------------------------------------------------------------

    def _load_economics_config(self, config_path: str) -> dict[str, Any]:
        """Load economics YAML and return a flat parameter dict.

        Falls back to an empty dict (all defaults applied by YieldEconomics)
        if the file is absent or unparseable.

        Args:
            config_path: Path to economics.yaml, or empty string to use
                the package-default location.

        Returns:
            Flat dict of economic parameters.
        """
        if not config_path:
            # Attempt to locate the config relative to this file.
            candidate = os.path.join(
                os.path.dirname(__file__), '..', 'config', 'economics.yaml'
            )
            config_path = os.path.normpath(candidate)

        if not os.path.isfile(config_path):
            self.get_logger().warn(
                f'Economics config not found at {config_path!r}; using defaults.'
            )
            return {}

        try:
            import yaml  # type: ignore

            with open(config_path, 'r', encoding='utf-8') as fh:
                data = yaml.safe_load(fh)

            # Support nested ros__parameters structure.
            if isinstance(data, dict):
                nested = data.get('economics', data)
                if isinstance(nested, dict):
                    params = nested.get('ros__parameters', nested)
                    if isinstance(params, dict):
                        return params
            return {}
        except Exception as exc:  # noqa: BLE001
            self.get_logger().warn(f'Failed to load economics config: {exc}')
            return {}

    def _ensure_default_plants(self) -> None:
        """Create 4 default parsley plants if the plants table is empty."""
        conn = self._db._conn
        cursor = conn.execute('SELECT COUNT(*) FROM plants')
        count = cursor.fetchone()[0]
        if count > 0:
            return

        now = time.time()
        for position in range(4):
            plant_id = str(uuid.uuid4())
            self._db.insert_plant(
                plant_id=plant_id,
                position_index=position,
                plant_profile=self._DEFAULT_PROFILE,
                planted_date=now,
            )
        self.get_logger().info(
            'Auto-created 4 default parsley plant records (positions 0–3).'
        )

    # ------------------------------------------------------------------
    # Subscription callbacks
    # ------------------------------------------------------------------

    def _on_inspection_result(self, msg: InspectionResult) -> None:
        """Persist all per-plant inspections and publish GrowthDataPoint messages."""
        for plant_state in msg.plants:
            plant_id: str = plant_state.plant_id
            if not plant_id:
                continue

            ts = _ros_time_to_float(msg.header)
            inspection_id = str(uuid.uuid4())

            # Persist the inspection.
            self._db.insert_inspection(
                inspection_id=inspection_id,
                plant_id=plant_id,
                timestamp=ts,
                canopy_area_cm2=plant_state.canopy_area_cm2,
                height_cm=plant_state.height_cm,
                leaf_count=int(plant_state.leaf_count),
                health_class=plant_state.health_state,
                deficiency_type=None,  # not separately encoded in PlantPositionState
                maturity_state=plant_state.status,
                image_paths=[],
            )

            # Update the plant's current stage/status.
            self._db.update_plant_stage(
                plant_id=plant_id,
                stage=plant_state.status.lower(),
                status=plant_state.status,
            )

            # Compute growth rate and publish GrowthDataPoint.
            growth_rate = self._growth_analytics.compute_growth_rate(plant_id)

            gdp = GrowthDataPoint()
            gdp.header.stamp = msg.header.stamp
            gdp.plant_id = plant_id
            gdp.position_index = plant_state.position_index
            gdp.canopy_area_cm2 = plant_state.canopy_area_cm2
            gdp.height_cm = plant_state.height_cm
            gdp.leaf_count = plant_state.leaf_count
            gdp.growth_rate_cm2_per_day = growth_rate
            # Nutrient readings are not available in this message; leave at 0.
            gdp.ph_at_reading = 0.0
            gdp.ec_at_reading = 0.0
            gdp.temp_at_reading = 0.0

            self._pub_growth.publish(gdp)

        self.get_logger().debug(
            f'Processed InspectionResult with {len(msg.plants)} plants.'
        )

    def _on_harvest_result(self, msg: HarvestResult) -> None:
        """Persist a harvest event from the harvest action server."""
        if not msg.success:
            return

        # Resolve the plant_id for this position from the DB.
        plant_id = self._get_plant_id_for_position(int(msg.position_index))
        if plant_id is None:
            self.get_logger().warn(
                f'No plant found at position {msg.position_index} for harvest.'
            )
            return

        ts = _ros_time_to_float(msg.header)
        harvest_id = str(uuid.uuid4())

        # Determine cut cycle number from current DB record.
        cut_cycle = self._get_cut_cycle_number(plant_id)

        self._db.insert_harvest(
            harvest_id=harvest_id,
            plant_id=plant_id,
            timestamp=ts,
            harvest_type=msg.action_type,
            weight_grams=msg.weight_grams,
            cut_cycle_number=cut_cycle,
        )

        self.get_logger().info(
            f'Harvest stored: position={msg.position_index}, '
            f'type={msg.action_type}, weight={msg.weight_grams:.1f}g'
        )

    def _on_nutrient_status(self, msg: NutrientStatus) -> None:
        """Persist nutrient readings at 0.1 Hz (down-sampled)."""
        now = time.time()
        if now - self._last_nutrient_write < self._DOWNSAMPLE_INTERVAL:
            return

        self._last_nutrient_write = now
        ts = _ros_time_to_float(msg.header) or now

        self._db.insert_nutrient_reading(
            timestamp=ts,
            ph=msg.ph_current,
            ec=msg.ec_current,
            temperature_c=msg.temperature_c,
            growth_stage=msg.growth_stage,
            a_b_ratio=msg.a_b_ratio,
            ph_pid_output=msg.ph_pid_output,
            ec_pid_output=msg.ec_pid_output,
        )

    def _on_system_alert(self, msg: SystemAlert) -> None:
        """Persist a system alert to the system_events table."""
        ts = _ros_time_to_float(msg.header) or time.time()
        details = json.dumps({
            'message': msg.message,
            'recommended_action': msg.recommended_action,
        })
        self._db.insert_system_event(
            timestamp=ts,
            event_type=msg.alert_type,
            severity=msg.severity,
            details=details,
        )

    def _on_light_status(self, msg: LightStatus) -> None:
        """Persist light status readings at 0.1 Hz (down-sampled)."""
        now = time.time()
        if now - self._last_light_write < self._DOWNSAMPLE_INTERVAL:
            return

        self._last_light_write = now
        ts = _ros_time_to_float(msg.header) or now

        # Compute cumulative watt-hours from DB max + incremental energy.
        cumulative_wh = self._compute_cumulative_watt_hours(
            intensity_percent=msg.grow_intensity_percent,
            interval_s=self._DOWNSAMPLE_INTERVAL,
        )

        self._db.insert_light_reading(
            timestamp=ts,
            intensity_percent=msg.grow_intensity_percent,
            schedule_state=msg.schedule_state,
            cumulative_watt_hours=cumulative_wh,
        )

    # ------------------------------------------------------------------
    # Service handlers
    # ------------------------------------------------------------------

    def _handle_get_yield_analytics(
        self,
        _request: GetYieldAnalytics.Request,
        response: GetYieldAnalytics.Response,
    ) -> GetYieldAnalytics.Response:
        """Populate and return a GetYieldAnalytics response."""
        response.total_yield_grams = self._yield_economics.compute_total_yield()
        response.avg_yield_per_cut = self._yield_economics.compute_avg_yield_per_cut()
        response.yield_per_watt_hour = self._yield_economics.compute_yield_per_watt_hour()
        response.yield_per_liter = self._yield_economics.compute_yield_per_liter_nutrient()
        response.cost_per_gram = self._yield_economics.compute_cost_per_gram()
        response.total_crop_cycles = self._yield_economics.compute_total_crop_cycles()
        return response

    def _handle_get_plant_history(
        self,
        request: GetPlantHistory.Request,
        response: GetPlantHistory.Response,
    ) -> GetPlantHistory.Response:
        """Populate and return a GetPlantHistory response."""
        plant_id: str = request.plant_id

        # Growth history as GrowthDataPoint messages.
        curve = self._growth_analytics.compute_growth_curve(plant_id)
        gdp_list: list[GrowthDataPoint] = []
        for point in curve:
            gdp = GrowthDataPoint()
            gdp.plant_id = plant_id
            gdp.canopy_area_cm2 = float(point['canopy_area_cm2'] or 0.0)
            gdp.height_cm = float(point['height_cm'] or 0.0)
            gdp.leaf_count = int(point['leaf_count'] or 0)
            gdp_list.append(gdp)
        response.growth_history = gdp_list

        # Harvest weights.
        all_harvests = self._db.get_all_harvests()
        response.harvest_weights = [
            float(h['weight_grams']) for h in all_harvests if h['plant_id'] == plant_id
        ]

        # Total inspection count.
        inspections = self._db.get_plant_inspections(plant_id)
        response.total_inspections = len(inspections)

        return response

    # ------------------------------------------------------------------
    # Timer callbacks
    # ------------------------------------------------------------------

    def _publish_yield_metrics(self) -> None:
        """Compute yield metrics and publish to /yield_metrics."""
        total_yield = self._yield_economics.compute_total_yield()
        total_harvests = len(self._db.get_all_harvests())
        yield_per_wh = self._yield_economics.compute_yield_per_watt_hour()
        yield_per_liter = self._yield_economics.compute_yield_per_liter_nutrient()
        cost_per_gram = self._yield_economics.compute_cost_per_gram()
        total_cycles = self._yield_economics.compute_total_crop_cycles()

        msg = YieldMetrics()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.total_yield_grams = total_yield
        msg.yield_per_watt_hour = yield_per_wh
        msg.yield_per_liter_nutrient = yield_per_liter
        msg.cost_per_gram = cost_per_gram
        msg.total_harvests = total_harvests
        msg.total_crop_cycles = total_cycles

        self._pub_yield.publish(msg)

        # Update in-memory cache.
        self._yield_cache = {
            'total_yield_grams': total_yield,
            'total_harvests': total_harvests,
            'yield_per_watt_hour': yield_per_wh,
            'yield_per_liter_nutrient': yield_per_liter,
            'cost_per_gram': cost_per_gram,
            'total_crop_cycles': total_cycles,
            'last_updated': time.time(),
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_plant_id_for_position(self, position_index: int) -> str | None:
        """Return the plant_id of the active plant at the given position.

        Args:
            position_index: Channel position 0–3.

        Returns:
            UUID string or None if not found.
        """
        conn = self._db._conn
        sql = (
            'SELECT plant_id FROM plants '
            'WHERE position_index = ? '
            'ORDER BY planted_date DESC LIMIT 1'
        )
        cursor = conn.execute(sql, (position_index,))
        row = cursor.fetchone()
        return str(row[0]) if row else None

    def _get_cut_cycle_number(self, plant_id: str) -> int:
        """Return the current cut_cycle_number for the given plant.

        Args:
            plant_id: UUID of the plant.

        Returns:
            Cut cycle number, or 0 if the plant is not found.
        """
        conn = self._db._conn
        cursor = conn.execute(
            'SELECT cut_cycle_number FROM plants WHERE plant_id = ?', (plant_id,)
        )
        row = cursor.fetchone()
        return int(row[0]) if row else 0

    def _compute_cumulative_watt_hours(
        self, intensity_percent: float, interval_s: float
    ) -> float:
        """Return running cumulative watt-hours including the latest increment.

        Args:
            intensity_percent: Current grow-light intensity 0–100.
            interval_s: Seconds elapsed since the last reading was stored.

        Returns:
            Updated cumulative watt-hours value.
        """
        grow_light_watts: float = float(self._economics_cfg.get('grow_light_watts', 25.0))
        current_watts = grow_light_watts * (intensity_percent / 100.0)
        increment_wh = current_watts * (interval_s / 3600.0)

        # Fetch the last recorded cumulative value from the DB.
        conn = self._db._conn
        cursor = conn.execute(
            'SELECT COALESCE(MAX(cumulative_watt_hours), 0.0) FROM light_readings'
        )
        row = cursor.fetchone()
        previous_wh = float(row[0]) if row else 0.0

        return previous_wh + increment_wh

    def get_yield_cache(self) -> dict[str, Any]:
        """Return the most recently computed yield metrics cache.

        This provides a REST-queryable snapshot without hitting the DB.

        Returns:
            Dict with yield metric keys, or empty dict if not yet populated.
        """
        return dict(self._yield_cache)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ros_time_to_float(header: Header) -> float:
    """Convert a std_msgs/Header stamp to a Unix float timestamp.

    Args:
        header: ROS2 message header carrying a builtin_interfaces/Time stamp.

    Returns:
        Seconds since epoch as a float.  Returns current wall time if the
        stamp is zero (unset).
    """
    sec: int = header.stamp.sec
    nanosec: int = header.stamp.nanosec
    if sec == 0 and nanosec == 0:
        return time.time()
    return float(sec) + float(nanosec) * 1e-9


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(args: list[str] | None = None) -> None:
    """Initialise rclpy and spin the DataPipeline node."""
    rclpy.init(args=args)
    node = DataPipeline()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node._db.close()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
