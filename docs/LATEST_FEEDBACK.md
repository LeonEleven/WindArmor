# WindArmor 当前开发交接

> **INTERNAL DEVELOPMENT HANDOFF — MUTABLE。** 本文件只记录当前任务状态和下一步，
> 不是普通用户操作文档、长期接口契约或 release evidence source of truth。历史发布事实
> 必须引用对应的版本化 release/verification 文档。

## 当前任务

- 任务：`DOC-2 — README/docs consolidation + verification archive + source-of-truth cleanup`
- 日期：2026-08-24
- task-start branch：`master`
- task-start HEAD：`b01b23f72f523bf60c4b4cabcaa2c180b16cca01`
- 当前 stable release：v0.3.2
- 当前开发目标：v0.4.0（未发布）
- Gate B / C / D：**COMPLETE / COMPLETE / COMPLETE**
- hardware / functional verification：**COMPLETE**
- release readiness：**PENDING**

## DOC-2 结果

DOC-2 已完成文档层面的三项目标：

1. 根 `README.md` 从 847 行压缩到 292 行，成为项目入口和正常操作主文档；
2. 新建版本化
   [`verification/v0.4.0/HARDWARE_VERIFICATION_RECORD.md`](verification/v0.4.0/HARDWARE_VERIFICATION_RECORD.md)，
   固化 v0.4.0 最终硬件/功能验证结论；
3. 收敛长期文档、历史计划、包 README 和 mutable handoff 的职责，减少重复正文和
   可变来源依赖。

本轮没有改变 Gate 判定，没有把 operator evidence 升级成 recorder evidence，也没有把
软件测试描述为真实硬件验证。v0.4.0 仍未发布。

## README 最终结构

根 README 现在只保留长期入口内容：

- 项目概览与当前版本；
- 硬件安全边界；
- 系统要求、构建与正常启动；
- motor MANUAL/HOME/LEGACY AUTO；
- fan MANUAL/LEGACY AUTO；
- E-stop、显式恢复和安全关机；
- 算法开发阅读顺序与 software-only demo；
- 默认纯软件 CI、新人隔离测试；
- 文档索引和版本化发布/验证历史。

Gate session、invalidated attempt、recorder timing、commit-level handoff、长篇架构内部原理
和 API 字段解释不再由 README 承载。

## 文档 source-of-truth map

| 内容 | 主要来源 |
| --- | --- |
| 项目入口与正常操作 | `README.md` |
| agent/project 工作流与硬件授权规则 | `AGENTS.md` |
| 新算法开发教程 | `docs/ALGORITHM_DEVELOPER_GUIDE.md` |
| 算法侧接口 | `docs/FLIGHT_CONTROL_API.md` |
| Runtime / authority / safety 架构 | `docs/FLIGHT_CONTROL_ARCHITECTURE.md` |
| 当前硬件、机械、坐标和接线 | `docs/HARDWARE_REFERENCE.md` |
| v0.4.0 最终验证结果 | `docs/verification/v0.4.0/HARDWARE_VERIFICATION_RECORD.md` |
| v0.4.0 完整执行过程与历史 | `docs/V0.4.0_HARDWARE_VERIFICATION_PLAN.md` |
| 当前内部任务交接 | `docs/LATEST_FEEDBACK.md` |

## Verification archive

新记录保留：

- Gate B 的 B0/B1/B2 最终判定和硬件边界；
- Gate C 的 C1、C2、C3、C4a、C4b authoritative session；
- C4b `2.021444233 s` procedural timing PASS；
- C1/C2/C3/C4a 重要 NOT VERIFIED、PREFLIGHT ABORT 和 invalidated attempt；
- 验证暴露的 production fixes；
- continuous recorder、helper timing、operator observation、software CI 的证据分级；
- RIGHT ESC 断电、C4b 未观察到明显风扇旋转、Gate D operator-only 项等限制；
- `Cannot shutdown a ROS adapter that is not running` 的 non-blocking 分类；
- hardware/functional verification COMPLETE 不自动授权 tag/release 或未来硬件操作。

verification plan 原有的 1826 行执行正文完整保留；加入状态 banner 和最终角色收口后为
1834 行，并在顶部标为 `STATUS: COMPLETED / HISTORICAL RELEASE-SPECIFIC EXECUTION PLAN`。
它是 execution provenance，不是当前 runbook 或最终结论的首选引用。

## Package 文档收敛

仓库实际跟踪的 package README 只有 `src/imu_cybergear_ros2/README.md`。它从 549 行
压缩到 250 行，继续保留包专属的：

- 节点、后端、launch 和键盘接口；
- target/初始化、反馈保护、transport 恢复和配置契约；
- ROS topic/service 摘要；
- 包级安全边界与测试入口。

整机启动、风扇操作、完整 wiring、Gate 状态和发布证据改为链接项目级权威文档。

包内三个早期指南没有删除，分别压缩为 18–22 行的 `LEGACY / HISTORICAL` 入口：

- `docs/IMU_CyberGear_Guide.md`；
- `docs/环境搭建到调试运行手册.md`；
- `docs/项目总览与功能清单.md`（明确 v0.2 历史）。

它们保留文件名、历史沿革和外部引用兼容性，不再复制可执行硬件命令。

## 其它长期/历史文档变化

- API、Architecture 和 Hardware Reference 的最终验证链接改指向版本化 record；
- Hardware Reference 保留 GPIO13 冲突诊断和 GPIO12/26 当前映射，移除重复的 B2 session
  叙事，改为链接 record；
- v0.3.2 release notes 不再把 mutable `LATEST_FEEDBACK.md` 当作详细发布证据；
- DOC-1 audit 增加 completed snapshot banner，避免审计时点的建议被当作 DOC-2 后现状；
- v0.3.2 RC checklist 继续保持 `HISTORICAL / NOT CURRENT HARDWARE INSTRUCTIONS`，历史值
  未改写。

## 验证

已执行的纯文档检查：

- `git diff --check`：PASS；
- stale-state 搜索：当前长期文档未发现 Gate C IN PROGRESS、Gate D NOT AUTHORIZED、
  hardware not verified、尚未实机验证或 v0.4.0 released 的冲突陈述；搜索模板本身只在
  Git 忽略的 `docs/NEXT_COMMAND.md` 中命中；
- GPIO13/GPIO26 检查：当前 mapping 由 Hardware Reference 主导；其它出现位置为简要
  安全摘要、版本化证据或明确历史文档；
- relative Markdown link check：检查 68 个相对文件链接，missing 0；
- README 和 verification record 链接：PASS。

没有运行 full CI，因为本轮只修改 Markdown，未修改生产代码或测试。没有启动 ROS、
没有访问 CAN/GPIO/PWM/串口，也没有给 actuator 通电。

## 变更边界

- production Python changed：**NO**
- tests changed：**NO**
- scripts changed：**NO**
- configs/launch/interfaces/algorithms changed：**NO**
- hardware executed or affected：**NO**
- branch created/switched：**NO**
- commit/push/tag/release：**NO**

## 下一任务

建议下一步为：

`DOC-3 — comments/docstrings cleanup + final documentation consistency`

DOC-3 应以当前 source-of-truth map 为边界，清理 production comments/docstrings 中的历史
任务措辞和重复架构说明，并执行最终文档一致性检查；除非另有明确授权，不应改变生产
行为或执行真实硬件。
