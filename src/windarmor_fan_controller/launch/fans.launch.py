"""启动 WindArmor 双涵道风扇控制节点。"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    params_file = LaunchConfiguration("params_file")
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "params_file",
                default_value=PathJoinSubstitution(
                    [
                        FindPackageShare("windarmor_fan_controller"),
                        "config",
                        "fan_params.yaml",
                    ]
                ),
            ),
            Node(
                package="windarmor_fan_controller",
                executable="fan_controller",
                name="fan_controller",
                parameters=[params_file],
                output="screen",
            ),
        ]
    )
