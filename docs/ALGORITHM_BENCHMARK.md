# WindArmor Algorithm Benchmark v1 Contract

本文定义算法 qualification 和历史同级比较的长期统一规则。它不是算法实现、candidate
结果、dynamic simulation、硬件操作手册或硬件授权。仓库安全规则以
[`AGENTS.md`](../AGENTS.md) 为准，任务能力边界以对应的独立 Task Spec 为准。

## 1. 文档与结果分层

正式记录必须分为三层，不能混写：

1. **Benchmark Contract**：本文件的全局版本、证据层级、元数据、hard gate 和比较规则；
2. **Task-specific Benchmark Profile**：某个 Task 的固定 fixture、scenario ID、阈值和容差；
3. **Candidate Result**：一次候选实现针对固定 Contract/Profile 的实际命令、环境和结果。

本文件同时承载 `Algorithm Benchmark v1` 的全局 Contract，以及任务级
`ALG-001 Profile v1`、`ALG-002 Profile v1`、`ALG-003 Profile v1`、`ALG-004 Profile v1` 和
`ALG-005 Profile v1`。它不包含任何 candidate result；Task Profile 的存在不表示对应 candidate
已实现或已 PASS。

## 2. 版本规则

| 资产 | 当前版本 |
| --- | --- |
| Benchmark Contract | `Algorithm Benchmark v1` |
| ALG-001 Task Benchmark Profile | `ALG-001 Profile v1` |
| ALG-002 Task Benchmark Profile | `ALG-002 Profile v1` |
| ALG-003 Task Benchmark Profile | `ALG-003 Profile v1` |
| ALG-004 Task Benchmark Profile | `ALG-004 Profile v1` |
| ALG-005 Task Benchmark Profile | `ALG-005 Profile v1` |

在两个 candidate 已开始正式历史比较后，不得静默修改 fixture、scenario、阈值、容差或
评分规则。实质变化必须升级对应版本：任务局部变化升级 Profile（例如 v1 → v2）；跨任务
契约变化升级整体 Contract。勘误若不改变可观察结果，仍应留下明确变更记录。

不同 Contract/Profile 版本的结果不得无说明直接横向比较。重新运行旧 candidate 时必须
生成新的 result，不能覆盖旧结果。

## 3. Candidate result metadata

每次正式 benchmark result 至少保存：

- Task ID 和 Task Spec version；
- Benchmark Contract version 和 Task Benchmark Profile version；
- baseline commit 与 candidate implementation commit（完整 SHA）；
- candidate configuration/parameters 的稳定序列化值；
- candidate lineage，以及它是否基于另一 candidate 修改；
- Python 版本和影响结果的相关环境/依赖信息；
- fixture version、scenario set 和实际执行命令；
- 总体 `PASS/FAIL`、每个 scenario 的结果和失败 layer；
- known limitations 和 tests not executed；
- `hardware access: NO`，或单独授权证据引用。

长期技术记录使用 `Candidate A`、`Candidate B` 等中性名称，不记录生成工具或模型身份作为
实现来源。配置必须固定；同一结果内不得在看到场景输出后调参。

## 4. 执行层级与结论边界

| Level | 名称 | v1 用途 | 不能声称 |
| --- | --- | --- | --- |
| A | Pure algorithm / pure-function qualification | 直接评分 task-local 抽象控制量 | FlightCommand 集成或真实执行器效果 |
| B | Controller / FlightCommand contract qualification | factory、state/command validation、完整帧、safe-stop | 机器人动力学或已验证分配 |
| C | synthetic DRY_RUN integration preview | 纯软件 `FlightState -> controller -> FlightCommand` 预览 | recovery time、overshoot、物理效果 |
| D | Replay / sequence benchmark | 时序、趋势、噪声和历史回归 | replay 外真实动力学 |
| E | Dynamic benchmark / trusted simulation（未来） | 模型内闭环动态指标 | 未验证的 sim-to-real 等价性 |
| F | Bounded hardware verification（未来） | 单独授权包线内真实行为 | 未测试包线或通用性能保证 |

ALG-001 Profile v1 必须覆盖 A/B；C 可以在 candidate implementation 后作为补充预览。当前
仓库 `synthetic_dry_run` 使用教学控制器，并非 ALG-001 candidate，因此不能作为 ALG-001
结果。Level F 永远需要 `AGENTS.md` 的独立十项授权门槛。

### 4.1 synthetic DRY_RUN 边界

synthetic DRY_RUN 只能证明 factory loading、fake state/command contract、software mapping、
safe-stop 和 preview。它不能证明机器人动力学、recovery time、overshoot、物理 actuator
effectiveness，或机器人受到推动后会重新站稳。

## 5. Qualification 与 comparative metrics

### 5.1 Hard Qualification

Hard Qualification 分为全局共同门槛和对应 Task Profile 定义的行为资格门槛，两部分都必须
全部 PASS。

#### 全局 Hard Qualification

所有 candidate 都必须满足：

- candidate、factory、固定配置和 implementation commit 可追溯，执行可重复；
- 对应 Task Spec、Benchmark Contract 和 Task Profile version 已固定并记录；
- 输入安全处理和 validation-layer 分类正确；
- 所有要求的 fail-close 场景返回合法、无载荷的 safe-stop，或在规定的前置 validation
  layer 被拒绝；
- reset 与 repeatability；
- 所有要求的输出为 finite；
- Level B `FlightCommand` 通过 validation，普通命令为完整 motor frame 和合法 fan command；
- future-task boundary review PASS；
- 测试不导入或访问 ROS/hardware I/O，`hardware access: NO`。

#### Task-specific behavior qualification

正常控制行为的具体 gate 由对应 Task Profile 定义，不由全局 Contract 为所有 Task 统一规定
total feedback 的方向或输入—输出关系。例如：

- ALG-001 Profile v1 要求 neutral、direction、monotonic magnitude、proportional
  consistency 和 symmetry；
- ALG-002 Profile v1 要求 ALG-001 inheritance、zero-rate behavior、diverging damping、
  recovering damping、zero-pitch moving damping、signed damping separation 和 mirror
  consistency。

因此，全局 Contract 不要求所有 Task 的 total feedback 始终与 `pitch_error` 同号。ALG-002
recovering behavior 仍按其 Profile 的 `P02 > P00`、`N02 < N00` 判定，并允许 total intent
在合理阻尼作用下穿过零点反号。

任何全局或对应 Task Profile 的 Hard Qualification 项 FAIL，结果都必须为 `NOT QUALIFIED`。
安全失败或 task-specific behavior 失败不能由其它数值表现或 comparative metrics 抵消。

### 5.2 Comparative metrics

Comparative metrics 由对应 Task Profile 定义，只有全局和 task-specific Hard Qualification
全部 PASS 后才能记录和比较。例如，ALG-001 Profile 可以记录：

- proportional consistency error；
- symmetry error；
- repeatability delta；
- implementation complexity（同时报告计算口径，例如 executable LOC/cyclomatic measure）；
- test coverage quality（同时报告工具、范围和未覆盖项）；
- configuration clarity（review 结论与具体理由）。

ALG-002 Profile v1 使用其已定义的 damping separation、damping separation mirror error、
mirror symmetry error、zero-pitch damping symmetry、repeatability delta、implementation
complexity 和 configuration clarity；具体计算口径仍以该 Profile 为准。

这些指标不合成为未经依据的 100 分总分，且 `Kp` 越大不表示更优。若未来引入 score，必须
版本化权重依据，并在 score 之外先通过全部 hard gates。不同 Task 的指标不能组成跨 Task
的直接排名。

## 6. Candidate independence 与历史比较

两个 candidate 只有属于相同 Task，并同时满足以下条件，才可作公平的历史同级比较：

- 相同 Task Spec version；
- 相同 Benchmark Contract version；
- 相同 Task Profile version；
- 相同 fixture/scenario set 和 tolerance；
- 可追溯 baseline、固定配置和各自独立 implementation commit；
- 相同执行层级；环境差异已记录且不会被隐藏。

例如 `ALG-001 Candidate A` 与 `ALG-001 Candidate B` 可以在满足上述条件后比较；同一规则也
适用于 `ALG-002 Candidate A` 与 `ALG-002 Candidate B`。

如果一个 candidate 后来基于另一个 candidate 的实现修改，必须记录新的 lineage/hybrid，
不得再称为完全独立实现。不同 Task、版本或 Level 的结果只能带限制地说明，不能包装成直接
排名。

## 7. ALG-001 Profile v1

对应 Task Spec：[`algorithm_tasks/ALG-001.md`](algorithm_tasks/ALG-001.md)，版本 `v1`。

### 7.1 Fixture 与抽象观测量

Profile v1 基于当前 `make_fake_flight_state()` 产生的纯内存合法状态，再用
`dataclasses.replace()` 只改变场景指定字段。必要电机键固定为：

```text
left_lift
left_pitch
right_pitch
right_lift
```

fixture 中的电机位置、姿态和其它数值只是 synthetic software inputs，不是机械中位、真实
安全倾角或可恢复倾角。fixture version 记为 `ALG001-FIXTURE-v1`。

LEVEL A 观测 task-local 抽象标量 `pitch_feedback_intent`，定义见 Task Spec。未来 candidate
必须提供可测试的纯函数或等价 seam；其名字和类结构不属于公开 Flight API。LEVEL B 观测
`FlightCommand` 和 validation 结果。因为当前 Flight API 没有抽象 control-effort 字段，
Profile v1 不从具体 motor/fan payload 反推 intent；真实 actuator direction/effectiveness 为
**当前不可评分 / 留待 ALG-006 与后续验证**。

所有正常场景使用相同固定 candidate configuration、`dt=0.02 s`，并在独立场景前调用
`reset()`。候选还必须证明另一个不同于 `0.02 s` 的正有限 `dt` 不改变本任务无时序历史的
基础 intent 关系；该检查不授权实现时间整形。

### 7.2 浮点容差

以下均为 benchmark software tolerance，不是真实机器人性能容差：

| 用途 | absolute tolerance | relative tolerance |
| --- | ---: | ---: |
| neutral intent | `1e-9` intent unit | `0` |
| direction 的非零判定 | 必须严格超出 `1e-9` intent unit | 不适用 |
| 比例、奇对称、重复性比较 | `1e-9` intent unit | `1e-6` |
| 比例系数 `feedback/error` 比较 | `1e-9` intent/rad | `1e-6` |

实现时使用 `math.isclose()` 或 `pytest.approx()` 的等价语义。禁止使用“差不多”“看起来正常”
等主观判定。若 candidate 的固定增益小到非零场景无法超过 direction 零容差，则 direction
gate FAIL；这不是要求更大的物理增益。

### 7.3 正常场景集

| Scenario ID | `relative_pitch_rad` | `pitch_error_rad` | 预期 abstract intent |
| --- | ---: | ---: | --- |
| `ALG001-N00` | `0.0` | `0.0` | 零容差内为零 |
| `ALG001-P01` | `+0.05` | `-0.05` | 负、有限、非零 |
| `ALG001-P02` | `+0.10` | `-0.10` | 负、有限，绝对值严格大于 P01 |
| `ALG001-N01` | `-0.05` | `+0.05` | 正、有限、非零 |
| `ALG001-N02` | `-0.10` | `+0.10` | 正、有限，绝对值严格大于 N01 |

`±0.05 rad` 和 `±0.10 rad` 简单、远离浮点零附近歧义，并提供 2:1 输入关系。它们只是
synthetic fixtures，不定义最大安全倾角、可恢复倾角或真实扰动范围。

### 7.4 关系指标

对五个正常场景，按以下规则评分：

- **Neutral bias**：`abs(feedback_N00) <= 1e-9`；
- **Direction**：每个非零 feedback 与对应 `pitch_error` 同号，且绝对值大于零容差；
- **Monotonic magnitude**：P02/P01、N02/N01 均为严格增加；
- **Proportional consistency**：对四个非零场景计算 `K_i = feedback_i / pitch_error_i`；
  每个 `K_i` 必须为正有限值，并在规定容差内等于 candidate 的同一个固定 `Kp`；
