# WindArmor 算法开发者指南

这是为刚加入 WindArmor 的算法开发者准备的软件优先路径。你只需要掌握基础 Python；
完成本教程不需要连接 ROS graph、树莓派、CAN、串口、GPIO、ESC、电机或风扇。

## 0. 这份文档给谁

算法开发通常只需要关注四项内容：控制器、`FlightState`、`FlightCommand` 和测试。
正常情况下不要修改 Runtime、控制权、motor/fan manager 或硬件驱动，也不要从算法模块
直接导入 ROS、CAN、串口、GPIO/PWM 或设备 SDK。

本教程分三级：

1. LEVEL 1：纯 Python 单元测试；
2. LEVEL 2：纯软件 synthetic DRY_RUN；
3. LEVEL 3：由维护者/操作者审核和执行的受限硬件冒烟测试。

前两级不访问硬件。阅读或完成本教程不构成任何硬件授权。

## 1. 一分钟理解数据流

```text
IMU / 电机反馈 / 系统状态
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
 Runtime 校验 / 安全机制 / 控制权
                 |
                 v
          电机与风扇管理器
                 |
                 v
                硬件
```

算法只计算从不可变状态到命令的映射。它不能直接控制 CAN、GPIO 或 PWM；即使算法返回
普通命令，Runtime 与底层安全层仍可拒绝执行。

## 2. 你通常修改哪些文件

- 算法目录：
  `src/windarmor_flight_control/windarmor_flight_control/algorithms/`
- 教学实现：
  `src/windarmor_flight_control/windarmor_flight_control/algorithms/example_algorithm_controller.py`
- 控制器测试：
  `src/windarmor_flight_control/test/test_example_algorithm_controller.py`
- 工厂加载器：
  `src/windarmor_flight_control/windarmor_flight_control/runtime/controller_loader.py`
- fake 状态辅助函数：
  `src/windarmor_flight_control/windarmor_flight_control/testing.py`
- synthetic 演示：
  `src/windarmor_flight_control/windarmor_flight_control/synthetic_dry_run.py`

不要从 `bounded_verification_controller.py` 复制新算法。它是版本/硬件验证工具，带有
控制权会话基线和验证防护，不是新人模板。

## 3. 第一个最小控制器

控制器必须提供 `reset()` 和 `update(state, dt)`。下面是当前教学控制器的完整核心模式：
它捕获一次四轴实测位置作为基线，根据相对俯仰角对 `left_pitch` 添加最多 `±0.05 rad`
的示例偏移，并生成最大 `0.10` 的归一化风扇预览。

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

仓库实现还会检查逻辑名称完整性、反馈是否存在以及数值是否有限；请直接以
`example_algorithm_controller.py` 为当前可运行版本。示例中的数值只用于软件教学，不是
机械中位、飞行调参或硬件授权值。

## 4. `reset()`

Runtime 会在控制器创建后调用 `reset()`；新的原子控制权会话成功提交时也会调用它，并
丢弃交接前的预览。单元测试也应在新场景开始前调用它。

`reset()` 只清理算法内部积分、滤波历史、基线或状态机。它不能清除 E-STOP/ERROR、
设置电机零点、启用硬件或恢复控制权。不要在新会话中复用旧基线。

## 5. `update(state, dt)`

- `state` 是本周期的不可变完整状态快照；
- `dt` 是相邻算法周期之间的单调时钟时间差，单位秒；
- 当前 Runtime 标称频率是 50 Hz，但算法不得假设 `dt` 永远等于 `0.02`；
- 非有限、零或负 `dt` 应触发失效后安全闭锁（fail-close），或按经过评审的规则处理；
- 每次必须返回新的 `FlightCommand`，不能直接发布消息或调用服务。

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

`FlightState` 和嵌套 dataclass 都不可变；不要修改状态快照，也不要把 `None` 当作零。
完整字段类型、单位和校验规则见 [Flight Control API](FLIGHT_CONTROL_API.md)。

## 7. IMU

- `roll_rad/pitch_rad/yaw_rad`：由原始四元数转换出的欧拉角，单位 rad；
- `relative_roll_rad/relative_pitch_rad`：统一轴向修正后相对最近成功 IMU zero reference 的
  角度，单位 rad；计算采用归一化角差；
- 原始观测与相对观测必须具有相同来源时间戳，才能组成有效状态快照；
- `valid=True` 表示结构、有限值、连接和零点代次都成立；
- `fresh=True` 还表示样本年龄没有超过 Runtime 新鲜度阈值；
- 当前没有稳定公开的 `relative_yaw_rad`，不要自行编造。

IMU 物理安装为 X+ 向机器人正面、Y+ 向左、Z+ 向上。具体安装和参考定义见
[硬件参考](HARDWARE_REFERENCE.md)。算法示例中的正负只表示已发布 API 值的符号；
不要在未经机械审核时推断真实执行器方向。

