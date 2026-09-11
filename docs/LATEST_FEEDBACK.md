# WindArmor 当前开发交接

> **INTERNAL DEVELOPMENT HANDOFF — MUTABLE。** 本文件只记录当前任务和对下一工作单元有价值的
> 稳定工程状态，不持续复制 branch、push、PR、CI、merge 或 branch deletion 等瞬时生命周期
> 状态；这些状态以 Git / GitHub 当前信息为准。本文件不是普通用户操作文档、长期接口契约或
> release evidence source of truth，历史发布事实必须引用对应的版本化 release/verification
> 文档。

## 当前状态

- 日期：2026-09-11
- 当前任务：`v0.5.0-006 — ALG-003 Task Spec + Benchmark Profile v1`
- task-start baseline：`origin/develop` /
  `77f3457bc8df977d2c5fde95ff8af53583db213f`
- 当前短期任务分支：`docs/v0.5-alg003-benchmark-contract`
- 当前阶段：**ALG-003 specification / benchmark definition**
- 当前 stable release：**v0.4.0**
- previous stable / history：v0.3.2
- 下一版本研发目标：**v0.5.0 — Balance Recovery；未发布**
- ALG-003 Task Spec：`v1`
- Benchmark：`Algorithm Benchmark v1 / ALG-003 Profile v1`
- Fixture：`ALG003-FIXTURE-v1`
- Inherited qualification：`ALG-001 Candidate A / ALG-001 QUALIFIED`；
  `ALG-002 Candidate A / ALG-002 QUALIFIED`
- ALG-003 implementation：**NOT IMPLEMENTED**
- hardware access：**NO**
- hardware authorization：**NONE**
- hardware validation：**NOT AUTHORIZED / NOT EXECUTED**
- 真实 Balance Recovery verification：**NOT VERIFIED / NOT CLAIMED**
- Tag / Release：**未创建**

## 已完成的稳定事实

- `v0.5.0-001`：**COMPLETE**；
- `v0.5.0-002`：**COMPLETE**；
- `v0.5.0-003`：**COMPLETE**；
- `v0.5.0-004A`：**COMPLETE**；
- `v0.5.0-004`：**COMPLETE**；
- `v0.5.0-005`：**COMPLETE**；
- ALG-001 Candidate A 固定 implementation commit：
  `fe575c9589013138d238e567e93dac2925384ab7`；
- ALG-001 Candidate A 已完成 Algorithm Benchmark v1 / ALG-001 Profile v1 Level A/B 正式
  纯软件资格验证，结论为 **ALG-001 QUALIFIED**；
- 正式 ALG-001 Candidate Result：
  [`algorithm_results/ALG-001_CANDIDATE_A.md`](algorithm_results/ALG-001_CANDIDATE_A.md)；
- ALG-002 Candidate A 固定 implementation commit：
  `77e7b4f98e60602d3b224618225e11e9fecc8fe8`；
- ALG-002 Candidate A 已完成 Algorithm Benchmark v1 / ALG-002 Profile v1 Level A/B 正式
  纯软件资格验证，结论为 **ALG-002 QUALIFIED**，并已进入 `develop`；
- 正式 ALG-002 Candidate Result：
  [`algorithm_results/ALG-002_CANDIDATE_A.md`](algorithm_results/ALG-002_CANDIDATE_A.md)；
- Flight API 已在 `develop` 提供与 `relative_pitch_rad` 同软件正方向的
  `relative_pitch_rate_rad_s`；
- default controller、教学控制器和 synthetic DRY_RUN 默认行为未改变；
- v0.5.0 尚未发布。

`ALG-001/ALG-002 QUALIFIED` 只表示各自固定 synthetic fixture 上的 Level A/B 软件
qualification，不是动态仿真、control allocation、硬件验证或真实 Balance Recovery 证据。
Candidate A 的普通命令仍只是复制当前合法、完整 motor feedback 的 hold preview，并给两路
风扇 `0.0`；该 payload 不编码 intent，也不具有真实执行器分配或恢复方向含义。

## 当前任务目标与边界

本任务建立 [ALG-003 Task Spec v1](algorithm_tasks/ALG-003.md) 与
[Algorithm Benchmark v1 / ALG-003 Profile v1](ALGORITHM_BENCHMARK.md#10-alg-003-profile-v1)。
`ALG003-FIXTURE-v1` 冻结平衡附近、非零姿态附近、rate-only noise、meaningful step、
diverging/recovering trend、可变 `dt`、reset/history 和 fail-close 序列。

Noise Suppression 与 Signal Preservation 是不能互相抵消的独立 Hard Gate。Profile 使用明确
公式衡量 output total variation、sign reversal、peak/mean activity、response delay、steady
signal attenuation、trend preservation、symmetry 和 repeatability；恒零 candidate 不能通过。

fixture 只是人为冻结的 synthetic software input，不是 Hiwonder IMU 实测噪声、机器人振动谱
或真实量化误差模型。本任务不实现 ALG-003，不改变 production code、Flight API、Runtime、
adapter、default controller、硬件配置或 ALG-001/ALG-002 历史 Result，不提前实现 ALG-004+
能力，也不授权任何硬件操作。

## 历史证据保留

v0.4.0 的 Gate B/C/D、PASS/FAIL/NOT VERIFIED、有效与无效 session、接线映射、release
blocker、安全结论、证据等级和已知限制继续长期保存在：

- [v0.4.0 硬件与功能验证记录](verification/v0.4.0/HARDWARE_VERIFICATION_RECORD.md)；
- [v0.4.0 硬件验证历史执行计划](V0.4.0_HARDWARE_VERIFICATION_PLAN.md)；
- [v0.4.0 发布说明](RELEASE_NOTES_v0.4.0.md)。

本次文档任务没有删除或改变这些历史证据，也不授权新的硬件操作。

## 下一推荐工作单元

ALG-003 Task Spec v1 与 ALG-003 Profile v1 经评审并进入 `develop` 后，下一独立工作单元是基于
冻结规范实现 ALG-003 Candidate。Candidate 必须先形成固定 implementation commit，再执行
正式 benchmark 并生成独立 Candidate Result；不得把实现与资格证据合并为不可追溯的结果。

ALG-003 implementation 当前仍为 `NOT IMPLEMENTED`。真实 IMU characterization、真实动态
验证、执行器映射和硬件测试均不在当前范围，且未获得授权。
