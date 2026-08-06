"""电机控制节点的纯软件、不可变配置契约。"""

import math
import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Mapping, Tuple

from .motor_motion import (
    MotionParameters,
    validate_auto_attitude_gains,
    validate_motion_parameters,
)


MOTOR_ID_MIN = 1
MOTOR_ID_MAX = 127
MASTER_ID_MIN = 0
MASTER_ID_MAX = 255
CYBERGEAR_POSITION_MIN_RAD = -4.0 * math.pi
CYBERGEAR_POSITION_MAX_RAD = 4.0 * math.pi
SUPPORTED_BACKENDS = frozenset({"socketcan_hat", "usb_can_serial"})
SUPPORTED_CONTROL_AXES = frozenset({"roll_left", "roll_right", "pitch"})
FIXED_CONTROL_KEYS = frozenset(
    {"m", "z", "x", "h", "p", " ", "r", "q", "+", "=", "-", "_", "[", "]"}
)


DEFAULT_PARAMETER_VALUES = {
    "imu_topic": "/imu/data_raw",
    "relative_attitude_topic": "/imu/relative_roll_pitch",
    "imu_zero_generation_topic": "/imu/zero_generation",
    "motor_mode_topic": "/motors/control_mode",
    "motor_mode_publish_rate_hz": 5.0,
    "imu_zero_timeout_sec": 1.0,
    "control_backend": "socketcan_hat",
    "master_id": 253,
    "usb_port": "/dev/ttyUSB0",
    "usb_baud": 921600,
    "motor_port": "/dev/ttyUSB0",
    "motor_baud": 921600,
    "can_channel": "can10",
    "can_bustype": "socketcan",
    "left_lift_motor_id": 4,
    "left_pitch_motor_id": 3,
    "right_pitch_motor_id": 2,
    "right_lift_motor_id": 1,
    "motor_names": ["left_lift", "left_pitch", "right_pitch", "right_lift"],
    "motor_ids": [4, 3, 2, 1],
    "motor_signs": [-1.0, 1.0, -1.0, 1.0],
    "motor_limits_min": [-1.57, -1.57, -1.57, 0.0],
    "motor_limits_max": [0.0, 1.57, 1.57, 1.57],
    "motor_control_axes": ["roll_left", "pitch", "pitch", "roll_right"],
    "motor_keys_forward": ["d", "w", "k", "l"],
    "motor_keys_backward": ["a", "s", "i", "j"],
    "default_speed": 10.0,
    "deadband_rad": 0.02,
    "auto_roll_gain": 1.0,
    "auto_pitch_gain": 1.0,
    "max_position_step": 0.4,
    "command_interval_sec": 0.02,
    "manual_motion_speed_rad_s": 4.0,
    "auto_motion_speed_rad_s": 4.0,
    "home_motion_speed_rad_s": 4.0,
    "motion_dt_max_sec": 0.05,
    "target_reached_tolerance_rad": 0.001,
    "manual_speed_min": 0.5,
    "manual_speed_max": 20.0,
    "manual_speed_step": 0.5,
    "roll_axis_sign": 1.0,
    "pitch_axis_sign": 1.0,
    "left_lift_sign": -1.0,
    "right_lift_sign": 1.0,
    "left_pitch_sign": 1.0,
    "right_pitch_sign": -1.0,
    "enable_keyboard": True,
    "keyboard_device": "/dev/tty",
    "manual_step_deg": 3.0,
    "manual_repeat_gap_sec": 0.8,
    "manual_repeat_dt_max_sec": 0.08,
    "manual_loop_hz": 50.0,
    "m1_min": 0.0,
    "m1_max": 1.57,
    "m2_min": -1.57,
    "m2_max": 1.57,
    "m3_min": -1.57,
    "m3_max": 1.57,
    "m4_min": -1.57,
    "m4_max": 0.0,
    "watchdog_timeout_ms": 200,
    "motor_temp_limit_degC": 80.0,
    "motor_temp_critical_degC": 90.0,
    "motor_current_limit_a": 5.0,
    "position_error_threshold_rad": 0.3,
    "warning_throttle_sec": 2.0,
    "reconnect_on_disconnect": True,
    "motor_status_topic": "/motor/status",
}

