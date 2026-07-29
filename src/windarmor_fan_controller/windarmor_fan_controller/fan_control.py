"""与 ROS 和硬件无关的双风扇命令仲裁与自动控制逻辑。"""

import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple


ALLOWED_MOTOR_MODES = {
    "MANUAL",
    "AUTO",
    "EMERGENCY_STOP",
    "DISABLED",
    "ERROR",
}


class FanControlState(str, Enum):
    SAFE_STOP = "SAFE_STOP"
    MANUAL_WAITING = "MANUAL_WAITING"
    MANUAL_ACTIVE = "MANUAL_ACTIVE"
    AUTO_WAITING = "AUTO_WAITING"
    AUTO_ACTIVE = "AUTO_ACTIVE"
    DISABLED = "DISABLED"
    EMERGENCY_STOP = "EMERGENCY_STOP"


@dataclass(frozen=True)
class FanControlConfig:
    min_pwm_us: int = 800
    max_pwm_us: int = 2200
    fan_stop_pwm_us: int = 800
    fan_start_pwm_us: int = 1200
    fan_auto_max_pwm_us: int = 1400
    fan_deadband_on_deg: float = 5.0
    fan_deadband_off_deg: float = 3.0
    fan_full_scale_deg: float = 45.0
    rise_step_pwm_us: int = 10
    fall_step_pwm_us: int = 20
    imu_timeout_sec: float = 0.2
    manual_command_timeout_sec: float = 0.5
    motor_mode_timeout_sec: float = 1.0
    fan_enabled_timeout_sec: float = 1.0
    require_motor_mode_for_manual: bool = False

    def validate(self) -> None:
        values = (
            self.fan_deadband_on_deg,
            self.fan_deadband_off_deg,
            self.fan_full_scale_deg,
            self.imu_timeout_sec,
            self.manual_command_timeout_sec,
            self.motor_mode_timeout_sec,
            self.fan_enabled_timeout_sec,
        )
        if not all(math.isfinite(value) for value in values):
            raise ValueError("风扇控制浮点参数必须为有限值")
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
        if self.rise_step_pwm_us <= 0 or self.fall_step_pwm_us <= 0:
            raise ValueError("风扇 PWM 上升和下降步长必须大于 0")
        if (
            self.imu_timeout_sec <= 0.0
            or self.manual_command_timeout_sec <= 0.0
            or self.motor_mode_timeout_sec <= 0.0
            or self.fan_enabled_timeout_sec <= 0.0
        ):
            raise ValueError("全部超时参数必须大于 0")


@dataclass(frozen=True)
class FanControlOutput:
    state: FanControlState
    command_pwm: Tuple[int, int]
    auto_target_pwm: Tuple[int, int]
    auto_enabled: bool
    auto_active: bool


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


def activity_to_pwm(activity_deg: float, running: bool, config: FanControlConfig) -> int:
    if not running:
        return config.fan_stop_pwm_us
    ratio = (activity_deg - config.fan_deadband_on_deg) / (
        config.fan_full_scale_deg - config.fan_deadband_on_deg
    )
    ratio = max(0.0, min(1.0, ratio))
    pwm = config.fan_start_pwm_us + ratio * (
        config.fan_auto_max_pwm_us - config.fan_start_pwm_us
    )
    return int(round(pwm))


def slew_pwm(current: int, target: int, rise_step: int, fall_step: int) -> int:
    difference = target - current
    limited = max(-fall_step, min(rise_step, difference))
    return current + limited


