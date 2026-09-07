# WindArmor 当前开发交接

> **INTERNAL DEVELOPMENT HANDOFF — MUTABLE。** 本文件只记录当前任务状态、关键决策和
> 下一步，不是普通用户操作文档、长期接口契约或 release evidence source of truth。历史
> 发布事实必须引用对应的版本化 release/verification 文档。

## 当前状态

- 日期：2026-09-07
- 当前任务：`v0.5.0-002 — ALG-001 Task Spec + Algorithm Benchmark v1 Contract`
- task-start baseline：`origin/develop` / `30d4e02c84a12604de81ff3d1fd24f25759a40c1`
- 当前任务分支：`docs/v0.5-alg001-benchmark-contract`
- 当前 stable release：**v0.4.0**
- previous stable / history：v0.3.2
- 下一版本研发目标：**v0.5.0 — Balance Recovery；未发布**
- 当前阶段：**Algorithm specification / benchmark contract**
- `v0.5.0-001` roadmap：**已进入 `develop`**
- `develop` Software CI：**已验证工作正常**
- ALG-001 implementation：**不存在 / NOT IMPLEMENTED**
- 新的真实 actuator 验证：**未执行**
- 当前硬件授权：**无**

## 本任务

本任务建立两个长期文档资产：

- [`algorithm_tasks/ALG-001.md`](algorithm_tasks/ALG-001.md)：ALG-001 Task Spec v1；
- [`ALGORITHM_BENCHMARK.md`](ALGORITHM_BENCHMARK.md)：Algorithm Benchmark v1 Contract 与
  ALG-001 Profile v1。

核心决策：

- `target_pitch_rad = 0`，`pitch_error_rad = target - relative_pitch_rad`；
- 使用 task-local `pitch_feedback_intent` 评分基础比例反馈的软件符号、幅值关系和重复性；
- 软件 feedback sign 不代表任何已验证的电机/风扇物理方向；
- LEVEL A 评分抽象 intent，LEVEL B 只评分 controller/`FlightCommand` 合法性和 fail-close；
- 在 ALG-006 以前，不从 motor/fan payload 反推物理 control allocation；相关指标明确为当前
  不可评分；
- Hard Qualification 与 comparative metrics 分离，任何安全 gate FAIL 都是
  `ALG-001 NOT QUALIFIED`；
- 本任务只制定规范，不创建 candidate、benchmark runner 或 production test。

## 规范与场景

- Task Spec：`v1`；Benchmark Contract：`v1`；ALG-001 Profile：`v1`；fixture：
  `ALG001-FIXTURE-v1`；
- 正常场景：`ALG001-N00`、`P01`、`P02`、`N01`、`N02`，synthetic pitch 为
  `0`、`±0.05`、`±0.10 rad`；
- fail-close：`ALG001-F01`–`F08` 和 `D01`–`D04`；
- reset：`ALG001-R01`；
- `relative_pitch_rad` 的 NaN/Inf、valid IMU 中缺失 pitch、motor key 缺失由前置 state
  validation 拒绝；合法 invalid/unobserved/stale/unhealthy state 和非法 `dt` 由 controller
  返回无载荷 safe-stop；
- ALG-002 damping、ALG-003 filtering、ALG-004 output shaping、ALG-005 recovery process、
  ALG-006 allocation、ALG-007 multi-axis 和 ALG-008 dynamic recovery 均保留为 future-task
  boundary。

## 本任务验证

- `git diff --check`：**PASS**；
- Markdown relative-link scan：**36 files scanned、131 links checked、missing 0**；
- `python3 scripts/check_ci_safety.py`：**PASS（2 files checked）**；
- full ROS 2 build/test：**未执行**；本任务只修改 Markdown，不改变 executable behavior；
- hardware validation：**未执行**；本任务不需要且没有硬件授权。

## 历史证据保留

v0.4.0 的 Gate B/C/D、PASS/FAIL/NOT VERIFIED、有效与无效 session、接线映射、release
blocker、安全结论、证据等级和已知限制已长期保存在：

- [v0.4.0 硬件与功能验证记录](verification/v0.4.0/HARDWARE_VERIFICATION_RECORD.md)；
- [v0.4.0 硬件验证历史执行计划](V0.4.0_HARDWARE_VERIFICATION_PLAN.md)；
- [v0.4.0 发布说明](RELEASE_NOTES_v0.4.0.md)。

本次更新没有删除或改变这些历史证据。它们不授权新的硬件操作，也不能扩展为 ALG-001 或
v0.5.0 真实 Balance Recovery 已验证。

## 变更与安全边界

- specification / benchmark / navigation documentation changed：**YES**
- production code / tests / Runtime / Flight API changed：**NO**
- default/example controller 或 synthetic DRY_RUN behavior changed：**NO**
- ALG-001 candidate / parameters / implementation created：**NO**
- motor/fan 参数、CAN/GPIO/PWM、机械限位或硬件映射 changed：**NO**
- package version changed to v0.5.0：**NO**
- 真实 IMU、CAN、电机、风扇、GPIO/PWM 或串口 accessed：**NO**
- powered test：**NO**
- commit / push / PR / merge / tag / release：**NO**

## 下一推荐任务

用户 review 并明确授权本任务的 commit、push 和 PR 后，下一工作单元才是正式启动
`ALG-001 implementation candidate`。该任务应从同一个冻结的 Task Spec v1、Algorithm
Benchmark v1 和 ALG-001 Profile v1 出发，建立可追溯且彼此独立的 implementation lineage；
不得自动提前创建 candidate 或进入硬件验证。
