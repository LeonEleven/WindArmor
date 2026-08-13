"""Stage 1 hardware observation: sensors/readers plus Flight dry-run only.

This launch opens the real IMU serial path and the CyberGear receive transport.
It must only be run after separate hardware-access authorization. It never starts
an actuator controller and hard-disables Flight authority takeover.
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, EmitEvent, RegisterEventHandler
from launch.event_handlers import OnProcessStart
from launch.events import matches_action
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import LifecycleNode, Node
from launch_ros.event_handlers import OnStateTransition
from launch_ros.events.lifecycle import ChangeState
from launch_ros.substitutions import FindPackageShare
from lifecycle_msgs.msg import Transition


def _autostart_lifecycle(node):
    configure = RegisterEventHandler(
        OnProcessStart(
            target_action=node,
            on_start=[
                EmitEvent(
                    event=ChangeState(
                        lifecycle_node_matcher=matches_action(node),
                        transition_id=Transition.TRANSITION_CONFIGURE,
                    )
                )
            ],
        )
    )
    activate = RegisterEventHandler(
        OnStateTransition(
            target_lifecycle_node=node,
            goal_state="inactive",
            entities=[
                EmitEvent(
                    event=ChangeState(
                        lifecycle_node_matcher=matches_action(node),
                        transition_id=Transition.TRANSITION_ACTIVATE,
                    )
                )
            ],
        )
    )
    return configure, activate


def generate_launch_description() -> LaunchDescription:
    observation_params = LaunchConfiguration("observation_params_file")
    flight_params = LaunchConfiguration("flight_params_file")
    control_backend = LaunchConfiguration("control_backend")
    can_channel = LaunchConfiguration("can_channel")

    imu_driver = LifecycleNode(
        package="imu_cybergear_ros2",
        executable="imu_driver_node",
        name="imu_driver_node",
        namespace="",
        parameters=[observation_params],
        output="screen",
    )
    imu_relative_observer = LifecycleNode(
        package="imu_cybergear_ros2",
        executable="imu_relative_observer_node",
        name="imu_relative_observer_node",
        namespace="",
        parameters=[observation_params],
        output="screen",
    )
    motor_feedback_observer = LifecycleNode(
        package="imu_cybergear_ros2",
        executable="motor_feedback_observer_node",
        name="motor_feedback_observer_node",
        namespace="",
        parameters=[
            observation_params,
            {
                "control_backend": control_backend,
                "can_channel": can_channel,
            },
        ],
        output="screen",
    )
    flight_runtime = Node(
        package="windarmor_flight_control",
        executable="flight_control_runtime_node",
        name="flight_control_runtime_node",
        parameters=[flight_params, {"flight_takeover_enabled": False}],
        output="screen",
    )

    lifecycle_handlers = []
    for lifecycle_node in (
        imu_driver,
        imu_relative_observer,
        motor_feedback_observer,
    ):
        lifecycle_handlers.extend(_autostart_lifecycle(lifecycle_node))

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "observation_params_file",
                default_value=PathJoinSubstitution(
                    [
                        FindPackageShare("imu_cybergear_ros2"),
                        "config",
                        "imu_cybergear_params.yaml",
                    ]
                ),
            ),
            DeclareLaunchArgument(
                "flight_params_file",
                default_value=PathJoinSubstitution(
                    [
                        FindPackageShare("windarmor_flight_control"),
                        "config",
                        "flight_control.yaml",
                    ]
                ),
            ),
            DeclareLaunchArgument(
                "control_backend",
                default_value="socketcan_hat",
                description="Receive-only CyberGear transport backend",
            ),
            DeclareLaunchArgument(
                "can_channel",
                default_value="can10",
                description="Existing SocketCAN interface; this launch never configures it",
            ),
            imu_driver,
            imu_relative_observer,
            motor_feedback_observer,
            flight_runtime,
            *lifecycle_handlers,
        ]
    )
