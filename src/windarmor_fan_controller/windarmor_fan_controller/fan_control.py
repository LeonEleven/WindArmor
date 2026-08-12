"""与 ROS 和硬件无关的双风扇命令仲裁与自动控制逻辑。"""

import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

from .fan_ownership import FanCommandOwner, FanOwnershipCore, OwnershipResult


ALLOWED_MOTOR_MODES = {
    "MANUAL",
    "AUTO",
    "EMERGENCY_STOP",
    "DISABLED",
    "ERROR",
}
CONTROL_READY_MOTOR_MODES = {"MANUAL", "AUTO"}
ALLOWED_RESPONSE_CURVES = {"linear", "smoothstep", "quadratic"}


class FanControlState(str, Enum):
    SAFE_STOP = "SAFE_STOP"
    MANUAL_DISARMED = "MANUAL_DISARMED"
    MANUAL_WAITING_FOR_NEUTRAL = "MANUAL_WAITING_FOR_NEUTRAL"
    MANUAL_WAITING = "MANUAL_WAITING"
    MANUAL_ACTIVE = "MANUAL_ACTIVE"
    AUTO_WAITING = "AUTO_WAITING"
    AUTO_ACTIVE = "AUTO_ACTIVE"
    FLIGHT_WAITING = "FLIGHT_WAITING"
    FLIGHT_ACTIVE = "FLIGHT_ACTIVE"
    DISABLED = "DISABLED"
    EMERGENCY_STOP = "EMERGENCY_STOP"


@dataclass(frozen=True)
class FanControlConfig:
    min_pwm_us: int = 800
    max_pwm_us: int = 2200
    fan_stop_pwm_us: int = 800
    fan_start_pwm_us: int = 1200
    fan_auto_max_pwm_us: int = 1400
    flight_fan_max_pwm_us: int = 1400
    fan_deadband_on_deg: float = 5.0
    fan_deadband_off_deg: float = 3.0
    fan_full_scale_deg: float = 45.0
    fan_response_curve: str = "smoothstep"
    rise_step_pwm_us: int = 10
    fall_step_pwm_us: int = 20
    imu_timeout_sec: float = 0.2
    manual_command_timeout_sec: float = 0.5
    motor_mode_timeout_sec: float = 1.0
    fan_enabled_timeout_sec: float = 1.0
    require_motor_mode_for_manual: bool = False
    fan_flight_command_timeout_sec: float = 0.25

    def validate(self) -> None:
        values = (
            self.min_pwm_us,
            self.max_pwm_us,
            self.fan_stop_pwm_us,
            self.fan_start_pwm_us,
            self.fan_auto_max_pwm_us,
            self.flight_fan_max_pwm_us,
            self.fan_deadband_on_deg,
            self.fan_deadband_off_deg,
            self.fan_full_scale_deg,
            self.rise_step_pwm_us,
            self.fall_step_pwm_us,
            self.imu_timeout_sec,
            self.manual_command_timeout_sec,
            self.motor_mode_timeout_sec,
            self.fan_enabled_timeout_sec,
            self.fan_flight_command_timeout_sec,
        )
        if not all(math.isfinite(value) for value in values):
            raise ValueError("风扇控制数值参数必须为有限值")
        if self.fan_response_curve not in ALLOWED_RESPONSE_CURVES:
            raise ValueError(
                "fan_response_curve 必须是 linear、smoothstep 或 quadratic"
            )
        if self.min_pwm_us >= self.max_pwm_us:
            raise ValueError("min_pwm_us 必须小于 max_pwm_us")
        if not (
            0.0 <= self.fan_deadband_off_deg
            < self.fan_deadband_on_deg
            < self.fan_full_scale_deg
        ):
            raise ValueError("风扇死区参数必须满足 0 <= off < on < full_scale")
        if not (
            self.min_pwm_us
            <= self.fan_stop_pwm_us
            <= self.fan_start_pwm_us
            <= self.fan_auto_max_pwm_us
            <= self.max_pwm_us
        ):
            raise ValueError("风扇 PWM 参数顺序或范围无效")
        if not self.fan_start_pwm_us <= self.flight_fan_max_pwm_us <= self.fan_auto_max_pwm_us:
            raise ValueError("flight_fan_max_pwm_us 必须位于 start 与 AUTO max 之间")
        if self.rise_step_pwm_us <= 0 or self.fall_step_pwm_us <= 0:
            raise ValueError("风扇 PWM 上升和下降步长必须大于 0")
        if (
            self.imu_timeout_sec <= 0.0
            or self.manual_command_timeout_sec <= 0.0
            or self.motor_mode_timeout_sec <= 0.0
            or self.fan_enabled_timeout_sec <= 0.0
            or self.fan_flight_command_timeout_sec <= 0.0
        ):
            raise ValueError("全部超时参数必须大于 0")


