# WindArmor 当前开发交接

> **INTERNAL DEVELOPMENT HANDOFF — MUTABLE。** 本文件只记录当前任务和对下一工作单元有价值的
> 稳定工程状态，不持续复制 branch、push、PR、CI、merge 或 branch deletion 等瞬时生命周期
> 状态；这些状态以 Git / GitHub 当前信息为准。本文件不是普通用户操作文档、长期接口契约或
> release evidence source of truth，历史发布事实必须引用对应的版本化 release/verification
> 文档。

## 当前状态

- 日期：2026-09-11
- 当前任务：`v0.5.0-007 — ALG-003 Candidate A Implementation`
- task-start baseline：`origin/develop` /
  `f71404e1fa302f2e097442d707a6688aac6e65a2`
- 当前短期任务分支：`feature/algo-003-candidate-a`
- 当前阶段：**implementation + pre-formal-qualification remote review**
- 当前 stable release：**v0.4.0**
- previous stable / history：v0.3.2
- 下一版本研发目标：**v0.5.0 — Balance Recovery；未发布**
- ALG-003 Task Spec：`v1`
- Benchmark：`Algorithm Benchmark v1 / ALG-003 Profile v1`
- Fixture：`ALG003-FIXTURE-v1`
- Inherited qualification：`ALG-001 Candidate A / ALG-001 QUALIFIED`；
  `ALG-002 Candidate A / ALG-002 QUALIFIED`
- Candidate：`ALG-003 Candidate A`
- Candidate algorithm：**two-sample input moving average**
- ALG-003 Candidate A：**UNDER REMOTE REVIEW**
- formal Candidate Result：**NOT GENERATED**
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

本任务基于冻结的 [ALG-003 Task Spec v1](algorithm_tasks/ALG-003.md) 与
[Algorithm Benchmark v1 / ALG-003 Profile v1](ALGORITHM_BENCHMARK.md#10-alg-003-profile-v1)
实现 Independent ALG-003 Candidate A。Candidate 在输入估计层保存上一条合法原始 pitch/rate，
对当前与上一样本作固定两样本 boxcar moving average，再使用继承的 `Kp=1.0`、`Kd=0.1`
关系计算 abstract intent。cold start 直接使用当前合法样本；reset、controller-layer
fail-close 和非法 `dt` 都清除本地历史。

本阶段只形成 implementation、pre-formal qualification 和 remote review checkpoint，不生成
`docs/algorithm_results/ALG-003_CANDIDATE_A.md`，也不提前写 `ALG-003 QUALIFIED`。普通
`FlightCommand` 仍复制当前合法完整 motor feedback hold preview，并输出 fan-zero；payload
不编码 intent。Flight API、Runtime、adapter、default/teaching controller、硬件配置和
ALG-001/ALG-002 历史 Result 保持不变，ALG-004+ 能力不在本任务内，也不授权硬件操作。

## 历史证据保留

v0.4.0 的 Gate B/C/D、PASS/FAIL/NOT VERIFIED、有效与无效 session、接线映射、release
blocker、安全结论、证据等级和已知限制继续长期保存在：

- [v0.4.0 硬件与功能验证记录](verification/v0.4.0/HARDWARE_VERIFICATION_RECORD.md)；
- [v0.4.0 硬件验证历史执行计划](V0.4.0_HARDWARE_VERIFICATION_PLAN.md)；
- [v0.4.0 发布说明](RELEASE_NOTES_v0.4.0.md)。

本次实现任务没有删除或改变这些历史证据，也不授权新的硬件操作。

## 下一推荐工作单元

当前 remote review 通过后，下一独立工作单元应针对固定的 ALG-003 Candidate A
implementation commit 重跑正式 benchmark，并生成独立 Candidate Result；不得把本阶段
pre-formal qualification 直接改写为正式资格证据。

正式 ALG-003 Candidate Result 当前为 **NOT GENERATED**。真实 IMU characterization、真实
动态验证、执行器映射和硬件测试均不在当前范围，且未获得授权。
