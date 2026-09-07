# WindArmor 当前开发交接

> **INTERNAL DEVELOPMENT HANDOFF — MUTABLE。** 本文件只记录当前任务状态、关键决策和
> 下一步，不是普通用户操作文档、长期接口契约或 release evidence source of truth。历史
> 发布事实必须引用对应的版本化 release/verification 文档。

## 当前状态

- 日期：2026-09-07
- 当前任务：`v0.5.0-001 — Balance Recovery Algorithm R&D Roadmap`
- task-start baseline：`origin/develop` / `47f0bf96ac13210aadf8dfaf3ffe77f77b1fc25a`
- 当前任务分支：`docs/v0.5-balance-recovery-roadmap`
- 当前 stable release：**v0.4.0**
- previous stable / history：v0.3.2
- 下一版本研发目标：**v0.5.0 — Balance Recovery**
- 当前阶段：**Algorithm R&D planning / roadmap**
- collaboration model：**master + develop + short-lived task branches**
- `develop`：**已建立，当前下一版本集成主线**
- GitHub branch protection：**维护者已确认建立；精确配置以 GitHub 当前设置为准**
- PR #2 required Software CI：**PASS**
- 新的真实 actuator 验证：**未执行**
- v0.5.0 release：**未发布；当前仅为研发目标**

## 本任务

本任务建立长期维护的 [`ALGORITHM_ROADMAP.md`](ALGORITHM_ROADMAP.md)，不实现或选择具体
控制算法。路线图定义：

- ALG-001 至 ALG-008 的单一主要能力递进；
- M1 Basic Feedback、M2 Recovery Controller、M3 Full Balance Recovery；
- Fast Progression Track 与 Independent Learning / Validation Track 的异步推进规则；
- implementation lineage、独立 ALG Task Spec、qualification 和历史同级比较原则；
- 从纯函数、synthetic DRY_RUN 到 replay/dynamic benchmark、可信仿真和受限硬件验证的
  证据升级；
- 软件研发完成与真实 Balance Recovery 已验证之间不可混用的结论边界。

`DEVELOPMENT_WORKFLOW.md` 同步为 `develop` 已投入使用的当前事实，并记录 branch protection
的高层确认；精确保护规则仍以 GitHub 当前设置为准。README 只增加路线图入口，改善算法
研发文档的可发现性。

## 本任务验证

- `git diff --check`：**PASS**；
- Markdown 相对链接扫描：**34 files scanned、116 links checked、missing 0**；
- PR #2 首次创建后，`develop` branch protection 要求的 `software-ci` 保持
  **Expected / Waiting for status to be reported**，且没有对应 GitHub Actions run；
- 根因是当时的 GitHub Actions workflow 仅监听 `master`；当前 PR 增加最小 branch trigger
  对齐，使 Software CI 同时支持 `master` 和 `develop`；
- trigger 修复提交并推送后，GitHub Actions 已产生真实的 `WindArmor Software CI` run
  `34079155920`，required job/context `software-ci` 为 **PASS**，PR #2 required checks 为
  **PASS**；这确认了面向 `develop` 的 required Software CI 已能正常工作；
- 本地 full ROS 2 software CI：**未执行**；本次 bootstrap 只修改 workflow branch trigger 和
  Markdown，不改变 CI job/test 内容或 production behavior；
- 硬件验证：**未执行**；本任务不需要且未获任何新硬件运行授权。

## 历史证据保留

v0.4.0 的 Gate B/C/D、PASS/FAIL/NOT VERIFIED、有效与无效 session、接线映射、release
blocker、安全结论、证据等级和已知限制均已长期保存在：

- [v0.4.0 硬件与功能验证记录](verification/v0.4.0/HARDWARE_VERIFICATION_RECORD.md)；
- [v0.4.0 硬件验证历史执行计划](V0.4.0_HARDWARE_VERIFICATION_PLAN.md)；
- [v0.4.0 发布说明](RELEASE_NOTES_v0.4.0.md)。

本文件切换到 v0.5.0 当前状态不会删除或改变上述历史证据。v0.4.0 仍是当前正式稳定发布，
其 Gate B/C/D 和 hardware/functional verification 结论仍为 COMPLETE；这些历史结论不授权
任何新的硬件操作，也不能扩展为 v0.5.0 算法或真实 Balance Recovery 已验证。

## 变更与安全边界

- roadmap / governance / navigation documentation changed：**YES**
- GitHub Actions CI branch trigger changed：**YES**
- CI job/test contents changed：**NO**
- production behavior changed：**NO**
- hardware behavior changed：**NO**
- develop PR required `software-ci` verification：**PASS**
- algorithm / Runtime / hardware manager / driver changed：**NO**
- Flight API 或 ROS topic/service contract changed：**NO**
- motor/fan 参数或 CAN/GPIO/PWM 映射 changed：**NO**
- package version changed to v0.5.0：**NO**
- 真实 IMU、CAN、电机、风扇或 GPIO/PWM accessed：**NO**
- powered test：**NO**
- 当前任务分支已有已提交并推送至远端的 roadmap 变更；
- merge to `develop`：**尚未完成**；
- tag / release：**未创建**；
- PR 生命周期状态以 GitHub 当前状态为准。

## 下一推荐任务

建立独立、可 review 的：

```text
ALG-001 Task Spec
+
Algorithm Benchmark v1 contract
```

下一任务仍应从软件验证开始，固定基础姿态反馈的符号、输入、输出、安全行为、fixture、
容差、qualification 和 benchmark 元数据；不得自动实现后续 ALG 能力或进入真实硬件验证。