class FanControlCore:
    """维护手动/自动缓存、急停锁存和唯一安全输出。"""

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

        self._manual_pwm = [stop, stop]
        self._manual_at: list[Optional[float]] = [None, None]
        self._pose: Optional[Tuple[float, float]] = None
        self._pose_at: Optional[float] = None
        self._pose_seq = 0
        self._zero_generation: Optional[int] = None

        self._motor_mode: Optional[str] = None
        self._motor_mode_at: Optional[float] = None
        self._motor_mode_seq = 0
        self._fan_enabled: Optional[bool] = None
        self._fan_enabled_at: Optional[float] = None
        self._fan_enabled_seq = 0

        self.e_stop_latched = False
        self._recovery_fan_seq = 0
        self._recovery_motor_seq = 0

    def _stop_immediately(self) -> None:
        stop = self.config.fan_stop_pwm_us
        self.command_pwm = (stop, stop)
        self.auto_target_pwm = (stop, stop)
        self._auto_running = [False, False]

    def _clear_manual(self) -> None:
        stop = self.config.fan_stop_pwm_us
        self._manual_pwm = [stop, stop]
        self._manual_at = [None, None]

    def _clear_auto(self) -> None:
        self.auto_requested = False
        self._auto_pose_cutoff = self._pose_seq
        self._stop_immediately()

    def _clear_all_commands(self) -> None:
        self._clear_manual()
        self._clear_auto()

    def _fresh(self, timestamp: Optional[float], now: float, timeout: float) -> bool:
        return timestamp is not None and 0.0 <= now - timestamp <= timeout

    def update_motor_mode(self, mode: str, now: float) -> bool:
        if mode not in ALLOWED_MOTOR_MODES or not math.isfinite(now):
            self._clear_all_commands()
            self.state = FanControlState.SAFE_STOP
            return False
        self._motor_mode = mode
        self._motor_mode_at = now
        self._motor_mode_seq += 1
        if self.auto_requested and mode != "AUTO":
            self._clear_auto()
        self._try_clear_e_stop(now)
        return True

    def update_fan_enabled(self, enabled: bool, now: float) -> None:
        self._fan_enabled = bool(enabled)
        self._fan_enabled_at = now
        self._fan_enabled_seq += 1
        if not enabled:
            self._clear_all_commands()
            self.state = FanControlState.DISABLED
        self._try_clear_e_stop(now)

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
        if self.auto_requested:
            self._clear_auto()
            self.state = FanControlState.SAFE_STOP

    def update_zero_generation(self, generation: int) -> None:
        if generation < 0:
            self._clear_auto()
            self.invalidate_pose()
            return
        changed = (
            self._zero_generation is None
            or generation != self._zero_generation
        )
        self._zero_generation = generation
        if changed:
            self.invalidate_pose()
            self._clear_auto()
            self.state = FanControlState.SAFE_STOP

    def update_manual_pair(self, left: int, right: int, now: float) -> bool:
        if not self._manual_values_valid((left, right), now):
            return False
        if self.auto_requested or self.e_stop_latched:
            return False
        self._manual_pwm = [int(left), int(right)]
        self._manual_at = [now, now]
        return True

    def update_manual_side(self, index: int, pwm: int, now: float) -> bool:
        if index not in (0, 1) or not self._manual_values_valid((pwm,), now):
            return False
        if self.auto_requested or self.e_stop_latched:
            return False
        self._manual_pwm[index] = int(pwm)
        self._manual_at[index] = now
        return True

    def _manual_values_valid(self, values: tuple[int, ...], now: float) -> bool:
        if not math.isfinite(now):
            return False
        return all(
            isinstance(value, int)
            and self.config.min_pwm_us <= value <= self.config.max_pwm_us
            for value in values
        )

    def request_auto(self, enabled: bool, now: float) -> Tuple[bool, str]:
        if not enabled:
            self._clear_all_commands()
            return True, "风扇 AUTO 已关闭；手动缓存已清除"
        failure = self._auto_precondition_failure(now, require_new_pose=False)
        if failure:
            self._clear_auto()
            return False, failure
        self._clear_manual()
        self._clear_auto()
        self.auto_requested = True
        self._auto_pose_cutoff = self._pose_seq
        self.state = FanControlState.AUTO_WAITING
        return True, "风扇 AUTO 请求已接受，等待启用后的新姿态"

    def emergency_stop(self) -> None:
        self.e_stop_latched = True
        self._recovery_fan_seq = self._fan_enabled_seq
        self._recovery_motor_seq = self._motor_mode_seq
        self._clear_all_commands()
        self._pose = None
        self._pose_at = None
        self.state = FanControlState.EMERGENCY_STOP

    def _try_clear_e_stop(self, now: float) -> None:
        if not self.e_stop_latched:
            return
        fan_recovered = (
            self._fan_enabled_seq > self._recovery_fan_seq
            and self._fan_enabled is True
            and self._fresh(
                self._fan_enabled_at,
                now,
                self.config.fan_enabled_timeout_sec,
            )
        )
        if self.config.require_motor_mode_for_manual:
            motor_recovered = (
                self._motor_mode_seq > self._recovery_motor_seq
                and self._motor_mode in ("MANUAL", "AUTO")
                and self._fresh(
                    self._motor_mode_at,
                    now,
                    self.config.motor_mode_timeout_sec,
                )
            )
        else:
            motor_recovered = True
        if fan_recovered and motor_recovered:
            self.e_stop_latched = False
            self.state = FanControlState.MANUAL_WAITING

    def _auto_precondition_failure(
        self,
        now: float,
        *,
        require_new_pose: bool,
    ) -> Optional[str]:
        if self.e_stop_latched:
            return "系统急停尚未完成恢复"
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

    def step(self, now: float) -> FanControlOutput:
        if self.e_stop_latched:
            self._stop_immediately()
            self.state = FanControlState.EMERGENCY_STOP
            return self.output

        if self._fan_enabled is not True or not self._fresh(
            self._fan_enabled_at, now, self.config.fan_enabled_timeout_sec
        ):
            self._clear_all_commands()
            self.state = FanControlState.DISABLED
            return self.output

        if self.auto_requested:
            failure = self._auto_precondition_failure(now, require_new_pose=False)
            if failure:
                self._clear_auto()
                self.state = FanControlState.SAFE_STOP
                return self.output
            if self._pose_seq <= self._auto_pose_cutoff:
                self._stop_immediately()
                self.state = FanControlState.AUTO_WAITING
                return self.output
            return self._step_auto()

        if self.config.require_motor_mode_for_manual and (
            self._motor_mode not in ("MANUAL", "AUTO")
            or not self._fresh(
                self._motor_mode_at,
                now,
                self.config.motor_mode_timeout_sec,
            )
        ):
            self._clear_manual()
            self._stop_immediately()
            self.state = FanControlState.SAFE_STOP
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
            if any(fresh)
            else FanControlState.MANUAL_WAITING
        )
        return self.output

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

    @property
    def output(self) -> FanControlOutput:
        return FanControlOutput(
            state=self.state,
            command_pwm=self.command_pwm,
            auto_target_pwm=self.auto_target_pwm,
            auto_enabled=self.auto_requested,
            auto_active=self.state == FanControlState.AUTO_ACTIVE,
        )