- **Symmetry**：P01 与 N01、P02 与 N02 各自满足近似奇对称；
- **Repeatability**：相同 state、`dt`、configuration 和 reset state 至少重复三次，每次结果
  在比较容差内相同；
- **Finite output**：所有反馈均为有限数。

Level B 对同一正常 state 调用 controller，并要求普通命令通过
`validate_flight_command()`：电机键完整且值有限，fan command 有限且位于 `[0,1]`。Level B
不对具体电机/风扇方向或幅值作 ALG-001 物理评分。

### 7.5 Fail-close 场景集

| Scenario ID | 输入 | Layer | PASS 条件 |
| --- | --- | --- | --- |
| `ALG001-F01` | `imu.valid=false`，并保持 `fresh=false` | controller | 合法 state；返回合法无载荷 safe-stop |
| `ALG001-F02` | `imu.fresh=false` | controller | 合法 state；返回合法无载荷 safe-stop |
| `ALG001-F03` | `required_inputs_fresh=false` | controller | 合法 state；返回合法无载荷 safe-stop |
| `ALG001-F04` | `relative_pitch_rad=None` | state validation + controller variants | valid-IMU 伪状态先被拒绝；合法 unobserved state 返回 safe-stop |
| `ALG001-F05` | `relative_pitch_rad=NaN` | state validation | `validate_flight_state()` 拒绝，不调用 controller |
| `ALG001-F06` | `relative_pitch_rad=+Inf/-Inf` | state validation | 两个 variant 均被拒绝，不调用 controller |
| `ALG001-F07` | 必要 motor key 缺失；以及完整 key 但 unobserved | state validation + controller variants | 缺 key 被拒绝；合法 unobserved 返回 safe-stop |
| `ALG001-F08` | 必要 motor stale/invalid/unhealthy | controller variants | 各合法 variant 均返回合法无载荷 safe-stop |
| `ALG001-D01` | `dt=0` | controller | 返回合法无载荷 safe-stop |
| `ALG001-D02` | `dt<0`（固定 `-0.01`） | controller | 返回合法无载荷 safe-stop |
| `ALG001-D03` | `dt=NaN` | controller | 返回合法无载荷 safe-stop |
| `ALG001-D04` | `dt=+Inf/-Inf` | controller | 两个 variant 均返回合法无载荷 safe-stop |

每个 controller-layer 结果都必须等于 `FlightCommand.safe_stop()` 并通过
`validate_flight_command()`。前置 validation 拒绝是该 layer 的 PASS；不得绕过 validation
把非法对象强塞给 `controller.update()`，也不得把“controller 未运行”写成 controller PASS。

`F08` 的 stale、invalid 和 unhealthy 要分别构造与当前 dataclass 交叉字段规则一致的状态；
例如 stale motor 不能仍声称 `healthy=true`。`F03` 只验证显式系统聚合门槛，不把
`required_inputs_fresh` 误写成整个系统 readiness。

### 7.6 Reset 场景

`ALG001-R01`：

1. reset candidate；以一个非零 pitch 和完整 motor baseline 执行；
2. 再次 reset；使用不同合法 motor baseline 和同一 pitch 执行；
3. LEVEL A feedback 只由当前 pitch 和固定 configuration 决定，不受上一场景 pitch/history
   影响；LEVEL B 不复用上一场景捕获的 motor baseline 或普通命令；
4. 两个结果均满足相应 validation；
5. 测试只观察算法对象，不能声称或尝试改变 Runtime authority、E-STOP/ERROR、真实零点或
   硬件状态。

### 7.7 Hard Qualification checklist

- [ ] metadata、fixture 和执行命令完整且可追溯；
- [ ] `ALG001-N00/P01/P02/N01/N02` 全部 PASS；
- [ ] neutral、direction、strict monotonic、proportional consistency、symmetry、finite 和
  repeatability 全部 PASS；
- [ ] `ALG001-F01`–`F08`、`D01`–`D04` 全部 PASS，layer 分类正确；
- [ ] `ALG001-R01` PASS；
- [ ] 所有 Level B 普通命令和 safe-stop 通过 `validate_flight_command()`；
- [ ] 正有限可变 `dt` 被接受，且未实现 ALG-002–004 的时序能力；
- [ ] code/review 证明没有使用禁止的控制输入或提前实现 ALG-002–008；
- [ ] 没有改动 Flight API/Runtime/default controller/hardware mapping；
- [ ] hardware access 为 `NO`。

任一复选项未通过时，result 必须写 `ALG-001 NOT QUALIFIED`，不能以比较指标或总分覆盖。

## 8. Candidate result 最小结构

未来结果文件至少使用以下结构；占位符只能在实际运行时填写：

```text
Candidate: Candidate A
Task: ALG-001 / Task Spec v1
Benchmark: Algorithm Benchmark v1 / ALG-001 Profile v1
Baseline commit: <full SHA>
Implementation commit: <full SHA>
Configuration: <stable values>
Fixture: ALG001-FIXTURE-v1
Environment: <Python and relevant dependencies>
Command: <exact command>
Hardware access: NO
Hard Qualification: PASS | FAIL
Overall: ALG-001 QUALIFIED | ALG-001 NOT QUALIFIED
Per-scenario results: <all IDs>
Comparative metrics: <independent values and methods>
Known limitations: <explicit>
Tests not executed: <explicit>
```

在 candidate 实际存在并有独立 implementation commit 前，不得创建虚构的 PASS 结果。

## 9. ALG-002 Profile v1

对应 Task Spec：[`algorithm_tasks/ALG-002.md`](algorithm_tasks/ALG-002.md)，版本 `v1`。
ALG-002 继承 ALG-001 基础姿态反馈，只新增统一 pitch-rate 输入驱动的 motion-trend/damping
能力。全局 Benchmark Contract 仍为 `Algorithm Benchmark v1`；本节没有改变
`ALG-001 Profile v1`。

### 9.1 Fixture 与观测量

`ALG002-FIXTURE-v1` 基于当前 `make_fake_flight_state()` 的纯内存合法状态，并用
`dataclasses.replace()` 只改变场景指定字段。必要电机键继续固定为：

```text
left_lift
left_pitch
right_pitch
right_lift
```

核心值固定为：

| 输入 | 固定值 |
| --- | --- |
| `relative_pitch_rad` | `0.0`, `+0.05`, `-0.05 rad` |
| `relative_pitch_rate_rad_s` | `0.0`, `+0.20`, `-0.20 rad/s` |

这些值简单、对称且远离浮点零值歧义，只是 synthetic software fixture。它们不是安全倾角、
安全角速度、最大恢复范围、实机扰动 envelope 或硬件限制。

Level A 观察 Task Spec 定义的 task-local `pitch_feedback_intent`。Level B 观察
`FlightCommand` 与 validation；不从 motor/fan payload 反推 intent，也不评分真实执行器方向。
所有独立场景使用同一固定 candidate configuration，并在场景开始前调用 `reset()`；除明确的
`dt` 场景外，正常场景固定使用 `dt=0.02 s`。

### 9.2 软件容差

以下容差不表示真实机器人性能：

| 用途 | absolute tolerance | relative tolerance |
| --- | ---: | ---: |
| pitch 输入零判定 | `1e-12 rad` | `0` |
| pitch-rate 输入零判定 | `1e-12 rad/s` | `0` |
| neutral intent | `1e-9` intent unit | `0` |
| direction 非零判定 | 必须严格超过 `1e-9` intent unit | 不适用 |
| 有符号关系、镜像与重复性 | `1e-9` intent unit | `1e-6` |
| damping effect present | 差异必须严格超过对应 `tol(a,b)` | 见下方定义 |

令 `tol(a,b) = 1e-9 + 1e-6 * max(abs(a), abs(b))`。本 Profile 要求的有符号 damping
separation 必须严格大于对应 `tol(a,b)`，不能以容差内相等通过。候选不得通过选择极小参数
使应为非零的 direction 或 damping separation 落入零容差。趋势分类先按上述 input tolerance
判断 pitch/rate 是否为零；两者均为非零时再使用 `pitch * rate` 的正负，不依赖浮点完全相等。

### 9.3 正常场景集

表中的 intent 均为抽象软件反馈意图：

| Scenario | pitch (rad) | rate (rad/s) | 趋势 | 有符号关系 |
| --- | ---: | ---: | --- | --- |
| `ALG002-P00` | `+0.05` | `0.0` | zero-rate | intent 为负且非零；positive-pitch 基础值 |
| `ALG002-P01` | `+0.05` | `+0.20` | diverging | `P01 < P00`；`P00 - P01 > tol(P00,P01)` |
| `ALG002-P02` | `+0.05` | `-0.20` | recovering | `P02 > P00`；`P02 - P00 > tol(P02,P00)` |
| `ALG002-N00` | `-0.05` | `0.0` | zero-rate | intent 为正且非零；negative-pitch 基础值 |
| `ALG002-N01` | `-0.05` | `-0.20` | diverging | `N01 > N00`；`N01 - N00 > tol(N01,N00)` |
| `ALG002-N02` | `-0.05` | `+0.20` | recovering | `N02 < N00`；`N00 - N02 > tol(N00,N02)` |
| `ALG002-Z01` | `0.0` | `+0.20` | pass-through-zero | intent 为负且严格超过零容差 |
| `ALG002-Z02` | `0.0` | `-0.20` | pass-through-zero | intent 为正且严格超过零容差 |

`P02/N02` 不附加 total intent sign 限制：它们可以仍保持 zero-rate feedback 的符号、在零容差
内为零或穿过零点反号。反号本身不是 FAIL；资格判定只要求相对于 `P00/N00` 的变化方向明确
反对 rate 且严格超过关系容差。所有输出必须有限。`P00/N00` 还必须与 ALG-001 inheritance
gate 的相同 pitch、zero-rate 结果一致。

### 9.4 ALG-001 inheritance gate

Hard Qualification 必须用未修改的 `ALG001-FIXTURE-v1`、ALG-001 Profile v1 场景和容差，
把新 candidate 的 `relative_pitch_rate_rad_s` 固定为 `0.0`，重新验证：

- `ALG001-N00/P01/P02/N01/N02` 的 neutral、direction 和 magnitude monotonicity；
- proportional-style consistency、symmetry、finite output 和三次 repeatability；
- `ALG001-F01`–`F08`、`D01`–`D04` 的 layer 分类和 fail-close；
- `ALG001-R01`、factory loading 和全部 Level B `FlightCommand` validation。

该 gate 不重跑或修改 ALG-001 Candidate A 的历史 Result；它只证明 ALG-002 candidate 没有
破坏继承能力。

### 9.5 Damping 关系与 effect gate

对正常场景定义有符号 damping separation：

```text
P_div = intent_P00 - intent_P01
P_rec = intent_P02 - intent_P00
N_div = intent_N01 - intent_N00
N_rec = intent_N00 - intent_N02
```

**Damping effect present** 要求四个值分别严格超过对应的 9.2 关系容差：

```text
P_div > tol(intent_P00, intent_P01)
P_rec > tol(intent_P02, intent_P00)
N_div > tol(intent_N01, intent_N00)
N_rec > tol(intent_N00, intent_N02)
```

并且正负场景必须通过 9.6 的镜像一致性。四个冻结的正常非零 rate 场景都必须真实体现
rate 对 feedback 的正确方向影响；不能以某一个场景或某一个 pitch 符号上的趋势响应代替。

### 9.6 Mirror、repeatability 与 finite

在关系容差内要求：

```text
intent_P00 ~= -intent_N00
intent_P01 ~= -intent_N01
intent_P02 ~= -intent_N02
intent_Z01 ~= -intent_Z02
```

每个正常场景在相同 state、`dt`、configuration 和 reset state 下至少重复三次，最大两两
差异必须在 repeatability tolerance 内。所有 intent 和全部 Level B payload 必须 finite。

### 9.7 Pitch-rate fail-close 场景

