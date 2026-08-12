from types import SimpleNamespace

import pytest

from windarmor_flight_control.runtime.fan_adapter import FanAdapter


def test_pwm_endpoints_are_normalized_without_rpm_or_thrust() -> None:
    adapter = FanAdapter(800.0, 2200.0)
    adapter.update_output(SimpleNamespace(data=[800, 2200]), 1.0)
    fans = adapter.snapshot(
        now=1.0, output_freshness_sec=1.0, state_freshness_sec=1.0
    )
    assert fans.left.applied_command == 0.0
    assert fans.right.applied_command == 1.0
    assert not hasattr(fans.left, "rpm")
    assert not hasattr(fans.left, "thrust")


@pytest.mark.parametrize("values", [[800], [800, 900, 1000], [799, 800], [800, 2201]])
def test_wrong_length_or_out_of_range_becomes_unknown(values) -> None:
    adapter = FanAdapter(800.0, 2200.0)
    adapter.update_output(SimpleNamespace(data=[800, 800]), 1.0)
    with pytest.raises(ValueError):
        adapter.update_output(SimpleNamespace(data=values), 1.1)
    fans = adapter.snapshot(
        now=1.1, output_freshness_sec=1.0, state_freshness_sec=1.0
    )
    assert not fans.left.output_known
    assert fans.left.applied_command is None


def test_stale_output_enabled_and_control_state_revert_to_unknown() -> None:
    adapter = FanAdapter(800.0, 2200.0)
    adapter.update_output(SimpleNamespace(data=[1000, 1200]), 1.0)
    adapter.update_enabled(False, 1.0)
    adapter.update_control_state("DISABLED", 1.0)
    fresh = adapter.snapshot(
        now=1.5, output_freshness_sec=1.0, state_freshness_sec=1.0
    )
    assert fresh.enabled is False
    assert fresh.control_state == "DISABLED"
    stale = adapter.snapshot(
        now=2.1, output_freshness_sec=1.0, state_freshness_sec=1.0
    )
    assert stale.enabled is None
    assert stale.control_state is None
    assert not stale.left.output_known