DEPRECATED_PARAMETER_REPLACEMENTS = {
    "left_lift_motor_id": (4, "motor_ids"),
    "left_pitch_motor_id": (3, "motor_ids"),
    "right_pitch_motor_id": (2, "motor_ids"),
    "right_lift_motor_id": (1, "motor_ids"),
    "left_lift_sign": (-1.0, "motor_signs"),
    "right_lift_sign": (1.0, "motor_signs"),
    "left_pitch_sign": (1.0, "motor_signs"),
    "right_pitch_sign": (-1.0, "motor_signs"),
    "m1_min": (0.0, "motor_limits_min"),
    "m1_max": (1.57, "motor_limits_max"),
    "m2_min": (-1.57, "motor_limits_min"),
    "m2_max": (1.57, "motor_limits_max"),
    "m3_min": (-1.57, "motor_limits_min"),
    "m3_max": (1.57, "motor_limits_max"),
    "m4_min": (-1.57, "motor_limits_min"),
    "m4_max": (0.0, "motor_limits_max"),
}

PARAMETER_NAMES = tuple(DEFAULT_PARAMETER_VALUES)


@dataclass(frozen=True)
class MotorChannelConfig:
    name: str
    motor_id: int
    sign: float
    limit_min: float
    limit_max: float
    control_axis: str
    key_forward: str
    key_backward: str


@dataclass(frozen=True)
class MotorCommunicationConfig:
    backend: str
    master_id: int
    usb_port: str
    usb_baud: int
    can_channel: str
    can_bustype: str
    fallback_parameters: Tuple[str, ...]


@dataclass(frozen=True)
class MotorControlConfig:
    motion: MotionParameters
    deadband_rad: float
    auto_roll_gain: float
    auto_pitch_gain: float
    roll_axis_sign: float
    pitch_axis_sign: float


@dataclass(frozen=True)
class MotorSafetyConfig:
    watchdog_timeout_ms: int
    motor_temp_limit_deg_c: float
    motor_temp_critical_deg_c: float
    motor_current_limit_a: float
    position_error_threshold_rad: float
    warning_throttle_sec: float
    reconnect_on_disconnect: bool


@dataclass(frozen=True)
class MotorRosInterfaceConfig:
    imu_topic: str
    relative_attitude_topic: str
    imu_zero_generation_topic: str
    motor_mode_topic: str
    motor_status_topic: str
    motor_mode_publish_rate_hz: float
    imu_zero_timeout_sec: float


@dataclass(frozen=True)
class MotorKeyboardConfig:
    enabled: bool
    device: str
    manual_loop_hz: float


@dataclass(frozen=True)
class MotorNodeConfig:
    channels: Tuple[MotorChannelConfig, ...]
    communication: MotorCommunicationConfig
    control: MotorControlConfig
    safety: MotorSafetyConfig
    ros: MotorRosInterfaceConfig
    keyboard: MotorKeyboardConfig


def default_motor_config_values() -> dict:
    """返回可供纯函数测试修改的默认原始参数副本。"""
    return deepcopy(DEFAULT_PARAMETER_VALUES)


def _require_finite_number(name: str, value) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} 必须是数值")
    converted = float(value)
    if not math.isfinite(converted):
        raise ValueError(f"{name} 必须是有限值")
    return converted


def _require_integer(name: str, value) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} 必须是整数")
    return value


def _require_nonblank(name: str, value) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} 必须是非空字符串")
    return value.strip()


def _validate_topic_name(name: str, value) -> str:
    topic = _require_nonblank(name, value)
    if (
        any(character.isspace() for character in topic)
        or "//" in topic
        or topic.endswith("/")
        or re.fullmatch(r"/?[A-Za-z_][A-Za-z0-9_/]*", topic) is None
    ):
        raise ValueError(f"{name} 不是可接受的 ROS 2 话题名: {value!r}")
    return topic


def _validate_deprecated_parameters(raw: Mapping[str, object]) -> None:
    for name, (default, replacement) in DEPRECATED_PARAMETER_REPLACEMENTS.items():
        if raw[name] != default:
            raise ValueError(
                f"{name} 已废弃且不会生效，请修改 {replacement}"
            )


