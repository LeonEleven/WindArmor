"""默认 DRY_RUN 示例工厂；其中的目标不是机械参考值。"""

from __future__ import annotations

from collections.abc import Mapping

from ..core.controller import FlightController
from .example_controller import NeutralExampleController


def create_controller(
    required_motor_names: tuple[str, ...],
    configuration: Mapping[str, object] | None = None,
) -> FlightController:
    """为每个逻辑键使用测试专用零值创建 API 示例。"""

    del configuration
    return NeutralExampleController(
        {name: 0.0 for name in required_motor_names}
    )
