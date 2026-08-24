# WindArmor Algorithm Developer Guide

这是一条给第一天加入 WindArmor 的算法开发者使用的 software-first 路径。你只需要会基础
Python；完成本教程不需要连接 ROS graph、树莓派、CAN、串口、GPIO、ESC、电机或风扇。

## 0. 这份文档给谁

算法开发通常只需要关注四件事：controller、`FlightState`、`FlightCommand` 和 tests。
正常情况下不要修改 Runtime、authority、motor/fan manager 或 hardware driver，也不要从
算法模块直接 import ROS、CAN、serial、GPIO/PWM 或设备 SDK。

本教程分三级：

1. LEVEL 1：纯 Python unit test；
2. LEVEL 2：software-only synthetic DRY_RUN；
3. LEVEL 3：由 maintainer/operator 审核和执行的 bounded hardware smoke test。

前两级不访问硬件。阅读或完成本教程不构成任何硬件授权。

## 1. 一分钟理解数据流

```text
IMU / motor feedback / system state
                 |
                 v
             FlightState
                 |
                 v
       controller.update(state, dt)
                 |
                 v
            FlightCommand
                 |
                 v
 Runtime validation / safety / authority
                 |
                 v
        motor and fan managers
                 |
                 v
              hardware
```

算法只计算不可变 state 到 command 的映射。它不能直接控制 CAN、GPIO 或 PWM；即使算法返回
normal command，Runtime 与底层安全层仍可拒绝执行。

## 2. 你通常修改哪些文件

- 算法目录：
  `src/windarmor_flight_control/windarmor_flight_control/algorithms/`
- 教学实现：
  `src/windarmor_flight_control/windarmor_flight_control/algorithms/example_algorithm_controller.py`
- controller tests：
  `src/windarmor_flight_control/test/test_example_algorithm_controller.py`
- factory loader：
  `src/windarmor_flight_control/windarmor_flight_control/runtime/controller_loader.py`
- fake state helpers：
  `src/windarmor_flight_control/windarmor_flight_control/testing.py`
- synthetic demo：
  `src/windarmor_flight_control/windarmor_flight_control/synthetic_dry_run.py`

不要从 `bounded_verification_controller.py` 复制新算法。它是 release/hardware verification
工具，带有 authority-session baseline 和 verification guard，不是新人模板。

## 3. 第一个最小 controller

controller 必须提供 `reset()` 和 `update(state, dt)`。下面是当前教学 controller 的完整核心
模式：它捕获一次四轴实测位置作为 baseline，根据 relative pitch 对 `left_pitch` 添加最多
`±0.05 rad` 的示例偏移，并生成最大 `0.10` 的归一化 fan preview。

```python
import math

from windarmor_flight_control.core.models import (
    FanCommand,
    FlightCommand,
    FlightState,
)


class MyPitchController:
    def __init__(self, required_motor_names):
        self.motor_names = tuple(required_motor_names)
        if "left_pitch" not in self.motor_names:
            raise ValueError("left_pitch is required")
        self.baseline = None

    def reset(self):
        self.baseline = None

    def update(self, state: FlightState, dt: float) -> FlightCommand:
        pitch = state.imu.relative_pitch_rad
        if (
            not isinstance(dt, (int, float))
            or isinstance(dt, bool)
            or not math.isfinite(dt)
            or dt <= 0.0
            or pitch is None
            or not math.isfinite(pitch)
            or state.system.e_stop_active is not False
            or not state.system.required_inputs_fresh
            or not state.imu.valid
            or not state.imu.fresh
        ):
            self.baseline = None
            return FlightCommand.safe_stop()

        if set(state.motors) != set(self.motor_names):
            return FlightCommand.safe_stop()
        for name in self.motor_names:
            motor = state.motors[name]
            if (
                motor.position_rad is None
                or not math.isfinite(motor.position_rad)
                or not motor.valid
                or not motor.fresh
                or not motor.healthy
            ):
                self.baseline = None
                return FlightCommand.safe_stop()

        if self.baseline is None:
            self.baseline = {
                name: state.motors[name].position_rad for name in self.motor_names
            }

        offset = max(-0.05, min(0.05, 0.25 * pitch))
        targets = dict(self.baseline)
        targets["left_pitch"] += offset
        fan_left = max(0.0, min(0.10, 0.5 * max(pitch, 0.0)))
        fan_right = max(0.0, min(0.10, 0.5 * max(-pitch, 0.0)))
        return FlightCommand(
            motor_positions_rad=targets,
            fan_commands=FanCommand(left=fan_left, right=fan_right),
        )


def create_controller(required_motor_names, configuration=None):
    del configuration
    return MyPitchController(required_motor_names)
```

