# MIT License
# simulation.launch.py — Launch the full Claudroponics system in simulation mode.
# No real hardware required. Uses mock nodes in place of the ESP32 bridge and cameras.

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, GroupAction, LogInfo
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
        description='Plant profile (parsley, basil, mint, cilantro).',
    )
    log_level_arg = DeclareLaunchArgument(
        'log_level',
        default_value='debug',
        description='ROS2 log level for all nodes (debug, info, warn, error).',
    )

    plant_profile   = LaunchConfiguration('plant_profile')
    log_level       = LaunchConfiguration('log_level')

    # ---------------------------------------------------------------------------
    # Package share paths
    # ---------------------------------------------------------------------------
    bringup_share   = FindPackageShare('hydroponics_bringup')
    vision_share    = FindPackageShare('hydroponics_vision')
    nutrients_share = FindPackageShare('hydroponics_nutrients')
    data_share      = FindPackageShare('hydroponics_data')
    mqtt_share      = FindPackageShare('hydroponics_mqtt')
    bt_share        = FindPackageShare('hydroponics_bt')

    # ---------------------------------------------------------------------------
    # Config file paths
    # ---------------------------------------------------------------------------
    system_config       = PathJoinSubstitution([bringup_share, 'config', 'system_config.yaml'])
    plant_profile_config = PathJoinSubstitution([
        bringup_share, 'config', 'plant_profiles',
        [plant_profile, '.yaml'],
    ])
    vision_params   = PathJoinSubstitution([vision_share,    'config', 'vision_params.yaml'])
    pid_params      = PathJoinSubstitution([nutrients_share, 'config', 'pid_params.yaml'])
    economics_config = PathJoinSubstitution([data_share,     'config', 'economics.yaml'])
    mqtt_config     = PathJoinSubstitution([mqtt_share,      'config', 'mqtt_config.yaml'])

    sim_params = {'use_sim': True}

    # ---------------------------------------------------------------------------
    # Nodes
    # ---------------------------------------------------------------------------
    nodes = GroupAction([

        LogInfo(msg='[simulation] Starting Claudroponics in SIMULATION mode — no hardware required'),

        # Mock ESP32 — simulates sensor readings and hardware responses
        Node(
            package='hydroponics_mocks',
            executable='mock_esp32',
            name='mock_esp32',
            output='screen',
            arguments=['--ros-args', '--log-level', log_level],
            parameters=[sim_params],
        ),

        # Mock cameras — generates synthetic inspection images
        Node(
            package='hydroponics_mocks',
            executable='mock_cameras',
            name='mock_cameras',
            output='screen',
            arguments=['--ros-args', '--log-level', log_level],
            parameters=[sim_params],
        ),

        # Vision node (Python — YOLOv8; uses mock camera images in sim)
        Node(
            package='hydroponics_vision',
            executable='vision_node',
            name='vision_node',
            output='screen',
            arguments=['--ros-args', '--log-level', log_level],
            parameters=[vision_params, system_config, sim_params],
        ),

        # Nutrient controller
        Node(
            package='hydroponics_nutrients',
            executable='nutrient_controller',
            name='nutrient_controller',
            output='screen',
            arguments=['--ros-args', '--log-level', log_level],
            parameters=[pid_params, system_config, plant_profile_config, sim_params],
        ),

        # Light controller
        Node(
            package='hydroponics_lighting',
            executable='light_controller',
            name='light_controller',
            output='screen',
            arguments=['--ros-args', '--log-level', log_level],
            parameters=[system_config, plant_profile_config, sim_params],
        ),

        # Harvest manager
        Node(
            package='hydroponics_harvest',
            executable='harvest_manager',
            name='harvest_manager',
            output='screen',
            arguments=['--ros-args', '--log-level', log_level],
            parameters=[system_config, plant_profile_config, sim_params],
        ),

        # Data pipeline
        Node(
            package='hydroponics_data',
            executable='data_pipeline',
            name='data_pipeline',
            output='screen',
            arguments=['--ros-args', '--log-level', log_level],
            parameters=[economics_config, system_config, sim_params],
        ),

        # MQTT bridge (will not actually connect unless broker_url is set)
        Node(
            package='hydroponics_mqtt',
            executable='mqtt_bridge',
            name='mqtt_bridge',
            output='screen',
            arguments=['--ros-args', '--log-level', log_level],
            parameters=[mqtt_config, system_config, sim_params],
        ),

        # Dashboard
        Node(
            package='hydroponics_dashboard',
            executable='dashboard',
            name='dashboard',
            output='screen',
            arguments=['--ros-args', '--log-level', log_level],
            parameters=[system_config, sim_params],
        ),

        # BT manager (orchestrator — drives the full inspection/harvest cycle)
        Node(
            package='hydroponics_bt',
            executable='bt_manager',
            name='bt_manager',
            output='screen',
            arguments=['--ros-args', '--log-level', log_level],
            parameters=[system_config, plant_profile_config, sim_params],
        ),

    ])

    return LaunchDescription([
        plant_profile_arg,
        log_level_arg,
        nodes,
    ])
