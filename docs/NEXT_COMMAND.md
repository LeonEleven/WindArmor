# NEXT_COMMAND

## Task

v0.4.0 Task 6.2.1 — Fix Observation-only Launch on ROS 2 Jazzy

## Baseline

Current baseline:

```text
a832580
```

Gate A0:

```text
PASS
```

Gate A1:

```text
PASS
```

Gate A2:

```text
BLOCKED BY SOFTWARE LAUNCH BUG
NOT EXECUTED
```

Real hardware observation attempt exposed:

```text
TypeError:
LifecycleNode.__init__() missing 1 required keyword-only argument: 'namespace'
```

No actuator test should continue until this is fixed.

---

## Objective

Fix the ROS 2 Jazzy launch compatibility bug in:

```text
src/windarmor_bringup/launch/windarmor_observation_only.launch.py
```

This is a narrowly scoped bug fix.

Do not redesign the observation architecture.

Do not change Flight authority, ownership, motor/fan control, configuration defaults, or verification controller behavior.

---

## Root Cause

`launch_ros.actions.LifecycleNode` requires an explicit keyword-only:

```python
namespace=
```

The observation-only launch currently creates:

```text
imu_driver
imu_relative_observer
motor_feedback_observer
```

without specifying `namespace`.

The existing normal launch:

```text
src/imu_cybergear_ros2/launch/imu_cybergear_system.launch.py
```

already uses:

```python
namespace=""
```

for LifecycleNode and should be used as the compatibility reference.

---

## Required Fix

For every `LifecycleNode` in:

```text
windarmor_observation_only.launch.py
```

add the explicit root namespace:

```python
namespace=""
```

At minimum verify:

```text
imu_driver
imu_relative_observer
motor_feedback_observer
```

Do not change node names.

Do not change topic names.

Do not change parameters.

Do not change lifecycle autostart logic unless required by a failing regression test.

---

## Required Regression Test

The previous software tests failed to catch this because they did not exercise actual Jazzy `LifecycleNode` construction strongly enough.

Add a regression test that imports the real launch file and calls:

```python
generate_launch_description()
```

in the ROS 2 Jazzy test environment.

The test must fail if a required `LifecycleNode` constructor argument is missing.

Prefer testing the real launch construction rather than only AST/string inspection.

Also verify the resulting launch description still contains:

```text
imu_driver_node
imu_relative_observer_node
motor_feedback_observer_node
flight_control_runtime_node
```

and does not add:

```text
imu_motor_controller_node
fan_controller
```

Do not actually execute hardware nodes in CI.

---

## Safety Boundary

This task must remain software-only.

Do not:

- access `/dev/*`;
- configure or open real CAN;
- connect to CyberGear;
- initialize GPIO/PWM;
- run fan/ESC;
- perform owner takeover;
- execute Gate A2;
- power motors;
- power fans.

Keep:

```text
flight_takeover_enabled=false
```

unchanged.

Keep:

```text
motor_feedback_timeout_sec=0.0
```

unchanged.

---

## Verification

Run at least:

```bash
source /opt/ros/jazzy/setup.bash

colcon build --symlink-install

source install/setup.bash

python3 -m pytest \
  src/windarmor_bringup/test \
  -q

./scripts/ci_software.sh
```

If relevant package tests are located elsewhere, run those as well.

Also run a software-only launch-description construction check, for example through pytest, not by opening hardware interfaces.

Do not execute:

```bash
ros2 launch windarmor_bringup windarmor_observation_only.launch.py
```

against real hardware as part of this task.

---

## Hardware Plan Update

Update:

```text
docs/V0.4.0_HARDWARE_VERIFICATION_PLAN.md
```

only if needed to record:

```text
Gate A2 paused because observation-only launch failed before node startup.
Root cause: missing LifecycleNode namespace argument.
Hardware execution must resume only after software fix is reviewed.
```

Do not mark Gate A2 PASS.

---

## Final Feedback

Update:

```text
docs/LATEST_FEEDBACK.md
```

Report:

### Root Cause

- exact exception;
- affected LifecycleNodes;
- why normal launch did not have the issue.

### Fix

- files changed;
- explicit namespace handling;
- regression test added.

### Safety Boundary

Confirm:

- Gate A2 was not executed successfully;
- no motor observer process was started during the failed launch;
- no actuator command was sent by this test;
- no motor/fan hardware was accessed during the fix;
- takeover defaults unchanged.

### Tests

Report exact test commands and results.

### Next Step

If all tests pass:

```text
Gate A2 may be retried under the previous separate hardware authorization procedure.
```

Do not execute the retry automatically.

---

## Out of Scope

Do not implement:

- new observer architecture;
- staged ownership;
- reservation keepalive;
- bounded controller changes;
- hardware protocol changes;
- CyberGear read query;
- control logic changes;
- release/version changes;
- commit/push/tag unless separately authorized.

---

## Git

Default:

```text
no commit
no push
no tag
```

Stable tags v0.3.0 / v0.3.1 / v0.3.2 must remain unchanged.