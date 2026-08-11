# 最新反馈：v0.4.0 Flight API Contract Polish

> 本文件只保留最近一次反馈。
>
> 日期：2026-08-11

## 执行结论

v0.4.0 Task 1.1 已完成 Flight API v1 的小范围契约收口：safe-stop 现在是不携带
actuator payload 的无参数撤销控制请求；startup 未观测状态可与明确 false/正常
状态区分；validation、示例、fake helpers、测试和长期文档已经同步。

本任务没有实现 Flight Runtime、ROS state aggregation、authority takeover 或
actuator dispatch，也没有修改现有 IMU、电机、风扇和 bringup 运行路径。
v0.3.2 的安全状态机和真实控制行为保持不变。

## 修改文件

- `src/windarmor_flight_control/windarmor_flight_control/core/models.py`：safe-stop
  payload Optional 化，并为外部观测型状态增加 `None`；
- `src/windarmor_flight_control/windarmor_flight_control/core/validation.py`：区分
  normal/safe-stop command，校验三态观测并禁止 unknown 状态被声明为可执行；
- `src/windarmor_flight_control/windarmor_flight_control/algorithms/example_controller.py`：
  inhibited 或 E-STOP 未明确安全时直接返回无参数 safe-stop；
- `src/windarmor_flight_control/windarmor_flight_control/testing.py`：提供 fully
  observed、unobserved startup 和 stale 三类 pure fake state；
- `src/windarmor_flight_control/test/test_models.py`：扩展所有嵌套模型和 mapping
  的 immutability 测试；
- `src/windarmor_flight_control/test/test_validation.py`：覆盖 safe-stop、混合 payload、
  unknown/false、空字符串和 fail-closed actuation；
- `src/windarmor_flight_control/test/test_example_controller.py`：覆盖 safe-stop 不依赖
  previous command；
- `docs/FLIGHT_CONTROL_API.md`：同步最终数据模型、validation、unknown 与示例；
- `docs/FLIGHT_CONTROL_ARCHITECTURE.md`：同步 payload-free safe-stop 和 startup
  arming 前置契约；
- `docs/LATEST_FEEDBACK.md`：记录 Task 1.1 最终结果。

`docs/NEXT_COMMAND.md` 是任务开始前的用户修改，Task 1.1 开始及反馈生成时
SHA-256 均为
`1aa722cbad888a686e25e613976b23d770def956ef3a07cb27728456db2ec6f7`。
其工程文档措辞已使用工具无关表达，没有列举具体生成工具、实现助手或模型名称，
本任务未进一步改写或覆盖该文件。

## Safe-stop 最终契约

最终模型为：

```python
@dataclass(frozen=True)
class FlightCommand:
    motor_positions_rad: Mapping[str, float] | None
    fan_commands: FanCommand | None
    request_safe_stop: bool = False

    @classmethod
    def safe_stop(cls) -> "FlightCommand":
        return cls(
            motor_positions_rad=None,
            fan_commands=None,
            request_safe_stop=True,
        )
```

validation 契约：

- normal command 必须同时携带完整 motor frame 和合法 `FanCommand`；
- motor keys 缺失、未知或 target 为 NaN/Inf 时拒绝；
- fan target 必须为有限的 `[0.0, 1.0]`；
- safe-stop 不要求 motor/fan target；
- safe-stop 只校验 flag 与 payload 互斥，不读取 required motor keys，也不受
  normal payload validation 阻止；
- `request_safe_stop=True` 同时携带任一 actuator payload 时拒绝混合语义。

safe-stop 不缓存、复制或重发 previous command，不用 `0.0` 制造伪目标。它只表示
算法主动放弃继续提供普通命令；不等于 hardware E-STOP，不清 ERROR，不恢复
MANUAL/AUTO/HOME，也不具备任何硬件副作用。

## Unknown / unobserved 最终表达

以下外部观测字段现在使用 Optional：

- `ImuState.connected: bool | None`；
- `ImuState.zero_generation: int | None`；
- `FanSystemState.enabled: bool | None`；
- `FanSystemState.control_state: str | None`；
- `SystemState.e_stop_active: bool | None`；
- `SystemState.motor_control_mode: str | None`；
- `SystemState.fan_control_state: str | None`。

`None` 表示尚未收到或当前没有可用观测，明确的 `False` 表示已知 false。空字符串
不是 unknown 的合法表达。`valid/fresh/healthy`、`flight_control_active`、
`actuation_allowed` 和 `required_inputs_fresh` 是本地派生判定，继续使用 bool；
false 表示对应条件当前不成立，而不是伪造外部观测。

