import signal

import pytest
from rclpy.signals import SignalHandlerOptions

from windarmor_flight_control.runtime import node as runtime_node


def _install_fake_main_environment(monkeypatch, spin_impl):
    events = []
    context = {"ok": False}
    previous_handlers = {
        signal.SIGINT: object(),
        signal.SIGTERM: object(),
    }
    handlers = dict(previous_handlers)

    def fake_getsignal(signum):
        return handlers[signum]

    def fake_signal(signum, handler):
        previous = handlers[signum]
        handlers[signum] = handler
        events.append(("signal_handler", signum, handler))
        return previous

    def fake_init(*, args, signal_handler_options):
        events.append(("init", args, signal_handler_options))
        context["ok"] = True

    def fake_ok():
        return context["ok"]

    def fake_shutdown():
        assert context["ok"]
        events.append(("shutdown",))
        context["ok"] = False

    class FakeRuntimeNode:
        def destroy_node(self):
            assert context["ok"]
            assert all(
                handlers[shutdown_signal] is signal.SIG_IGN
                for shutdown_signal in runtime_node._RUNTIME_SHUTDOWN_SIGNALS
            )
            events.append(("destroy_node",))

    def fake_spin(node):
        events.append(("spin",))
        spin_impl(node, handlers)

    monkeypatch.setattr(runtime_node.signal, "getsignal", fake_getsignal)
    monkeypatch.setattr(runtime_node.signal, "signal", fake_signal)
    monkeypatch.setattr(runtime_node.rclpy, "init", fake_init)
    monkeypatch.setattr(runtime_node.rclpy, "ok", fake_ok)
    monkeypatch.setattr(runtime_node.rclpy, "shutdown", fake_shutdown)
    monkeypatch.setattr(runtime_node.rclpy, "spin", fake_spin)
    monkeypatch.setattr(runtime_node, "FlightControlRuntimeNode", FakeRuntimeNode)
    return events, context, handlers, previous_handlers


@pytest.mark.parametrize("shutdown_signal", [signal.SIGINT, signal.SIGTERM])
def test_signal_shutdown_keeps_context_valid_and_cleans_up_once(
    monkeypatch,
    shutdown_signal,
):
    def interrupt_spin(_node, handlers):
        handler = handlers[shutdown_signal]
        assert handler is runtime_node._runtime_shutdown_signal_handler
        handler(shutdown_signal, None)

    events, context, handlers, previous_handlers = _install_fake_main_environment(
        monkeypatch,
        interrupt_spin,
    )

    assert runtime_node.main(["--test-runtime-arg"]) is None

    assert ("init", ["--test-runtime-arg"], SignalHandlerOptions.NO) in events
    assert events.count(("destroy_node",)) == 1
    assert events.count(("shutdown",)) == 1
    destroy_index = events.index(("destroy_node",))
    shutdown_index = events.index(("shutdown",))
    assert destroy_index < shutdown_index
    assert not context["ok"]
    assert handlers == previous_handlers


def test_unexpected_runtime_error_propagates_after_ordered_cleanup(monkeypatch):
    def fail_spin(_node, _handlers):
        raise RuntimeError("unexpected executor failure")

    events, context, handlers, previous_handlers = _install_fake_main_environment(
        monkeypatch,
        fail_spin,
    )

    with pytest.raises(RuntimeError, match="unexpected executor failure"):
        runtime_node.main()

    assert events.count(("destroy_node",)) == 1
    assert events.count(("shutdown",)) == 1
    destroy_index = events.index(("destroy_node",))
    shutdown_index = events.index(("shutdown",))
    assert destroy_index < shutdown_index
    assert not context["ok"]
    assert handlers == previous_handlers
