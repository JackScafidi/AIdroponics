# MIT License
# transport_test.launch.py — Isolated launch for rail transport testing.
# Launches only the micro-ROS bridge and transport controller so the
# rail stepper can be exercised without the full system.

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description() -> LaunchDescription:
    # ---------------------------------------------------------------------------
    # Launch arguments
    # ---------------------------------------------------------------------------
    homing_arg = DeclareLaunchArgument(
        'homing_on_start',
        default_value='true',
        description='Run homing sequence on startup (true/false).',
    )

    homing_on_start = LaunchConfiguration('homing_on_start')

    # ---------------------------------------------------------------------------
    # Package paths
    # ---------------------------------------------------------------------------
    transport_share  = FindPackageShare('hydroponics_transport')
    micro_ros_share  = FindPackageShare('hydroponics_micro_ros_bridge')
    bringup_share    = FindPackageShare('hydroponics_bringup')

    transport_params = PathJoinSubstitution([transport_share, 'config', 'transport_params.yaml'])
    system_config    = PathJoinSubstitution([bringup_share, 'config', 'system_config.yaml'])

    # ---------------------------------------------------------------------------
    # Nodes
    # ---------------------------------------------------------------------------
    return LaunchDescription([
        homing_arg,

        LogInfo(msg='[transport_test] Starting transport controller in isolation.'),
        LogInfo(msg='[transport_test] Test with:'),
        LogInfo(msg='  ros2 action send_goal /transport_to hydroponics_msgs/action/TransportTo "{target_position: INSPECT}"'),
        LogInfo(msg='  ros2 topic echo /hydroponics/transport_status'),

        # micro-ROS bridge must be running first for stepper commands
        Node(
            package='hydroponics_micro_ros_bridge',
            executable='micro_ros_bridge',
            name='micro_ros_bridge',
            output='screen',
            parameters=[system_config],
        ),

        # Transport controller
        Node(
            package='hydroponics_transport',
            executable='transport_controller',
            name='transport_controller',
            output='screen',
            parameters=[
                transport_params,
                system_config,
                {'homing_on_start': homing_on_start},
            ],
        ),
    ])