def _build_channels(raw: Mapping[str, object]) -> Tuple[MotorChannelConfig, ...]:
    list_names = (
        "motor_names",
        "motor_ids",
        "motor_signs",
        "motor_limits_min",
        "motor_limits_max",
        "motor_control_axes",
        "motor_keys_forward",
        "motor_keys_backward",
    )
    values = {name: list(raw[name]) for name in list_names}
    lengths = {name: len(value) for name, value in values.items()}
    if not lengths["motor_ids"]:
        raise ValueError("电机列表不得为空；" + ", ".join(f"{k}={v}" for k, v in lengths.items()))
    if len(set(lengths.values())) != 1:
        raise ValueError(
            "电机列表参数长度不一致: "
            + ", ".join(f"{name}={length}" for name, length in lengths.items())
        )

    motor_ids = []
    for index, value in enumerate(values["motor_ids"]):
        motor_id = _require_integer(f"motor_ids[{index}]", value)
        if not MOTOR_ID_MIN <= motor_id <= MOTOR_ID_MAX:
            raise ValueError(
                f"motor_ids[{index}] 必须在 {MOTOR_ID_MIN}～{MOTOR_ID_MAX}"
            )
        motor_ids.append(motor_id)
    if len(set(motor_ids)) != len(motor_ids):
        raise ValueError("motor_ids 不得包含重复 ID")

    names = [
        _require_nonblank(f"motor_names[{index}]", value)
        for index, value in enumerate(values["motor_names"])
    ]
    if len(set(names)) != len(names):
        raise ValueError("motor_names 不得包含重复名称")

    signs = []
    for index, value in enumerate(values["motor_signs"]):
        sign = _require_finite_number(f"motor_signs[{index}]", value)
        if sign not in (-1.0, 1.0):
            raise ValueError(f"motor_signs[{index}] 必须严格为 +1.0 或 -1.0")
        signs.append(sign)

    limits_min = [
        _require_finite_number(f"motor_limits_min[{index}]", value)
        for index, value in enumerate(values["motor_limits_min"])
    ]
    limits_max = [
        _require_finite_number(f"motor_limits_max[{index}]", value)
        for index, value in enumerate(values["motor_limits_max"])
    ]
    for index, (low, high) in enumerate(zip(limits_min, limits_max)):
        if low >= high:
            raise ValueError(
                f"motor_limits_min[{index}] 必须严格小于 motor_limits_max[{index}]"
            )
        if low < CYBERGEAR_POSITION_MIN_RAD or high > CYBERGEAR_POSITION_MAX_RAD:
            raise ValueError(
                f"电机软限位[{index}] 必须位于 CyberGear 位置协议范围 [-4π, +4π]"
            )

    axes = []
    for index, value in enumerate(values["motor_control_axes"]):
        axis = _require_nonblank(f"motor_control_axes[{index}]", value)
        if axis not in SUPPORTED_CONTROL_AXES:
            raise ValueError(
                f"motor_control_axes[{index}] 不受支持: {axis!r}"
            )
        axes.append(axis)

    forward = list(values["motor_keys_forward"])
    backward = list(values["motor_keys_backward"])
    all_keys = []
    for parameter_name, keys in (
        ("motor_keys_forward", forward),
        ("motor_keys_backward", backward),
    ):
        for index, key in enumerate(keys):
            if not isinstance(key, str) or len(key) != 1:
                raise ValueError(f"{parameter_name}[{index}] 必须是单字符字符串")
            if key != key.lower():
                raise ValueError(f"{parameter_name}[{index}] 必须使用小写字符")
            if key in FIXED_CONTROL_KEYS or key.isdigit():
                raise ValueError(
                    f"{parameter_name}[{index}]={key!r} 与固定控制键或数字选中键冲突"
                )
            all_keys.append(key)
    if len(set(all_keys)) != len(all_keys):
        raise ValueError("全部电机前进和后退键必须唯一")
    for index, (key_forward, key_backward) in enumerate(zip(forward, backward)):
        if key_forward == key_backward:
            raise ValueError(f"电机[{index}] 的前进键和后退键不能相同")

    return tuple(
        MotorChannelConfig(
            name=names[index],
            motor_id=motor_ids[index],
            sign=signs[index],
            limit_min=limits_min[index],
            limit_max=limits_max[index],
            control_axis=axes[index],
            key_forward=forward[index],
            key_backward=backward[index],
        )
        for index in range(len(motor_ids))
    )


