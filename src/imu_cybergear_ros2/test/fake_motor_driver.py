"""完全内存化的 CyberGear fake；不得访问 CAN、串口或真实驱动。"""

from collections import Counter
from threading import Event, Lock


class FakeMotorDriver:
    def __init__(
        self,
        *,
        failures=None,
        connect_result=True,
        close_failure=False,
        blockers=None,
        reconnect_results=None,
        **_kwargs,
    ):
        self.backend_name = "fake"
        self.failures = set(failures or ())
        self.connect_result = connect_result
        self.close_failure = close_failure
        self.blockers = dict(blockers or {})
        self.reconnect_results = list(reconnect_results or ())
        self.calls = []
        self.counts = Counter()
        self.feedback_callback = None
        self.feedback_error_callback = None
        self.transport_event_callback = None
        self.close_attempts = 0
        self._connection_generation = 0
        self._connected = False
        self._activity_lock = Lock()
        self.active_calls = 0
        self.max_active_calls = 0

    def _call(self, operation, motor_id=None, index=None, value=None):
        key = (operation, motor_id, index)
        self.calls.append((operation, motor_id, index, value))
        self.counts[key] += 1
        with self._activity_lock:
            self.active_calls += 1
            self.max_active_calls = max(self.max_active_calls, self.active_calls)
        try:
            blocker = self.blockers.get(key) or self.blockers.get(
                (operation, motor_id, None)
            )
            if blocker is not None:
                entered, release = blocker
                entered.set()
                if not release.wait(timeout=2.0):
                    raise RuntimeError(f"fake blocker timeout: {key}")
            if key in self.failures or (operation, motor_id, None) in self.failures:
                raise RuntimeError(f"injected failure: {key}")
        finally:
            with self._activity_lock:
                self.active_calls -= 1

    def connect_with_retry(self, **_kwargs):
        self._call("connect")
        if self.connect_result:
            self._connected = True
            self._connection_generation += 1
        return self.connect_result

    def connect(self):
        self._call("connect_once")
        result = self.reconnect_results.pop(0) if self.reconnect_results else True
        if isinstance(result, BaseException):
            raise result
        if not result:
            raise RuntimeError("injected reconnect failure")
        self._connected = True
        self._connection_generation += 1

    @property
    def connection_generation(self):
        return self._connection_generation

    @property
    def is_connected(self):
        return self._connected

    def register_feedback_callback(self, callback):
        self.feedback_callback = callback
        self._call("register_feedback")

    def register_feedback_error_callback(self, callback):
        self.feedback_error_callback = callback
        self._call("register_feedback_error")

    def clear_feedback_callbacks(self):
        self.feedback_callback = None
        self.feedback_error_callback = None
        self._call("clear_feedback_callbacks")

    def register_transport_event_callback(self, callback):
        self.transport_event_callback = callback
        self._call("register_transport_event")

    def clear_transport_event_callbacks(self):
        self.transport_event_callback = None
        self._call("clear_transport_event_callbacks")

    def emit_transport_event(self, event):
        callback = self.transport_event_callback
        if callback is not None:
            callback(event)

    def emit_feedback(self, status):
        """Synchronously deliver fake feedback without any hardware access."""
        callback = self.feedback_callback
        if callback is None:
            return
        try:
            callback(status)
        except Exception as exc:
            if self.feedback_error_callback is not None:
                self.feedback_error_callback(exc)

    def write_sdo_int(self, motor_id, index, value):
        self._call("write_sdo_int", motor_id, index, value)

    def write_sdo_float(self, motor_id, index, value):
        self._call("write_sdo_float", motor_id, index, value)

    def enter_control_mode(self, motor_id):
        self._call("enter_control_mode", motor_id)

    def stop_motor(self, motor_id):
        self._call("stop_motor", motor_id)

    def set_zero(self, motor_id):
        self._call("set_zero", motor_id)

    def close(self):
        self.close_attempts += 1
        self._call("close")
        self._connected = False
        if self.close_failure:
            raise RuntimeError("injected close failure")


def event_blocker():
    return Event(), Event()
