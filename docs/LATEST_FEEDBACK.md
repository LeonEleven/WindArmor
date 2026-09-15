# WindArmor 当前开发交接

> **INTERNAL DEVELOPMENT HANDOFF — MUTABLE。** 本文件只记录当前任务和对下一工作单元有价值的稳定工程状态。branch、push、PR、CI、merge 和 branch deletion 的实时生命周期状态以 Git / GitHub 为准；本文不复制这些瞬时状态，也不是 release evidence source of truth。

## 当前状态

- 日期：2026-09-14
- 当前任务：`v0.5.0-008 — ALG-004 Task Spec + Benchmark Profile v1`
- task-start baseline：`origin/develop` / `fb8d8e916cd1cc82d782e2ed298e43d28af7e66b`
- 当前短期任务分支：`docs/algo-004-spec-benchmark-v1`
- 当前阶段：**ALG-004 Task Spec / Benchmark Profile freeze / remote review**
- 当前 stable release：**v0.4.0**；previous stable：v0.3.2
- 下一版本研发目标：**v0.5.0 — Balance Recovery；未发布**
- 继承软件资格：**ALG-001 Candidate A / ALG-001 QUALIFIED**；**ALG-002 Candidate A / ALG-002 QUALIFIED**；**ALG-003 Candidate A / ALG-003 QUALIFIED**
- ALG-004 Task Spec：[`v1`](algorithm_tasks/ALG-004.md)
- Benchmark：[`Algorithm Benchmark v1 / ALG-004 Profile v1`](ALGORITHM_BENCHMARK.md#11-alg-004-profile-v1)
- Fixture：`ALG004-FIXTURE-v1`
- ALG-004 Candidate：**NOT IMPLEMENTED**；无 Candidate Result 或 implementation commit
- hardware access：**NO**
- hardware authorization：**NONE**
- hardware validation：**NOT AUTHORIZED / NOT EXECUTED**
- real Balance Recovery：**NOT VERIFIED / NOT CLAIMED**

## 已完成的稳定事实与边界

- ALG-001 Candidate A 固定 implementation commit `fe575c9589013138d238e567e93dac2925384ab7`；[正式 Result](algorithm_results/ALG-001_CANDIDATE_A.md) 为 `ALG-001 QUALIFIED`。
- ALG-002 Candidate A 固定 implementation commit `77e7b4f98e60602d3b224618225e11e9fecc8fe8`；[正式 Result](algorithm_results/ALG-002_CANDIDATE_A.md) 为 `ALG-002 QUALIFIED`。
- ALG-003 Candidate A 固定 implementation commit `240cda9f1c2b73dad7ae70bf0c2c9205a76f0364`；[正式 Result](algorithm_results/ALG-003_CANDIDATE_A.md) 为 `ALG-003 QUALIFIED`。
- Flight API 在 `develop` 提供与 `relative_pitch_rad` 同软件正方向的 `relative_pitch_rate_rad_s`；default controller、教学控制器、synthetic DRY_RUN 默认行为未改变。
- 上述资格只是固定 synthetic fixture 的软件结论。Candidate A 的普通 `FlightCommand` 是当前完整 motor feedback position hold 与 fan-zero preview，不编码 abstract intent 或真实执行器方向；v0.5.0 尚未发布。

## 当前任务目标与下一步

本工作单元仅建立 [ALG-004 Task Spec v1](algorithm_tasks/ALG-004.md)、[ALG-004 Profile v1 / ALG004-FIXTURE-v1](ALGORITHM_BENCHMARK.md#11-alg-004-profile-v1)，冻结 synthetic abstract intent 的幅值、slew、directed transition、信号保留、符号切换、reset/fail-close 和 ALG-001/002/003 继承资格。`0.10 intent unit`、`2.0 intent unit/s` 不是机器人或执行器硬件安全 envelope。没有实现 ALG-004 Candidate，没有修改 Flight API/Runtime/default controller，没有 actuator allocation，也没有硬件访问。

下一推荐工作单元是 `v0.5.0-009 — ALG-004 Candidate A Implementation`，但**必须等待本 Task Spec / Benchmark Profile 的 remote review 完成，并经用户单独授权 PR、PR 合入 `develop` 后才能启动**。真实 IMU characterization、可信动态验证、执行器映射和硬件测试均为独立工作单元，当前未获授权。

## 历史证据保留

v0.4.0 的 Gate B/C/D、PASS/FAIL/NOT VERIFIED、有效与无效 session、接线映射、release blocker、安全结论、证据等级及已知限制长期保存在 [硬件与功能验证记录](verification/v0.4.0/HARDWARE_VERIFICATION_RECORD.md)、[硬件验证历史执行计划](V0.4.0_HARDWARE_VERIFICATION_PLAN.md) 和 [发布说明](RELEASE_NOTES_v0.4.0.md)。本次文档任务不改变这些历史证据，也不授权新硬件操作。
