"""IMU + CyberGear 电机控制系统 launch 文件。

启动 imu_driver_node 和 imu_motor_controller_node 两个 LifecycleNode，
默认自动执行 configure → activate 生命周期转换；受控维护模式可以只自动 configure。

可通过 launch 参数控制是否启动控制器节点、选择 CAN 后端等。
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, EmitEvent, RegisterEventHandler
from launch.conditions import IfCondition
from launch.event_handlers import OnProcessExit, OnProcessStart
from launch.events import Shutdown, matches_action
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import LifecycleNode
from launch_ros.event_handlers import OnStateTransition
from launch_ros.events.lifecycle import ChangeState
from launch_ros.substitutions import FindPackageShare
from lifecycle_msgs.msg import Transition


def generate_launch_description():
    params_file = LaunchConfiguration("params_file")
    start_controller = LaunchConfiguration("start_controller")
    start_rviz = LaunchConfiguration("start_rviz")
    enable_keyboard = LaunchConfiguration("enable_keyboard")
    control_backend = LaunchConfiguration("control_backend")
    can_channel = LaunchConfiguration("can_channel")
    can_bustype = LaunchConfiguration("can_bustype")
    imu_auto_activate = LaunchConfiguration("imu_auto_activate")

    # ---- IMU 驱动节点（LifecycleNode） ----
    imu_node = LifecycleNode(
        package="imu_cybergear_ros2",
        executable="imu_driver_node",
        name="imu_driver_node",
        namespace="",
        parameters=[params_file],
        output="screen",
    )

    # IMU 节点启动后自动 configure
    imu_configure_handler = RegisterEventHandler(
        event_handler=OnProcessStart(
            target_action=imu_node,
            on_start=[
                EmitEvent(
                    event=ChangeState(
                        lifecycle_node_matcher=matches_action(imu_node),
                        transition_id=Transition.TRANSITION_CONFIGURE,
                    ),
                ),
            ],
        ),
    )

    # IMU 节点 configure 完成后自动 activate
    imu_activate_handler = RegisterEventHandler(
        event_handler=OnStateTransition(
            target_lifecycle_node=imu_node,
            goal_state="inactive",
            entities=[
                EmitEvent(
                    event=ChangeState(
                        lifecycle_node_matcher=matches_action(imu_node),
                        transition_id=Transition.TRANSITION_ACTIVATE,
                    ),
                ),
            ],
        ),
        condition=IfCondition(imu_auto_activate),
    )

    # ---- 电机控制节点（LifecycleNode） ----
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
        condition=IfCondition(start_controller),
    )

    # 控制节点启动后自动 configure
    controller_configure_handler = RegisterEventHandler(
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
        condition=IfCondition(start_controller),
    )

    # 控制节点 configure 完成后自动 activate
    controller_activate_handler = RegisterEventHandler(
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
        condition=IfCondition(start_controller),
    )

    # 控制节点负责系统级键盘输入和电机安全停止。它在收到 q 或异常退出时，
    # 关闭整个 LaunchService，确保 IMU 与风扇节点不会继续留在后台运行。
    controller_exit_handler = RegisterEventHandler(
        event_handler=OnProcessExit(
            target_action=controller_node,
            on_exit=[
                EmitEvent(
                    event=Shutdown(reason="电机控制节点已退出，正在关闭整套系统")
                ),
            ],
        ),
        condition=IfCondition(start_controller),
    )

    # ---- RViz 节点（普通 Node，非 Lifecycle） ----
    from launch_ros.actions import Node as RegularNode

    rviz_node = RegularNode(
        package="rviz2",
        executable="rviz2",
        name="rviz2",
        output="screen",
        condition=IfCondition(start_rviz),
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "params_file",
                default_value=PathJoinSubstitution(
                    [FindPackageShare("imu_cybergear_ros2"), "config", "imu_cybergear_params.yaml"]
                ),
                description="参数文件路径",
            ),
            DeclareLaunchArgument(
                "start_controller",
                default_value="true",
                description="是否启动电机控制节点",
            ),
            DeclareLaunchArgument(
                "imu_auto_activate",
                default_value="true",
                description="IMU configure 后是否自动 activate",
            ),
            DeclareLaunchArgument(
                "enable_keyboard",
                default_value="true",
                description="是否启用键盘控制",
            ),
            DeclareLaunchArgument(
                "control_backend",
                default_value="socketcan_hat",
                description="电机通信后端：usb_can_serial 或 socketcan_hat",
            ),
            DeclareLaunchArgument(
                "can_channel",
                default_value="can10",
                description="SocketCAN 通道名，例如 can0/can10/can11",
            ),
            DeclareLaunchArgument(
                "can_bustype",
                default_value="socketcan",
                description="SocketCAN 总线类型，通常为 socketcan",
            ),
            DeclareLaunchArgument(
                "start_rviz",
                default_value="false",
                description="是否同时启动 RViz",
            ),
            # 注册事件处理器（必须在节点之前声明）
            imu_configure_handler,
            imu_activate_handler,
            controller_configure_handler,
            controller_activate_handler,
            controller_exit_handler,
            # 节点
            imu_node,
            controller_node,
            rviz_node,
        ]
    )
