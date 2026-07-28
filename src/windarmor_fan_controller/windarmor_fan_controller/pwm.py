"""与硬件无关的 PWM 换算与限幅逻辑。"""

from dataclasses import dataclass


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