`e_stop_active` 调整为 `bool | None`，因为 startup 尚未收到急停状态时不能把未知
误表示为明确安全。只有 `e_stop_active is False`、fan enabled 明确为 true、
motor/fan mode 已观测、所需输入新鲜且 Flight authority 活动时，state validation
才允许 `actuation_allowed=True`。Task 2 Runtime 仍需实际实现该 arming 前置条件。

## Immutability

`FlightState`、全部子状态、`FlightCommand` 和 `FanCommand` 继续使用 frozen
dataclass。`FlightState.motors` 与 normal `FlightCommand.motor_positions_rad` 在
构造时复制为 `MappingProxyType`；构造后修改调用方原始 dict 不会改变 snapshot
或 command。safe-stop 的 mapping 为 `None`，不存在可变或可执行 payload。

## 与建议设计相比的细化

- 除任务明确建议的 fan/system 字段外，IMU `connected` 和 `zero_generation` 也
  改为 Optional，避免 startup 使用 false/zero 冒充外部观测；
- authority、generation 和几个 runtime 派生 bool 保持非 Optional，因为它们是
  runtime 本地裁决状态，不是异步硬件观测；
- 对混合 safe-stop/payload 采用文档优先建议的明确拒绝；
- 保留单一 `FlightCommand` dataclass，没有引入复杂 command hierarchy；
- 新增独立 `make_unobserved_flight_state()` 和 `make_stale_flight_state()`，避免
  fully observed helper 的默认值被误读为未来 Runtime 的真实安全默认值。

## 软件验证

执行的命令与结果：

```bash
PYTHONPATH=src/windarmor_flight_control \
python3 -m pytest \
  src/windarmor_flight_control/test \
  src/windarmor_interfaces/test -q
```

- 第一轮：`44 passed, 1 failed`；唯一失败是旧测试仍匹配旧 `e-stop` 错误文本，
  新 validation 已输出更明确的 `e_stop_active` 文本；同步测试断言后重跑通过；
- 最终专项：`45 passed`。

```bash
python3 -m py_compile \
  src/windarmor_flight_control/windarmor_flight_control/*.py \
  src/windarmor_flight_control/windarmor_flight_control/core/*.py \
  src/windarmor_flight_control/windarmor_flight_control/algorithms/*.py
git diff --check
```

- Python compile：通过；
- `git diff --check`：通过。

```bash
./scripts/ci_software.sh
```

- CI safety：通过；
- Git whitespace：通过；
- Python compile：通过；
- workspace build：`5 packages finished`；
- motor package pure/fake tests：`359 passed`；
- fan safety pure/mock regression：`98 passed`；
- Flight/interface pure tests：`45 passed`；
- workspace colcon：`527 tests, 0 errors, 0 failures, 0 skipped`。

最终验证没有 warning、error、failure 或 skipped。全部命令均在无硬件路径运行。

## Runtime 与 Task 2

本任务没有触碰现有 runtime、ROS topic/service、legacy AUTO、MANUAL、HOME、
ERROR、E-STOP、transport recovery、motor feedback/temperature protection、fan
safety 或 actuator dispatch。两个新 package 版本保持 `0.4.0`，三个稳定 package
版本未修改。

Task 1.1 没有发现进入 Task 2 的阻塞项。Task 2 仍需实现真实 StateAggregator、
freshness、DRY_RUN Runtime 和 authority/arming，但必须遵守本次冻结的 unknown
fail-closed 与 payload-free safe-stop 契约。

## 硬件安全声明

本任务没有运行 ROS 2 node/launch/topic/service，没有运行 `sudo` 或 CAN setup，
没有访问 IMU、`/dev/*`、真实串口、CAN、SocketCAN、USB-CAN、CyberGear、
GPIO12/GPIO13、PWM 或电调。4 个微电机和 2 个风扇均未因本任务被控制。

真实 Runtime、actuator integration 和所有实机验证均未执行，原因是它们超出
Task 1.1 范围且当前没有硬件授权。本次结果是纯软件验证，不是实机验证或硬件
安全认证。

## Git 状态（反馈生成时）

- HEAD：`63a30571f89229c2e53118fbc997b08470d8c647`；
- 分支：`master`；本地 tracking ref 显示与 `origin/master` ahead/behind `0/0`；
- 本任务实现/验证阶段执行 commit：否；
- 本任务实现/验证阶段执行 push：否；
- 本任务实现/验证阶段执行 tag：否；
- 远端状态在本任务内核验：否；只检查本地 tracking ref，未执行网络查询；
- `v0.3.2` 仍指向 `398ea9b035929f745be79c4d75cfd99d73c77702`；
- 工作区包含 Task 1.1 修改以及任务开始前的 `docs/NEXT_COMMAND.md` 修改，均未暂存；
- 稳定 tag 未创建、移动、删除或重建。
