# WindArmor 当前开发交接

> **INTERNAL DEVELOPMENT HANDOFF — MUTABLE。** 本文件只记录当前任务和对下一工作单元有价值的
> 稳定工程状态，不持续复制 branch、push、PR、CI、merge 或 branch deletion 等瞬时生命周期
> 状态；这些状态以 Git / GitHub 当前信息为准。本文件不是普通用户操作文档、长期接口契约或
> release evidence source of truth，历史发布事实必须引用对应的版本化 release/verification
> 文档。

## 当前状态

- 日期：2026-09-09
- 当前任务：`v0.5.0-004A — Flight Pitch Rate Coordinate Contract`
- task-start baseline：`origin/develop` /
  `73cd22a002a7f6c9203b1205c084a6bb0482d8b3`
- 当前短期任务分支：`feature/flight-pitch-rate-contract`
- 当前阶段：**解除 ALG-002 specification blocker**
- 当前 stable release：**v0.4.0**
- previous stable / history：v0.3.2
- 下一版本研发目标：**v0.5.0 — Balance Recovery；未发布**
- Task Spec：`ALG-001 v1`
- Benchmark：`Algorithm Benchmark v1 / ALG-001 Profile v1`
- ALG-002 specification：**BLOCKED；等待 pitch-rate contract 合入 develop**
- 当前 API 目标：建立 `relative_pitch_rate_rad_s`
- hardware access：**NO**
- hardware authorization：**NONE；无新的硬件授权**
- 真实 Balance Recovery verification：**NOT EXECUTED / NOT CLAIMED**
- Integration lifecycle：以 Git / GitHub 当前 branch、PR 与 Actions 状态为准
- Tag / Release：**未创建**

## 已完成的稳定事实

- `v0.5.0-001`：**COMPLETE**；
- `v0.5.0-002`：**COMPLETE**；
- `v0.5.0-003`：**COMPLETE**；
- ALG-001 Candidate A：**ALG-001 QUALIFIED**；
- Candidate A implementation commit：
  `fe575c9589013138d238e567e93dac2925384ab7`；
- 正式 Candidate Result：
  [`algorithm_results/ALG-001_CANDIDATE_A.md`](algorithm_results/ALG-001_CANDIDATE_A.md)；
- Candidate A 已进入 `develop`，对应 post-merge WindArmor Software CI：**PASS**；
- default controller、教学控制器和 synthetic DRY_RUN 默认行为未改变；
- v0.5.0 尚未发布。

`ALG-001 QUALIFIED` 只表示固定 synthetic fixture 上的 Level A/B 软件 qualification，不是动态
仿真、control allocation、硬件验证或真实 Balance Recovery 证据。Candidate A 的普通命令仍
只是复制当前合法、完整 motor feedback 的 hold preview，并给两路风扇 `0.0`；该 payload 不
编码 intent，也不具有真实执行器分配或恢复方向含义。

## 当前任务目标与边界

本任务为 `ImuState` 建立可由算法直接消费的 `relative_pitch_rate_rad_s` 坐标契约。它由
Flight adapter 使用同一原始 IMU 样本的 orientation 和 body-frame angular velocity 按当前
Z-Y-X 欧拉运动学派生，并应用与 `relative_pitch_rad` 一致的 `pitch_axis_sign`；不使用角度
有限差分，不改变原始 `angular_velocity_rad_s` 的 IMU/body frame 语义。

本任务只解除 ALG-002 的 pitch-rate API / 坐标阻塞，不创建 ALG-002 Task Spec、Benchmark
Profile 或 Candidate，不实现 damping、filter、deadband、slew-rate、状态机、actuator
allocation、roll controller 或动态恢复，也不改变真实执行器映射或获得硬件授权。

## 历史证据保留

v0.4.0 的 Gate B/C/D、PASS/FAIL/NOT VERIFIED、有效与无效 session、接线映射、release
blocker、安全结论、证据等级和已知限制继续长期保存在：

- [v0.4.0 硬件与功能验证记录](verification/v0.4.0/HARDWARE_VERIFICATION_RECORD.md)；
- [v0.4.0 硬件验证历史执行计划](V0.4.0_HARDWARE_VERIFICATION_PLAN.md)；
- [v0.4.0 发布说明](RELEASE_NOTES_v0.4.0.md)。

本次治理更新没有删除或改变这些历史证据，也不授权新的硬件操作。

## 下一推荐工作单元

本 pitch-rate contract 经远端评审并合入 `develop` 后，重新启动：

```text
v0.5.0-004 — ALG-002 Task Spec + Benchmark Profile v1
```

ALG-002 的控制律、候选与资格结果仍必须在后续独立任务中确定。