仓库实现额外检查 logical name 完整性、反馈 presence 和有限数值；请直接以
`example_algorithm_controller.py` 为当前可运行版本。示例中的数值只用于软件教学，不是
机械中位、飞行调参或硬件授权值。

## 4. `reset()`

Runtime 会在 controller 创建后调用 `reset()`，在新的 atomic authority session 成功提交时
也会 reset 并丢弃 handoff 前 preview。unit test 也应在新场景开始前调用它。

`reset()` 只清理算法内部积分、滤波历史、baseline 或状态机。它不能清除 E-STOP/ERROR、
设置电机零点、enable hardware 或恢复 authority。不要在新 session 复用旧 baseline。

## 5. `update(state, dt)`

- `state` 是本 tick 的不可变、完整 snapshot；
- `dt` 是相邻算法 tick 的 monotonic 时间差，单位秒；
- 当前 Runtime nominal rate 是 50 Hz，但算法不得假设 `dt` 永远等于 `0.02`；
- 非有限、零或负 `dt` 应 fail closed，或按经过评审的规则处理；
- 每次必须返回新的 `FlightCommand`，不能直接 publish 或调用 service。

## 6. 最常用的 `FlightState`

新人通常先使用：

```python
state.imu.relative_roll_rad
state.imu.relative_pitch_rad
state.imu.valid
state.imu.fresh
state.motors["left_pitch"].position_rad
state.motors["left_pitch"].valid
state.motors["left_pitch"].fresh
state.motors["left_pitch"].healthy
state.system.required_inputs_fresh
state.system.e_stop_active
```

`FlightState` 和嵌套 dataclass 都是 immutable；不要修改 snapshot，也不要把 `None` 当作零。
完整字段类型、单位和 validation 见 [Flight Control API](FLIGHT_CONTROL_API.md)。

## 7. IMU

- `roll_rad/pitch_rad/yaw_rad`：raw quaternion 转换出的 Euler angle，单位 rad；
- `relative_roll_rad/relative_pitch_rad`：统一轴向修正后相对最近成功 IMU zero reference 的
  角度，单位 rad；计算采用归一化角差；
- raw 与 relative observation 必须具有相同 source stamp 才会组成有效 snapshot；
- `valid=True` 表示结构、有限值、连接和 zero generation 都成立；
- `fresh=True` 还表示样本年龄没有超过 Runtime freshness threshold；
- 当前没有稳定公开的 `relative_yaw_rad`，不要自行编造。

IMU 物理安装为 X+ 向机器人正面、Y+ 向左、Z+ 向上。具体安装和 reference 见
[Hardware Reference](HARDWARE_REFERENCE.md)。算法示例中的正负只表示已发布 API 值的符号；
不要在未经机械审核时推断真实 actuator 方向。

## 8. Motors

算法层使用四个 logical name，而不是 CAN ID：

```text
left_lift
left_pitch
right_pitch
right_lift
```

位置单位是 rad，速度是 rad/s，力矩是 N·m。`position_rad=None` 表示没有可验证的位置，
不是 `0.0 rad`。normal `FlightCommand` 必须包含全部配置 motor keys：遗漏一个轴不能表示
“保持旧目标”，多一个未知轴也会被 validation 拒绝。

安全的教学 hold 模式是：从同一有效 snapshot 捕获全部 motor 的当前反馈位置，保存为本次
算法 session baseline，然后每帧输出完整 frame。CAN ID、方向修正、软限位和机械映射属于
hardware/integration reference，不应硬编码到算法。

## 9. Fans

`FanCommand(left, right)` 使用无量纲闭区间 `[0.0, 1.0]`：

- `0.0` 是停止请求；
- `1.0` 是 Flight API 最大 normalized request；
- 它不是 RPM、推力比例或 PWM 微秒；
- Runtime adapter/manager 才负责把合法命令映射到实际 PWM，并继续应用下层 safety/slew。

教学 controller 的 fan clamp 为 `0.10`，只用于 unit/DRY_RUN 展示。算法代码不得写
`800/2200` 之类 PWM 微秒值。