| Scenario | 输入 | Layer | PASS 条件 |
| --- | --- | --- | --- |
| `ALG002-F01` | valid IMU 的 rate 为 `None` | state validation | 拒绝完整测量矛盾，不调用 controller |
| `ALG002-F01` | 合法 unobserved IMU，rate 为 `None` | controller | 返回合法无载荷 safe-stop |
| `ALG002-F02` | rate 为 `NaN/+Inf/-Inf` | state validation | 三个 variant 均被拒绝，不调用 controller |
| `ALG002-F03` | `imu.valid=true`, `imu.fresh=false`，聚合 freshness 同步为 false | controller | 合法一致 state；返回合法无载荷 safe-stop |
| `ALG002-F04` | IMU/motors 均 valid/fresh，但 `required_inputs_fresh=false` | controller | 合法 state；返回合法无载荷 safe-stop |

ALG-001 的 motor、E-STOP、缺失输入和其它 safety contract 通过 9.4 inheritance gate 继续适用。
所有 controller-layer safe-stop 必须精确等于 `FlightCommand.safe_stop()` 并通过
`validate_flight_command()`；validation-layer 拒绝不能记作 controller PASS。

### 9.8 `dt` 与 reset 场景

| Scenario | 输入 | PASS 条件 |
| --- | --- | --- |
| `ALG002-D00A` | 合法固定 state/config，`dt=0.02` | 正常 intent/command，作为合法基准 |
| `ALG002-D00B` | 相同 state/config，`dt=0.037` | intent 与 D00A 在关系容差内相同 |
| `ALG002-D01` | `dt=0` | 合法无载荷 safe-stop |
| `ALG002-D02` | `dt=-0.01` | 合法无载荷 safe-stop |
| `ALG002-D03` | `dt=NaN` | 合法无载荷 safe-stop |
| `ALG002-D04` | `dt=+Inf/-Inf` | 两个 variant 均为合法无载荷 safe-stop |

`ALG002-R01`：reset 前后以相同 pitch/rate/config、但不同合法当前 motor baseline 调用。Level A
intent 必须一致；Level B 不得复用上一普通 command 或 motor baseline；reset 不修改 Runtime
authority、E-STOP/ERROR 或外部状态。候选不得借 `dt` 或 reset 引入有限差分、filter、slew-rate
或其它未经 Task Spec 允许的历史。

### 9.9 推荐 sequence 扩展

下列场景属于 **Level D recommended extension，不属于 ALG-002 Profile v1 Hard
Qualification**：

| Scenario | 预定义输入顺序 | 推荐检查 |
| --- | --- | --- |
| `ALG002-S01` | 固定 `+0.05` pitch：`+0.20 -> 0.0 -> -0.20` rate | `P01 < P00 < P02` 且两个 separation 均超容差；各结果与独立场景一致 |
| `ALG002-S02` | 固定 `-0.05` pitch：`-0.20 -> 0.0 -> +0.20` rate | `N01 > N00 > N02` 且两个 separation 均超容差；S01 的镜像且无意外历史 |
| `ALG002-S03` | `+0.05/-0.20 -> 0.0/-0.20` | 两个状态的 rate 作用均反对负 rate；zero-pitch intent 为正；各结果与独立场景一致 |

每个 sequence 前调用 reset，并可反序重放以检查顺序一致性。S03 不要求 recovering total
intent 在正 pitch 时保持负值，也不把穿过零点前反号视为 FAIL；它检查当前状态的 rate 作用
方向、zero-pitch moving 语义和无意外历史依赖。若候选存在数学不连续点必须明确解释。它们只是
预定义 `FlightState -> controller -> output` 序列，不是 dynamic/closed-loop simulation，不能
产生 recovery time、overshoot、最大扰动、机器人动力学或 Balance Recovery 结论。

### 9.10 Hard Qualification checklist

- [ ] metadata、固定 configuration、fixture 和执行命令完整可追溯；
- [ ] ALG-001 inheritance gate：PASS；
- [ ] 控制输入只使用正式 `relative_pitch_rad + relative_pitch_rate_rad_s`；
- [ ] `ALG002-P00/N00` zero-rate behavior：PASS；
- [ ] `ALG002-P01/N01` diverging behavior：相对同 pitch zero-rate baseline 沿反对 rate
  的方向变化并严格超过关系容差；
- [ ] `ALG002-P02/N02` recovering behavior：相对同 pitch zero-rate baseline 沿反对 rate
  的方向变化并严格超过关系容差，不限制 total intent sign；
- [ ] `ALG002-Z01/Z02` zero-pitch moving damping：PASS；
- [ ] damping effect present：PASS；
- [ ] sign/mirror、finite 和 repeatability：PASS；
- [ ] `ALG002-F01`–`F04` 的所有 variant 和 layer 分类：PASS；
- [ ] `ALG002-D00A/D00B`、`D01`–`D04`：PASS；
- [ ] `ALG002-R01`：PASS；
- [ ] factory loading 和所有普通/safe-stop `FlightCommand` validation：PASS；
- [ ] code/review 证明 ALG-003+ leakage：`NO`；
- [ ] 不使用 raw gyro axis/sign logic，不实现真实 actuator allocation；
- [ ] hardware access：`NO`。

任何一项失败时，总体必须为 `ALG-002 NOT QUALIFIED`。Level D 推荐 sequence 或 comparative
metrics 不能抵消 Hard Qualification 失败。

### 9.11 Comparative metrics

只有 Hard Qualification 全部 PASS 后才独立记录：

- **Damping separation**：分别报告 9.5 的 `P_div/P_rec/N_div/N_rec`，单位 intent unit；
- **Damping separation mirror error**：分别报告 `abs(P_div-N_div)` 与
  `abs(P_rec-N_rec)`；
- **Mirror symmetry error**：报告 `P00+N00`、`P01+N01`、`P02+N02` 绝对值的最大值；
- **Zero-pitch damping symmetry**：`abs(intent_Z01 + intent_Z02)`；
- **Repeatability delta**：所有正常场景三次结果的最大两两绝对差；
- **Implementation complexity**：报告可复现的 physical LOC 口径；若未测 cyclomatic
  complexity 必须明确；
- **Configuration clarity**：记录参数数量、稳定序列化值、默认值、单位、合法范围、非法值
  拒绝和 benchmark 期间是否调参。

这些指标不合成为未经依据的 100 分总分，不把 `Kd` 或任一 damping 参数越大描述为越好。
不同 Task/Profile/Level 的结果不能包装成公平同级排名。

### 9.12 Candidate Result 要求与边界

未来正式结果除第 3 节全局 metadata 外，还必须列出全部 9.10 Hard Qualification 项、所有
场景/variant、独立 comparative metrics、已知限制和未执行测试。Candidate 未建立固定
implementation commit 前不得创建 Result 或填写虚构 PASS。

ALG-002 v1 明确禁止 integral、filter/deadband/hysteresis、slew-rate/output shaping、恢复
状态机、control allocation、roll/multi-axis control 和完整动态恢复。Level A/B PASS 仅表示
固定 synthetic fixture 中的软件运动趋势/阻尼资格，不是动态仿真或硬件验证。

## 10. ALG-003 Profile v1

对应 Task Spec：[`algorithm_tasks/ALG-003.md`](algorithm_tasks/ALG-003.md)，版本 `v1`。
ALG-003 继承 ALG-001/ALG-002，只新增对小幅 synthetic pitch/pitch-rate 波动的鲁棒性。全局
Benchmark Contract 仍为 `Algorithm Benchmark v1`；本节不修改第 7、9 节 Profile 的场景、
阈值、容差或 PASS/FAIL 语义。

### 10.1 Fixture、观测量与执行约定

`ALG003-FIXTURE-v1` 基于 `make_fake_flight_state()` 的纯内存合法状态，以
`dataclasses.replace()` 设置每帧的：

```text
state.imu.relative_pitch_rad
state.imu.relative_pitch_rate_rad_s
```

必要 motor keys 仍为 `left_lift/left_pitch/right_pitch/right_lift`。

Level A 通过无 ROS、无硬件的 task-local 软件 seam 观察 Candidate 的抽象控制量，验证算法计算
本身。Level D 使用 `ALG003-FIXTURE-v1` 冻结的 Q/S 输入序列，按顺序驱动同一个 Level A
seam，并组织和评分 history、noise suppression、response delay、trend preservation、reset/replay
与 repeatability。Level D 是 deterministic software replay / benchmark orchestration 层级，不要求
Candidate 增加第二套 production API；同一个 benchmark runner 按冻结 sequence 调用 Level A seam
并计算 Level D 指标是允许且推荐的。Level D 不是 closed-loop simulation、Runtime integration、
actuator simulation 或 hardware replay。

Level B 保持独立：它观察 `FlightCommand` 与 validation，负责 factory、`FlightState`、safe-stop 和
完整 command frame；Profile 不从 motor/fan payload 反推 intent，也不评分真实执行器方向。

fixture 中所有序列均为显式列值，不调用 runtime random generator。每个独立 run 使用同一
固定 candidate configuration，先创建全新 controller 或调用 `reset()`，再输入该场景的未计分
priming sample（若有）和计分序列。除 `dt` 场景外，基准 `dt=0.020 s`。

`ALG003-FIXTURE-v1` 只是 synthetic software noise fixture。`±0.004 rad` pitch noise、
`±0.04 rad/s` pitch-rate noise、`±0.05 rad` meaningful pitch 和 `±0.20 rad/s` meaningful rate
不是 Hiwonder IMU 实测统计、机器人振动谱、量化误差模型、安全 envelope、动态模型或硬件
性能阈值。

### 10.2 Raw inherited baseline

同一 sequence 的 raw inherited baseline 独立按下式计算：

```text
b_i = -1.0 * pitch_i - 0.1 * rate_i
```

其中 `1.0 intent/rad` 和 `0.1 intent/(rad/s)` 冻结自已资格化的 ALG-001/ALG-002 软件继承
参考配置。benchmark runner 必须直接实现该公式；不得导入当前 ALG-002 Candidate A production
module，不得让 ALG-003 candidate 修改 baseline，也不得按场景重新调参。该 baseline 是公平的
软件比较参考，不把 PD 写成 ALG-003 必选实现；candidate 可以使用任意可解释的输入抑噪方法，
但都与相同 `b_i` 比较。

### 10.3 指标、单位与容差

令计分 intent sequence 为 `y_0 ... y_(n-1)`，均使用 intent unit。定义：

```text
TV(y)   = sum(abs(y_i - y_(i-1))), i=1..n-1
PEAK(y) = max(abs(y_i))
MAA(y)  = sum(abs(y_i)) / n
P2P(y)  = max(y_i) - min(y_i)
```

有效符号零容差固定为 `eps_sign = 2e-3 intent unit`。计算 sign reversal 时先删除所有
`abs(y_i) <= eps_sign` 的样本，再统计剩余相邻样本符号改变的次数；插入零不能隐藏一次反转。
若剩余样本少于两个，计数为零。
该零带只用于区分“有效符号反转”和已被压低的残余活动，不替代继承 direction 容差、meaningful
response 阈值或其它数值 gate。

通用 finite/repeatability/mirror 比较继续使用：

```text
abs_tol = 1e-9 intent unit
rel_tol = 1e-6
tol(a,b) = 1e-9 + 1e-6 * max(abs(a), abs(b))
```

镜像序列的对齐输出要求 `abs(y_positive_i + y_negative_i) <= tol(...)`。每个完整 run 重复三次，
相同索引的最大两两差必须在 `tol` 内。所有 candidate intent、baseline 与 Level B payload 必须
finite。“更平滑”“活动较小”等没有上述公式和阈值的描述不能作为 PASS。

### 10.4 冻结 noise sequence

下表中一个方括号元素表示 `(pitch rad, rate rad/s)`；`*2` 是文档简写，runner 必须展开为
列出的六帧按原顺序重复一次，共 12 个计分样本。

| Scenario | 未计分 priming | 12 帧计分序列 | 目的 |
| --- | --- | --- | --- |
| `ALG003-Q01` | `(0,0)` | `[(+.003,+.03),(-.003,-.03),(+.004,+.04),(-.004,-.04),(+.002,+.02),(-.002,-.02)] * 2` | 平衡附近 angle+rate 小噪声 |
| `ALG003-Q02` | `(+.05,0)` | `[(+.053,+.03),(+.047,-.03),(+.054,+.04),(+.046,-.04),(+.052,+.02),(+.048,-.02)] * 2` | 正非零稳定姿态附近噪声 |
| `ALG003-Q03` | `(-.05,0)` | Q02 每帧 pitch/rate 同时取反 | Q02 的精确负镜像 |
| `ALG003-Q04` | `(0,0)` | `[(0,+.04),(0,-.04),(0,+.03),(0,-.03),(0,+.02),(0,-.02)] * 2` | 平衡姿态附近 rate-only 噪声 |

