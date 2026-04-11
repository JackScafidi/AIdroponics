# MIT License
# Copyright (c) 2026 AIdroponics Project
#
# V0.1 single-plant launch file.
# Brings up all nodes for the minimal single-plant analysis platform:
#   - probe_arm_node       (servo probe cycle)
#   - aeration_node        (airstone cycle)
#   - plant_vision_node    (dual CSI camera + NDVI + AprilTag + segmentation)
#   - water_level_node     (ultrasonic sensor + auto top-off)
#   - dosing_node          (pH + A/B EC auto-dosing with safety scaffolding)
#   - plant_health_analyzer_node (YAML rule engine diagnostics)
#   - led_status_node      (GPIO RGB LED status indicator)
#   - micro_ros_bridge     (ESP32 serial link)
#   - light_controller     (grow light schedule)
#   - data_pipeline        (SQLite logging)
#   - mqtt_bridge          (cloud telemetry)
#   - dashboard            (FastAPI web UI)
#
# Usage:
#   ros2 launch hydroponics_bringup v01_single_plant.launch.py plant_type:=basil

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare

import os
import yaml


def _load_plant_library(plant_type: str) -> dict:
    """Load plant thresholds from plant_library.yaml for the given plant type."""
    bringup_share = os.path.join(
        os.path.dirname(__file__), '..', 'config', 'plant_library.yaml'
    )
    try:
        with open(os.path.abspath(bringup_share), 'r') as f:
            lib = yaml.safe_load(f)
        return lib.get('plants', {}).get(plant_type, {})
    except Exception:
        return {}


def generate_launch_description() -> LaunchDescription:
    # ---------------------------------------------------------------------------
    # Launch arguments
    # ---------------------------------------------------------------------------
    plant_type_arg = DeclareLaunchArgument(
        'plant_type',
        default_value='basil',
        description='Active plant type (basil, mint, parsley, rosemary). '
                    'Must match a key in plant_library.yaml.',
    )

    plant_type = LaunchConfiguration('plant_type')

    # ---------------------------------------------------------------------------
    # Package share paths
    # ---------------------------------------------------------------------------
    bringup_share = FindPackageShare('hydroponics_bringup')
    probe_share = FindPackageShare('hydroponics_probe')
    vision_share = FindPackageShare('hydroponics_vision')
    water_share = FindPackageShare('hydroponics_water')
    dosing_share = FindPackageShare('hydroponics_dosing')
    diagnostics_share = FindPackageShare('hydroponics_diagnostics')
    led_share = FindPackageShare('hydroponics_led')
    micro_ros_share = FindPackageShare('hydroponics_micro_ros_bridge')
    lighting_share = FindPackageShare('hydroponics_lighting')
    data_share = FindPackageShare('hydroponics_data')
    mqtt_share = FindPackageShare('hydroponics_mqtt')
    dashboard_share = FindPackageShare('hydroponics_dashboard')

    # ---------------------------------------------------------------------------
    # Config paths
    # ---------------------------------------------------------------------------
    v01_config = PathJoinSubstitution([bringup_share, 'config', 'v01_system.yaml'])
    plant_lib = PathJoinSubstitution([bringup_share, 'config', 'plant_library.yaml'])
    diagnostic_rules = PathJoinSubstitution([bringup_share, 'config', 'diagnostic_rules.yaml'])
    economics_config = PathJoinSubstitution([data_share, 'config', 'economics.yaml'])
    mqtt_config = PathJoinSubstitution([mqtt_share, 'config', 'mqtt_config.yaml'])

    # ---------------------------------------------------------------------------
    # Nodes
    # ---------------------------------------------------------------------------

    # 1. micro-ROS bridge (C++ — ESP32 serial link)
    micro_ros_bridge = Node(
        package='hydroponics_micro_ros_bridge',
        executable='micro_ros_bridge',
        name='micro_ros_bridge',
        output='screen',
        parameters=[v01_config],
    )

    # 2. Probe arm node (Python — servo probe cycle with /probe/set_interval)
    probe_arm_node = Node(
        package='hydroponics_probe',
        executable='probe_arm_node',
        name='probe_arm_node',
        output='screen',
        parameters=[v01_config],
    )

    # 3. Aeration node (Python — airstone servo + air pump cycle)
    aeration_node = Node(
        package='hydroponics_probe',
        executable='aeration_node',
        name='aeration_node',
        output='screen',
        parameters=[v01_config],
    )

    # 4. Plant vision node (Python — RGB + NoIR dual camera, NDVI, AprilTag, segmentation)
    plant_vision_node = Node(
        package='hydroponics_vision',
        executable='plant_vision_node',
        name='plant_vision_node',
        output='screen',
        parameters=[
            v01_config,
            {'plant_type': plant_type},
        ],
    )

    # 5. Water level node (Python — ultrasonic sensor + auto top-off + CSV log)
    water_level_node = Node(
        package='hydroponics_water',
        executable='water_level_node',
        name='water_level_node',
        output='screen',
        parameters=[v01_config],
    )

    # 6. Dosing node (Python — explicit pH + A/B EC dosing with safety scaffolding)
    dosing_node = Node(
        package='hydroponics_dosing',
        executable='dosing_node',
        name='dosing_node',
        output='screen',
        parameters=[
            v01_config,
            # Plant-specific thresholds injected as flat parameters
            # (launch-time resolved from plant_library.yaml)
            {'plant_type': plant_type},
        ],
    )

    # 7. Plant health analyzer node (Python — YAML rule engine diagnostics)
    plant_health_analyzer_node = Node(
        package='hydroponics_diagnostics',
        executable='plant_health_analyzer_node',
        name='plant_health_analyzer_node',
        output='screen',
        parameters=[
            v01_config,
            {'rules_config_path': diagnostic_rules},
            {'plant_type': plant_type},
        ],
    )

    # 8. LED status node (Python — GPIO RGB LED)
    led_status_node = Node(
        package='hydroponics_led',
        executable='led_status_node',
        name='led_status_node',
        output='screen',
        parameters=[v01_config],
    )

    # 9. Light controller (Python — grow light schedule)
    light_controller = Node(
        package='hydroponics_lighting',
        executable='light_controller',
        name='light_controller',
        output='screen',
        parameters=[v01_config],
    )

    # 10. Data pipeline (Python — SQLite storage + analytics)
    data_pipeline = Node(
        package='hydroponics_data',
        executable='data_pipeline',
        name='data_pipeline',
        output='screen',
        parameters=[economics_config, v01_config],
    )

    # 11. MQTT bridge (Python — cloud telemetry)
    mqtt_bridge = Node(
        package='hydroponics_mqtt',
        executable='mqtt_bridge',
        name='mqtt_bridge',
        output='screen',
        parameters=[mqtt_config, v01_config],
    )

    # 12. Dashboard (Python — FastAPI web UI)
    dashboard = Node(
        package='hydroponics_dashboard',
        executable='dashboard',
        name='dashboard',
        output='screen',
        parameters=[v01_config],
    )

    return LaunchDescription([
        plant_type_arg,
        micro_ros_bridge,
        probe_arm_node,
        aeration_node,
        plant_vision_node,
        water_level_node,
        dosing_node,
        plant_health_analyzer_node,
        led_status_node,
        light_controller,
        data_pipeline,
        mqtt_bridge,
        dashboard,
    ])
