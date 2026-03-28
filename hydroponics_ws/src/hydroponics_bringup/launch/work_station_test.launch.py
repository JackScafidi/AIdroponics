# MIT License
# work_station_test.launch.py — Isolated launch for Z-axis and tool testing.
# Starts only the work station controller and micro-ROS bridge.

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description() -> LaunchDescription:
    # ---------------------------------------------------------------------------
    # Launch arguments
    # ---------------------------------------------------------------------------
    tool_arg = DeclareLaunchArgument(
        'tool',
        default_value='cutter',
        description='Initial tool to select on startup: cutter or gripper.',
        choices=['cutter', 'gripper'],
    )

    tool = LaunchConfiguration('tool')

    # ---------------------------------------------------------------------------
    # Package paths
    # ---------------------------------------------------------------------------
    work_station_share = FindPackageShare('hydroponics_work_station')
    bringup_share      = FindPackageShare('hydroponics_bringup')

    work_station_params = PathJoinSubstitution(
        [work_station_share, 'config', 'work_station_params.yaml'])
    system_config = PathJoinSubstitution([bringup_share, 'config', 'system_config.yaml'])

    # ---------------------------------------------------------------------------
    # Nodes
    # ---------------------------------------------------------------------------
    return LaunchDescription([
        tool_arg,

        LogInfo(msg='[work_station_test] Starting work station controller in isolation.'),
        LogInfo(msg='[work_station_test] Test with:'),
        LogInfo(msg='  ros2 action send_goal /work_station/move_z hydroponics_msgs/action/MoveZ "{height_mm: 100.0}"'),
        LogInfo(msg='  ros2 service call /work_station/get_status hydroponics_msgs/srv/GetWorkStationStatus {}'),

        # micro-ROS bridge (for Z stepper + servo commands)
        Node(
            package='hydroponics_micro_ros_bridge',
            executable='micro_ros_bridge',
            name='micro_ros_bridge',
            output='screen',
            parameters=[system_config],
        ),

        # Work station controller
        Node(
            package='hydroponics_work_station',
            executable='work_station_controller',
            name='work_station_controller',
            output='screen',
            parameters=[
                work_station_params,
                system_config,
                {'initial_tool': tool},
            ],
        ),
    ])