def build_motor_node_config(raw: Mapping[str, object]) -> MotorNodeConfig:
    """从原始参数构造并完整校验配置，不创建 ROS 或硬件资源。"""
    missing = [name for name in PARAMETER_NAMES if name not in raw]
    if missing:
        raise ValueError(f"缺少电机配置参数: {', '.join(missing)}")
    _validate_deprecated_parameters(raw)
    channels = _build_channels(raw)

    backend = _require_nonblank("control_backend", raw["control_backend"])
    if backend not in SUPPORTED_BACKENDS:
        raise ValueError(f"control_backend 不受支持: {backend!r}")
    master_id = _require_integer("master_id", raw["master_id"])
    if not MASTER_ID_MIN <= master_id <= MASTER_ID_MAX:
        raise ValueError("master_id 必须在 0～255")
    if master_id in {channel.motor_id for channel in channels}:
        raise ValueError("master_id 不得与任何 motor_id 相同")

    fallback_parameters = []
    usb_port = raw["usb_port"]
    usb_baud = raw["usb_baud"]
    if backend == "usb_can_serial":
        if not isinstance(usb_port, str):
            raise ValueError("usb_port 必须是字符串")
        if not usb_port.strip():
            usb_port = raw["motor_port"]
            fallback_parameters.append("motor_port")
        if usb_baud == 0:
            usb_baud = raw["motor_baud"]
            fallback_parameters.append("motor_baud")
        usb_port = _require_nonblank("usb_port（解析后）", usb_port)
        usb_baud = _require_integer("usb_baud（解析后）", usb_baud)
        if usb_baud <= 0:
            raise ValueError("usb_baud（解析后）必须是正整数")
    else:
        usb_port = str(usb_port)
        usb_baud = _require_integer("usb_baud", usb_baud)

    can_channel = str(raw["can_channel"])
    can_bustype = str(raw["can_bustype"])
    if backend == "socketcan_hat":
        can_channel = _require_nonblank("can_channel", raw["can_channel"])
        can_bustype = _require_nonblank("can_bustype", raw["can_bustype"])

    motion = MotionParameters(
        command_interval_sec=_require_finite_number(
            "command_interval_sec", raw["command_interval_sec"]
        ),
        motion_dt_max_sec=_require_finite_number(
            "motion_dt_max_sec", raw["motion_dt_max_sec"]
        ),
        target_reached_tolerance_rad=_require_finite_number(
            "target_reached_tolerance_rad", raw["target_reached_tolerance_rad"]
        ),
        manual_motion_speed_rad_s=_require_finite_number(
            "manual_motion_speed_rad_s", raw["manual_motion_speed_rad_s"]
        ),
        auto_motion_speed_rad_s=_require_finite_number(
            "auto_motion_speed_rad_s", raw["auto_motion_speed_rad_s"]
        ),
        home_motion_speed_rad_s=_require_finite_number(
            "home_motion_speed_rad_s", raw["home_motion_speed_rad_s"]
        ),
        manual_step_rad=math.radians(
            _require_finite_number("manual_step_deg", raw["manual_step_deg"])
        ),
        manual_repeat_gap_sec=_require_finite_number(
            "manual_repeat_gap_sec", raw["manual_repeat_gap_sec"]
        ),
        manual_repeat_dt_max_sec=_require_finite_number(
            "manual_repeat_dt_max_sec", raw["manual_repeat_dt_max_sec"]
        ),
        max_position_step=_require_finite_number(
            "max_position_step", raw["max_position_step"]
        ),
        default_speed=_require_finite_number("default_speed", raw["default_speed"]),
        manual_speed_min=_require_finite_number(
            "manual_speed_min", raw["manual_speed_min"]
        ),
        manual_speed_max=_require_finite_number(
            "manual_speed_max", raw["manual_speed_max"]
        ),
        manual_speed_step=_require_finite_number(
            "manual_speed_step", raw["manual_speed_step"]
        ),
    )
    validate_motion_parameters(motion)
    deadband = _require_finite_number("deadband_rad", raw["deadband_rad"])
    if deadband < 0.0:
        raise ValueError("deadband_rad 不得小于 0")
    roll_gain = _require_finite_number("auto_roll_gain", raw["auto_roll_gain"])
    pitch_gain = _require_finite_number("auto_pitch_gain", raw["auto_pitch_gain"])
    validate_auto_attitude_gains(roll_gain, pitch_gain)
    roll_sign = _require_finite_number("roll_axis_sign", raw["roll_axis_sign"])
    pitch_sign = _require_finite_number("pitch_axis_sign", raw["pitch_axis_sign"])
    if roll_sign not in (-1.0, 1.0) or pitch_sign not in (-1.0, 1.0):
        raise ValueError("roll_axis_sign 和 pitch_axis_sign 必须严格为 +1.0 或 -1.0")

    watchdog = _require_integer("watchdog_timeout_ms", raw["watchdog_timeout_ms"])
    if watchdog < 0:
        raise ValueError("watchdog_timeout_ms 不得为负数；0 表示禁用")
    temp_limit = _require_finite_number(
        "motor_temp_limit_degC", raw["motor_temp_limit_degC"]
    )
    temp_critical = _require_finite_number(
        "motor_temp_critical_degC", raw["motor_temp_critical_degC"]
    )
    if temp_critical <= temp_limit:
        raise ValueError("motor_temp_critical_degC 必须严格大于 motor_temp_limit_degC")
    current_limit = _require_finite_number(
        "motor_current_limit_a", raw["motor_current_limit_a"]
    )
    if current_limit <= 0.0:
        raise ValueError("motor_current_limit_a 必须大于 0")
    position_error = _require_finite_number(
        "position_error_threshold_rad", raw["position_error_threshold_rad"]
    )
    if position_error <= 0.0:
        raise ValueError("position_error_threshold_rad 必须大于 0")
    warning_throttle = _require_finite_number(
        "warning_throttle_sec", raw["warning_throttle_sec"]
    )
    if warning_throttle <= 0.0:
        raise ValueError("warning_throttle_sec 必须大于 0")

    rate = _require_finite_number(
        "motor_mode_publish_rate_hz", raw["motor_mode_publish_rate_hz"]
    )
    zero_timeout = _require_finite_number(
        "imu_zero_timeout_sec", raw["imu_zero_timeout_sec"]
    )
    manual_loop_hz = _require_finite_number("manual_loop_hz", raw["manual_loop_hz"])
    for name, value in (
        ("motor_mode_publish_rate_hz", rate),
        ("imu_zero_timeout_sec", zero_timeout),
        ("manual_loop_hz", manual_loop_hz),
    ):
        if value <= 0.0:
            raise ValueError(f"{name} 必须大于 0")

    if not isinstance(raw["enable_keyboard"], bool):
        raise ValueError("enable_keyboard 必须是布尔值")
    if not isinstance(raw["reconnect_on_disconnect"], bool):
        raise ValueError("reconnect_on_disconnect 必须是布尔值")
    keyboard_device = raw["keyboard_device"]
    if not isinstance(keyboard_device, str):
        raise ValueError("keyboard_device 必须是字符串")

    return MotorNodeConfig(
        channels=channels,
        communication=MotorCommunicationConfig(
            backend=backend,
            master_id=master_id,
            usb_port=usb_port,
            usb_baud=usb_baud,
            can_channel=can_channel,
            can_bustype=can_bustype,
            fallback_parameters=tuple(fallback_parameters),
        ),
        control=MotorControlConfig(
            motion=motion,
            deadband_rad=deadband,
            auto_roll_gain=roll_gain,
            auto_pitch_gain=pitch_gain,
            roll_axis_sign=roll_sign,
            pitch_axis_sign=pitch_sign,
        ),
        safety=MotorSafetyConfig(
            watchdog_timeout_ms=watchdog,
            motor_temp_limit_deg_c=temp_limit,
            motor_temp_critical_deg_c=temp_critical,
            motor_current_limit_a=current_limit,
            position_error_threshold_rad=position_error,
            warning_throttle_sec=warning_throttle,
            reconnect_on_disconnect=raw["reconnect_on_disconnect"],
        ),
        ros=MotorRosInterfaceConfig(
            imu_topic=_validate_topic_name("imu_topic", raw["imu_topic"]),
            relative_attitude_topic=_validate_topic_name(
                "relative_attitude_topic", raw["relative_attitude_topic"]
            ),
            imu_zero_generation_topic=_validate_topic_name(
                "imu_zero_generation_topic", raw["imu_zero_generation_topic"]
            ),
            motor_mode_topic=_validate_topic_name(
                "motor_mode_topic", raw["motor_mode_topic"]
            ),
            motor_status_topic=_validate_topic_name(
                "motor_status_topic", raw["motor_status_topic"]
            ),
            motor_mode_publish_rate_hz=rate,
            imu_zero_timeout_sec=zero_timeout,
        ),
        keyboard=MotorKeyboardConfig(
            enabled=raw["enable_keyboard"],
            device=keyboard_device,
            manual_loop_hz=manual_loop_hz,
        ),
    )
