# MIT License
# vision_test.launch.py — Isolated launch for camera capture + YOLO inference testing.
# Launches the vision node, light controller, and micro-ROS bridge only.

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description() -> LaunchDescription:
    # ---------------------------------------------------------------------------
    # Launch arguments
    # ---------------------------------------------------------------------------
    save_images_arg = DeclareLaunchArgument(
        'save_images',
        default_value='false',
        description='Save captured inspection images to disk (true/false).',
    )
    model_path_arg = DeclareLaunchArgument(
        'model_path',
        default_value='',
        description='Path to custom YOLOv8 .pt weights file. '
                    'Empty = use default yolov8n.pt (downloaded automatically).',
    )

    save_images = LaunchConfiguration('save_images')
    model_path  = LaunchConfiguration('model_path')

    # ---------------------------------------------------------------------------
    # Package paths
    # ---------------------------------------------------------------------------
    vision_share    = FindPackageShare('hydroponics_vision')
    bringup_share   = FindPackageShare('hydroponics_bringup')

    vision_params   = PathJoinSubstitution([vision_share, 'config', 'vision_params.yaml'])
    system_config   = PathJoinSubstitution([bringup_share, 'config', 'system_config.yaml'])

    # ---------------------------------------------------------------------------
    # Nodes
    # ---------------------------------------------------------------------------
    return LaunchDescription([
        save_images_arg,
        model_path_arg,

        LogInfo(msg='[vision_test] Starting vision pipeline in isolation.'),
        LogInfo(msg='[vision_test] Trigger inspection with:'),
        LogInfo(msg='  ros2 service call /trigger_inspection hydroponics_msgs/srv/TriggerInspection {}'),
        LogInfo(msg='[vision_test] Monitor results with:'),
        LogInfo(msg='  ros2 topic echo /hydroponics/inspection_result'),

        # micro-ROS bridge (needed for inspection LED control)
        Node(
            package='hydroponics_micro_ros_bridge',
            executable='micro_ros_bridge',
            name='micro_ros_bridge',
            output='screen',
            parameters=[system_config],
        ),

        # Light controller (manages inspection LEDs)
        Node(
            package='hydroponics_lighting',
            executable='light_controller',
            name='light_controller',
            output='screen',
            parameters=[system_config],
        ),

        # Vision node
        Node(
            package='hydroponics_vision',
            executable='vision_node',
            name='vision_node',
            output='screen',
            parameters=[
                vision_params,
                system_config,
                {
                    'save_inspection_images': save_images,
                    'model_path': model_path,
                },
            ],
        ),
    ])
