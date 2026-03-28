# MIT License
# Full system launch file for the Claudroponics autonomous hydroponics system.
# Launches all 11 nodes with parameters loaded from shared config YAML files.

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, GroupAction
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description() -> LaunchDescription:
    # ---------------------------------------------------------------------------
    # Launch arguments
    # ---------------------------------------------------------------------------
    plant_profile_arg = DeclareLaunchArgument(
        'plant_profile',
        default_value='parsley',
        description='Plant profile name (parsley, basil, mint, cilantro). '
                    'Must match a YAML file in hydroponics_bringup/config/plant_profiles/.',
    )

    # ---------------------------------------------------------------------------
    # Package share paths
    # ---------------------------------------------------------------------------
    bringup_share = FindPackageShare('hydroponics_bringup')
    transport_share = FindPackageShare('hydroponics_transport')
    work_station_share = FindPackageShare('hydroponics_work_station')
    vision_share = FindPackageShare('hydroponics_vision')
    nutrients_share = FindPackageShare('hydroponics_nutrients')
    lighting_share = FindPackageShare('hydroponics_lighting')
    harvest_share = FindPackageShare('hydroponics_harvest')
    data_share = FindPackageShare('hydroponics_data')
    bt_share = FindPackageShare('hydroponics_bt')
    mqtt_share = FindPackageShare('hydroponics_mqtt')
    dashboard_share = FindPackageShare('hydroponics_dashboard')
    micro_ros_share = FindPackageShare('hydroponics_micro_ros_bridge')

    # ---------------------------------------------------------------------------
    # Config file paths
    # ---------------------------------------------------------------------------
    system_config = PathJoinSubstitution([bringup_share, 'config', 'system_config.yaml'])
    plant_profile_config = PathJoinSubstitution([
        bringup_share, 'config', 'plant_profiles',
        [LaunchConfiguration('plant_profile'), '.yaml'],
    ])
    transport_params = PathJoinSubstitution([transport_share, 'config', 'transport_params.yaml'])
    work_station_params = PathJoinSubstitution([work_station_share, 'config', 'work_station_params.yaml'])
    vision_params = PathJoinSubstitution([vision_share, 'config', 'vision_params.yaml'])
    pid_params = PathJoinSubstitution([nutrients_share, 'config', 'pid_params.yaml'])
    mqtt_config = PathJoinSubstitution([mqtt_share, 'config', 'mqtt_config.yaml'])
    economics_config = PathJoinSubstitution([data_share, 'config', 'economics.yaml'])

    # ---------------------------------------------------------------------------
    # Nodes
    # ---------------------------------------------------------------------------
    nodes = GroupAction([

        # 1. micro-ROS bridge (C++ — manages serial link to ESP32)
        Node(
            package='hydroponics_micro_ros_bridge',
            executable='micro_ros_bridge',
            name='micro_ros_bridge',
            output='screen',
            parameters=[system_config],
        ),

        # 2. Transport controller (C++ — rail stepper)
        Node(
            package='hydroponics_transport',
            executable='transport_controller',
            name='transport_controller',
            output='screen',
            parameters=[transport_params, system_config],
        ),

        # 3. Work-station controller (C++ — Z-axis + turret + tools)
        Node(
            package='hydroponics_work_station',
            executable='work_station_controller',
            name='work_station_controller',
            output='screen',
            parameters=[work_station_params, system_config],
        ),

        # 4. Vision node (Python — dual-camera capture + YOLOv8)
        Node(
            package='hydroponics_vision',
            executable='vision_node',
            name='vision_node',
            output='screen',
            parameters=[vision_params, system_config],
        ),

        # 5. Nutrient controller (Python — pH/EC PID)
        Node(
            package='hydroponics_nutrients',
            executable='nutrient_controller',
            name='nutrient_controller',
            output='screen',
            parameters=[pid_params, system_config, plant_profile_config],
        ),

        # 6. Light controller (Python — grow panel + schedule)
        Node(
            package='hydroponics_lighting',
            executable='light_controller',
            name='light_controller',
            output='screen',
            parameters=[system_config, plant_profile_config],
        ),

        # 7. Harvest manager (Python — cut-and-regrow cycle tracking)
        Node(
            package='hydroponics_harvest',
            executable='harvest_manager',
            name='harvest_manager',
            output='screen',
            parameters=[system_config, plant_profile_config],
        ),

        # 8. Data pipeline (Python — SQLite storage + analytics)
        Node(
            package='hydroponics_data',
            executable='data_pipeline',
            name='data_pipeline',
            output='screen',
            parameters=[economics_config, system_config],
        ),

        # 9. Behavior tree manager (C++ — orchestrates all operations)
        Node(
            package='hydroponics_bt',
            executable='bt_manager',
            name='bt_manager',
            output='screen',
            parameters=[system_config, plant_profile_config],
        ),

        # 10. MQTT bridge (Python — cloud telemetry + HA discovery)
        Node(
            package='hydroponics_mqtt',
            executable='mqtt_bridge',
            name='mqtt_bridge',
            output='screen',
            parameters=[mqtt_config, system_config],
        ),

        # 11. Dashboard (Python — FastAPI web UI)
        Node(
            package='hydroponics_dashboard',
            executable='dashboard',
            name='dashboard',
            output='screen',
            parameters=[system_config],
        ),

    ])

    return LaunchDescription([
        plant_profile_arg,
        nodes,
    ])
