"""Start only the observation-only Flight Runtime."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description() -> LaunchDescription:
    params_file = LaunchConfiguration("params_file")
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "params_file",
                default_value=PathJoinSubstitution(
                    [
                        FindPackageShare("windarmor_flight_control"),
                        "config",
                        "flight_control.yaml",
                    ]
                ),
            ),
            Node(
                package="windarmor_flight_control",
                executable="flight_control_runtime_node",
                name="flight_control_runtime_node",
                parameters=[params_file],
                output="screen",
            ),
        ]
    )