@dataclass(frozen=True)
class FanControlOutput:
    state: FanControlState
    command_pwm: Tuple[int, int]
    auto_target_pwm: Tuple[int, int]
    auto_enabled: bool
    auto_active: bool


@dataclass(frozen=True)
class FanSafetySnapshot:
    """Read-only view of the existing core; it owns no control state."""

    e_stop_latched: bool
    control_state: str
    enabled_observed: bool
    enabled: bool
    manual_armed: bool
    legacy_auto_requested: bool
    legacy_auto_active: bool
    safety_reason: str
    passive_for_takeover: bool


def attitude_activities(
    relative_roll_rad: float,
    relative_pitch_rad: float,
) -> Tuple[float, float]:
    """按已批准方向公式返回左右活动角，单位为度。"""
    if not math.isfinite(relative_roll_rad) or not math.isfinite(relative_pitch_rad):
        raise ValueError("相对姿态必须为有限值")
    roll_deg = math.degrees(relative_roll_rad)
    pitch_activity = abs(math.degrees(relative_pitch_rad))
    return (
        max(pitch_activity, max(0.0, -roll_deg)),
        max(pitch_activity, max(0.0, roll_deg)),
    )


def update_hysteresis(
    activity_deg: float,
    was_running: bool,
    *,
    on_deg: float,
    off_deg: float,
) -> bool:
    if not all(math.isfinite(value) for value in (activity_deg, on_deg, off_deg)):
        raise ValueError("迟滞输入必须为有限值")
    if was_running:
        return activity_deg >= off_deg
    return activity_deg >= on_deg


def apply_response_curve(normalized_activity: float, curve_name: str) -> float:
    """将归一化活动量映射到目标比例；不依赖 ROS 或硬件状态。"""
    if not math.isfinite(normalized_activity):
        raise ValueError("归一化风扇活动量必须为有限值")
    if curve_name not in ALLOWED_RESPONSE_CURVES:
        raise ValueError(
            "fan_response_curve 必须是 linear、smoothstep 或 quadratic"
        )
    x = max(0.0, min(1.0, normalized_activity))
    if curve_name == "linear":
        return x
    if curve_name == "smoothstep":
        return x * x * (3.0 - 2.0 * x)
    return x * x


def activity_to_pwm(activity_deg: float, running: bool, config: FanControlConfig) -> int:
    if not running:
        return config.fan_stop_pwm_us
    ratio = (activity_deg - config.fan_deadband_on_deg) / (
        config.fan_full_scale_deg - config.fan_deadband_on_deg
    )
    curve_value = apply_response_curve(ratio, config.fan_response_curve)
    pwm = config.fan_start_pwm_us + curve_value * (
        config.fan_auto_max_pwm_us - config.fan_start_pwm_us
    )
    return int(round(pwm))


def slew_pwm(current: int, target: int, rise_step: int, fall_step: int) -> int:
    difference = target - current
    limited = max(-fall_step, min(rise_step, difference))
    return current + limited


