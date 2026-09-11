# WindArmor 当前开发交接

> **INTERNAL DEVELOPMENT HANDOFF — MUTABLE。** 本文件只记录当前任务和对下一工作单元有价值的
> 稳定工程状态，不持续复制 branch、push、PR、CI、merge 或 branch deletion 等瞬时生命周期
> 状态；这些状态以 Git / GitHub 当前信息为准。本文件不是普通用户操作文档、长期接口契约或
> release evidence source of truth，历史发布事实必须引用对应的版本化 release/verification
> 文档。

## 当前状态

- 日期：2026-09-10
- 当前任务：`v0.5.0-005 — ALG-002 Candidate A Implementation`
- task-start baseline：`origin/develop` /
  `e58e66144e1e9640adb330dc0f2eed1927e95624`
- 当前短期任务分支：`feature/algo-002-candidate-a`
- 当前阶段：**formal qualification evidence complete / remote review**
- 当前 stable release：**v0.4.0**
- previous stable / history：v0.3.2
- 下一版本研发目标：**v0.5.0 — Balance Recovery；未发布**
- Task Spec：`ALG-002 v1`
- Benchmark：`Algorithm Benchmark v1 / ALG-002 Profile v1`
- Fixture：`ALG002-FIXTURE-v1`
- Candidate：`Candidate A`
- ALG-001 Candidate A：**ALG-001 QUALIFIED**
- ALG-002 Candidate A implementation commit：
  `77e7b4f98e60602d3b224618225e11e9fecc8fe8`
- Candidate Result：
  [`algorithm_results/ALG-002_CANDIDATE_A.md`](algorithm_results/ALG-002_CANDIDATE_A.md)
- Hard Qualification：**PASS**
- Overall：**ALG-002 QUALIFIED**
- v0.5.0-004A：**COMPLETE**
- `relative_pitch_rate_rad_s`：**已进入 develop**
- hardware access：**NO**
- hardware authorization：**NONE；无新的硬件授权**
- 真实 Balance Recovery verification：**NOT VERIFIED / NOT CLAIMED**
- Integration lifecycle：以 Git / GitHub 当前 branch、PR 与 Actions 状态为准
- Tag / Release：**未创建**

## 已完成的稳定事实

- `v0.5.0-001`：**COMPLETE**；
- `v0.5.0-002`：**COMPLETE**；
- `v0.5.0-003`：**COMPLETE**；
- `v0.5.0-004A`：**COMPLETE**；
- `v0.5.0-004`：**COMPLETE**；
- ALG-001 Candidate A：**ALG-001 QUALIFIED**；
- ALG-001 Candidate A implementation commit：
  `fe575c9589013138d238e567e93dac2925384ab7`；
- 正式 Candidate Result：
  [`algorithm_results/ALG-001_CANDIDATE_A.md`](algorithm_results/ALG-001_CANDIDATE_A.md)；
- ALG-001 Candidate A 已进入 `develop`，对应 post-merge WindArmor Software CI：**PASS**；
- ALG-002 Candidate A 固定 implementation commit 为
  `77e7b4f98e60602d3b224618225e11e9fecc8fe8`；
- ALG-002 Candidate A 已针对固定 SHA 完成 Algorithm Benchmark v1 / ALG-002 Profile v1
  Level A/B 正式纯软件资格验证，结论为 **ALG-002 QUALIFIED**；
- 正式 ALG-002 Candidate Result：
  [`algorithm_results/ALG-002_CANDIDATE_A.md`](algorithm_results/ALG-002_CANDIDATE_A.md)；
- Flight API 已在 `develop` 提供与 `relative_pitch_rad` 同软件正方向的
  `relative_pitch_rate_rad_s`；
- default controller、教学控制器和 synthetic DRY_RUN 默认行为未改变；
- v0.5.0 尚未发布。

`ALG-001 QUALIFIED` 只表示固定 synthetic fixture 上的 Level A/B 软件 qualification，不是动态
仿真、control allocation、硬件验证或真实 Balance Recovery 证据。Candidate A 的普通命令仍
只是复制当前合法、完整 motor feedback 的 hold preview，并给两路风扇 `0.0`；该 payload 不
编码 intent，也不具有真实执行器分配或恢复方向含义。

## 当前任务目标与边界

本任务已经固定 ALG-002 Candidate A implementation SHA，并针对该精确提交完成 ALG-001
inheritance、正常趋势、fail-close、`dt`、reset、repeatability、factory、完整
`FlightCommand` 和 Software CI 的正式纯软件资格验证。结果严格限定为 ALG-002 Profile v1
的 synthetic Level A/B 软件证据，不是动态仿真、真实 actuator direction 或 Balance Recovery
实机证据。

本任务不实现 filtering/deadband/slew-rate、恢复状态机、actuator allocation、roll control
或动态恢复，也不改变 Flight API、Runtime、ALG-001 历史结果、真实执行器映射或硬件状态。

## 历史证据保留

v0.4.0 的 Gate B/C/D、PASS/FAIL/NOT VERIFIED、有效与无效 session、接线映射、release
blocker、安全结论、证据等级和已知限制继续长期保存在：

- [v0.4.0 硬件与功能验证记录](verification/v0.4.0/HARDWARE_VERIFICATION_RECORD.md)；
- [v0.4.0 硬件验证历史执行计划](V0.4.0_HARDWARE_VERIFICATION_PLAN.md)；
- [v0.4.0 发布说明](RELEASE_NOTES_v0.4.0.md)。

本次文档任务没有删除或改变这些历史证据，也不授权新的硬件操作。

## 下一推荐工作单元

ALG-002 Candidate Result 经远端评审通过后，下一集成动作需要用户针对当前任务单独授权：

```text
Create PR: feature/algo-002-candidate-a -> develop
```

PR、merge 和分支清理均不在当前授权范围；v0.5.0 仍未发布，真实 Balance Recovery 仍为
`NOT VERIFIED / NOT CLAIMED`。
