"""WindArmor 的 IMU、四电机与双风扇统一启动文件。"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    motor_params_file = LaunchConfiguration("motor_params_file")
    fan_params_file = LaunchConfiguration("fan_params_file")
    start_controller = LaunchConfiguration("start_controller")
    start_fans = LaunchConfiguration("start_fans")
    enable_motor_keyboard = LaunchConfiguration("enable_motor_keyboard")
    control_backend = LaunchConfiguration("control_backend")
    can_channel = LaunchConfiguration("can_channel")

    imu_and_motors = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution(
                [
                    FindPackageShare("imu_cybergear_ros2"),
                    "launch",
                    "imu_cybergear_system.launch.py",
                ]
            )
        ),
        launch_arguments={
            "params_file": motor_params_file,
            "start_controller": start_controller,
            "enable_keyboard": enable_motor_keyboard,
            "control_backend": control_backend,
            "can_channel": can_channel,
            "can_bustype": "socketcan",
            "start_rviz": "false",
        }.items(),
    )

    fan_system = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            PathJoinSubstitution(
                [
                    FindPackageShare("windarmor_fan_controller"),
                    "launch",
                    "fans.launch.py",
                ]
            )
        ),
        launch_arguments={
            "params_file": fan_params_file,
            "require_motor_mode_for_manual": "true",
        }.items(),
        condition=IfCondition(start_fans),
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "motor_params_file",
                default_value=PathJoinSubstitution(
                    [
                        FindPackageShare("imu_cybergear_ros2"),
                        "config",
                        "imu_cybergear_params.yaml",
                    ]
                ),
                description="IMU 与四电机参数文件",
            ),
            DeclareLaunchArgument(
                "fan_params_file",
                default_value=PathJoinSubstitution(
                    [
                        FindPackageShare("windarmor_fan_controller"),
                        "config",
                        "fan_params.yaml",
                    ]
                ),
                description="双风扇参数文件",
            ),
            DeclareLaunchArgument(
                "start_controller",
                default_value="true",
                description="是否启动四电机控制器",
            ),
            DeclareLaunchArgument(
                "start_fans",
                default_value="true",
                description="是否启动双风扇 GPIO 控制器",
            ),
            DeclareLaunchArgument(
                "enable_motor_keyboard",
                default_value="true",
                description="是否在当前终端启用电机键盘控制",
            ),
            DeclareLaunchArgument(
                "control_backend",
                default_value="socketcan_hat",
                description="电机通信后端",
            ),
            DeclareLaunchArgument(
                "can_channel",
                default_value="can10",
                description="微雪 CAN HAT+ 的 SocketCAN 通道",
            ),
            imu_and_motors,
            fan_system,
        ]
    )
