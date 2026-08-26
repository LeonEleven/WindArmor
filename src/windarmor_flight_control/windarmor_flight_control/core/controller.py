"""飞控算法控制器的统一接口契约。"""

from __future__ import annotations

from typing import Protocol

from .models import FlightCommand, FlightState


class FlightController(Protocol):
    """不依赖 ROS 或真实硬件的纯算法控制器。"""

    def reset(self) -> None:
        """只重置算法内部状态。"""
        ...

    def update(self, state: FlightState, dt: float) -> FlightCommand:
        """使用以单调时钟秒数表示的正 ``dt``，把状态快照映射为控制意图。

        控制器必须接受可变更新间隔。普通结果包含完整的配置电机帧；输入不可用时
        应返回 safe-stop。
        """
        ...