raw baseline 的冻结校核值为：

| Scenario | `TV(b)` | reversal | `PEAK(b)` | `MAA(b)` | `P2P(b)` |
| --- | ---: | ---: | ---: | ---: | ---: |
| `Q01` | `0.134` | `11` | `0.008` | `0.006` | `0.016` |
| `Q02` | `0.134` | `0` | `0.058` | `0.050` | `0.016` |
| `Q03` | `0.134` | `0` | `0.058` | `0.050` | `0.016` |
| `Q04` | `0.066` | `7` | `0.004` | `0.003` | `0.008` |

Q03 的 baseline 与 Q02 逐帧奇对称。数值比较使用未舍入的公式结果；表中三位小数只用于人工
审核。

### 10.5 Noise Suppression Hard Gate

下列要求在 10.10 的每个合法 `dt` variant 上分别成立：

| Scenario | `TV(candidate)` | reversal | activity/peak | 其它 |
| --- | ---: | ---: | --- | --- |
| `Q01` | `<= 0.40 * TV(raw) = 0.0536` | `<= 2` 且不超过 raw | `PEAK <= 0.0040`; `MAA <= 0.0024` | finite |
| `Q02` | `<= 0.60 * TV(raw) = 0.0804` | 不高于 raw（即 `0`） | `P2P <= 0.0120` | finite |
| `Q03` | `<= 0.60 * TV(raw) = 0.0804` | 不高于 raw（即 `0`） | `P2P <= 0.0120` | finite；与 Q02 镜像 |
| `Q04` | `<= 0.40 * TV(raw) = 0.0264` | `<= 2` 且不超过 raw | `PEAK <= 0.0020`; `MAA <= 0.0012` | finite |

所有不等式包含端点；浮点实现可以在阈值比较中加入第 10.3 节 `abs_tol`，不得加入未版本化的
宽松裕量。Q01/Q04 同时形成 equilibrium noise activity 与 sign-reversal suppression gate；
Q02/Q03 防止只在绝对零附近工作的机制绕过非零姿态噪声。四项全部 PASS 才能记
`Noise Suppression Gate: PASS`。

Profile 不要求完全零输出，也不限定 deadband、low-pass、moving average、median、hysteresis
或其它实现。最终 intent 的 slew-rate limiter 或 output shaping 属于 ALG-004，不能作为本 gate
的 ALG-003 实现依据。

### 10.6 冻结 meaningful signal sequence

`Q01[0:8]` 表示 Q01 展开后前 8 个计分样本。

| Scenario | 明确输入顺序 | raw 参考 |
| --- | --- | --- |
| `ALG003-S01` | reset；`Q01[0:8]`；随后 `(+.05,+.20)` 保持 6 帧 | meaningful tail `-0.070` |
| `ALG003-S02` | S01 每帧 pitch/rate 同时取反 | meaningful tail `+0.070` |
| `ALG003-S03P` | reset；`(+.05,0)` 6 帧；随后 `(+.05,+.20)` 6 帧 | `-0.050 -> -0.070` diverging |
| `ALG003-S03N` | S03P 的精确负镜像 | `+0.050 -> +0.070` diverging |
| `ALG003-S04P` | reset；`(+.05,0)` 6 帧；随后 `(+.05,-.20)` 6 帧 | `-0.050 -> -0.030` recovering |
| `ALG003-S04N` | S04P 的精确负镜像 | `+0.050 -> +0.030` recovering |

这些是预定义 open-loop software input replay，不是机器人状态由输出推进的 closed-loop dynamic
simulation。

### 10.7 Signal Preservation Hard Gate

该 gate 与 10.5 独立判定，不能由 noise 指标抵消。

**Meaningful positive/negative response：** S01/S02 从 meaningful tail 第一帧起计数。前三帧内
至少一帧必须达到与 raw baseline 同方向且绝对值不小于 `0.035 intent unit` 的有效响应。
`frames_to_response` 是首个满足该条件的 1-based 帧号，必须 `<=3`；同时记录从变化前边界到
该帧结束的累计 synthetic elapsed time。

**Steady nonzero preservation：** 分别取 S01/S02 最后 3 帧的有符号均值。S01 必须位于
`[-0.084,-0.056]`，S02 必须位于 `[+0.056,+0.084]`，即保留 raw steady magnitude 的
`80%..120%` 并保持正确方向。恒零或长期衰减到零明确 FAIL。

**Diverging trend：** 分别取 S03P/N 转换前最后 3 帧与转换后最后 3 帧均值，记为
`before/after`。要求：

```text
S03P: before - after >= 0.010 intent unit
S03N: after - before >= 0.010 intent unit
```

**Recovering trend：** 同样计算 S04P/N 的窗口均值，要求：

```text
S04P: after - before >= 0.010 intent unit
S04N: before - after >= 0.010 intent unit
```

四个 `0.010` 阈值是 raw damping separation `0.020` 的 50%。它们保留 ALG-002 的 signed damping
方向，不限制 recovering total intent 必须保持 pitch-error 符号。S01/S02、S03P/N、S04P/N
还必须逐帧通过 10.3 的镜像 gate。上述项目全部 PASS 才能记
`Signal Preservation Gate: PASS`。

因此 trivial zero-output candidate 会同时在 meaningful direction、response delay、steady
nonzero、diverging 和 recovering gate 失败；即使它的 Q01/Q04 活动为零，也必须判
`ALG-003 NOT QUALIFIED`。

### 10.8 ALG-001 / ALG-002 inheritance gate

使用未修改的 `ALG001-FIXTURE-v1`、`ALG002-FIXTURE-v1` 数值、关系、fail-close 场景和容差，
重新验证当前 ALG-003 candidate，而不是引用历史 Candidate A 的 PASS。考虑到 ALG-003 允许
显式时间历史，每个原有正常 state 在 reset 后保持 6 帧；首帧仍须 finite 且方向正确（neutral
仍在零容差内），最后 3 帧均值必须满足原 Profile 的全部 neutral、direction、magnitude、
proportional-style、zero-rate、diverging、recovering、zero-pitch moving、signed damping 和
mirror 关系。不得改变原输入值、容差或关系方向。

同时重新执行原 Profile 的 state-validation/controller fail-close、factory loading、reset、
repeatability 和 Level B `FlightCommand` gate。继承 gate 只适配有历史 candidate 的观测窗口，
不修改第 7、9 节，也不重写 ALG-001/ALG-002 历史 Result。ALG-001 inheritance 与 ALG-002
inheritance 必须分别 PASS。

### 10.9 Invalid/stale/freshness 与 history invalidation

| Scenario | 输入 / layer | PASS 条件 |
| --- | --- | --- |
| `ALG003-F01` | valid IMU 的 pitch 或 rate 为 `None` / state validation | 两个 variant 均拒绝，不调用 controller |
| `ALG003-F02` | pitch 或 rate 为 `NaN/+Inf/-Inf` / state validation | 所有 variant 均拒绝，不调用 controller |
| `ALG003-F03` | 合法 unobserved/invalid IMU / controller | 合法无载荷 safe-stop；本地历史失效 |
| `ALG003-F04` | `imu.fresh=false` / controller | 合法无载荷 safe-stop；本地历史失效 |
| `ALG003-F05` | `required_inputs_fresh=false` / controller | 合法无载荷 safe-stop；本地历史失效 |
| `ALG003-F06` | 必要 motor unobserved/invalid/stale/unhealthy 或 E-STOP 非明确 false / controller | 每个合法 variant 均 safe-stop；本地历史失效 |

每个 controller-layer 场景先用 Q02 或 Q03 建立非零 history，再注入故障。safe-stop 必须精确
等于 `FlightCommand.safe_stop()` 并通过 validation，不复用旧 command。故障后的第一条合法
输入结果必须与 `reset()` 后同一输入的 cold-start 结果在 10.3 容差内相同。validation-layer
拒绝后，由 harness 调用 `reset()` 再作同样的 cold-start 比较；不得把 controller 未运行记成
controller-layer PASS。

### 10.10 `dt` contract

全部 Q/S Hard Gate 分别执行以下三种 `dt` variant，sequence 的输入值和计分窗口不变：

| Scenario | 每帧 `dt` |
| --- | --- |
| `ALG003-D00A` | 恒定 `0.020 s` |
| `ALG003-D00B` | 恒定 `0.037 s` |
| `ALG003-D00C` | `0.020, 0.037` 交替，第一帧为 `0.020 s` |

candidate 必须说明 filter/history 在变 `dt` 时的语义；时间常数配置使用秒。固定帧方案只有在
三个 variant 全部通过且明确说明 elapsed-time 差异时可接受。response report 同时保存 frame
count 和到首个有效响应为止的 `sum(dt)`，不得将其声称为真实机器人响应时间。

非法值场景 `ALG003-D01=0`、`D02=-0.01`、`D03=NaN`、`D04=+Inf/-Inf` 均要求合法无载荷
safe-stop、history invalidation 和下一合法样本 cold-start 等价。非法 `dt` 不得更新、保留或
继续输出旧 filtered state。

### 10.11 Reset、symmetry 与 repeatability

`ALG003-R01`：运行 Q02 建立 history，调用 `reset()`，再运行 Q01；Q01 每帧必须与全新
controller 的 Q01 cold run 等价。Level B 不复用 Q02 的 motor baseline 或普通 command。

`ALG003-R02`：按 `Q02 -> reset -> Q03` 与 `Q03 -> reset -> Q02` 两种顺序执行；同一场景结果
与执行顺序无关，且 Q02/Q03 保持逐帧镜像。reset 清除所有 filter/history/latch/cache，不修改
Runtime、IMU zero、authority 或 E-STOP，不访问硬件。

所有 Q/S/继承正常场景按 10.3 重复三次；三个 `dt` variants 各自判 repeatability。对所有明确
的正负 mirror pair 执行逐帧 symmetry gate。任何 history 泄漏、执行顺序依赖或不对称超容差
均 FAIL。

### 10.12 Level B、factory 与 capability boundary

candidate 必须通过现有 `module.path:factory` loader，固定配置可稳定序列化，非法/unknown 配置
明确拒绝。所有合法正常帧与 safe-stop 均通过 `validate_flight_command()`；普通命令拥有完整
motor keys 和 `[0,1]` 的左右 fan payload。算法模块和测试不得导入或访问 ROS/hardware I/O。

review 必须确认：

- 控制输入只使用统一 `relative_pitch_rad + relative_pitch_rate_rad_s + dt`；
- 没有最终 intent slew-rate、output shaping 或其它 ALG-004 输出限制；
- 没有 ALG-005 recovery state/timeout/process management；
- 没有 ALG-006 allocation/actuator direction、ALG-007 roll/multi-axis 或 ALG-008 full recovery；
- Flight API、Runtime、default controller、hardware mapping 和既有安全机制未改变；
- hardware access：`NO`。

### 10.13 Hard Qualification checklist

- [ ] metadata、固定 configuration、fixture、raw baseline 与执行命令完整可追溯；
- [ ] ALG-001 inheritance：PASS；
- [ ] ALG-002 inheritance：PASS；
- [ ] deterministic fixture：PASS；
- [ ] Noise Suppression Gate：PASS；
- [ ] Q01/Q04 sign-reversal suppression 与 equilibrium activity：PASS；
- [ ] Q02/Q03 nonzero-pose suppression 与 symmetry：PASS；
- [ ] Signal Preservation Gate：PASS，且未被 noise gate 抵消；
- [ ] meaningful positive/negative response、delay 与 steady nonzero：PASS；
- [ ] diverging/recovering signed trend preservation：PASS；
- [ ] `D00A/B/C` 合法 `dt` 与 `D01`–`D04` 非法 `dt`：PASS；
- [ ] `F01`–`F06` validation/fail-close/history invalidation：PASS；
- [ ] `R01/R02` reset/history isolation：PASS；
- [ ] finite、mirror symmetry 与三次 repeatability：PASS；
- [ ] factory loading、固定配置和全部 Level B `FlightCommand` validation：PASS；
- [ ] ALG-004+ capability leakage：`NO`；
- [ ] hardware access：`NO`。

