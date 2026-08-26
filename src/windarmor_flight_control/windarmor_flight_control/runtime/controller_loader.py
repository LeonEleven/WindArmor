"""通过显式导入和工厂函数加载纯 ``FlightController`` 对象。"""

from __future__ import annotations

import importlib
import inspect
from typing import Iterable, Mapping

from ..core.controller import FlightController


class ControllerLoadError(RuntimeError):
    """配置的控制器导入或工厂契约失败。"""


def load_controller(
    factory_contract: str,
    required_motor_names: Iterable[str],
    configuration: Mapping[str, object] | None = None,
) -> FlightController:
    """按 ``module.path:factory`` 加载，且不回退、不产生控制权副作用。

    工厂函数接收必要电机名称；函数签名允许时，还接收可选配置映射。导入或工厂函数
    失败属于配置错误；算法模块在加载期间不得依赖 ROS 或硬件副作用。
    """

    if not isinstance(factory_contract, str) or factory_contract.count(":") != 1:
        raise ControllerLoadError(
            "controller_factory must use 'module.path:factory_name'"
        )
    module_name, factory_name = factory_contract.split(":", 1)
    if not module_name or not factory_name:
        raise ControllerLoadError(
            "controller_factory must use 'module.path:factory_name'"
        )
    try:
        module = importlib.import_module(module_name)
        factory = getattr(module, factory_name)
        if not callable(factory):
            raise TypeError("configured factory is not callable")
        names = tuple(required_motor_names)
        settings = dict(configuration or {})
        signature = inspect.signature(factory)
        try:
            signature.bind(names, settings)
        except TypeError:
            signature.bind(names)
            controller = factory(names)
        else:
            controller = factory(names, settings)
    except Exception as exc:
        raise ControllerLoadError(
            f"failed to load controller factory {factory_contract!r}: {exc}"
        ) from exc
    if not callable(getattr(controller, "reset", None)) or not callable(
        getattr(controller, "update", None)
    ):
        raise ControllerLoadError(
            "controller factory result must provide reset() and update()"
        )
    return controller
