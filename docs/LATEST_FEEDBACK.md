# WindArmor 当前开发交接

> **INTERNAL DEVELOPMENT HANDOFF — MUTABLE。** 当前 branch、push、PR、CI 与 merge 等实时
> 生命周期状态以 Git / GitHub 为准；本文件仅保留下一工作单元需要的稳定工程状态。

## 当前工作单元

- 日期：2026-09-23；Task：`v0.5.0-020A — Relative Roll-rate Singularity + API Compatibility Design Freeze`；
  task branch：`docs/alg-007-roll-rate-prereq`。
- task-start baseline：`origin/develop@ae27a2b0e3dd17ccfb111fdc2c61842ba9cc53bf`；
  v0.5.0-019 已 **MERGED / INTEGRATED**。
- Stable release：`v0.4.0`；v0.5.0：**NOT RELEASED**。
- ALG-001～006：**QUALIFIED / INTEGRATED**。ALG-006 fixed implementation SHA：
  `9a7a624713010eff48cf7112b0501266eb24521e`；Formal Qualification/Result evidence SHA：
  `6729443d5e190986c75b8521a4ec7ebd0554d34e`。
- [ALG-007 Task Spec](algorithm_tasks/ALG-007.md) 与
  [Benchmark §14](ALGORITHM_BENCHMARK.md#14-alg-007-planned-profile-design-v1)：020A 已冻结
  roll-rate formula、conditioning model、optional-derived API compatibility、sign wiring 与
  lifecycle design；exact numerical near-singularity rule **NOT FROZEN**；full Profile
  **NOT FROZEN**。
- ALG-007 Candidate：**BLOCKED / NOT IMPLEMENTED**；Candidate Result：**NOT CREATED**；
  Formal Qualification：**NOT EXECUTED**。

## 稳定工程结论与前置依赖

从当前 source/tests 确认：`ImuState` 是全部字段无 default 的 frozen dataclass，有相对
roll/pitch 与统一 pitch rate，但没有 `relative_roll_rate_rad_s`；仓库 4 个直接构造点均为
keyword construction。当前 `imu.valid` 要求完整 base measurement set，ALG-001～006 都依赖
`imu.valid/fresh`，但没有旧算法读取 roll rate。020A 因此冻结未来字段为 append-at-end、
default-`None` 的 optional derived measurement；它不进入 legacy/base complete set。source
合法但 roll conditioning unavailable 时保留 pair、字段置 `None`，不使整体 IMU invalid；需要
roll rate 的 consumer 显式要求 base valid/fresh、字段存在且 finite。无需额外 public validity
flag，prior roll rate 不得补入新 unavailable frame。

Z-Y-X 公式及 `||a(phi,theta)||_2=1/abs(cos(theta))` 已独立确认。现有 pitch-rate `1e-9`
guard 只表示接近数学奇异点；在 accepted side 理论 amplification 仍可接近 `1e9`。仓库缺少
经验证的 body-rate/orientation error bound、允许 roll-rate output error budget 或 operating
envelope，因此 exact numerical guard **NOT FROZEN**，不得猜测角度或 `K_max`。

`roll_axis_sign` 未来复用 relative attitude producer 的同名 key，严格为 `+1/-1`，不能从
`motor_signs` 或 actuator mapping 推断。Flight Runtime 当前只 wiring `pitch_axis_sign`；020B
须显式新增 roll sign、跨两份 node-scoped config 比较与防 roll/pitch 互换测试。同一 raw
orientation/body-rate、exact stamp pairing、freshness、disconnect/reconnect、zero-generation
与 no-prior-reuse contract 已冻结。共享字段/Runtime/tests/API docs 均仍
**PLANNED / NOT IMPLEMENTED**。

`ALG007-SYNTHETIC-VECTOR-v1` 已冻结无状态逐轴 cap + combined L1 等比例预算、
exact zero、signed residual 和 `FAIL_CLOSED` / `TIMEOUT` / `NEUTRAL` / `INFEASIBLE` /
`ALLOCATED` / `SATURATED` 的优先级。当前 Level B 仍只做 motor hold / fan zero；
nominal 双轴 caps/budget **NOT APPLICABLE**。`ALG007-SYNTHETIC-COUPLING-v1` 已由
candidate-independent 纯软件 sanity study 冻结对称状态耦合方程、`dt`、场景、horizon 与
逐轴 Level E gates；这些数值不表征真实硬件。

**Executable nonzero FlightCommand projection = SEPARATE REVIEWED PREREQUISITE = NOT
DEFINED / NOT VERIFIED。** 当前没有从 normalized pitch/roll request 到 absolute motor rad
和/或非零 fan command 的方向、基线、包络及相对 authority 证据。roll request 来源及其与
继承 pitch `0.10` intent 的兼容关系也待评审。完成这些前置依赖及完整 Profile review 前，
不得进入 ALG-007 Candidate。

## Hardware / evidence boundary 与下一步

- Hardware access：**NO**；authorization：**NONE**；hardware validation / Level F：
  **NOT AUTHORIZED / NOT EXECUTED**。
- Real actuator safety、dynamic closed-loop recovery on hardware 与 real Balance Recovery：
  **NOT VERIFIED**。motor torque、fan thrust、力臂、真实轴向分配、相对/动态 authority、
  availability → numerical authority、最大可恢复扰动和 sim-to-real 均 **UNKNOWN / NOT VERIFIED**。
- 下一工作单元优先关闭 exact near-singularity 数值证据 blocker：提供并评审 source error /
  acceptable output error budget，或 verified operating envelope。数值规则冻结后才进入 020B
  shared API/runtime implementation；另立 nonzero executable projection 的证据/安全契约。
  020A 未修改 production、测试、config、launch、API/architecture 文档或历史 Result，也未执行
  硬件验证。