任一项 FAIL 时 Overall 必须为 `ALG-003 NOT QUALIFIED`。trivial zero-output、极强 deadband、
无限期旧 filtered state 或单纯“最平滑”的 candidate 不能通过 Signal Preservation Gate。

### 10.14 Comparative metrics

只有 Hard Qualification 全部 PASS 后才分别记录，不合成总分：

- 每个 Q 场景的 `TV(raw)`、`TV(candidate)` 和 reduction ratio
  `1 - TV(candidate)/TV(raw)`；
- sign reversal raw/candidate count 与 reduction；
- Q01/Q04 `PEAK`、`MAA`，Q02/Q03 `P2P`；
- S01/S02 `frames_to_response` 与 synthetic elapsed time；
- steady signal attenuation：最后 3 帧均值绝对值除以 `0.070`；
- trend preservation error：分别报告四个实际 separation 与 raw `0.020` 的绝对误差；
- mirror symmetry error：所有 mirror pair 的 `max(abs(y_pos_i+y_neg_i))`；
- repeatability delta：全部三次 run 对齐样本的最大两两绝对差；
- implementation complexity：给出可复现 LOC/cyclomatic 口径；未测项明确写明；
- configuration clarity：参数数量、序列化值、单位、合法范围、非法值拒绝及是否中途调参。

不能仅按“最平滑”排名，不把某个 filter time constant、deadband 或 hysteresis 越大描述为越好。
不同 Task/Profile/Level 的指标不能包装为公平同级排名。

### 10.15 Candidate Result、Level 与结论边界

正式 Result 除第 3 节 metadata 外，还必须列出 10.13 全部 Hard Gate、每个 scenario/variant、
两个独立总 gate、raw/candidate metrics、已知限制和未执行测试。candidate 必须先有固定独立
implementation commit；本 Profile 不创建或预填虚构 Result。

ALG-003 v1 Hard Qualification 包含 Level A、Level B 和本节预定义的 Level D deterministic
sequence replay。Level D 不是 dynamic simulation。Level C synthetic DRY_RUN 可补充但不替代
Hard Gate；Level E/F 不属于本 Profile。

PASS 只能表述为固定 synthetic fixture 上的 ALG-003 软件资格，不能声称真实 IMU 噪声已验证、
机器人不会振荡、电机不会抖动、真实 actuator direction 已确认或 Balance Recovery 已实现。

## 11. ALG-004 Profile v1

对应 [ALG-004 Task Spec v1](algorithm_tasks/ALG-004.md)。本 Profile 只约束已生成 abstract recovery intent 的输出侧，不改变全局 `Algorithm Benchmark v1` 或历史 ALG-001/002/003 Profile 的输入、阈值、容差、关系方向和 Result。ALG-003 负责输入侧 pitch/rate 估计与噪声抑制；ALG-004 不重新过滤输入、不重调 `Kp/Kd`，不做 actuator allocation。

### 11.1 观测、fixture 与执行约定

`ALG004-FIXTURE-v1` 的 Level A/D 输入直接是每帧 synthetic `requested_intent` 和 `dt_i`，输出是 task-local `shaped_intent`。此 seam 仅用于资格验证，不是公开 Flight API；不得从 motor/fan payload 反推。每个独立 run 使用同一固定、稳定序列化的 candidate 配置，创建 fresh controller 或先 `reset()`，从精确 `y_(-1)=0.0 intent unit` 开始；无未计分 priming。`× n` 表示连续重复，镜像场景逐帧精确取反。所有序列确定性列值，无 runtime random generator。Level D 只组织确定性软件 replay，不是 dynamic/closed-loop simulation 或硬件 replay。

Level B 独立使用纯内存合法 `FlightState`、现有 factory/loader 与校验函数。普通命令须复制**当前合法完整** `left_lift/left_pitch/right_pitch/right_lift` motor feedback position hold，左右 fan 均为 `0.0`，并通过 `validate_flight_command()`；safe-stop 为现有精确无载荷 `FlightCommand.safe_stop()`。不得把 shaped intent 编码为 motor/fan direction。Factory 固定配置、拒绝非法及 unknown 配置；算法和测试不导入或访问 ROS/hardware I/O。正常、继承、fail-close 与 reset/history 的 Level B 结果分别评分，不能由 Level A 替代。

### 11.2 软件 envelope、容差和逐帧 Hard Gates

```text
U = max_abs_intent = 0.10 intent unit
S = max_slew_rate = 2.0 intent unit/s
r_i = requested_intent
t_i = clamp(r_i, -U, +U)
y_i = shaped_intent
dt_i = 当前正有限秒数
y_(i-1) = 前一合法 shaped_intent
```

cold start、`reset()`、controller-layer fail-close 或非法 `dt` 后，上一输出基线均为 `y_(-1)=0.0 intent unit`。包括首帧在内，每个合法 update 必须同时满足：

```text
finite(y_i)
abs(y_i) <= U + tol(abs(y_i), U)
abs(y_i - y_(i-1)) <= S * dt_i + tol(abs(y_i - y_(i-1)), S * dt_i)
min(y_(i-1), t_i) - tol(y_i, min(y_(i-1), t_i)) <= y_i
y_i <= max(y_(i-1), t_i) + tol(y_i, max(y_(i-1), t_i))
```

后两项是 Directed Transition / no-overshoot Gate：输出朝当前 target 移动或保持，不得人为远离或越过 target 制造 shaping 自身的 overshoot；不推断真实机器人闭环单调性。不得以首帧无 previous output 绕过 slew。

沿用 ALG-003 Profile 冻结的通用比较方式：

```text
eps_sign = 2e-3 intent unit
abs_tol = 1e-9 intent unit
rel_tol = 1e-6
tol(a,b) = 1e-9 + 1e-6 * max(abs(a), abs(b))
TV(y) = sum(abs(y_i - y_(i-1))), i=1..n-1
```

有效 sign reversal 先删去 `abs(y_i)<=eps_sign` 的样本，再数剩余相邻样本的符号变化；不足两样本计零，插零不能隐藏真实反向。只允许本 Profile 固定 tolerance，不得添加未版本化裕量。所有合法 requested intent、target、输出和 Level B payload 均须 finite。

`U/S` 仅是 **ALG-004 Profile v1 synthetic software qualification envelope**，不是 CyberGear rad、motor velocity、torque、PWM、fan thrust、机器人实际安全 envelope 或真实执行器 capability；不建立物理语义映射。

### 11.3 `ALG004-FIXTURE-v1`：neutral 与 steady

每行独立 reset；默认 `dt=0.020 s`，还须按 11.7 的其它合法 variant 完整重跑。

| Scenario | requested-intent sequence | clamped target |
| --- | --- | ---: |
| `ALG004-N00` | `0.00 × 6` | `0.00` |
| `ALG004-P01` / `ALG004-N01` | `+0.03 × 6` / P01 精确取反 | `±0.03` |
| `ALG004-P02` / `ALG004-N02` | `+0.07 × 6` / P02 精确取反 | `±0.07` |
| `ALG004-P03` / `ALG004-N03` | `+0.10 × 6` / P03 精确取反 | `±0.10` |
| `ALG004-P04` / `ALG004-N04` | `+0.20 × 6` / P04 精确取反 | `±0.10` |

N00 每帧在 `abs_tol` 内为零；P/N pair 逐帧镜像。P04/N04 必须以 `±0.10` 为 clamp target，不能把 `±0.20` 当作允许输出或物理限值。

### 11.4 Step、full reversal 与高频反向

| Scenario | reset 后完整 requested-intent sequence | clamped target / 目的 |
| --- | --- | --- |
| `ALG004-S01P` | `0.00 × 3; +0.07 × 6` | 第二段 `+0.07` |
| `ALG004-S01N` | S01P 完整 sequence 精确取反 | 第二段 `-0.07` |
| `ALG004-S02P` | `0.00 × 3; +0.20 × 6` | 第二段 `+0.10` |
| `ALG004-S02N` | S02P 完整 sequence 精确取反 | 第二段 `-0.10` |
| `ALG004-S03P` | `+0.20 × 6; -0.20 × 12` | `+0.10 -> -0.10` |
| `ALG004-S03N` | S03P 完整 sequence 精确取反 | `-0.10 -> +0.10` |
| `ALG004-S04P` | `[+0.20, -0.20] × 6`，共 12 帧 | `[+0.10, -0.10] × 6` |
| `ALG004-S04N` | S04P 完整 sequence 精确取反，即 `[-0.20, +0.20] × 6` | S04P 镜像 |

S04 target 的冻结 reference 为 `TV(target)=2.20 intent unit`、`effective sign reversal(target)=11`。这些是开环软件请求，不是机器人状态由输出推进的 dynamic simulation。

### 11.5 Steady、step、reversal Hard Gates

以下各门槛互不抵消；11.2 的逐帧契约始终同时适用。

**Steady Signal Preservation：** P01–P04/N01–N04，以及 S01/S02 最终常值段，分别取最后三帧有符号平均值 `mean_tail`。须与非零 clamped target 同号，且满足：

```text
0.80 * abs(target) <= abs(mean_tail) <= abs(target) + tol(abs(mean_tail), abs(target))
```

下界只可使用固定 `abs_tol` 比较；恒零、长期过度衰减或输出固定很小值 FAIL。S03 第二段最后三帧也须满足同一 80%..100% 门槛。

**Step Response：** P01–P04/N01–N04 从 cold-start 非零 target 首帧计数；S01/S02 从第二段首帧计数。前三帧内至少一帧同号且 `abs(y)>=0.50*abs(target)`。记录首次达标的 1-based `frames_to_50pct` 和从变化边界至该帧结束累计的 `synthetic_elapsed_time_to_50pct=sum(dt_i)`。仅固定 `abs_tol` 用于阈值比较；合成时间不是实机响应 SLA。

**Full Reversal：** S03 第一段先建立非零 history。第二段前六帧至少一帧与新 opposite target 同号且达到其幅值的 50%；`±0.10` target 时须达到相反方向 `0.05`。第二段末三帧通过 steady gate；全程通过 finite、amplitude、slew、directed transition 和 mirror。永久零附近、长期旧方向、极慢规避反向或瞬时跳变均 FAIL。

**High-frequency Reversal：** S04P/N 的 12 帧分别满足：

```text
TV(candidate) <= 0.60 * TV(target) = 1.32 intent unit
effective sign reversal(candidate) <= 4
```

TV 比较只可用固定 `abs_tol`，反向整数计数不得放宽；逐帧仍通过全部输出契约。本 gate 与 steady gate 独立：恒零在 steady gate FAIL；单纯逐帧 clamp `±0.20 -> ±0.10` 在 slew/TV FAIL；持续小幅正负 ping-pong 即使 TV 低也因有效反向次数 FAIL。

### 11.6 ALG-001 / ALG-002 / ALG-003 inheritance

未来 ALG-004 candidate 的**最终 post-shaped abstract intent** 是评分对象；必须重新运行未修改的 `ALG001-FIXTURE-v1`、`ALG002-FIXTURE-v1`、`ALG003-FIXTURE-v1`，不能引用历史 Candidate A PASS 代替。原输入、阈值、关系方向与历史 Result 不变。ALG-001/002 正常 state 沿用 ALG-003 Profile 10.8 的六帧保持、首帧方向/finite 与末三帧均值观测窗口。ALG-001 neutral/direction/proportional-style、ALG-002 signed damping/trend、ALG-003 noise suppression **和** signal/trend preservation、各自 fail-close、reset、factory、Level B、mirror 与 repeatability 均须重新通过。`output *= 0.1` 等破坏继承语义的实现 FAIL。