## 10. `FlightCommand.safe_stop()`

输入 unknown、invalid、stale，算法内部计算非法，或无法生成完整 frame 时返回：

```python
return FlightCommand.safe_stop()
```

它是 command-level “我放弃继续提供普通控制意图”，其 motor/fan payload 都是 `None`。它：

- 不等于系统 `/e_stop`；
- 不清除 ERROR/E-STOP；
- 不恢复 legacy owner；
- 不允许混入 motor/fan payload；
- 在 DRY_RUN 中只是 preview，在 ACTIVE 中由 Runtime 导向 fail-closed 路径。

## 11. 第一个 unit test

下面的 test 完全在内存中运行：

```python
from dataclasses import replace

import pytest

from windarmor_flight_control.algorithms.example_algorithm_controller import (
    ExampleAlgorithmController,
)
from windarmor_flight_control.core.validation import validate_flight_command
from windarmor_flight_control.testing import make_fake_flight_state


MOTORS = ("left_lift", "left_pitch", "right_pitch", "right_lift")


def test_positive_pitch_produces_a_complete_bounded_preview():
    state = make_fake_flight_state(MOTORS)
    state = replace(
        state,
        imu=replace(
            state.imu,
            pitch_rad=0.10,
            relative_pitch_rad=0.10,
        ),
    )
    controller = ExampleAlgorithmController(MOTORS)
    controller.reset()

    command = controller.update(state, dt=0.02)

    validate_flight_command(command, MOTORS)
    assert set(command.motor_positions_rad) == set(MOTORS)
    assert command.motor_positions_rad["left_pitch"] == pytest.approx(0.025)
    assert command.fan_commands.left == pytest.approx(0.05)
    assert command.fan_commands.right == 0.0
    assert command.request_safe_stop is False
```

再为 negative pitch、clamp、reset、stale/invalid input 和完整 frame 增加用例。仓库现有
`test_example_algorithm_controller.py` 已覆盖这些场景。

## 12. 如何运行测试

从仓库根目录运行：

```bash
PYTHONPATH=src/windarmor_flight_control \
python3 -m pytest -p no:cacheprovider \
  src/windarmor_flight_control/test/test_example_algorithm_controller.py -q
```

预期只看到 pytest 通过结果。该命令不需要 ROS build，不访问硬件。

## 13. LEVEL 1：纯算法测试

迭代顺序建议为：

1. 用 `make_fake_flight_state()` 构造 fully observed fixture；
2. 用 `dataclasses.replace()` 修改 pitch、motor feedback 或 system flags；
3. 调用 `controller.reset()` 和 `update()`；
4. 先调用 `validate_flight_command()`，再断言算法语义；
5. 用 `make_stale_flight_state()` 和 `make_unobserved_flight_state()` 验证 fail closed。

fake state 是测试数据，不是实机观测、机械中位或硬件 PASS。

## 14. LEVEL 2：software-only synthetic DRY_RUN

运行：

```bash
PYTHONPATH=src/windarmor_flight_control \
python3 -m windarmor_flight_control.synthetic_dry_run
```

自定义输入：

```bash
PYTHONPATH=src/windarmor_flight_control \
python3 -m windarmor_flight_control.synthetic_dry_run \
  --pitches -0.20 -0.10 0.0 0.10 0.20
```

demo 通过真实 factory loader 创建 non-default teaching controller，对 synthetic immutable
state 执行 state/command validation，并逐 tick 输出：

```text
input: pitch = +0.100 rad
output: left_pitch target = +0.0250 rad
        fan_left = 0.050
        fan_right = 0.000
        safe_stop = false
dispatch: preview only; authority=NONE; actuation_allowed=false
```

最后一个 stale case 应显示 payload-free safe-stop。这个 demo 不 import `rclpy`，不创建 ROS
node/publisher/service/client，不读取 `/dev`，不连接 CAN/serial，不初始化 GPIO/PWM/ESC，也不
创建 actuator authority。它是 software integration demonstration，不是实机验证。

仓库另有 `flight_control_dry_run.launch.py`，它只启动 observer Runtime，但需要外部 state
publishers 才有 meaningful live preview；这些 publisher 可能来自真实硬件，所以不是本教程的
software-only 默认入口。

## 15. authority 的新人解释