## 8. 电机

算法层使用四个逻辑名称，而不是 CAN ID：

```text
left_lift
left_pitch
right_pitch
right_lift
```

位置单位是 rad，速度是 rad/s，力矩是 N·m。`position_rad=None` 表示没有可验证的位置，
不是 `0.0 rad`。普通 `FlightCommand` 必须包含全部配置电机键：遗漏一个轴不能表示
“保持旧目标”，多一个未知轴也会被校验拒绝。

安全的教学保持模式是：从同一有效状态快照捕获全部电机的当前反馈位置，保存为本次算法
会话基线，然后每帧输出完整帧。CAN ID、方向修正、软限位和机械映射属于硬件/集成参考，
不应硬编码到算法。

## 9. 风扇

`FanCommand(left, right)` 使用无量纲闭区间 `[0.0, 1.0]`：

- `0.0` 是停止请求；
- `1.0` 是 Flight API 最大归一化请求；
- 它不是 RPM、推力比例或 PWM 微秒；
- Runtime 适配器/管理器负责把合法命令映射到实际 PWM，并继续应用底层安全限制和斜率限制。

教学控制器的风扇限幅为 `0.10`，只用于单元测试/DRY_RUN 展示。算法代码不得写入
`800/2200` 之类 PWM 微秒值。

## 10. `FlightCommand.safe_stop()`

输入未知、无效、过期，算法内部计算非法，或无法生成完整帧时返回：

```python
return FlightCommand.safe_stop()
```

它是命令层的“我放弃继续提供普通控制意图”，其电机/风扇载荷都为 `None`。它：

- 不等于系统 `/e_stop`；
- 不清除 ERROR/E-STOP；
- 不恢复旧控制归属；
- 不允许混入电机/风扇载荷；
- 在 DRY_RUN 中只是预览，在 ACTIVE 中由 Runtime 导向失效后安全闭锁路径。

## 11. 第一个单元测试

下面的测试完全在内存中运行：

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

再为负俯仰角、限幅、重置、过期/无效输入和完整帧增加用例。仓库现有
`test_example_algorithm_controller.py` 已覆盖这些场景。

## 12. 如何运行测试

从仓库根目录运行：

```bash
PYTHONPATH=src/windarmor_flight_control \
python3 -m pytest -p no:cacheprovider \
  src/windarmor_flight_control/test/test_example_algorithm_controller.py -q
```

预期只看到 pytest 通过结果。该命令不需要构建 ROS 工作空间，也不访问硬件。

## 13. LEVEL 1：纯算法测试

迭代顺序建议为：

1. 用 `make_fake_flight_state()` 构造观测完整的 fixture；
2. 用 `dataclasses.replace()` 修改俯仰角、电机反馈或系统标志；
3. 调用 `controller.reset()` 和 `update()`；
4. 先调用 `validate_flight_command()`，再断言算法语义；
5. 用 `make_stale_flight_state()` 和 `make_unobserved_flight_state()` 验证失效后安全闭锁。

fake 状态是测试数据，不是实机观测、机械中位或硬件 PASS。

## 14. LEVEL 2：纯软件 synthetic DRY_RUN

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

演示通过真实工厂加载器创建非默认教学控制器，对 synthetic 不可变状态执行状态/命令校验，
并逐周期输出：

```text
input: pitch = +0.100 rad
output: left_pitch target = +0.0250 rad
        fan_left = 0.050
        fan_right = 0.000
        safe_stop = false
dispatch: preview only; authority=NONE; actuation_allowed=false
```

最后一个过期场景应显示不含载荷的 safe-stop。这个演示不导入 `rclpy`，不创建 ROS
node/publisher/service/client，不读取 `/dev`，不连接 CAN/串口，不初始化 GPIO/PWM/ESC，也不
创建执行器控制权。它是纯软件集成演示，不是实机验证。

仓库另有 `flight_control_dry_run.launch.py`，它只启动观测模式 Runtime，但需要外部状态
发布者才能形成有意义的实时预览；这些发布者可能来自真实硬件，所以它不是本教程的纯软件
默认入口。

## 15. 控制权（authority）的新人解释

控制权回答一个问题：“Runtime 当前是否允许这条命令真正进入执行器路径？”

- `authority=NONE`、`actuation_allowed=false`：算法输出只是预览；
- `FLIGHT_CONTROL` 和 `actuation_allowed=true`：仍需通过 Runtime 校验、控制归属 token、
  电机/风扇管理器、命令时效租约、看门狗、软限位和 E-STOP；
- 输入恢复不会自动重新授权。

算法不请求或管理控制权。epoch、generation、原子提交、控制归属和回滚的维护者细节见
[飞控架构](FLIGHT_CONTROL_ARCHITECTURE.md)。

## 16. LEVEL 3：受限硬件冒烟测试