历史 ALG-003 Profile 10.12 中仅因“ALG-004 属未来任务”而禁止最终 intent output shaping 的一项，在当前 ALG-004 inheritance gate 自然 supersede，不作为失败条件；不修改历史 Profile。其余可观察能力与 ALG-005+ future-task prohibition 继续有效。

### 11.7 合法 `dt`、mirror 与 repeatability

全部正常 N/P/S、steady/step/reversal Hard Gate 与 ALG-001/002/003 inheritance 正常场景须在每个 variant 下分别完整运行、评分和重复三次：

| Variant | 每帧真实 `dt_i` |
| --- | --- |
| `ALG004-D00A` | 恒定 `0.020 s` |
| `ALG004-D00B` | 恒定 `0.037 s` |
| `ALG004-D00C` | `0.020, 0.037 s` 交替，第一帧 `0.020 s` |

D00C 沿完整 run 连续推进索引，跨 S01/S02/S03 segment 边界不重启。slew 用每帧真实 `dt_i`，不能假设固定 period。相同索引输出的三次最大两两差须在 `tol()` 内。P01–P04/N01–N04、S01–S04 P/N 及继承中的明确 mirror pair 均逐帧检查 `abs(y_positive_i+y_negative_i)<=tol(y_positive_i,-y_negative_i)`。任何 history 泄漏、执行顺序依赖、不重复或不对称超 tolerance 均 FAIL。每次重复使用相同 dt schedule 和固定配置。

### 11.8 Fail-close 与非法 `dt`

| Scenario | 输入 / layer | PASS 条件 |
| --- | --- | --- |
| `ALG004-F01` | valid IMU 的必要 pitch 或 rate 为 `None` / state validation | 两种缺失分别拒绝，不调用 controller；harness reset 后 cold-start 等价 |
| `ALG004-F02` | pitch/rate 为 NaN、`+Inf/-Inf` / state validation | 全部 variant 拒绝，不调用 controller；harness reset 后 cold-start 等价 |
| `ALG004-F03` | 合法 unobserved/invalid IMU / controller | 精确无载荷 safe-stop、双层历史清除、cold-start 等价 |
| `ALG004-F04` | IMU stale / controller | 同上 |
| `ALG004-F05` | `required_inputs_fresh=false` / controller | 同上 |
| `ALG004-F06` | 必要 motor unavailable/invalid/stale/unhealthy 或 E-STOP unknown/active / controller | 各合法 variant 分别执行，同上 |
| `ALG004-D01` | `dt=0` / controller | 同上 |
| `ALG004-D02` | `dt=-0.01` / controller | 同上 |
| `ALG004-D03` | `dt=NaN` / controller | 同上 |
| `ALG004-D04` | `dt=+Inf/-Inf` / controller | 两种分别执行，同上 |

每个 controller-layer case 先用合法前置 sequence 建立**非零 ALG-003 输入/filter history 和 ALG-004 shaped-output history**，再注入故障。返回须精确等于合法 `FlightCommand.safe_stop()`，无旧 shaped intent/ordinary command/cache/latch。下一合法输入在 `tol()` 内等价于 `reset()` 加同一输入的 fresh cold start。非法 dt 同样清除双层历史。state-validation layer 由 `validate_flight_state()` 先拒绝、不调用 controller；之后 harness `reset()` 再检查恢复，不把前置拒绝记为 controller PASS。F/D controller 场景在每个合法 dt variant 的前置 history 下执行。

### 11.9 Reset / history isolation

`ALG004-R01`：运行 P04 建立接近 `+0.10` 的非零 shaping history，调用 `reset()`，再运行 N02；N02 与全新 controller 的 N02 cold run 逐帧在 `tol()` 内一致。

`ALG004-R02`：分别执行 `P02 -> reset -> N02` 和 `N02 -> reset -> P02`；同场景结果与顺序无关，P02/N02 逐帧镜像。reset 清除 ALG-003 输入/filter history、ALG-004 shaped output、旧 ordinary command/cache/latch；Level B 不复用旧 motor baseline。reset 不改变 Runtime、authority、IMU zero、E-STOP 或外部硬件状态。R01/R02 在三个合法 dt variant 下执行。

### 11.10 Level 与 Hard Qualification checklist

| Level | ALG-004 v1 要求 | 结论边界 |
| --- | --- | --- |
| A | **HARD GATE** | task-local seam 的数值、历史与继承 |
| B | **HARD GATE** | factory、state/command validation、当前完整 hold frame、fan-zero、safe-stop |
| C | optional preview | 不能代替 A/B/D |
| D | **HARD GATE** | deterministic software replay，非 dynamic simulation |
| E | **NOT REQUIRED** | dynamic benchmark / trusted simulation 从 ALG-005 开始 |
| F | **NOT AUTHORIZED / NOT EXECUTED** | 真实硬件另需独立授权 |

正式 Candidate Result 必须逐项报告 PASS/FAIL；Candidate 未实现时不预填资格：

- [ ] metadata、baseline/implementation commit、配置、Profile、fixture、环境、命令与全部 scenario/variant 完整；
- [ ] finite output：PASS；
- [ ] Output Envelope Gate：PASS；
- [ ] Slew Rate Gate（包括首帧与当前 `dt_i`）：PASS；
- [ ] Directed Transition / no-overshoot Gate：PASS；
- [ ] Neutral Gate：PASS；
- [ ] Steady Signal Preservation Gate：PASS；
- [ ] Step Response Gate：PASS；
- [ ] Saturation Gate：PASS；
- [ ] Full Reversal Gate：PASS；
- [ ] High-frequency Reversal Gate：PASS；
- [ ] D00A/B/C 三种合法 dt variants：PASS；
- [ ] D01–D04 invalid dt fail-close：PASS；
- [ ] F01–F06 validation/fail-close 与双层 history invalidation：PASS；
- [ ] R01/R02 reset/history isolation：PASS；
- [ ] mirror symmetry：PASS；
- [ ] 三次 repeatability：PASS；
- [ ] ALG-001 inheritance：PASS；
- [ ] ALG-002 inheritance：PASS；
- [ ] ALG-003 inheritance：PASS；
- [ ] factory/configuration：PASS；
- [ ] Level B `FlightCommand` validation：PASS；
- [ ] Future-task boundary：PASS；
- [ ] hardware access：`NO`；hardware validation：`NOT AUTHORIZED / NOT EXECUTED`。

任一全局或本节 Hard Gate FAIL，`Overall = ALG-004 NOT QUALIFIED`；比较指标不得抵消。禁止新 pitch/rate filter、`Kp/Kd` 重调、integral/anti-windup、ALG-005 process/state machine、ALG-006 motor/fan allocation、ALG-007 multi-axis、ALG-008 full recovery；不改 Flight API、Runtime、adapters、default/teaching controller、hardware manager/mapping、E-STOP、watchdog 或 soft limits。

### 11.11 Comparative metrics 与结论

仅全部 Hard Qualification PASS 后，按场景和 dt variant 分别报告：`max_abs_output`；`max_observed_slew_rate=max(abs(y_i-y_(i-1))/dt_i)`（包含首帧）；steady attenuation ratio `abs(mean_tail)/abs(target)`；首次达到 target 50%/80% 的帧数和累计 synthetic elapsed time；S03 首次有效越零/相反符号时间与达到 opposite 50% 的时间；S04 TV、相对 `TV(target)` 的 reduction ratio `1-TV(candidate)/TV(target)`、有效 sign reversal count；最大 mirror symmetry error；三次 repeatability delta；implementation physical LOC（注明口径）；configuration clarity（参数、单位、范围、非法值拒绝、稳定序列化和是否中途调参）。未测项明确注明，不合成为未经依据的 100 分总分。

`Actuator-safe Output` 只是 roadmap 标签。即使未来 `ALG-004 QUALIFIED`，也只证明固定 synthetic fixture 中 abstract intent 满足幅值、变化率、信号保留、符号切换与历史重置约束，较适合后续 actuator integration；不证明 `REAL ACTUATOR SAFE`、CyberGear/fan/PWM 安全、allocation/方向正确、真实执行器动态安全、机器人可恢复平衡或真实 Balance Recovery。当前 Candidate `NOT IMPLEMENTED`，无 Result，无硬件验证。

## 12. ALG-005 Profile v1

对应 [ALG-005 Task Spec v1](algorithm_tasks/ALG-005.md)。本 Profile 只新增 recovery process
管理与 normalized single-axis synthetic closed-loop qualification，不修改全局
`Algorithm Benchmark v1` 或历史 ALG-001～004 Profile/Result 的输入、阈值、容差和结论。
ALG-005 Candidate 尚未实现；本节冻结设计，不预填 Candidate PASS。

### 12.1 观测 seam、层级与执行约定

Level A/D/E 通过无 ROS、无硬件的 task-local seam 观察：

```text
final abstract process intent u
phase = STABLE | DISTURBED | RECOVERING | SETTLING | TIMED_OUT
episode_elapsed_sec
stable_dwell_sec
首次 SETTLING entry 与各次 phase-entry elapsed observation (或等价的 timer seam)
timeout_latched
```

名称和代码结构不是公开 Flight API；observable 值及本文关系是资格契约。Level A 评分单帧
process 语义和最终 intent；Level D 用 `ALG005-FIXTURE-v1` 评分 deterministic scripted
process replay；Level E 用 `ALG005-SYNTHETIC-PLANT-v1` 评分 deterministic normalized
closed-loop trajectory。Level D 不是 dynamic simulation；Level E 不是 trusted physical robot
model、actuator simulation、hardware replay、sim-to-real evidence 或硬件验证。

Level B 独立观察现有 factory、`FlightState`、`FlightCommand` 和 validation。普通命令继续复制
当前合法完整 motor feedback position hold，左右 fan 为 `0.0`；外部 fail-close 或内部
TIMED_OUT 返回精确 `FlightCommand.safe_stop()`。不得从 motor/fan payload 反推 `u`。

除 inheritance 指定的合法 variable `dt` 外，ALG005-FIXTURE-v1 和 Level E 使用固定
`dt=0.020 s`。所有时间来自已接受正有限 `dt` 的累计，不读取 wall clock、ROS clock 或测试
机器执行时间。fixture 不调用 runtime random generator。每个独立 run 使用相同固定配置，
创建 fresh controller 或先显式 `reset()`；全部明确镜像 pair 和完整 run 分别重复三次。
candidate 必须稳定序列化 inherited 与 process configuration；本 Profile 的 process thresholds、
dwell、timeout、plant 和 U/S 不得按场景、dt 或运行结果调参。ALG-001/002 的 Kp/Kd 与
ALG-003 输入鲁棒性不能作为 ALG-005 新能力重调或替代。

### 12.2 阈值、容差与 phase 判定

Profile v1 冻结以下 inclusive 比较：

```text
disturbance = abs(theta) >= 0.040 rad
              OR abs(omega) >= 0.200 rad/s
settling = abs(theta) <= 0.020 rad
           AND abs(omega) <= 0.100 rad/s
stable_confirmation = abs(theta) <= 0.010 rad
                      AND abs(omega) <= 0.050 rad/s
stable_dwell = 0.300 s continuous valid time
T_timeout = 3.000 s valid episode time
```

这里 `theta` 对应 `relative_pitch_rad`，`omega` 对应
`relative_pitch_rate_rad_s`。`>=`/`<=` 包含端点；测试值按二进制浮点计算，并只使用：

```text
abs_tol = 1e-9
rel_tol = 1e-6
tol(a,b) = 1e-9 + 1e-6 * max(abs(a), abs(b))
```

容差只处理软件浮点比较，不放宽 phase threshold 或整数计数。上述数字仅是 ALG-005 Profile
v1 synthetic qualification envelope，不是安全倾角、最大可恢复角度/角速度、IMU noise
envelope、actuator capability 或 hardware safety envelope。

判定与 timer 记账按每次合法 update 冻结：

1. state-validation 始终保持前置；已有 timeout latch 的 controller 路径保持
   `TIMED_OUT`、`u=0.0`，后续输入不解除 latch、不累计 episode/dwell；
