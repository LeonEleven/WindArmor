"""最小 API 示例；这不是真实飞控算法。"""

from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

from ..core.models import FanCommand, FlightCommand, FlightState


class NeutralExampleController:
    """返回调用方配置的中性电机目标和停止风扇命令。

    本类只用于演示和测试 Flight API。配置的目标并不代表任何真实机器人的机械中位。
    """

    def __init__(self, neutral_motor_positions_rad: Mapping[str, float]) -> None:
        self._neutral_motor_positions_rad = MappingProxyType(
            dict(neutral_motor_positions_rad)
        )

    def reset(self) -> None:
        """重置算法内部状态；本无状态示例没有需要清理的内容。"""

    def update(self, state: FlightState, dt: float) -> FlightCommand:
        """构造中性帧；输入被闭锁时请求安全停止。"""

        del dt
        if (
            state.system.e_stop_active is not False
            or not state.system.actuation_allowed
            or not state.system.required_inputs_fresh
        ):
            return FlightCommand.safe_stop()
        return FlightCommand(
            motor_positions_rad=self._neutral_motor_positions_rad,
            fan_commands=FanCommand(left=0.0, right=0.0),
        )
