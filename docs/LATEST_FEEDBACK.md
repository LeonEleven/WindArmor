# WindArmor 当前开发交接

> **INTERNAL DEVELOPMENT HANDOFF — MUTABLE。** 本文件只记录当前任务状态、关键决策和
> 下一步，不是普通用户操作文档、长期接口契约或 release evidence source of truth。历史
> 发布事实必须引用对应的版本化 release/verification 文档。

## 当前状态

- 日期：2026-09-08
- 当前任务：`v0.5.0-003 — ALG-001 Candidate A Implementation`
- implementation task-start baseline：`origin/develop` /
  `7971ffa14d7f60d93a6100d128e875ee79908c2f`
- 当前任务分支：`feature/algo-001-candidate-a`
- 当前 stable release：**v0.4.0**
- previous stable / history：v0.3.2
- 下一版本研发目标：**v0.5.0 — Balance Recovery；未发布**
- Task Spec：`ALG-001 v1`
- Benchmark：`Algorithm Benchmark v1 / ALG-001 Profile v1`
- Candidate：`Candidate A`
- 当前阶段：**implementation + pre-commit qualification**
- implementation commit：**尚不存在 / PENDING REVIEW**
- final Candidate Result：**尚未生成**
- hardware access：**NO**
- hardware authorization：**NONE**

## 本任务实现

Candidate A 使用固定默认配置 `Kp = 1.0 intent/rad`，实现：

```text
target_pitch_rad = 0.0
pitch_error_rad = target_pitch_rad - relative_pitch_rad
pitch_feedback_intent = Kp * pitch_error_rad
```

Level A 通过不依赖 ROS/硬件的纯函数与 controller seam 暴露抽象
`pitch_feedback_intent`。Level B 复用现有 factory/loader；普通命令逐帧复制当前合法、完整的
motor feedback 作为 hold preview，并给两路风扇 `0.0`。该 payload 不编码 intent，不具有真实
control allocation 或恢复方向含义，也不复用上一帧命令或 motor baseline。

Candidate A 是非默认软件候选。默认控制器、教学控制器、Runtime、Flight API、authority、
ownership、synthetic DRY_RUN 默认行为和硬件配置均未改变。

## Pre-commit qualification

- Targeted Candidate A / ALG-001：**47 collected、47 PASS**；
- `ALG001-N00/P01/P02/N01/N02`：**PASS（Level A + Level B）**；
- neutral、direction、strict monotonic magnitude、proportional consistency、symmetry、finite
  output：**PASS**；
- repeatability：**PASS（每个正常场景 3 次）**；
- `ALG001-F01`–`F08`：**PASS，state-validation/controller layer 分类符合 Profile v1**；
- `ALG001-D01`–`D04`：**PASS**；
- `ALG001-R01`：**PASS**；
- 正有限可变 `dt` 与完整 `FlightCommand` validation：**PASS**；
- factory loading、配置追溯与非法配置拒绝：**PASS**；
- 不加载构建后 install overlay 时可直接运行的 Flight 回归子集：**275 PASS**；
- 统一 `scripts/ci_software.sh`：**PASS**；五包 build PASS，motor 431 PASS、fan 159 PASS、
  flight/interface 365 PASS，最终 `986 tests, 0 errors, 0 failures, 0 skipped`；
- future-task boundary review：**PASS；未实现 ALG-002–ALG-008**；
- Level C synthetic DRY_RUN：**NOT EXECUTED；当前工具固定选择教学控制器，本任务不改变其
  默认行为**；
- hardware validation：**NOT EXECUTED / NOT AUTHORIZED**。

以上只是尚未提交实现的 pre-commit qualification，不是带 implementation SHA 的正式
Candidate Result，也不是动态仿真、control allocation 或真实 Balance Recovery 证据。

## 历史证据保留

v0.4.0 的 Gate B/C/D、PASS/FAIL/NOT VERIFIED、有效与无效 session、接线映射、release
blocker、安全结论、证据等级和已知限制已长期保存在：

- [v0.4.0 硬件与功能验证记录](verification/v0.4.0/HARDWARE_VERIFICATION_RECORD.md)；
- [v0.4.0 硬件验证历史执行计划](V0.4.0_HARDWARE_VERIFICATION_PLAN.md)；
- [v0.4.0 发布说明](RELEASE_NOTES_v0.4.0.md)。

本次更新没有删除或改变这些历史证据。它们不授权新的硬件操作，也不能扩展为 ALG-001 或
v0.5.0 真实 Balance Recovery 已验证。

## 变更与安全边界

- Candidate A production algorithm code changed：**YES**
- Candidate A / reusable ALG-001 software tests changed：**YES**
- README development status changed：**YES**
- Task Spec / Benchmark Contract changed：**NO**
- Runtime / Flight API / authority / ownership changed：**NO**
- default/example controller 或 synthetic DRY_RUN behavior changed：**NO**
- real motor/fan allocation implemented：**NO**
- motor/fan 参数、CAN/GPIO/PWM、机械限位或硬件映射 changed：**NO**
- package version changed to v0.5.0：**NO**
- 真实 IMU、CAN、电机、风扇、GPIO/PWM 或串口 accessed：**NO**
- powered test：**NO**
- implementation commit / push / PR / tag / release：**未创建**

## 下一步

```text
代码/测试 review
  -> 用户授权 implementation commit
  -> 固定 implementation SHA
  -> 针对固定 SHA 正式 rerun Algorithm Benchmark v1
  -> 生成 Candidate A Result
```

在取得 implementation commit 的明确授权前，不 commit、不 push、不创建 PR，也不生成声称
最终 PASS 的 Candidate Result。