2. 外部 validation/controller fault 按 12.8 fail-close，不进入普通 phase 计算；
3. 无 active episode 且 disturbance 为真时创建 episode，该 update 可观察 `DISTURBED`；
4. active episode 的每个合法 update（包括 DISTURBED update）把当前 `dt` 加入
   `episode_elapsed_sec`；处于 stable confirmation envelope 时把当前 `dt` 加入连续
   `stable_dwell_sec`，否则 dwell 精确清零；
5. 若此前尚未确认 STABLE 且累计 episode time 达到 `T_timeout`，当前 update 进入并锁存
   `TIMED_OUT`；只有在 `episode_elapsed_sec < T_timeout` 时完成 dwell 才可先回到 STABLE；
6. 未 timeout 时，完整 dwell 进入 `STABLE` 并关闭 episode；否则当前在 settling envelope
   则为 `SETTLING`，离开则为 `RECOVERING`；首次触发 update 保留可观察 DISTURBED，后续
   update 才按 SETTLING/RECOVERING 显示；
7. 无 active episode 且未触发 disturbance 时保持 `STABLE`。guard band 输入不虚构 episode。

observable timer 是接受当前 `dt` 后的累计值；phase event elapsed 使用该累计值，不使用
推进前的 `t_k` 或 wall clock。每次 SETTLING entry 的局部 interval 累计当前合法 `dt`，
离开该 phase 时终止；最终局部 interval 只用于诊断。用于 `settling_completion_time` 的起点
固定为 scoring recovery episode 的首次 SETTLING entry；此后直到最终 STABLE confirmation
持续累计合法 `dt`，包括 setback 和中间 phase 的 update，不随再次进入 SETTLING 重置。

stable dwell 离开更严格的 stable confirmation envelope 即清零；若仍在 settling envelope，
phase 保持 SETTLING。离开 settling envelope 返回 RECOVERING。两种 setback 均不重置整个
episode timer、首次 DISTURBED 的 recovery scoring origin 或首次 SETTLING 的 completion
scoring origin。单帧过零不能结束 episode。

### 12.3 `ALG005-FIXTURE-v1` scripted process

Level D 每个 `× n` 段把同一 `(theta rad, omega rad/s)` 输入连续 `n` 个 update；P/N pair
同时取反。fixture state 的其它字段使用当前纯内存合法完整值。Level D 直接评分 phase、timer、
latch、输出和 history，不用 Level E 轨迹抵消失败。

| Scenario | 冻结 scripted sequence / 注入 | 必须观察 |
| --- | --- | --- |
| `ALG005-D00` | `(0,0) × 30` | 全程 STABLE；无 episode/timeout；finite |
| `ALG005-D01P/N` | `(0,0) × 15`; `(±0.040,0) × 1`; `(±0.050,±0.150) × 2` | 边界触发；STABLE → DISTURBED → RECOVERING |
| `ALG005-D02P/N` | `(0,0) × 15`; `(±0.050,±0.200) × 1`; `(±0.050,±0.150) × 4`; `(±0.018,±0.080) × 4`; `(±0.009,±0.040) × 15` | DISTURBED → RECOVERING → SETTLING → STABLE；完整 0.300 s dwell |
| `ALG005-D03P/N` | D02 前三段；`(±0.018,±0.080) × 5`; `(±0.009,±0.040) × 5`; `(±0.025,±0.120) × 5`; `(±0.018,±0.080) × 5`; `(±0.009,±0.040) × 15` | transient SETTLING；setback 回 RECOVERING；dwell 清零；episode timer 不重置；最终 STABLE |
| `ALG005-D04P/N` | fresh `(±0.039,±0.199) × 1`；reset；`(0,±0.200) × 1`; `(±0.020,±0.100) × 1`; `(±0.010,±0.050) × 15` | guard band 不触发；rate 边界触发；settling/stable 边界均 inclusive |
| `ALG005-D90P/N` | `(0,0) × 15`; `(±0.050,±0.200)` 持续至 150 个 active updates；再输入 `(0,0) × 5` | 正好累计 3.000 s 时 TIMED_OUT；`u=0.0`；稳定输入仍 latch |
| `ALG005-R01` | 运行 D02 至 RECOVERING 且建立 ALG-001～005 history；`reset()`；`(0,0) × 3` | 所有 history/timer/latch 清除；与 fresh cold run 等价 |
| `ALG005-R02` | 建立 D90 timeout latch；`reset()`；`(0,0) × 3` | latch 清除；与 fresh cold run 等价 |
| `ALG005-F01` | 运行 D02 至 RECOVERING；注入 `required_inputs_fresh=false`；再恢复相同合法输入 | 精确 safe-stop；全 history 清除；下一合法输入 cold-start 等价 |
| `ALG005-I01`–`I04` | active episode 中分别输入 `dt=0,-0.01,NaN,+Inf/-Inf` | 不错误累计 timer；精确 safe-stop；全 history 清除；layer 分类保持 |
| `ALG005-O01` | D01/D02/D03/D04/D90 的 P/N pair 各三次；reset 后正序与反序执行 | phase/event sample 镜像；三次重复；无跨场景 history 污染 |

D90 的“150 个 active updates”包含首次 DISTURBED update：`150*0.020=3.000 s`。第 149 个
update 的 elapsed 为 `2.980 s`，不得提前 timeout；第 150 个 update 必须 TIMED_OUT。D02 的
最后 15 帧连续 stable-confirmation 输入恰为 `0.300 s`；第 14 帧不得报告 STABLE，第 15 帧
必须报告 STABLE。D03 首次 stable-confirmation 段只有 `0.100 s`，不能结束 episode。

F01 是 task-local 代表场景；ALG-001～004 inheritance 和 12.8 仍须覆盖现有全部
invalid/stale/unhealthy/motor/E-STOP variants。validation-layer reject 不调用 controller；harness
reset 后检查 cold-start 等价，不能冒充 controller safe-stop。

### 12.4 `ALG005-SYNTHETIC-PLANT-v1`

Level E 只建模 normalized single-axis pitch surrogate，直接消费最终 abstract process intent：

```text
state:
  theta [rad]
  omega [rad/s]
input:
  u [intent unit]
external disturbance:
  a_ext [rad/s^2]
dt = 0.020 s

unstable_pitch_coefficient = 1.0 s^-2
control_effectiveness = 6.0 rad/s^2 per intent unit
linear_damping = 2.4 s^-1

alpha_k = 1.0 * theta_k + 6.0 * u_k - 2.4 * omega_k + a_ext_k
omega_(k+1) = omega_k + dt * alpha_k
theta_(k+1) = theta_k + dt * omega_(k+1)
```

更新使用 semi-implicit Euler，顺序固定为：以当前 `theta_k/omega_k` 构造纯内存合法
`FlightState`；调用 candidate/task-local seam 得到 `u_k` 和 observables；按场景确定
`a_ext_k`；计算 `alpha_k`；先推进 omega、再用新 omega 推进 theta；最后把 synthetic time
增加 `dt`。sample time `t_k=k*dt` 对应推进前状态；事件 elapsed 使用已完成 interval 的
累计值。不得从 `FlightCommand` payload 反推 `u`。

所有 ordinary output 继承 ALG-004 的 `abs(u)<=0.10 intent unit`、
`abs(u_k-u_(k-1))<=2.0*dt` 和 directed
transition gates；plant 不新增 actuator saturation、allocation 或 motor/fan/PWM model。所有
状态、`alpha`、`u`、timer 和指标必须 finite。模型常量固定，不得按 Candidate 输出调参。

ordinary directed-transition 的 reference 不得被 process manager 偷换：令当前 ALG-003
inherited requested intent 为 `r_k`，`target_k=clamp(r_k,-0.10,+0.10)`，上一 ordinary final
intent 为 `u_(k-1)`（cold/reset/fail-close 后为精确 0.0），最终 `u_k` 必须满足：

```text
min(u_(k-1), target_k) - tol(u_k, min(u_(k-1), target_k)) <= u_k
u_k <= max(u_(k-1), target_k) + tol(u_k, max(u_(k-1), target_k))
```

process-dependent intent management 只能在此 inherited envelope 内工作，不能用新 process
target 掩盖反向、远离或越过 inherited target。

TIMED_OUT 是继承 fail-close 的非 ordinary-output 边界：task-local `u=0.0` 是明确的 stop
sentinel，Level B 是无载荷 safe-stop，不把 stop sentinel 与前一 ordinary intent 的差值计作
ordinary slew/directed-transition。timeout 前所有 ordinary output 和 reset 后首个 ordinary
output 均完整受 ALG-004 gate 约束；不得借此为普通 process shaping 增加豁免。

### 12.5 Level E scenario set

P/N 场景对 `theta_0`、`omega_0`、冲量和 `a_ext` 同时取反；candidate reset 后独立运行。
“运行 4.000 s”表示 200 个 plant steps；E04 的 0.500 s 预段为 25 steps，扰动后的 4.000 s
另计。每个场景完整运行，不得达到某个 gate 后提前停止。

| Scenario | 初态 / disturbance | 时长与目的 |
| --- | --- | --- |
| `ALG005-E00` | `theta_0=0`, `omega_0=0`, `a_ext=0` | `4.000 s` neutral hold；全程 STABLE、无 episode/timeout |
| `ALG005-E01P/N` | `theta_0=±0.080`, `omega_0=0`, `a_ext=0` | `4.000 s` initial tilt |
| `ALG005-E02P/N` | `theta_0=±0.050`, `omega_0=±0.200` 同号，`a_ext=0` | `4.000 s` diverging disturbance |
| `ALG005-E03P/N` | `theta_0=±0.050`, `omega_0=∓0.200` 反号，`a_ext=0` | `4.000 s` initially recovering motion |
| `ALG005-E04P/N` | 从 `(0,0)` 运行 `0.500 s`；第 25 step 后、下一 controller update 前施加 `Delta omega=±0.250`；之后 `a_ext=0` | 建立 STABLE 后再扰动；扰动后运行 `4.000 s` |
| `ALG005-E90P/N` | `theta_0=±0.050`, `omega_0=0`；持续同号 `a_ext=±0.700` | `3.500 s` intentionally unrecoverable timeout fixture |

E03 用于防止把正在自然朝零运动误判为新的发散趋势。E04 的 episode 和指标窗口从冲量后
第一个 controller update 的 DISTURBED entry 开始，不能把预段已有的 STABLE 样本当成恢复。
E90 不是最大真实扰动，只是 synthetic timeout fixture；不得误报 recovered。

### 12.6 Level E metric definitions

recoverable 场景的 scoring interval 从 DISTURBED entry 到 run 结束；E04 只使用冲量后的区间。
定义：

```text
recovery_time = 从本场景首次 DISTURBED entry 到最终重新确认 STABLE 的累计合法 dt
settling_completion_time = 从 scoring recovery episode 首次 SETTLING entry 到最终重新确认 STABLE 的累计合法 dt
final_settling_interval = 从最终一次 SETTLING entry 到最终 STABLE confirmation 的累计合法 dt
settling_setback_count = scoring recovery episode 中实际 SETTLING -> RECOVERING phase transition 次数
peak_abs_pitch = max(abs(theta_k))
peak_abs_pitch_rate = max(abs(omega_k))
final_steady_state_error = abs(mean(theta_k over final 0.500 s))
abstract_control_effort = sum(abs(u_k) * dt)
phase_timeline = 每次 phase 变化的 (synthetic elapsed time, phase)
overshoot = 按下述首次零交叉后的镜像规则计算
overshoot_ratio = overshoot / abs(theta_at_episode_start) (E01/E02/E03)
effective_pitch_sign_reversal_count = 按下述 epsilon 去零带规则统计的有效 pitch 符号反转次数
```
recovery_time 的求和包含首次 DISTURBED update 和确认 STABLE 的 update；
settling_completion_time 包含首次 SETTLING entry update、此后全部合法 update 和最终确认
STABLE 的 update；final_settling_interval 包含最终 SETTLING entry update 和最终确认 STABLE
的 update。三项时间均按 interval 的 `sum(dt)` 记账，只累计已接受正有限 `dt`，不使用
wall clock，也不用两个 after-update event timestamp 相减少计首帧。
本场景只有一次外部扰动；后续若再次触发 episode，scoring origin 仍固定为首次 DISTURBED，
settling completion origin 仍固定为首次 SETTLING，不得因 phase setback、新 SETTLING entry
或新 episode 重启任一评分计时来缩短结果。若从未进入 SETTLING，两个 settling 时间记为
未定义且 Settling Gate FAIL，不能填零冒充完成。settling_setback_count 只统计从首次 DISTURBED
到最终 STABLE confirmation 的实际 phase transition；只重置 dwell 而保持 SETTLING 不增加计数。
最终 confirmation 必须对应 run 末尾连续稳定窗口，
不能挑选较早的 transient STABLE；final tail 的 phase 必须为 STABLE。
final_settling_interval 与 settling_setback_count 仅为 comparative/diagnostic，不设独立数值
Hard Gate 或任意回退次数上限，也不得仅凭局部 interval 更短将额外 setback 判为更优。

