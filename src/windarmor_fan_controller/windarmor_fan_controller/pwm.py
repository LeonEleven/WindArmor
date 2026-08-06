"""与硬件无关的 PWM 换算与限幅逻辑。"""

import math
from dataclasses import dataclass
from typing import Optional


def validate_positive_finite_timeout(value) -> float:
    """返回正有限超时；非法值不得被解释为关闭安全看门狗。"""
    try:
        timeout = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("command_timeout_sec 必须是正有限数值") from exc
    if not math.isfinite(timeout) or timeout <= 0.0:
        raise ValueError("command_timeout_sec 必须是正有限数值")
    return timeout


@dataclass(frozen=True)
class PwmRange:
    """涵道风扇电调使用的 PWM 范围。"""

    minimum_us: int = 800
    maximum_us: int = 2200

    def __post_init__(self) -> None:
        if self.minimum_us >= self.maximum_us:
            raise ValueError("minimum_us 必须小于 maximum_us")

    def clamp(self, pwm_us: int) -> int:
        """把脉宽限制在电调允许的范围内。"""
        return max(self.minimum_us, min(self.maximum_us, int(pwm_us)))

    def to_servo_value(self, pwm_us: int) -> float:
        """把微秒脉宽线性映射到 gpiozero Servo 的 [-1, 1]。"""
        safe_pwm = self.clamp(pwm_us)
        span = self.maximum_us - self.minimum_us
        return ((safe_pwm - self.minimum_us) / span) * 2.0 - 1.0


class FanCommandGate:
    """底层 enabled 锁存和命令看门狗的纯状态逻辑。"""

    def __init__(self, *, enabled: bool = True) -> None:
        self.enabled = bool(enabled)
        self.last_command_time: Optional[float] = None
        self.timed_out = False

    def accept(self, now: float) -> bool:
        if not self.enabled or not math.isfinite(now):
            return False
        self.last_command_time = now
        self.timed_out = False
        return True

    def disable(self) -> None:
        self.enabled = False
        self.last_command_time = None
        self.timed_out = False

    def enable(self) -> None:
        self.enabled = True
        self.last_command_time = None
        self.timed_out = False

    def check_timeout(self, now: float, timeout: float) -> bool:
        timeout = validate_positive_finite_timeout(timeout)
        if (
            not self.enabled
            or self.last_command_time is None
        ):
            return False
        if now - self.last_command_time <= timeout:
            return False
        self.last_command_time = None
        self.timed_out = True
        return True
