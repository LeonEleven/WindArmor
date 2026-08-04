"""与 ROS 和硬件无关的电机目标推进计算。"""

from dataclasses import dataclass
from enum import Enum
import math


class MotionSource(str, Enum):
    """内部普通运动源；不改变公开的电机控制模式。"""

    IDLE = "IDLE"
    MANUAL = "MANUAL"
    AUTO = "AUTO"
    HOME = "HOME"


@dataclass(frozen=True)
class MotionParameters:
    """统一目标推进所需的参数集合。"""

    command_interval_sec: float
    motion_dt_max_sec: float
    target_reached_tolerance_rad: float
    manual_motion_speed_rad_s: float
    auto_motion_speed_rad_s: float
    home_motion_speed_rad_s: float
    manual_step_rad: float
    manual_repeat_gap_sec: float
    manual_repeat_dt_max_sec: float
    max_position_step: float
    default_speed: float
    manual_speed_min: float
    manual_speed_max: float
    manual_speed_step: float


def validate_motion_parameters(params: MotionParameters) -> None:
    """验证参数有限性和相互关系，非法时抛出 ``ValueError``。"""
    values = {
        field_name: getattr(params, field_name)
        for field_name in params.__dataclass_fields__
    }
    non_finite = [name for name, value in values.items() if not math.isfinite(value)]
    if non_finite:
        raise ValueError(f"运动参数必须为有限值: {', '.join(non_finite)}")

    errors = []
    if params.command_interval_sec <= 0.0:
        errors.append("command_interval_sec 必须大于 0")
    if params.motion_dt_max_sec < params.command_interval_sec:
        errors.append("motion_dt_max_sec 必须大于或等于 command_interval_sec")
    if params.target_reached_tolerance_rad < 0.0:
        errors.append("target_reached_tolerance_rad 不得小于 0")
    if params.manual_motion_speed_rad_s <= 0.0:
        errors.append("manual_motion_speed_rad_s 必须大于 0")
    if params.auto_motion_speed_rad_s <= 0.0:
        errors.append("auto_motion_speed_rad_s 必须大于 0")
    if params.home_motion_speed_rad_s <= 0.0:
        errors.append("home_motion_speed_rad_s 必须大于 0")
    if params.manual_step_rad <= 0.0:
        errors.append("manual_step_deg 必须大于 0")
    if params.manual_repeat_gap_sec <= 0.0:
        errors.append("manual_repeat_gap_sec 必须大于 0")
    if params.manual_repeat_dt_max_sec <= 0.0:
        errors.append("manual_repeat_dt_max_sec 必须大于 0")
    if params.manual_repeat_dt_max_sec > params.manual_repeat_gap_sec:
        errors.append("manual_repeat_dt_max_sec 不得大于 manual_repeat_gap_sec")
    if params.max_position_step <= 0.0:
        errors.append("max_position_step 必须大于 0")
    if params.default_speed <= 0.0:
        errors.append("default_speed 必须大于 0")
    if params.manual_speed_min <= 0.0:
        errors.append("manual_speed_min 必须大于 0")
    if params.manual_speed_max < params.manual_speed_min:
        errors.append("manual_speed_max 必须大于或等于 manual_speed_min")
    if params.manual_speed_step <= 0.0:
        errors.append("manual_speed_step 必须大于 0")
    if errors:
        raise ValueError("；".join(errors))


def speed_for_source(source: MotionSource, params: MotionParameters) -> float:
    """返回给定运动源的软件目标速度。"""
    if source == MotionSource.MANUAL:
        return params.manual_motion_speed_rad_s
    if source == MotionSource.AUTO:
        return params.auto_motion_speed_rad_s
    if source == MotionSource.HOME:
        return params.home_motion_speed_rad_s
    return 0.0


def advance_target(
    current: float,
    desired: float,
    *,
    mode_speed_rad_s: float,
    motor_speed_limit_rad_s: float,
    elapsed_sec: float,
    motion_dt_max_sec: float,
    max_position_step: float,
    target_reached_tolerance_rad: float,
    limit_min: float,
    limit_max: float,
) -> float:
    """用真实时间差将一个当前位置命令向期望目标推进一次。"""
    finite_values = (
        current,
        desired,
        mode_speed_rad_s,
        motor_speed_limit_rad_s,
        elapsed_sec,
        motion_dt_max_sec,
        max_position_step,
        target_reached_tolerance_rad,
        limit_min,
        limit_max,
    )
    if not all(math.isfinite(value) for value in finite_values):
        raise ValueError("目标推进输入必须全部为有限值")
    if limit_min > limit_max:
        raise ValueError("软限位下限不得大于上限")
    if mode_speed_rad_s <= 0.0 or motor_speed_limit_rad_s <= 0.0:
        raise ValueError("模式速度和电机速度上限必须大于 0")
    if motion_dt_max_sec < 0.0 or max_position_step <= 0.0:
        raise ValueError("dt 上限不得为负且单周期位置上限必须大于 0")
    if target_reached_tolerance_rad < 0.0:
        raise ValueError("目标到达容差不得为负")

    current = max(limit_min, min(limit_max, current))
    desired = max(limit_min, min(limit_max, desired))
    error = desired - current
    if abs(error) <= target_reached_tolerance_rad:
        return desired

    dt_used = max(0.0, min(motion_dt_max_sec, elapsed_sec))
    effective_speed = min(mode_speed_rad_s, motor_speed_limit_rad_s)
    allowed_step = min(max_position_step, effective_speed * dt_used)
    delta = max(-allowed_step, min(allowed_step, error))
    result = max(limit_min, min(limit_max, current + delta))
    if abs(desired - result) <= target_reached_tolerance_rad:
        return desired
    return result


def manual_event_increment(
    *,
    is_repeat: bool,
    event_dt_sec: float,
    manual_step_rad: float,
    manual_motion_speed_rad_s: float,
    motor_speed_limit_rad_s: float,
    manual_repeat_dt_max_sec: float,
    max_position_step: float,
) -> float:
    """计算一个手动运动字符产生的有限期望目标增量绝对值。"""
    values = (
        event_dt_sec,
        manual_step_rad,
        manual_motion_speed_rad_s,
        motor_speed_limit_rad_s,
        manual_repeat_dt_max_sec,
        max_position_step,
    )
    if not all(math.isfinite(value) for value in values):
        raise ValueError("手动按键计算输入必须全部为有限值")
    if (
        manual_step_rad <= 0.0
        or manual_motion_speed_rad_s <= 0.0
        or motor_speed_limit_rad_s <= 0.0
        or manual_repeat_dt_max_sec <= 0.0
        or max_position_step <= 0.0
    ):
        raise ValueError("手动按键速度、步长和限制必须大于 0")
    if not is_repeat:
        return min(manual_step_rad, max_position_step)
    repeat_dt = max(0.0, min(manual_repeat_dt_max_sec, event_dt_sec))
    effective_speed = min(manual_motion_speed_rad_s, motor_speed_limit_rad_s)
    return min(max_position_step, effective_speed * repeat_dt)