E01/E02/E03 的 overshoot 从 episode start 后第一次 theta 零交叉计算。正初态：

```text
overshoot = max(0, -min(theta after first zero crossing))
overshoot_ratio = overshoot / abs(theta_at_episode_start)
```

负初态镜像定义。若未零交叉但 Recovery Gate 通过，overshoot 和 ratio 均记 `0`。E04 由 rate
impulse 建立扰动，不评分 ratio，但记录 peak tilt。

oscillation 使用 `theta_sign_epsilon=0.005 rad`：先删除 scoring interval 内所有
`abs(theta)<=epsilon` 的样本，再统计剩余相邻样本的符号变化；不足两样本为零，插入零附近
样本不能隐藏反转。计数窗口延伸到完整 run 结束，以捕获重新报告 STABLE 后的再次振荡。

重新确认 STABLE 后，run 的最终 `0.500 s` 必须连续保持 stable confirmation envelope；
最终窗口内任何离开都使 Recovery Gate FAIL，不能选取较早的短暂稳定段。final tail 恰为最后 25 个
`dt=0.020 s` samples。所有 metric 使用未舍入值，显示值可舍入但不能改变 gate 比较。

### 12.7 Level E Hard Gates

各 gate 互不抵消，并与 finite、mirror、repeatability、inheritance 独立成立。

**Recovery Gate — E01/E02/E03/E04 全部 P/N：**

- 必须创建 episode，并包含可观察 DISTURBED、RECOVERING、SETTLING；
- 必须最终重新确认 STABLE，`recovery_time <= 2.500 s + abs_tol`；
- 最终至少连续 `0.500 s` 保持 stable confirmation envelope；
- 不得以 TIMED_OUT 或 reset 结束并计为 recovered。

**Settling Gate — 全部 recoverable scenario：**

- 这是过程语义 Hard Gate，不是局部 interval 的数值上限：最终 STABLE 前必须观察到 SETTLING；
- SETTLING 判定须同时满足 `abs(theta)<=0.020 rad` 和 `abs(omega)<=0.100 rad/s`，边界 inclusive；
- stable confirmation 须同时满足 `abs(theta)<=0.010 rad` 和 `abs(omega)<=0.050 rad/s`，边界 inclusive；
- 完整连续 `0.300 s` 已接受正有限 `dt` 的 stable dwell 前不得报告 STABLE；
- 离开 stable confirmation envelope 但仍在 settling envelope 时，dwell 清零、phase 保持 SETTLING；
- 离开 settling envelope 时返回 RECOVERING、dwell 清零，不重置 episode timer、首次 DISTURBED
  recovery origin 或首次 SETTLING completion origin；
- 最终一次 SETTLING 必须连续进入最终 STABLE，且最终 `0.500 s` stable tail 仍须满足 Recovery Gate；
- `settling_completion_time` 如实记录完整完成耗时，`final_settling_interval` 和
  `settling_setback_count` 仅用于 comparative/diagnostic；不另设 settling 时间或回退次数数值上限。

**Timeout Gate — E90P/N：**

- 不得报告 recovered；首次 TIMED_OUT 的 episode elapsed 满足
  `3.000 <= observed_timeout_time < 3.000 + 0.020 s`；
- 进入 TIMED_OUT 后 `u` 精确为 `0.0`，Level B 精确 safe-stop；
- phase/output latch 保持到显式 reset，普通合法输入不能恢复 ordinary control。

**Overshoot Gate — E01/E02/E03 全部 P/N：**

```text
overshoot_ratio <= 0.50 + abs_tol
```

**Oscillation Gate — E01/E02/E03/E04 全部 P/N：**

```text
effective_pitch_sign_reversal_count <= 2
```

**Mirror / repeatability / finite Gate：** 每个 P/N pair 的初态、输入、逐帧 theta/omega/u、phase
transition sample、recovery_time、settling_completion_time、final_settling_interval、timeout time
和全部镜像不变量须在 `tol()` 内对应，settling_setback_count、phase
枚举和整数计数精确相同；每个完整 run 三次输出逐帧在 `tol()` 内相同；E00～E90 全部数值
finite。任一单项 FAIL 即 `ALG-005 NOT QUALIFIED`。

### 12.8 Reset、外部 fail-close 与 timeout latch

显式 `reset()` 必须原子清除 ALG-001～003 输入/filter history、ALG-004 shaped-output history、
ALG-005 phase/history、episode/settling timer、stable dwell、timeout latch 和 task-local cache/counter；
reset 后同一合法输入逐帧等价于 fresh controller cold start。reset 不修改 Runtime、authority、
ownership、IMU zero、E-STOP、ERROR 或硬件状态。

现有 state-validation reject 与 controller-layer fault 分类保持。controller-layer
invalid/stale/unhealthy/`required_inputs_fresh=false`/非法 `dt` 必须精确 safe-stop，清除全部
ALG-001～005 history，不输出旧 ordinary command/recovery intent；下一合法输入 cold-start
等价。非法 update 不累计 timeout 或 dwell。validation-layer reject 后由 harness 显式 reset。

内部 TIMED_OUT 不按上述 transient fault 自动清除；它保持 task-local latch，Level A/D/E
`u=0.0`、Level B safe-stop，直到显式 reset。timeout 不修改 Runtime authority、E-STOP 或硬件。
外部 fail-close 的全 history 清除适用于尚未锁存 TIMED_OUT 的路径；已有 timeout latch 后，
外部 transient fault 仍返回 safe-stop、不能累计 timer 或复用 ordinary history，但不得顺便
清除 timeout latch。validation reject 仍由前置 layer 拒绝；只有 harness 显式 reset 才清 latch。
因此“下一合法输入 cold-start 等价”不能用来自动复活已 timeout 的 controller。

### 12.9 ALG-001～004 inheritance 与 capability boundary

未来 ALG-005 Candidate 必须在最终 process intent 上重新运行未修改的 ALG-001～004 fixtures、
normal/fault/reset 场景、阈值、容差和关系；覆盖 attitude feedback、damping/motion trend、noise
robustness、history、ALG-004 envelope/slew/directed transition、合法 variable `dt`、factory、
Level B、symmetry、repeatability 和全部现有 fail-close。历史 PASS 不代替本轮 inheritance。
ALG-004 requested-intent fixtures 必须通过同一最终 ordinary-output qualification path，使用
无 active episode 的 process context 评分最终 `u`，而不是只评分 ALG-004 中间组件；不得用
stub process manager 绕过最终输出。完整 FlightState/process sequence 还须独立检查 12.4 的
current inherited target、最终输出 envelope、slew 和 directed-transition。qualification seam
可以适配这些 task-local 输入，不增加公开 Flight API。

历史 Profile 中仅因“ALG-005 属未来任务”而存在的 prohibition 在当前 inheritance 自然
supersede，不回写历史 Task Spec/Profile/Result。仍禁止新 input filter、以 Kp/Kd 重调冒充
process management、integral/anti-windup、绕过 ALG-004、ALG-006 actuator allocation、ALG-007 multi-axis 和 ALG-008
full recovery；Flight API、Runtime、adapters、default/teaching controller、hardware manager、
mapping、E-STOP、watchdog、lease 和 soft limits 均不得改变。

### 12.10 Hard Qualification checklist 与结论

| Level | ALG-005 v1 要求 | 结论边界 |
| --- | --- | --- |
| A | **HARD GATE** | final abstract intent、phase/timer/latch、reset 与 inheritance |
| B | **HARD GATE** | factory、validation、完整 hold frame、fan-zero、safe-stop |
| C | optional preview | 不能代替 A/B/D/E |
| D | **HARD GATE** | `ALG005-FIXTURE-v1` scripted replay，非 dynamic simulation |
| E | **HARD GATE** | `ALG005-SYNTHETIC-PLANT-v1` normalized dynamic benchmark，非真实机器人模型 |
| F | **NOT AUTHORIZED / NOT EXECUTED** | 真实硬件另需独立授权 |

正式 Candidate Result 必须逐项报告，Candidate 未实现时不得预填：

- [ ] metadata、固定 configuration、implementation SHA、Profile、fixture、plant、环境和命令完整；
- [ ] phase/threshold/inclusive-boundary 与 timer accounting：PASS；
- [ ] Level D D00/D01/D02/D03/D04/D90、R01/R02、F01、I01–I04、O01：PASS；
- [ ] Level E E00、E01P/N、E02P/N、E03P/N、E04P/N、E90P/N：PASS；
- [ ] Recovery Gate：PASS；
- [ ] Settling Gate：PASS；
- [ ] Timeout Gate 与 latch：PASS；
- [ ] Overshoot Gate：PASS；
- [ ] Oscillation Gate：PASS；
- [ ] finite、mirror symmetry 与三次 repeatability：PASS；
- [ ] reset、外部 fail-close、history isolation：PASS；
- [ ] ALG-001 inheritance：PASS；
- [ ] ALG-002 inheritance：PASS；
- [ ] ALG-003 inheritance：PASS；
- [ ] ALG-004 inheritance：PASS；
- [ ] factory/configuration 与 Level B：PASS；
- [ ] Future-task boundary：PASS；
- [ ] hardware access `NO`；hardware validation `NOT AUTHORIZED / NOT EXECUTED`。

任一全局或本节 Hard Gate FAIL，Overall 必须为 `ALG-005 NOT QUALIFIED`；Level D/E 或比较
指标不得互相抵消。全部 PASS 也只证明固定 implementation、Profile、fixture 和 normalized
synthetic plant 内的软件 recovery process 资格，不证明 real actuator safety、allocation、真实
机器人动力学、最大可恢复扰动、sim-to-real 等价或 real Balance Recovery。

### 12.11 Comparative metrics 与版本边界

只有全部 Hard Qualification PASS 后，才按场景独立报告 `peak_abs_pitch`、
`peak_abs_pitch_rate`、`recovery_time`、`settling_completion_time`、`final_settling_interval`、
`settling_setback_count`、`overshoot`、`overshoot_ratio`、`effective_pitch_sign_reversal_count`、
`final_steady_state_error`、`abstract_control_effort`、完整 `phase_timeline`、最大镜像误差、三次
repeatability delta、implementation physical LOC（注明口径）与 configuration clarity。除 12.7
明确指定的项目外，其余只用于同 Task/同 Profile candidate 的比较，不合成无依据总分。
完整 settling 完成耗时须与 recovery_time、phase_timeline 和 setback count 一起解释；最终局部
interval 可能因额外 setback 后重新进入 SETTLING 而缩短，不能作为独立“越小越好”的资格或排名依据。

fixture、plant 常量、更新顺序、scenario、阈值、metric 公式或 Hard Gate 的实质修改必须升级
`ALG-005 Profile` 版本；跨任务证据契约变化才升级整体 Benchmark Contract。Profile v1 冻结前
的纯内存 sanity analysis 只验证数值有限、镜像和定义可实现，不是 Candidate Result，不得为
使某个 Candidate 通过而反复调 benchmark。
本轮 Profile v1 Remote Review 修复发生在 Candidate `NOT IMPLEMENTED`、正式结果与历史比较
均未开始时：移除奖励晚进入 SETTLING 的局部时间 Hard Gate，明确固定 completion origin 与
过程语义 gate；没有按 Candidate 输出调整 fixture、plant、继承参数或其它 Hard Gates。
