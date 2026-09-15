# WindArmor 当前开发交接

> **INTERNAL DEVELOPMENT HANDOFF — MUTABLE。** 本文件只记录当前任务和对下一工作单元有价值的稳定工程状态。branch、push、PR、CI、merge 和 branch deletion 的实时生命周期状态以 Git / GitHub 为准；本文不复制这些瞬时状态，也不是 release evidence source of truth。

## 当前状态

- 日期：2026-09-15
- 当前任务：`v0.5.0-009 — ALG-004 Candidate A Implementation`
- task-start baseline：`origin/develop` / `1cfab2f22d82d1468ac3ad5fd37ad7b6380c9065`
- 当前短期任务分支：`feature/algo-004-candidate-a`
- 当前阶段：**ALG-004 Candidate A implementation / Remote Review Checkpoint**
- 当前 stable release：**v0.4.0**；previous stable：v0.3.2
- 下一版本研发目标：**v0.5.0 — Balance Recovery；未发布**
- 继承软件资格：**ALG-001 QUALIFIED**；**ALG-002 QUALIFIED**；**ALG-003 QUALIFIED**
- ALG-004 Task Spec：[`v1 / FROZEN`](algorithm_tasks/ALG-004.md)
- ALG-004 Profile：[`v1 / FROZEN`](ALGORITHM_BENCHMARK.md#11-alg-004-profile-v1)
- Fixture：`ALG004-FIXTURE-v1`
- Candidate A：**IMPLEMENTED FOR REVIEW**
- Implementation-stage software verification：**PASS**
- Formal qualification：**NOT EXECUTED**
- Candidate Result：**NOT CREATED**
- hardware access：**NO**
- hardware authorization：**NONE**
- hardware validation：**NOT AUTHORIZED / NOT EXECUTED**
- real actuator safety：**NOT VERIFIED / NOT CLAIMED**
- real Balance Recovery：**NOT VERIFIED / NOT CLAIMED**

## 已实现的稳定范围与边界

ALG-004 Candidate A 复用 ALG-003 Candidate A 的固定两样本输入移动平均与 `Kp=1.0`、
`Kd=0.1` 软件反馈语义，只在 inherited abstract intent 后增加 `0.10 intent unit` 幅值限制和
`2.0 intent unit/s` 对称、按实际 `dt` 归一化的 slew limiter。reset、非法输入和
controller-layer fail-close 会同时清除 ALG-003 输入/filter history 与 ALG-004 shaped-output
history。

普通 `FlightCommand` 仍只复制当前合法完整 motor feedback position hold，左右 fan 为
`0.0`；shaped intent 未映射到电机或风扇。Flight API、Runtime、default controller、教学
controller、硬件映射和现有安全机制未改变；未实现 actuator allocation 或 ALG-005+ 能力。

本阶段测试是 fixed synthetic fixture、pure/fake/mock 路径的 implementation-stage 软件验证，
不是正式 ALG-004 qualification、动态闭环仿真、真实执行器安全验证或 Balance Recovery
验证。`0.10 intent unit` 与 `2.0 intent unit/s` 不是 CyberGear、PWM、fan thrust 或机器人
实际安全 envelope。

## 下一步

先完成当前 implementation checkpoint 的 Remote Review。Remote Review PASS 后，固定 exact
implementation SHA，再作为独立工作阶段执行 Algorithm Benchmark v1 / ALG-004 Profile v1
正式 qualification；只有该阶段完成后才允许生成
`docs/algorithm_results/ALG-004_CANDIDATE_A.md`。当前不得宣布 `ALG-004 QUALIFIED`。

## 历史证据保留

ALG-001 Candidate A 固定 implementation commit
`fe575c9589013138d238e567e93dac2925384ab7`；ALG-002 Candidate A 固定 implementation commit
`77e7b4f98e60602d3b224618225e11e9fecc8fe8`；ALG-003 Candidate A 固定 implementation commit
`240cda9f1c2b73dad7ae70bf0c2c9205a76f0364`。相应正式 Result 保持不变。

v0.4.0 的 Gate B/C/D、PASS/FAIL/NOT VERIFIED、接线映射、release blocker、安全结论和证据等级
长期保存在 [硬件与功能验证记录](verification/v0.4.0/HARDWARE_VERIFICATION_RECORD.md)、
[硬件验证历史执行计划](V0.4.0_HARDWARE_VERIFICATION_PLAN.md) 和
[发布说明](RELEASE_NOTES_v0.4.0.md)。本任务不改变这些历史证据，也不授权新硬件操作。
