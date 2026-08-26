"""面向新人示例控制器、易读的纯软件 DRY_RUN。"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import replace
from typing import Iterable, TextIO

from .core.authority import CommandAuthority
from .core.models import FlightCommand, FlightState
from .core.validation import validate_flight_command, validate_flight_state
from .runtime.controller_loader import load_controller
from .testing import make_fake_flight_state, make_stale_flight_state


MOTOR_NAMES = ("left_lift", "left_pitch", "right_pitch", "right_lift")
CONTROLLER_FACTORY = (
    "windarmor_flight_control.algorithms."
    "example_algorithm_controller:create_controller"
)


def _synthetic_state(pitch_rad: float, sequence: int) -> FlightState:
    state = make_fake_flight_state(MOTOR_NAMES)
    return replace(
        state,
        timestamp_sec=1.0 + sequence * 0.02,
        sequence=sequence,
        imu=replace(
            state.imu,
            pitch_rad=pitch_rad,
            relative_pitch_rad=pitch_rad,
        ),
        fans=replace(state.fans, control_state="SAFE_STOP"),
        system=replace(
            state.system,
            command_authority=CommandAuthority.NONE,
            authority_epoch=0,
            authority_generation=0,
            motor_control_mode="MANUAL",
            fan_control_state="SAFE_STOP",
            flight_control_active=False,
            actuation_allowed=False,
            required_inputs_fresh=True,
        ),
    )


def _print_command(
    stream: TextIO,
    *,
    pitch_rad: float | None,
    command: FlightCommand,
) -> None:
    pitch_text = "stale" if pitch_rad is None else f"{pitch_rad:+.3f} rad"
    print(f"input: pitch = {pitch_text}", file=stream)
    if command.request_safe_stop:
        print("output: safe_stop = true (no motor/fan payload)", file=stream)
    else:
        assert command.motor_positions_rad is not None
        assert command.fan_commands is not None
        print(
            "output: left_pitch target = "
            f"{command.motor_positions_rad['left_pitch']:+.4f} rad",
            file=stream,
        )
        print(f"        fan_left = {command.fan_commands.left:.3f}", file=stream)
        print(f"        fan_right = {command.fan_commands.right:.3f}", file=stream)
        print("        safe_stop = false", file=stream)
    print("dispatch: preview only; authority=NONE; actuation_allowed=false", file=stream)
    print(file=stream)


def run_demo(pitches_rad: Iterable[float], stream: TextIO = sys.stdout) -> None:
    """运行确定性的 fake 周期，且不构造 ROS 或硬件对象。"""

    pitches = tuple(float(value) for value in pitches_rad)
    if not pitches or any(not math.isfinite(value) for value in pitches):
        raise ValueError("pitches must contain finite values")

    controller = load_controller(CONTROLLER_FACTORY, MOTOR_NAMES)
    controller.reset()
    print("WindArmor software-only synthetic DRY_RUN", file=stream)
    print("hardware access: NO (no ROS, CAN, serial, GPIO, PWM, ESC, or actuator)", file=stream)
    print(f"controller: {CONTROLLER_FACTORY}", file=stream)
    print(file=stream)

    for sequence, pitch_rad in enumerate(pitches, start=1):
        state = _synthetic_state(pitch_rad, sequence)
        validate_flight_state(state, MOTOR_NAMES)
        command = controller.update(state, dt=0.02)
        validate_flight_command(command, MOTOR_NAMES)
        _print_command(stream, pitch_rad=pitch_rad, command=command)

    stale = make_stale_flight_state(MOTOR_NAMES)
    stale = replace(
        stale,
        system=replace(
            stale.system,
            command_authority=CommandAuthority.NONE,
            authority_epoch=0,
            authority_generation=0,
            flight_control_active=False,
            actuation_allowed=False,
        ),
    )
    validate_flight_state(stale, MOTOR_NAMES)
    stale_command = controller.update(stale, dt=0.02)
    validate_flight_command(stale_command, MOTOR_NAMES)
    _print_command(stream, pitch_rad=None, command=stale_command)


def main(argv: list[str] | None = None, stream: TextIO = sys.stdout) -> int:
    parser = argparse.ArgumentParser(
        description="Run the WindArmor software-only synthetic DRY_RUN demo."
    )
    parser.add_argument(
        "--pitches",
        type=float,
        nargs="+",
        default=(-0.30, -0.10, 0.0, 0.10, 0.30),
        metavar="RAD",
        help="synthetic relative pitch values in radians",
    )
    args = parser.parse_args(argv)
    run_demo(args.pitches, stream=stream)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
