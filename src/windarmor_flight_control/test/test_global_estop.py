from windarmor_flight_control.runtime.state_aggregator import StateAggregator

from .runtime_helpers import (
    fan_safety_message,
    motor_safety_message,
    runtime_config,
)


def aggregator():
    return StateAggregator(runtime_config(motor_names=["axis_a"]))


def estop(value, agg, now):
    return agg.build_snapshot(now).system.e_stop_active is value


def test_both_unknown_and_each_one_sided_false_are_unknown():
    agg = aggregator()
    assert estop(None, agg, 10.0)
    agg.update_motor_safety(motor_safety_message(), 10.1)
    assert estop(None, agg, 10.1)

    agg = aggregator()
    agg.update_fan_safety(fan_safety_message(), 10.1)
    assert estop(None, agg, 10.1)


def test_both_fresh_false_clear_but_stale_false_returns_unknown():
    agg = aggregator()
    agg.update_motor_safety(motor_safety_message(), 10.0)
    agg.update_fan_safety(fan_safety_message(), 10.0)
    assert estop(False, agg, 10.1)
    assert estop(None, agg, 12.0)


def test_any_known_latched_true_dominates_other_stale_or_unknown():
    agg = aggregator()
    agg.update_motor_safety(
        motor_safety_message(
            controller_state="EMERGENCY_STOP",
            public_control_mode="EMERGENCY_STOP",
            e_stop_latched=True,
        ),
        10.0,
    )
    assert estop(True, agg, 100.0)


def test_trigger_true_is_immediate_and_false_never_clears_by_itself():
    agg = aggregator()
    agg.update_e_stop(True, 10.0)
    assert estop(True, agg, 10.0)
    agg.update_e_stop(False, 10.1)
    assert estop(True, agg, 10.1)


def test_trigger_clears_only_after_both_new_authoritative_false_readbacks():
    agg = aggregator()
    agg.update_motor_safety(motor_safety_message(), 9.0)
    agg.update_fan_safety(fan_safety_message(), 9.0)
    agg.update_e_stop(True, 10.0)
    assert estop(True, agg, 10.0)
    agg.update_motor_safety(motor_safety_message(sequence=2), 10.1)
    assert estop(True, agg, 10.1)
    agg.update_fan_safety(fan_safety_message(sequence=2), 10.2)
    assert estop(False, agg, 10.2)
