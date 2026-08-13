"""Explicit import-and-factory loading for pure FlightController objects."""

from __future__ import annotations

import importlib
import inspect
from typing import Iterable, Mapping

from ..core.controller import FlightController


class ControllerLoadError(RuntimeError):
    pass


def load_controller(
    factory_contract: str,
    required_motor_names: Iterable[str],
    configuration: Mapping[str, object] | None = None,
) -> FlightController:
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