authority 回答一个问题：“Runtime 当前是否允许这个 command 真正进入 actuator path？”

- `authority=NONE`、`actuation_allowed=false`：算法输出只是 preview；
- `FLIGHT_CONTROL` 和 `actuation_allowed=true`：仍需通过 Runtime validation、owner token、
  motor/fan manager、lease、watchdog、软限位和 E-STOP；
- 输入恢复不会自动重新授权。

算法不请求或管理 authority。epoch、generation、atomic commit、ownership 和 rollback 的维护者
细节见 [Flight Control Architecture](FLIGHT_CONTROL_ARCHITECTURE.md)。

## 16. LEVEL 3：Bounded Hardware Smoke Test

算法开发者提交：

- controller 和 unit tests；
- synthetic DRY_RUN 输出；
- 所需输入、单位、符号、clamp 和 fail-closed 说明；
- 建议的 motor/fan bounds 与停止条件。

maintainer/operator 负责：code review、production integration review、十项硬件授权、允许的
motor/fan 值、continuous recorder、E-STOP、physical kill、供电、现场观察、执行与证据分类。

算法开发者不得自行启用 `flight_takeover_enabled`、调用 authority prepare、选择真实
verification values、启动 hardware launch、set zero、reset E-STOP/ERROR 或给 actuator 通电。
阅读本节不构成授权，也不提供一键硬件动作命令。

项目已使用 `BoundedVerificationController` 证明 simple controller → Runtime → authority →
真实 motor/fan 的受控路径可行，但该 controller 是 release verification tool，不是算法模板。

## 17. 常见错误

- 把 degrees 当 radians；
- normal command 缺少一个 motor key；
- 把 `required_inputs_fresh` 当成 whole-system readiness；
- 把 `None` 当零，或忽略 `valid/fresh/healthy`；
- 假设 `dt` 永远固定；
- 从算法直接控制 hardware 或 ROS service；
- 复制 bounded verification controller 作为 production algorithm；
- 忘记在新 session/reset 后清理积分、baseline 或滤波历史；
- 写错 `left_lift/left_pitch/right_pitch/right_lift`；
- 把 fan normalized command 当成 PWM 微秒、RPM 或 thrust；
- 用当前 motor feedback 每 tick 叠加 offset，造成目标累积漂移；
- safe-stop 同时携带 actuator payload。

特别注意：`required_inputs_fresh` 当前只聚合 paired IMU freshness 与全部 configured motor
feedback freshness。它不证明 fan state、安全 readback、ownership 或 authority ready；是否可
下发由 `actuation_allowed` 和 Runtime/lower-level safety 独立决定。

## 18. Debug checklist

1. Unit：state/command validation 是否通过？motor keys、单位、有限值是否正确？
2. Unit：unknown/stale/invalid、reset、正负输入和 clamp 是否有测试？
3. DRY_RUN：factory contract 能否 load？输出是否明确显示 `authority=NONE`？
4. DRY_RUN：synthetic pitch 变化是否得到预期 preview？stale 是否 safe-stop？
5. Integration：仅由 maintainer 检查 Runtime config、preview/status 和 import boundary；
6. Review：确认没有 ROS/hardware import，没有默认配置变更，没有绕过 safety；
7. Hardware：只有新的明确授权完成后，operator 才能进入 bounded scenario。

如果 LEVEL 1/2 失败，不要用真实硬件“帮助调试”。

## 19. 算法 review checklist

- [ ] `reset()` 清理全部 algorithm-local state；
- [ ] `update()` 接受正、有限、非固定 `dt`；
- [ ] 输入单位、frame/sign、`None`、validity 和 freshness 已写清；
- [ ] normal output 是完整四 motor frame和左右 fan command；
- [ ] motor/fan 输出有限并有明确 clamp；
- [ ] stale/invalid/unknown input 返回 payload-free safe-stop；
- [ ] 没有 ROS、CAN、serial、GPIO/PWM、driver 或 manager import；
- [ ] unit tests 覆盖 neutral、正负、边界、reset 和 failure；
- [ ] synthetic DRY_RUN 可重复，且显示无 authority/无 actuation；
- [ ] 没有修改默认 controller、takeover 或 hardware config；
- [ ] maintainer 已理解 requested bounds 和 failure behavior；
- [ ] 若提议 LEVEL 3，已单独准备授权、E-STOP、physical kill 和 evidence plan。
