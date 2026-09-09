# WindArmor 当前开发交接

> **INTERNAL DEVELOPMENT HANDOFF — MUTABLE。** 本文件只记录当前任务和对下一工作单元有价值的
> 稳定工程状态，不持续复制 branch、push、PR、CI、merge 或 branch deletion 等瞬时生命周期
> 状态；这些状态以 Git / GitHub 当前信息为准。本文件不是普通用户操作文档、长期接口契约或
> release evidence source of truth，历史发布事实必须引用对应的版本化 release/verification
> 文档。

## 当前状态

- 日期：2026-09-09
- 当前任务：`v0.5.0-005 — ALG-002 Candidate A Implementation`
- task-start baseline：`origin/develop` /
  `e58e66144e1e9640adb330dc0f2eed1927e95624`
- 当前短期任务分支：`feature/algo-002-candidate-a`
- 当前阶段：**implementation + pre-formal-qualification remote review**
- 当前 stable release：**v0.4.0**
- previous stable / history：v0.3.2
- 下一版本研发目标：**v0.5.0 — Balance Recovery；未发布**
- Task Spec：`ALG-002 v1`
- Benchmark：`Algorithm Benchmark v1 / ALG-002 Profile v1`
- Fixture：`ALG002-FIXTURE-v1`
- Candidate：`Candidate A`
- ALG-001 Candidate A：**ALG-001 QUALIFIED**
- ALG-002 Candidate A：**UNDER REMOTE REVIEW**
- formal Candidate Result：**NOT GENERATED**
- v0.5.0-004A：**COMPLETE**
- `relative_pitch_rate_rad_s`：**已进入 develop**
- hardware access：**NO**
- hardware authorization：**NONE；无新的硬件授权**
- 真实 Balance Recovery verification：**NOT EXECUTED / NOT CLAIMED**
- Integration lifecycle：以 Git / GitHub 当前 branch、PR 与 Actions 状态为准
- Tag / Release：**未创建**

## 已完成的稳定事实

- `v0.5.0-001`：**COMPLETE**；
- `v0.5.0-002`：**COMPLETE**；
- `v0.5.0-003`：**COMPLETE**；
- `v0.5.0-004A`：**COMPLETE**；
- `v0.5.0-004`：**COMPLETE**；
- ALG-001 Candidate A：**ALG-001 QUALIFIED**；
- Candidate A implementation commit：
  `fe575c9589013138d238e567e93dac2925384ab7`；
- 正式 Candidate Result：
  [`algorithm_results/ALG-001_CANDIDATE_A.md`](algorithm_results/ALG-001_CANDIDATE_A.md)；
- Candidate A 已进入 `develop`，对应 post-merge WindArmor Software CI：**PASS**；
- Flight API 已在 `develop` 提供与 `relative_pitch_rad` 同软件正方向的
  `relative_pitch_rate_rad_s`；
- default controller、教学控制器和 synthetic DRY_RUN 默认行为未改变；
- v0.5.0 尚未发布。

`ALG-001 QUALIFIED` 只表示固定 synthetic fixture 上的 Level A/B 软件 qualification，不是动态
仿真、control allocation、硬件验证或真实 Balance Recovery 证据。Candidate A 的普通命令仍
只是复制当前合法、完整 motor feedback 的 hold preview，并给两路风扇 `0.0`；该 payload 不
编码 intent，也不具有真实执行器分配或恢复方向含义。

## 当前任务目标与边界

本任务实现 ALG-002 Candidate A：在 ALG-001 基础姿态反馈上，只使用统一的
`relative_pitch_rad` 和 `relative_pitch_rate_rad_s` 增加无历史状态的 Motion Trend / Damping
软件能力，并按冻结的 ALG-002 Profile v1 验证继承、正常趋势、fail-close、`dt`、reset、
repeatability、factory 和完整 `FlightCommand` 契约。

本阶段只形成供远端评审的 implementation checkpoint；正式 Candidate Result 尚未生成，
不得提前写入 `ALG-002 QUALIFIED`。本任务不实现 filtering/deadband/slew-rate、恢复状态机、
actuator allocation、roll control 或动态恢复，也不改变 Flight API、Runtime、ALG-001 历史
结果、真实执行器映射或硬件状态。

## 历史证据保留

v0.4.0 的 Gate B/C/D、PASS/FAIL/NOT VERIFIED、有效与无效 session、接线映射、release
blocker、安全结论、证据等级和已知限制继续长期保存在：

- [v0.4.0 硬件与功能验证记录](verification/v0.4.0/HARDWARE_VERIFICATION_RECORD.md)；
- [v0.4.0 硬件验证历史执行计划](V0.4.0_HARDWARE_VERIFICATION_PLAN.md)；
- [v0.4.0 发布说明](RELEASE_NOTES_v0.4.0.md)。

本次文档任务没有删除或改变这些历史证据，也不授权新的硬件操作。

## 下一推荐工作单元

Candidate A implementation checkpoint 经远端评审通过并固定 implementation SHA 后，才可启动：

```text
ALG-002 Candidate A Formal Qualification
```

下一阶段必须在干净的固定 implementation commit 上重跑 Algorithm Benchmark v1 / ALG-002
Profile v1，再生成独立 Candidate Result；当前没有 ALG-002 qualification 结论。
