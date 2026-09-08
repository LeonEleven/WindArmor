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
- implementation commit：`fe575c9589013138d238e567e93dac2925384ab7`
- 当前 stable release：**v0.4.0**
- previous stable / history：v0.3.2
- 下一版本研发目标：**v0.5.0 — Balance Recovery；未发布**
- Task Spec：`ALG-001 v1`
- Benchmark：`Algorithm Benchmark v1 / ALG-001 Profile v1`
- Candidate：`Candidate A`
- 当前阶段：**formal qualification evidence complete / awaiting PR decision**
- 正式 Candidate Result：
  [`algorithm_results/ALG-001_CANDIDATE_A.md`](algorithm_results/ALG-001_CANDIDATE_A.md)
- 正式 Hard Qualification：**PASS**
- Overall：**ALG-001 QUALIFIED**
- hardware access：**NO**
- hardware authorization：**NONE**
- 真实 Balance Recovery verification：**NOT EXECUTED / NOT CLAIMED**

## Candidate A implementation

固定 implementation 使用默认配置 `Kp = 1.0 intent/rad`，实现：

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

## Formal qualification

正式 benchmark 开始前工作区干净，`HEAD` 精确为固定 implementation commit。全部软件证据
取得后才生成长期 Result。

- Environment：Ubuntu 24.04.4 LTS，Linux 6.8.0-1064-raspi aarch64，ROS 2 Jazzy，
  Python 3.12.3，pytest 7.4.4；
- Targeted Candidate A / ALG-001：**47 collected、47 PASS**；
- `ALG001-N00/P01/P02/N01/N02`：**PASS（Level A + Level B）**；
- 实际 intent：`0.0`、`-0.05`、`-0.1`、`+0.05`、`+0.1`；
- neutral、direction、strict monotonic magnitude、proportional consistency、symmetry、finite
  output：**PASS**；
- repeatability：**PASS（每个正常场景 3 次）**；
- `ALG001-F01`–`F08`：**PASS，state-validation/controller layer 分类符合 Profile v1**；
- `ALG001-D01`–`D04`：**PASS，包括 D04 的 `+Inf/-Inf` variant**；
- `ALG001-R01`：**PASS**；
- proportional consistency error：`0.0 intent/rad`；
- symmetry error：`0.0 intent unit`；
- repeatability delta：`0.0 intent unit`；
- complete `windarmor_flight_control` regression：**357 PASS**；
- 统一 `scripts/ci_software.sh`：**PASS**；五包 build PASS，motor 431 PASS、fan 159 PASS、
  flight/interface 365 PASS，最终 `986 tests, 0 errors, 0 failures, 0 skipped`；
- future-task boundary review：**PASS；ALG-002–ALG-008 leakage = NO**；
- Level C synthetic DRY_RUN：**NOT EXECUTED；当前工具固定选择教学控制器，本任务未改变其
  默认行为**；
- hardware validation：**NOT EXECUTED / NOT AUTHORIZED**。

完整环境、命令、逐场景结果、comparative metrics、限制和未执行测试见正式 Candidate
Result。`ALG-001 QUALIFIED` 只表示固定 synthetic fixture 上的 Level A/B 软件 qualification，
不是动态仿真、control allocation、硬件验证或真实 Balance Recovery 证据。

## 历史证据保留

v0.4.0 的 Gate B/C/D、PASS/FAIL/NOT VERIFIED、有效与无效 session、接线映射、release
blocker、安全结论、证据等级和已知限制已长期保存在：

- [v0.4.0 硬件与功能验证记录](verification/v0.4.0/HARDWARE_VERIFICATION_RECORD.md)；
- [v0.4.0 硬件验证历史执行计划](V0.4.0_HARDWARE_VERIFICATION_PLAN.md)；
- [v0.4.0 发布说明](RELEASE_NOTES_v0.4.0.md)。

本次更新没有删除或改变这些历史证据。它们不授权新的硬件操作，也不能扩展为 ALG-001 或
v0.5.0 真实 Balance Recovery 已验证。

## 变更与安全边界

- implementation 已存在于远端任务分支；
- 正式 Candidate Result 与 handoff 已形成任务分支文档证据；
- Candidate A production source / test semantics changed：**NO**
- Task Spec / Benchmark Contract changed：**NO**
- Runtime / Flight API / authority / ownership changed：**NO**
- default/example controller 或 synthetic DRY_RUN behavior changed：**NO**
- real motor/fan allocation implemented：**NO**
- motor/fan 参数、CAN/GPIO/PWM、机械限位或硬件映射 changed：**NO**
- 真实 IMU、CAN、电机、风扇、GPIO/PWM 或串口 accessed：**NO**
- powered test：**NO**
- PR / merge 状态：以 GitHub 当前状态为准；
- tag / release：**未创建**。

## 下一步

```text
正式 Candidate Result 已进入任务分支
  -> 用户决定是否创建 PR 到 develop
```

本轮不自动创建 PR、merge、tag 或 release；等待用户决定下一 Git 生命周期步骤。
