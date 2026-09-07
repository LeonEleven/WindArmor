# WindArmor Algorithm Benchmark v1 Contract

本文定义算法 qualification 和历史同级比较的长期统一规则。它不是算法实现、candidate
结果、dynamic simulation、硬件操作手册或硬件授权。仓库安全规则以
[`AGENTS.md`](../AGENTS.md) 为准，任务能力边界以对应的独立 Task Spec 为准。

## 1. 文档与结果分层

正式记录必须分为三层，不能混写：

1. **Benchmark Contract**：本文件的全局版本、证据层级、元数据、hard gate 和比较规则；
2. **Task-specific Benchmark Profile**：某个 Task 的固定 fixture、scenario ID、阈值和容差；
3. **Candidate Result**：一次候选实现针对固定 Contract/Profile 的实际命令、环境和结果。

本文件同时承载 `Algorithm Benchmark v1` 的全局 Contract，以及首个
`ALG-001 Profile v1`。它不包含任何 candidate result，也不表示 ALG-001 已 PASS。

## 2. 版本规则

| 资产 | 当前版本 |
| --- | --- |
| Benchmark Contract | `Algorithm Benchmark v1` |
| ALG-001 Task Benchmark Profile | `ALG-001 Profile v1` |

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
| D | Replay / sequence benchmark（未来） | 时序、趋势、噪声和历史回归 | replay 外真实动力学 |
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

以下 gate 必须全部 PASS：

- candidate、factory 和配置可追溯，执行可重复；
- 输入安全处理和 validation-layer 分类正确；
- 所有要求的 fail-close 场景返回合法、无载荷的 safe-stop，或在规定的前置 validation
  layer 被拒绝；
- neutral、direction、monotonic magnitude、proportional consistency 和 finite output；
- reset 与 repeatability；
- Level B `FlightCommand` 通过 validation，普通命令为完整 motor frame 和合法 fan command；
- future-task boundary review PASS；
- 测试不导入或访问 ROS/hardware I/O，`hardware access: NO`。

任何一项 FAIL，结果必须为 `NOT QUALIFIED`。安全失败不能由其它数值表现抵消。

### 5.2 Comparative metrics

通过 hard gates 后，可以独立记录：

- proportional consistency error；
- symmetry error；
- repeatability delta；
- implementation complexity（同时报告计算口径，例如 executable LOC/cyclomatic measure）；
- test coverage quality（同时报告工具、范围和未覆盖项）；
- configuration clarity（review 结论与具体理由）。

这些指标不合成为未经依据的 100 分总分，且 `Kp` 越大不表示更优。若未来引入 score，必须
版本化权重依据，并在 score 之外先通过全部 hard gates。

## 6. Candidate independence 与历史比较

两个 candidate 只有同时满足以下条件，才可作公平的 ALG-001 同级比较：

- 相同 Task Spec version；
- 相同 Benchmark Contract version；
- 相同 ALG-001 Profile version；
- 相同 fixture/scenario set 和 tolerance；
- 可追溯 baseline、固定配置和各自独立 implementation commit；
- 相同执行层级；环境差异已记录且不会被隐藏。

如果一个 candidate 后来基于另一个 candidate 的实现修改，必须记录新的 lineage/hybrid，
不得再称为完全独立实现。不同 task、版本或 Level 的结果只能带限制地说明，不能包装成直接
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
