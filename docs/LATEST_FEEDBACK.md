# WindArmor 当前开发交接

> **INTERNAL DEVELOPMENT HANDOFF — MUTABLE。** 当前 branch、push、PR、CI 与 merge 等实时
> 生命周期状态以 Git / GitHub 为准；本文件仅保留下一工作单元需要的稳定工程状态。

## 当前工作单元

- 日期：2026-09-22；Task：`v0.5.0-019 — ALG-007 Pre-Candidate Contract Freeze + Prerequisite Split`。
- task-start baseline：`origin/develop@f4b08f16fa1eee1510046b3e2c09b7587f5b6131`；
  前一 ALG-007 design review 已 **PASS / INTEGRATED**。
- Stable release：`v0.4.0`；v0.5.0：**NOT RELEASED**。
- ALG-001～006：**QUALIFIED / INTEGRATED**。ALG-006 fixed implementation SHA：
  `9a7a624713010eff48cf7112b0501266eb24521e`；Formal Qualification/Result evidence SHA：
  `6729443d5e190986c75b8521a4ec7ebd0554d34e`。
- [ALG-007 Task Spec](algorithm_tasks/ALG-007.md) 与
  [Benchmark §14](ALGORITHM_BENCHMARK.md#14-alg-007-planned-profile-design-v1)：
  **PRE-CANDIDATE CONTRACTS PARTIALLY FROZEN / full Profile NOT FROZEN**。
- ALG-007 Candidate：**BLOCKED / NOT IMPLEMENTED**；Candidate Result：**NOT CREATED**；
  Formal Qualification：**NOT EXECUTED**。

## 稳定工程结论与前置依赖

从当前 source/tests 确认：`ImuState` 有相对 roll/pitch 角和统一 pitch rate，但没有
`relative_roll_rate_rad_s`；现有 raw IMU 姿态/角速度与相对姿态按来源时间戳配对。
未来 roll-rate 的 Z-Y-X 公式、同采样、符号、有效性和新鲜度已在 Task Spec §7 写为
**PLANNED CONTRACT / NOT IMPLEMENTED**。roll 的 `tan(theta)` 数值条件不能直接复用
现有 pitch-rate `1e-9` guard；缺少输入误差/速率界，奇异点规则 **NOT FROZEN**。

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
- 下一工作单元优先独立评审并实现 shared roll-rate API/runtime prerequisite，包含奇异点
  数值规则、兼容迁移和纯软件测试；另立 nonzero executable projection 的证据/安全契约。
  当前工作单元未修改 production、测试、API 文档或历史 Result，也未执行硬件验证。
