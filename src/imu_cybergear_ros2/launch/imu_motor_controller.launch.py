"""单独启动控制器节点的 launch 文件（自动 configure → activate）。

用于双终端模式的终端 B，一条命令完成启动和生命周期转换。
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, EmitEvent, RegisterEventHandler
from launch.event_handlers import OnProcessStart
from launch.events import matches_action
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import LifecycleNode
from launch_ros.event_handlers import OnStateTransition
from launch_ros.events.lifecycle import ChangeState
from launch_ros.substitutions import FindPackageShare
from lifecycle_msgs.msg import Transition


def generate_launch_description():
    params_file = LaunchConfiguration("params_file")
    enable_keyboard = LaunchConfiguration("enable_keyboard")
    control_backend = LaunchConfiguration("control_backend")
    can_channel = LaunchConfiguration("can_channel")
    can_bustype = LaunchConfiguration("can_bustype")

    controller_node = LifecycleNode(
        package="imu_cybergear_ros2",
        executable="imu_motor_controller_node",
        name="imu_motor_controller_node",
        namespace="",
        parameters=[
            params_file,
            {
                "enable_keyboard": enable_keyboard,
                "control_backend": control_backend,
                "can_channel": can_channel,
                "can_bustype": can_bustype,
            },
        ],
        output="screen",
    )

    # 启动后自动 configure
    configure_handler = RegisterEventHandler(
        event_handler=OnProcessStart(
            target_action=controller_node,
            on_start=[
                EmitEvent(
                    event=ChangeState(
                        lifecycle_node_matcher=matches_action(controller_node),
                        transition_id=Transition.TRANSITION_CONFIGURE,
                    ),
                ),
            ],
        ),
    )

    # configure 完成后自动 activate
    activate_handler = RegisterEventHandler(
        event_handler=OnStateTransition(
            target_lifecycle_node=controller_node,
            goal_state="inactive",
            entities=[
                EmitEvent(
                    event=ChangeState(
                        lifecycle_node_matcher=matches_action(controller_node),
                        transition_id=Transition.TRANSITION_ACTIVATE,
                    ),
                ),
            ],
        ),
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "params_file",
                default_value=PathJoinSubstitution(
                    [FindPackageShare("imu_cybergear_ros2"), "config", "imu_cybergear_params.yaml"]
                ),
            ),
            DeclareLaunchArgument("enable_keyboard", default_value="true"),
            DeclareLaunchArgument("control_backend", default_value="socketcan_hat"),
            DeclareLaunchArgument("can_channel", default_value="can10"),
            DeclareLaunchArgument("can_bustype", default_value="socketcan"),
            configure_handler,
            activate_handler,
            controller_node,
        ]
    )
