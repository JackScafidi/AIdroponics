# MIT License
# nutrient_test.launch.py — Isolated launch for nutrient PID controller testing.
# Starts the nutrient controller, micro-ROS bridge, and data pipeline only.

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo
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
        description='Plant profile to load (parsley, basil, mint, cilantro).',
    )
    dry_run_arg = DeclareLaunchArgument(
        'dry_run',
        default_value='false',
        description='Dry-run mode: read sensors and compute PID output but do not '
                    'actuate pumps. Useful for verifying sensor calibration.',
    )

    plant_profile = LaunchConfiguration('plant_profile')
    dry_run       = LaunchConfiguration('dry_run')

    # ---------------------------------------------------------------------------
    # Package paths
    # ---------------------------------------------------------------------------
    bringup_share   = FindPackageShare('hydroponics_bringup')
    nutrients_share = FindPackageShare('hydroponics_nutrients')
    data_share      = FindPackageShare('hydroponics_data')

    system_config       = PathJoinSubstitution([bringup_share, 'config', 'system_config.yaml'])
    plant_profile_config = PathJoinSubstitution([
        bringup_share, 'config', 'plant_profiles',
        [plant_profile, '.yaml'],
    ])
    pid_params       = PathJoinSubstitution([nutrients_share, 'config', 'pid_params.yaml'])
    economics_config = PathJoinSubstitution([data_share, 'config', 'economics.yaml'])

    # ---------------------------------------------------------------------------
    # Nodes
    # ---------------------------------------------------------------------------
    return LaunchDescription([
        plant_profile_arg,
        dry_run_arg,

        LogInfo(msg='[nutrient_test] Starting nutrient controller in isolation.'),
        LogInfo(msg='[nutrient_test] Monitor with:'),
        LogInfo(msg='  ros2 topic echo /hydroponics/nutrient_status'),
        LogInfo(msg='[nutrient_test] Force dose (requires dry_run:=false):'),
        LogInfo(msg='  ros2 service call /force_dose hydroponics_msgs/srv/ForceDose '
                    '"{pump_id: ph_up, amount_ml: 1.0}"'),

        # micro-ROS bridge (sensor readings + pump commands to ESP32)
        Node(
            package='hydroponics_micro_ros_bridge',
            executable='micro_ros_bridge',
            name='micro_ros_bridge',
            output='screen',
            parameters=[system_config],
        ),

        # Nutrient controller
        Node(
            package='hydroponics_nutrients',
            executable='nutrient_controller',
            name='nutrient_controller',
            output='screen',
            parameters=[
                pid_params,
                system_config,
                plant_profile_config,
                {'disable_dosing': dry_run},
            ],
        ),

        # Data pipeline (records nutrient readings)
        Node(
            package='hydroponics_data',
            executable='data_pipeline',
            name='data_pipeline',
            output='screen',
            parameters=[economics_config, system_config],
        ),
    ])