def normalized_flight_command_to_pwm(value: float, config: FanControlConfig) -> int:
    """Map dimensionless Flight intent to the existing bounded PWM domain."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Flight fan command must be numeric")
    value = float(value)
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError("Flight fan command must be within [0.0, 1.0]")
    if value == 0.0:
        return config.fan_stop_pwm_us
    return int(round(
        config.fan_start_pwm_us
        + value * (config.flight_fan_max_pwm_us - config.fan_start_pwm_us)
    ))


class FanControlCore:
    """集中维护授权、缓存、急停锁存和唯一安全输出。"""

    def __init__(self, config: FanControlConfig):
        config.validate()
        self.config = config
        stop = config.fan_stop_pwm_us
        self.state = FanControlState.SAFE_STOP
        self.command_pwm = (stop, stop)
        self.auto_target_pwm = (stop, stop)
        self._auto_running = [False, False]
        self.auto_requested = False
        self._auto_pose_cutoff = 0

        self.manual_armed = False
        self._manual_neutral_received = False
        self._manual_pwm = [stop, stop]
        self._manual_at: list[Optional[float]] = [None, None]

        self._pose: Optional[Tuple[float, float]] = None
        self._pose_at: Optional[float] = None
        self._pose_seq = 0
        self._zero_generation: Optional[int] = None

        self._motor_mode: Optional[str] = None
        self._motor_mode_at: Optional[float] = None
        self._motor_mode_event_count = 0
        self._fan_enabled: Optional[bool] = None
        self._fan_enabled_at: Optional[float] = None

        self.e_stop_latched = False
        self._e_stop_active: Optional[bool] = None
        self._e_stop_at: Optional[float] = None
        self._safety_reason = "启动后等待显式选择控制路径"
        self._immediate_stop_pending = True
        self.ownership = FanOwnershipCore(
            command_timeout_sec=config.fan_flight_command_timeout_sec
        )
        self._flight_target_pwm = (stop, stop)

    @property
    def safety_reason(self) -> str:
        return self._safety_reason

    @property
    def manual_neutral_received(self) -> bool:
        return self._manual_neutral_received

    @property
    def safety_snapshot(self) -> FanSafetySnapshot:
        """Return authoritative safety readback without advancing control."""

        passive = (
            not self.e_stop_latched
            and not self.manual_armed
            and not self.auto_requested
            and self.state
            in (FanControlState.SAFE_STOP, FanControlState.MANUAL_DISARMED)
        )
        return FanSafetySnapshot(
            e_stop_latched=self.e_stop_latched,
            control_state=self.state.value,
            enabled_observed=self._fan_enabled is not None,
            enabled=self._fan_enabled is True,
            manual_armed=self.manual_armed,
            legacy_auto_requested=self.auto_requested,
            legacy_auto_active=self.state is FanControlState.AUTO_ACTIVE,
            safety_reason=self._safety_reason,
            passive_for_takeover=passive,
        )

    def _stop_immediately(self) -> None:
        stop = self.config.fan_stop_pwm_us
        self.command_pwm = (stop, stop)
        self.auto_target_pwm = (stop, stop)
        self._auto_running = [False, False]

    def _clear_manual_cache(self) -> None:
        stop = self.config.fan_stop_pwm_us
        self._manual_pwm = [stop, stop]
        self._manual_at = [None, None]

    def _disarm_manual(self) -> None:
        self.manual_armed = False
        self._manual_neutral_received = False
        self._clear_manual_cache()

    def _clear_auto(self) -> None:
        self.auto_requested = False
        self._auto_pose_cutoff = self._pose_seq
        self.auto_target_pwm = (
            self.config.fan_stop_pwm_us,
            self.config.fan_stop_pwm_us,
        )
        self._auto_running = [False, False]

    def _clear_all_control(self) -> None:
        self._disarm_manual()
        self._clear_auto()

    def force_safe_stop(
        self,
        reason: str,
        *,
        state: FanControlState = FanControlState.SAFE_STOP,
        release_flight: bool = True,
    ) -> None:
        """幂等清除全部授权和旧命令，并请求立即发布停止值。"""
        self._clear_all_control()
        self._stop_immediately()
        self.state = state
        self._safety_reason = reason
        self._immediate_stop_pending = True
        self._flight_target_pwm = (
            self.config.fan_stop_pwm_us,
            self.config.fan_stop_pwm_us,
        )
        if release_flight:
            self.ownership.release_to_none()

    def take_immediate_stop(self) -> bool:
        pending = self._immediate_stop_pending
        self._immediate_stop_pending = False
        return pending

    def _fresh(self, timestamp: Optional[float], now: float, timeout: float) -> bool:
        return (
            math.isfinite(now)
            and timestamp is not None
            and 0.0 <= now - timestamp <= timeout
        )

    def update_e_stop(self, active: bool, now: float) -> bool:
        if not isinstance(active, bool) or not math.isfinite(now):
            self.force_safe_stop("急停输入或时间无效")
            return False
        self._e_stop_active = active
        self._e_stop_at = now
        if active:
            self.emergency_stop()
        return True

    def emergency_stop(self) -> None:
        self.e_stop_latched = True
        self._e_stop_active = True
        self._pose = None
        self._pose_at = None
        self.force_safe_stop(
            "收到系统急停；等待 /fans/reset_e_stop 显式复位",
            state=FanControlState.EMERGENCY_STOP,
        )

    def update_motor_mode(self, mode: str, now: float) -> bool:
        self._motor_mode_event_count += 1
        if (
            not isinstance(mode, str)
            or not mode.strip()
            or mode not in ALLOWED_MOTOR_MODES
            or not math.isfinite(now)
        ):
            self._motor_mode = None
            self._motor_mode_at = None
            state = (
                FanControlState.EMERGENCY_STOP
                if self.e_stop_latched
                else FanControlState.SAFE_STOP
            )
            self.force_safe_stop("收到未知或非法电机模式", state=state)
            return False

        self._motor_mode = mode
        self._motor_mode_at = now
        if mode not in CONTROL_READY_MOTOR_MODES:
            state = (
                FanControlState.EMERGENCY_STOP
                if self.e_stop_latched or mode == "EMERGENCY_STOP"
                else FanControlState.SAFE_STOP
            )
            self.force_safe_stop(f"电机模式 {mode} 不允许风扇输出", state=state)
        elif self.auto_requested and mode != "AUTO":
            self.force_safe_stop(
                "AUTO 因电机模式退出；等待重新显式授权",
                state=FanControlState.MANUAL_DISARMED,
            )
        return True

    def update_fan_enabled(self, enabled: bool, now: float) -> bool:
        if not isinstance(enabled, bool) or not math.isfinite(now):
            self._fan_enabled = None
            self._fan_enabled_at = None
            self.force_safe_stop("底层风扇 enabled 状态无效")
            return False
        self._fan_enabled = enabled
        self._fan_enabled_at = now
        if not enabled:
            state = (
                FanControlState.EMERGENCY_STOP
                if self.e_stop_latched
                else FanControlState.DISABLED
            )
            self.force_safe_stop("底层风扇已停用", state=state)
        return True

    def update_pose(self, roll_rad: float, pitch_rad: float, now: float) -> bool:
        if not all(math.isfinite(value) for value in (roll_rad, pitch_rad, now)):
            self.invalidate_pose()
            return False
        self._pose = (roll_rad, pitch_rad)
        self._pose_at = now
        self._pose_seq += 1
        return True

    def invalidate_pose(self) -> None:
        self._pose = None
        self._pose_at = None
        if self.auto_requested or self.manual_armed:
            self.force_safe_stop(
                "相对姿态失效；等待重新显式授权",
                state=FanControlState.SAFE_STOP,
            )

    def update_zero_generation(self, generation: int) -> bool:
        if not isinstance(generation, int) or generation < 0:
            self._zero_generation = None
            self._pose = None
            self._pose_at = None
            self.force_safe_stop("统一零点代次无效")
            return False
        changed = (
            self._zero_generation is None
            or generation != self._zero_generation
        )
        self._zero_generation = generation
        if changed:
            self._pose = None
            self._pose_at = None
            self.force_safe_stop("统一零点已变化；等待新姿态和重新授权")
        return True

    def _manual_values_valid(self, values: tuple[int, ...], now: float) -> bool:
        if not math.isfinite(now):
            return False
        return all(
            isinstance(value, int)
            and self.config.min_pwm_us <= value <= self.config.max_pwm_us
            for value in values
        )

    def update_manual_pair(self, left: int, right: int, now: float) -> bool:
        if not self._manual_values_valid((left, right), now):
            return False
        if (
            self.ownership.owner is not FanCommandOwner.LEGACY_MANUAL
            or not self.manual_armed
            or self.auto_requested
            or self.e_stop_latched
        ):
            return False
        failure = self._manual_precondition_failure(now)
        if failure:
            self.force_safe_stop(
                failure,
                state=FanControlState.MANUAL_DISARMED,
            )
            return False

        stop = self.config.fan_stop_pwm_us
        if not self._manual_neutral_received:
            if (left, right) != (stop, stop):
                return False
            self._manual_neutral_received = True
            self._manual_pwm = [stop, stop]
            self._manual_at = [now, now]
            self.state = FanControlState.MANUAL_WAITING
            return True

        self._manual_pwm = [int(left), int(right)]
        self._manual_at = [now, now]
        return True

    def update_manual_side(self, index: int, pwm: int, now: float) -> bool:
        if index not in (0, 1) or not self._manual_values_valid((pwm,), now):
            return False
        if (
            not self.manual_armed
            or self.ownership.owner is not FanCommandOwner.LEGACY_MANUAL
            or not self._manual_neutral_received
            or self.auto_requested
            or self.e_stop_latched
        ):
            return False
        failure = self._manual_precondition_failure(now)
        if failure:
            self.force_safe_stop(
                failure,
                state=FanControlState.MANUAL_DISARMED,
            )
            return False
        self._manual_pwm[index] = int(pwm)
        self._manual_at[index] = now
        return True

    def request_manual(self, enabled: bool, now: float) -> Tuple[bool, str]:
        if not isinstance(enabled, bool) or not math.isfinite(now):
            self.force_safe_stop("手动授权请求无效")
            return False, "手动授权请求或时间无效"
        if self.ownership.owner in (
            FanCommandOwner.FLIGHT_RESERVED,
            FanCommandOwner.FLIGHT_CONTROL,
        ):
            return False, "Flight ownership 活动，拒绝 MANUAL"
        if not enabled:
            self.force_safe_stop(
                "手动控制已取消；等待重新授权",
                state=FanControlState.MANUAL_DISARMED,
            )
            self.ownership.release_to_none()
            return True, "风扇 MANUAL 已关闭，旧命令已清除"

        failure = self._manual_precondition_failure(now)
        if failure:
            state = (
                FanControlState.EMERGENCY_STOP
                if self.e_stop_latched
                else FanControlState.SAFE_STOP
            )
            self.force_safe_stop(failure, state=state)
            return False, failure
        if self.auto_requested or self.state in (
            FanControlState.AUTO_WAITING,
            FanControlState.AUTO_ACTIVE,
        ):
            self.force_safe_stop("AUTO 尚未退出，不能启用 MANUAL")
            return False, "AUTO 当前已请求或活动，不能启用 MANUAL"

        self._clear_auto()
        self._disarm_manual()
        self.manual_armed = True
        self._manual_neutral_received = False
        self._stop_immediately()
        self._immediate_stop_pending = True
        self._safety_reason = ""
        self.state = FanControlState.MANUAL_WAITING_FOR_NEUTRAL
        self.ownership.claim_legacy_manual()
        return True, "MANUAL 已授权；等待本次授权后的双路停止基线"

    def request_auto(self, enabled: bool, now: float) -> Tuple[bool, str]:
        if not isinstance(enabled, bool) or not math.isfinite(now):
            self.force_safe_stop("AUTO 请求无效")
            return False, "AUTO 请求或时间无效"
        if self.ownership.owner in (
            FanCommandOwner.FLIGHT_RESERVED,
            FanCommandOwner.FLIGHT_CONTROL,
        ):
            return False, "Flight ownership 活动，拒绝 legacy AUTO"
        if not enabled:
            self.force_safe_stop(
                "风扇 AUTO 已关闭；等待重新显式选择控制路径",
                state=FanControlState.MANUAL_DISARMED,
            )
            return True, "风扇 AUTO 已关闭；MANUAL 授权和旧命令已清除"

        failure = self._auto_precondition_failure(now, require_new_pose=False)
        if failure:
            state = (
                FanControlState.EMERGENCY_STOP
                if self.e_stop_latched
                else FanControlState.SAFE_STOP
            )
            self.force_safe_stop(failure, state=state)
            return False, failure

        self._disarm_manual()
        self._clear_auto()
        self.auto_requested = True
        self._auto_pose_cutoff = self._pose_seq
        self._stop_immediately()
        self._immediate_stop_pending = True
        self._safety_reason = ""
        self.state = FanControlState.AUTO_WAITING
        self.ownership.claim_legacy_auto()
        return True, "风扇 AUTO 请求已接受，等待启用后的新姿态"

    def reset_e_stop(self, now: float) -> Tuple[bool, str]:
        if not math.isfinite(now):
            return False, "复位时间无效"
        if not self.e_stop_latched:
            return False, "系统急停当前未锁存"
        if self._e_stop_active is not False:
            return False, "急停输入仍为 true 或尚未明确观察到 false"
        if self._fan_enabled is not True or not self._fresh(
            self._fan_enabled_at, now, self.config.fan_enabled_timeout_sec
        ):
            return False, "底层风扇 enabled 状态缺失、过期或为 false"
        if self._motor_mode not in CONTROL_READY_MOTOR_MODES or not self._fresh(
            self._motor_mode_at, now, self.config.motor_mode_timeout_sec
        ):
            return False, "电机模式缺失、过期或不是合法的 MANUAL/AUTO"

        self.e_stop_latched = False
        self._pose = None
        self._pose_at = None
        self.force_safe_stop(
            "急停已复位；等待重新显式选择 MANUAL 或 AUTO",
            state=FanControlState.MANUAL_DISARMED,
        )
        return True, "风扇管理器急停已复位；输出保持停止且控制路径未授权"

    def _manual_precondition_failure(self, now: float) -> Optional[str]:
        if self.e_stop_latched:
            return "系统急停尚未显式复位"
        if self._e_stop_active is True:
            return "急停输入仍为 true"
        if self._fan_enabled is not True or not self._fresh(
            self._fan_enabled_at, now, self.config.fan_enabled_timeout_sec
        ):
            return "底层风扇未启用或 enabled 状态已超时"
        if self._motor_mode not in CONTROL_READY_MOTOR_MODES or not self._fresh(
            self._motor_mode_at, now, self.config.motor_mode_timeout_sec
        ):
            return "电机模式不是新鲜的 MANUAL/AUTO"
        return None

    def _auto_precondition_failure(
        self,
        now: float,
        *,
        require_new_pose: bool,
    ) -> Optional[str]:
        if self.e_stop_latched:
            return "系统急停尚未显式复位"
        if self._e_stop_active is True:
            return "急停输入仍为 true"
        if self._motor_mode != "AUTO" or not self._fresh(
            self._motor_mode_at, now, self.config.motor_mode_timeout_sec
        ):
            return "电机模式不是新鲜的 AUTO"
        if self._fan_enabled is not True or not self._fresh(
            self._fan_enabled_at, now, self.config.fan_enabled_timeout_sec
        ):
            return "底层风扇未启用或 enabled 状态已超时"
        if self._pose is None or not self._fresh(
            self._pose_at, now, self.config.imu_timeout_sec
        ):
            return "相对姿态无效或已超时"
        if require_new_pose and self._pose_seq <= self._auto_pose_cutoff:
            return "等待 AUTO 启用后的新姿态"
        return None

    def control_tick(self, now: float) -> FanControlOutput:
        """唯一正常输出推进入口；普通状态更新不得调用此方法。"""
        if not math.isfinite(now):
            self.force_safe_stop("控制单调时间无效")
            return self.output
        if self.ownership.timed_out(now):
            self.force_safe_stop("Flight command timeout；等待显式重新授权")
            return self.output
        if self.e_stop_latched:
            self._stop_immediately()
            self.state = FanControlState.EMERGENCY_STOP
            return self.output

        if self._fan_enabled is not True or not self._fresh(
            self._fan_enabled_at, now, self.config.fan_enabled_timeout_sec
        ):
            self.force_safe_stop(
                "底层风扇未启用或 enabled 状态已超时",
                state=FanControlState.DISABLED,
            )
            return self.output

        if self.ownership.owner is FanCommandOwner.FLIGHT_RESERVED:
            self._stop_immediately()
            self.state = FanControlState.FLIGHT_WAITING
            return self.output
        if self.ownership.owner is FanCommandOwner.FLIGHT_CONTROL:
            failure = self._flight_precondition_failure(now)
            if failure:
                self.force_safe_stop(failure)
                return self.output
            if self.ownership.last_command_sequence is None:
                self._stop_immediately()
                self.state = FanControlState.FLIGHT_WAITING
                return self.output
            self.command_pwm = tuple(
                slew_pwm(
                    self.command_pwm[index],
                    self._flight_target_pwm[index],
                    self.config.rise_step_pwm_us,
                    self.config.fall_step_pwm_us,
                )
                for index in (0, 1)
            )
            self.state = FanControlState.FLIGHT_ACTIVE
            return self.output

        if self.auto_requested:
            failure = self._auto_precondition_failure(now, require_new_pose=False)
            if failure:
                self.force_safe_stop(failure)
                return self.output
            if self._pose_seq <= self._auto_pose_cutoff:
                self._stop_immediately()
                self.state = FanControlState.AUTO_WAITING
                return self.output
            return self._step_auto()

        if self.manual_armed:
            failure = self._manual_precondition_failure(now)
            if failure:
                self.force_safe_stop(
                    failure,
                    state=FanControlState.MANUAL_DISARMED,
                )
                return self.output
            if not self._manual_neutral_received:
                self._stop_immediately()
                self.state = FanControlState.MANUAL_WAITING_FOR_NEUTRAL
                return self.output

            fresh = [
                self._fresh(
                    timestamp,
                    now,
                    self.config.manual_command_timeout_sec,
                )
                for timestamp in self._manual_at
            ]
            stop = self.config.fan_stop_pwm_us
            self.command_pwm = tuple(
                self._manual_pwm[index] if fresh[index] else stop
                for index in (0, 1)
            )
            self.auto_target_pwm = (stop, stop)
            self.state = (
                FanControlState.MANUAL_ACTIVE
                if any(
                    fresh[index] and self._manual_pwm[index] != stop
                    for index in (0, 1)
                )
                else FanControlState.MANUAL_WAITING
            )
            return self.output

        self._stop_immediately()
        if self.state not in (
            FanControlState.SAFE_STOP,
            FanControlState.DISABLED,
            FanControlState.EMERGENCY_STOP,
        ):
            self.state = FanControlState.MANUAL_DISARMED
        return self.output

    def step(self, now: float) -> FanControlOutput:
        """兼容纯逻辑调用；生产管理器只使用 control_tick。"""
        return self.control_tick(now)

    def _step_auto(self) -> FanControlOutput:
        left_activity, right_activity = attitude_activities(*self._pose)
        activities = (left_activity, right_activity)
        targets = []
        for index, activity in enumerate(activities):
            self._auto_running[index] = update_hysteresis(
                activity,
                self._auto_running[index],
                on_deg=self.config.fan_deadband_on_deg,
                off_deg=self.config.fan_deadband_off_deg,
            )
            targets.append(
                activity_to_pwm(
                    activity,
                    self._auto_running[index],
                    self.config,
                )
            )
        self.auto_target_pwm = tuple(targets)
        self.command_pwm = tuple(
            slew_pwm(
                self.command_pwm[index],
                targets[index],
                self.config.rise_step_pwm_us,
                self.config.fall_step_pwm_us,
            )
            for index in (0, 1)
        )
        self.state = FanControlState.AUTO_ACTIVE
        return self.output

    def _flight_precondition_failure(self, now: float) -> Optional[str]:
        if self.e_stop_latched or self._e_stop_active is True:
            return "系统急停覆盖 Flight ownership"
        if self._fan_enabled is not True or not self._fresh(
            self._fan_enabled_at, now, self.config.fan_enabled_timeout_sec
        ):
            return "底层风扇未启用或 enabled 状态已超时"
        if self._motor_mode not in CONTROL_READY_MOTOR_MODES or not self._fresh(
            self._motor_mode_at, now, self.config.motor_mode_timeout_sec
        ):
            return "电机模式不是新鲜的 MANUAL/AUTO"
        return None

    def prepare_flight_ownership(
        self, epoch: int, generation: int, *, now: float
    ) -> OwnershipResult:
        safe = self._flight_precondition_failure(now) is None
        result = self.ownership.prepare(epoch, generation, now=now, safe=safe)
        if result.success:
            self.force_safe_stop(
                "Flight ownership reserved；等待 commit",
                state=FanControlState.FLIGHT_WAITING,
                release_flight=False,
            )
        return result

    def commit_flight_ownership(
        self, epoch: int, generation: int, *, now: float
    ) -> OwnershipResult:
        safe = self._flight_precondition_failure(now) is None
        result = self.ownership.commit(epoch, generation, now=now, safe=safe)
        if result.success:
            self._stop_immediately()
            self.state = FanControlState.FLIGHT_WAITING
            self._safety_reason = ""
        return result

    def revoke_flight_ownership(self, epoch: int, generation: int) -> OwnershipResult:
        matches = (self.ownership.authority_epoch, self.ownership.generation) == (
            epoch,
            generation,
        )
        result = self.ownership.revoke(epoch, generation)
        if result.success and matches:
            self.force_safe_stop(
                "Flight ownership revoked；等待显式选择 legacy owner"
            )
        return result

    def update_flight_command(
        self,
        epoch: int,
        generation: int,
        sequence: int,
        left: float,
        right: float,
        *,
        now: float,
    ) -> OwnershipResult:
        try:
            target = (
                normalized_flight_command_to_pwm(left, self.config),
                normalized_flight_command_to_pwm(right, self.config),
            )
        except ValueError:
            return OwnershipResult(False, "invalid_fan_payload", epoch, generation)
        if self._flight_precondition_failure(now) is not None:
            return OwnershipResult(False, "flight_command_not_allowed", epoch, generation)
        result = self.ownership.accept_command(
            epoch, generation, sequence, now=now
        )
        if result.success:
            self._flight_target_pwm = target
        return result

    def accept_flight_safe_stop(
        self, epoch: int, generation: int, sequence: int, *, now: float
    ) -> OwnershipResult:
        accepted = self.ownership.accept_command(
            epoch, generation, sequence, now=now
        )
        if not accepted.success:
            return accepted
        self.force_safe_stop("Flight safe-stop；等待显式重新授权")
        return OwnershipResult(True, "revoked", epoch, generation)

    @property
    def output(self) -> FanControlOutput:
        return FanControlOutput(
            state=self.state,
            command_pwm=self.command_pwm,
            auto_target_pwm=self.auto_target_pwm,
            auto_enabled=self.auto_requested,
            auto_active=self.state == FanControlState.AUTO_ACTIVE,
        )
