"""启动 WindArmor 双涵道风扇控制节点。"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    params_file = LaunchConfiguration("params_file")
    require_motor_mode_for_manual = LaunchConfiguration(
        "require_motor_mode_for_manual"
    )
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
            DeclareLaunchArgument(
                "require_motor_mode_for_manual",
                default_value="false",
                description="手动风扇是否要求新鲜且允许的电机模式",
            ),
            Node(
                package="windarmor_fan_controller",
                executable="fan_command_manager",
                name="fan_command_manager",
                parameters=[
                    params_file,
                    {
                        "require_motor_mode_for_manual":
                            require_motor_mode_for_manual,
                    },
                ],
                output="screen",
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
