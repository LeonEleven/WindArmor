#!/usr/bin/env python3
"""Prewarmed E-STOP watchdog for authorized Flight hardware verification."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from enum import Enum
import math
import sys
import time
from typing import Callable, Optional

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import Bool
from windarmor_interfaces.msg import FlightAuthorityStatus


class WatchdogEvent(Enum):
    READY = "ready"
    READINESS_TIMEOUT = "readiness_timeout"
    ACTIVE_DETECTED = "active_detected"
    ESTOP_ACTIVE_DELAY = "estop_active_delay"
    ESTOP_NO_ACTIVE_TIMEOUT = "estop_no_active_timeout"


def _positive_finite(value: float, name: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0.0
    ):
        raise ValueError(f"{name} must be a positive finite number")
    return float(value)


def _finite_non_negative(value: float, name: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0.0
    ):
        raise ValueError(f"{name} must be a finite non-negative number")
    return float(value)


@dataclass
class GateCEstopWatchdogCore:
    """Pure monotonic trigger and deadline state for the verification tool."""

    started_at: float
    delay_sec: float = 2.0
    active_timeout_sec: float = 10.0
    publisher_ready_timeout_sec: float = 10.0

    def __post_init__(self) -> None:
        self.delay_sec = _positive_finite(self.delay_sec, "delay_sec")
        if self.delay_sec >= 3.0:
            raise ValueError("delay_sec must be less than 3.0")
        self.active_timeout_sec = _positive_finite(
            self.active_timeout_sec, "active_timeout_sec"
        )
        self.publisher_ready_timeout_sec = _positive_finite(
            self.publisher_ready_timeout_sec,
            "publisher_ready_timeout_sec",
        )
        self.started_at = _finite_non_negative(self.started_at, "started_at")
        self.ready_at: Optional[float] = None
        self.active_detected_at: Optional[float] = None
        self.estop_requested_at: Optional[float] = None
        self.estop_reason: Optional[str] = None
        self.readiness_failed = False
        self._last_now = self.started_at

    def _validate_now(self, now: float) -> float:
        current = _finite_non_negative(now, "monotonic time")
        if current < self._last_now:
            raise ValueError("monotonic time moved backwards")
        self._last_now = current
        return current

    def update_publisher_readiness(
        self,
        subscription_count: int,
        now: float,
    ) -> Optional[WatchdogEvent]:
        current = self._validate_now(now)
        if (
            isinstance(subscription_count, bool)
            or not isinstance(subscription_count, int)
            or subscription_count < 0
        ):
            raise ValueError("subscription_count must be a non-negative integer")
        if self.ready_at is not None or self.readiness_failed:
            return None
        if subscription_count >= 1:
            self.ready_at = current
            return WatchdogEvent.READY
        if current - self.started_at >= self.publisher_ready_timeout_sec:
            self.readiness_failed = True
            return WatchdogEvent.READINESS_TIMEOUT
        return None

    def observe_authority(
        self,
        *,
        authority_state: str,
        command_authority: str,
        actuation_allowed: bool,
        now: float,
    ) -> Optional[WatchdogEvent]:
        current = self._validate_now(now)
        if (
            self.ready_at is None
            or self.readiness_failed
            or self.estop_requested_at is not None
            or self.active_detected_at is not None
        ):
            return None
        if (
            authority_state == "ACTIVE"
            and command_authority == "FLIGHT_CONTROL"
            and actuation_allowed is True
        ):
            self.active_detected_at = current
            return WatchdogEvent.ACTIVE_DETECTED
        return None

    def tick(self, now: float) -> Optional[WatchdogEvent]:
        current = self._validate_now(now)
        if (
            self.ready_at is None
            or self.readiness_failed
            or self.estop_requested_at is not None
        ):
            return None
        if self.active_detected_at is not None:
            if current - self.active_detected_at < self.delay_sec:
                return None
            event = WatchdogEvent.ESTOP_ACTIVE_DELAY
        else:
            if current - self.ready_at < self.active_timeout_sec:
                return None
            event = WatchdogEvent.ESTOP_NO_ACTIVE_TIMEOUT
        self.estop_requested_at = current
        self.estop_reason = event.value
        return event


class FlightEstopWatchdog(Node):
    """Observe Flight authority and publish only a latched E-STOP request."""

    def __init__(
        self,
        *,
        delay_sec: float = 2.0,
        active_timeout_sec: float = 10.0,
        publisher_ready_timeout_sec: float = 10.0,
        monotonic_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__("flight_estop_watchdog")
        self._monotonic = monotonic_fn
        self._logic = GateCEstopWatchdogCore(
            started_at=self._monotonic(),
            delay_sec=delay_sec,
            active_timeout_sec=active_timeout_sec,
            publisher_ready_timeout_sec=publisher_ready_timeout_sec,
        )
        self._done = False
        self._exit_code = 0
        self._post_publish_deadline: Optional[float] = None
        self._estop_observed = False

        command_qos = QoSProfile(
            depth=10,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
        )
        self._estop_pub = self.create_publisher(Bool, "/e_stop", command_qos)
        self._authority_sub = self.create_subscription(
            FlightAuthorityStatus,
            "/flight_control/authority/status",
            self._on_authority_status,
            command_qos,
        )
        self._timer = self.create_timer(0.02, self._tick)

    @property
    def done(self) -> bool:
        return self._done

    @property
    def exit_code(self) -> int:
        return self._exit_code

    def _on_authority_status(self, message: FlightAuthorityStatus) -> None:
        now = self._monotonic()
        event = self._logic.observe_authority(
            authority_state=message.authority_state,
            command_authority=message.command_authority,
            actuation_allowed=message.actuation_allowed,
            now=now,
        )
        if event is WatchdogEvent.ACTIVE_DETECTED:
            print("ACTIVE DETECTED", flush=True)
            print("E-STOP TIMER START", flush=True)
            print(f"ACTIVE_DETECTED_MONOTONIC={now:.9f}", flush=True)

        if (
            self._logic.estop_requested_at is not None
            and not self._estop_observed
            and message.global_e_stop_active
            and not message.actuation_allowed
        ):
            self._estop_observed = True
            elapsed = now - self._logic.estop_requested_at
            print("ESTOP OBSERVED BY FLIGHT", flush=True)
            print(f"PUBLISH_TO_INHIBIT_SEC={elapsed:.9f}", flush=True)
            self._done = True

    def _publish_estop(self, event: WatchdogEvent, now: float) -> None:
        if event is WatchdogEvent.ESTOP_NO_ACTIVE_TIMEOUT:
            print("NO ACTIVE WITHIN TIMEOUT", flush=True)
        message = Bool()
        message.data = True
        self._estop_pub.publish(message)
        print("E-STOP PUBLISHED", flush=True)
        print(f"ESTOP_PUBLISHED_MONOTONIC={now:.9f}", flush=True)
        if self._logic.active_detected_at is not None:
            elapsed = now - self._logic.active_detected_at
            print(f"ACTIVE_TO_PUBLISH_SEC={elapsed:.9f}", flush=True)
        self._post_publish_deadline = now + 1.0

    def _tick(self) -> None:
        now = self._monotonic()
        if self._logic.ready_at is None:
            event = self._logic.update_publisher_readiness(
                self._estop_pub.get_subscription_count(),
                now,
            )
            if event is WatchdogEvent.READY:
                print("WATCHDOG READY", flush=True)
                print(f"WATCHDOG_READY_MONOTONIC={now:.9f}", flush=True)
            elif event is WatchdogEvent.READINESS_TIMEOUT:
                print(
                    "WATCHDOG NOT READY: NO E-STOP SUBSCRIBER",
                    file=sys.stderr,
                    flush=True,
                )
                self._exit_code = 2
                self._done = True
            return

        event = self._logic.tick(now)
        if event in {
            WatchdogEvent.ESTOP_ACTIVE_DELAY,
            WatchdogEvent.ESTOP_NO_ACTIVE_TIMEOUT,
        }:
            self._publish_estop(event, now)
        if (
            self._post_publish_deadline is not None
            and now >= self._post_publish_deadline
        ):
            self._done = True


def _delay(value: str) -> float:
    try:
        delay = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("delay must be a number") from exc
    try:
        checked = _positive_finite(delay, "delay_sec")
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc
    if checked >= 3.0:
        raise argparse.ArgumentTypeError("delay_sec must be less than 3.0")
    return checked


def _timeout(value: str) -> float:
    try:
        timeout = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("timeout must be a number") from exc
    try:
        return _positive_finite(timeout, "timeout")
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def parse_arguments(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delay-sec", type=_delay, default=2.0)
    parser.add_argument("--active-timeout-sec", type=_timeout, default=10.0)
    parser.add_argument(
        "--publisher-ready-timeout-sec",
        type=_timeout,
        default=10.0,
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    options = parse_arguments(argv)
    rclpy.init(args=[])
    node: Optional[FlightEstopWatchdog] = None
    try:
        node = FlightEstopWatchdog(
            delay_sec=options.delay_sec,
            active_timeout_sec=options.active_timeout_sec,
            publisher_ready_timeout_sec=options.publisher_ready_timeout_sec,
        )
        while rclpy.ok() and not node.done:
            rclpy.spin_once(node, timeout_sec=0.1)
        return node.exit_code if node.done else 1
    except KeyboardInterrupt:
        return 130
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