算法开发者提交：

- 控制器和单元测试；
- synthetic DRY_RUN 输出；
- 所需输入、单位、符号、限幅和失效后安全闭锁说明；
- 建议的电机/风扇边界与停止条件。

维护者/操作者负责：代码审查、生产集成审查、十项硬件授权、允许的电机/风扇值、连续记录器、
E-STOP、物理断电、供电、现场观察、执行与证据分类。

算法开发者不得自行启用 `flight_takeover_enabled`、调用 authority prepare、选择真实
验证值、启动硬件 launch、设置零点、复位 E-STOP/ERROR 或给执行器通电。
阅读本节不构成授权，也不提供一键硬件动作命令。

项目已使用 `BoundedVerificationController` 证明简单控制器 → Runtime → 控制权 → 真实
电机/风扇的受控路径可行，但该控制器是版本验证工具，不是算法模板。

## 17. 常见错误

- 把角度制当作弧度制；
- 普通命令缺少一个电机键；
- 把 `required_inputs_fresh` 当成整个系统的就绪状态；
- 把 `None` 当作零，或忽略 `valid/fresh/healthy`；
- 假设 `dt` 永远固定；
- 从算法直接控制硬件或调用 ROS 服务；
- 复制受限验证控制器作为生产算法；
- 忘记在新会话/重置后清理积分、基线或滤波历史；
- 写错 `left_lift/left_pitch/right_pitch/right_lift`；
- 把风扇归一化命令当成 PWM 微秒、RPM 或推力；
- 用当前电机反馈每周期叠加偏移，造成目标累积漂移；
- safe-stop 同时携带执行器载荷。

特别注意：`required_inputs_fresh` 当前只聚合已配对 IMU 与全部配置电机反馈的新鲜度。
它不证明风扇状态、安全回读、控制归属或控制权已经就绪；是否可下发由
`actuation_allowed` 和 Runtime/底层安全机制独立决定。

## 18. 调试检查表

1. 单元测试：状态/命令校验是否通过？电机键、单位、有限值是否正确？
2. 单元测试：未知/过期/无效、重置、正负输入和限幅是否有测试？
3. DRY_RUN：能否按工厂契约加载？输出是否明确显示 `authority=NONE`？
4. DRY_RUN：synthetic 俯仰角变化是否得到预期预览？过期输入是否触发 safe-stop？
5. 集成：仅由维护者检查 Runtime 配置、预览/状态和导入边界；
6. 审查：确认没有导入 ROS/硬件，没有默认配置变更，没有绕过安全机制；
7. 硬件：只有取得新的明确授权后，操作者才能进入受限场景。

如果 LEVEL 1/2 失败，不要用真实硬件“帮助调试”。

## 19. 算法审查检查表

- [ ] `reset()` 清理全部算法内部状态；
- [ ] `update()` 接受正、有限、非固定 `dt`；
- [ ] 输入单位、坐标系/符号、`None`、有效性和新鲜度已写清；
- [ ] 普通输出是完整四电机帧和左右风扇命令；
- [ ] 电机/风扇输出为有限值并有明确限幅；
- [ ] 过期/无效/未知输入返回不含载荷的 safe-stop；
- [ ] 没有导入 ROS、CAN、串口、GPIO/PWM、驱动或管理器；
- [ ] 单元测试覆盖中性输入、正负输入、边界、重置和故障；
- [ ] synthetic DRY_RUN 可重复，且显示无控制权/无执行许可；
- [ ] 没有修改默认控制器、控制权接管或硬件配置；
- [ ] 维护者已理解请求边界和故障行为；
- [ ] 若提议 LEVEL 3，已单独准备授权、E-STOP、物理断电和证据计划。

## 20. Git / 协作流程

完整分支职责、PR、release/hotfix 和保护规则见
[开发协作流程](DEVELOPMENT_WORKFLOW.md)。算法成员的标准协作顺序是：

1. 从 `develop` 获取最新集成代码；
2. 为单一算法任务创建 `feature/algo-<short-name>` 短期分支；
3. 实现算法并运行对应 unit test；
4. 运行纯软件 synthetic DRY_RUN，确认输出、safe-stop 和无执行许可状态；
5. push 任务分支并向 `develop` 创建 PR；
6. 等待 WindArmor Software CI；
7. 由 maintainer review 算法边界、API、测试和安全假设；
8. review 与 CI 通过后合入 `develop`，再删除短期分支。

算法任务通常只修改 algorithms、algorithm tests 和必要算法文档。共享 `FlightController`、
`FlightState`、`FlightCommand` 或 controller factory contract 的变化必须作为 API change
协调，不得静默改变。代码合入 `develop` 只表示软件集成完成；任何真实电机、风扇、CAN、
串口、GPIO 或 PWM 测试仍须维护者准备受限范围，并由用户/operator 独立明确授权。
