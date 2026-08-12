# NEXT_COMMAND

## Task

v0.4.0 Task 5 — Repository Cleanup & Algorithm Developer Handoff

## Objective

在 v0.4.0 Task 4.1 已完成、软件飞控主线具备 Flight API、Structured State、
authority、owner handoff 和 actuator adapter 之后，进行一次**不改变控制行为**的
仓库整理与多人协作交接。

本任务目标：

1. 清理过期、重复或不再适合作为权威来源的文档；
2. 将 `FIRST_COMMAND.md` 中仍然唯一有价值的硬件/机械/坐标信息迁移到正式长期文档；
3. 删除已经过期的 `MANUAL_VERIFICATION.md`，但不丢失长期安全规则；
4. 更新 `AGENTS.md` 的稳定版本、权威来源、五包 CI 和工作流规则；
5. 精简 README 中与正式 Flight 架构/API 重复的实现细节；
6. 把 Flight API 整理成另一名算法开发成员可以快速上手的交接入口；
7. 全仓库审计 stale version、stale TODO/comment、未使用文件/config/code 和重复内容；
8. 清理源代码、注释和正式文档中不必要的生成工具/实现助手身份措辞；
9. 不改变 motor / fan / IMU / Flight Runtime 的行为、接口和安全语义；
10. 完成后重新运行完整无硬件软件 CI。

本任务不是 hardware verification，也不是 v0.4.0 RC。

---

## Baseline

当前开发基线：

```text
a1e4d2c
加固飞控交接回滚与租约机制
```

当前软件状态：

- 稳定发布仍为 `v0.3.2`；
- 当前开发目标为 `v0.4.0 Flight Control Integration Foundation`；
- Flight API v1 已建立；
- Structured State / DRY_RUN Runtime 已建立；
- authoritative safety readback 已建立；
- authority / arming / handoff contract 已建立；
- motor/fan actuator adapter 已完成软件集成；
- rollback / handoff lease 已完成软件加固；
- `flight_takeover_enabled=false` 默认保持；
- 尚未执行真实 Flight takeover 硬件验证；
- Task 4.1 软件反馈未发现进入 hardware verification planning 前的软件 blocker。

当前已知文档问题：

- `AGENTS.md` 仍写 `v0.3.1` 是当前稳定发布基线；
- `AGENTS.md` 仍把 `docs/FIRST_COMMAND.md` 列为权威来源；
- `docs/FIRST_COMMAND.md` 是项目最早期整合任务背景，但仍包含 IMU 安装方向、
  motor CAN ID 与机械位置等需要保留的信息；
- `docs/MANUAL_VERIFICATION.md` 声称只保存“最新人工验证”，但内容仍针对
  v0.3.0 后的统一速度改动，已经不再是当前最新验证文档；
- README 仍链接 `docs/MANUAL_VERIFICATION.md`；
- Flight 架构/API 已成为长期正式文档，README 中存在较多重复实现说明。

---

## Required Reading

执行前必须阅读：

1. `AGENTS.md`
2. `README.md`
3. `docs/FLIGHT_CONTROL_ARCHITECTURE.md`
4. `docs/FLIGHT_CONTROL_API.md`
5. `docs/FIRST_COMMAND.md`
6. `docs/MANUAL_VERIFICATION.md`
7. `docs/RELEASE_NOTES_v0.3.2.md`
8. `docs/V0.3.2_RC_HARDWARE_CHECKLIST.md`
9. `docs/LATEST_FEEDBACK.md`
10. 当前 `docs/NEXT_COMMAND.md`

还必须检查：

- 全部 `package.xml`
- `setup.py` / `setup.cfg`
- `CMakeLists.txt`
- launch files
- YAML config
- `.github/workflows`
- `scripts/ci_software.sh`
- `scripts/check_ci_safety.py`
- ROS entry points
- tests

如果当前 HEAD、分支或用户已有修改与以上描述不同：

- 不覆盖用户修改；
- 不 reset / checkout / clean；
- 先报告差异；
- 以 `AGENTS.md` 为最高安全与 Git 规则。

---

## Safety and Git Constraints

本任务默认：

- 不执行真实硬件操作；
- 不启动任何可能访问真实 IMU/CAN/GPIO/PWM 的节点或 launch；
- 不访问 `/dev/*`；
- 不配置 SocketCAN；
- 不使用 `sudo` 做硬件配置；
- 不改变任何硬件参数；
- 不授权 commit；
- 不授权 push；
- 不授权 tag；
- 不创建、移动、删除或重建稳定 tag。

不得改变：

- ERROR 不自动恢复；
- transport reconnect 只恢复通信；
- MANUAL / AUTO / HOME 不自动恢复；
- old target 不重发；
- E-STOP；
- watchdog；
- soft limit；
- command write consistency；
- feedback/temperature safety；
- motor/fan ownership；
- authority epoch/generation；
- FlightCommandEnvelope；
- handoff / active command leases；
- `motor_feedback_timeout_sec=0.0`；
- `flight_takeover_enabled=false` 默认；
- fan normalized command 不是 thrust；
- torque 不得推导 `current_a`。

本任务应以“文档/结构清理”为主。
若某项 cleanup 需要改变控制逻辑或 public ROS contract，停止并报告，不在本任务执行。

---

# Deliverable 1 — Create `docs/HARDWARE_REFERENCE.md`

新增长期文档：

```text
docs/HARDWARE_REFERENCE.md
```

它用于承接 `FIRST_COMMAND.md` 中仍然有效、但不应继续埋在历史启动任务里的硬件背景。

至少整理：

## Platform

- Raspberry Pi 5；
- Ubuntu 24.04；
- ROS 2 Jazzy；
- Waveshare 2-CH CAN HAT+；
- current CAN interface `can10`；
- 4 个 CyberGear；
- Hiwonder IMU；
- 2 个涵道风扇。

不要把 patch-level OS 版本写成长期硬件契约，除非仓库当前确有依赖。

## Motor physical mapping

从历史项目背景迁移机械映射：

```text
CAN ID 1 -> 机器人右臂左右/侧向肩部轴
CAN ID 2 -> 机器人右臂前后肩部轴
CAN ID 3 -> 机器人左臂前后肩部轴
CAN ID 4 -> 机器人左臂左右/侧向肩部轴
```

请结合当前 config / README / tests 核对措辞，不要凭历史文档单独推断新的机械命名。

同时记录当前 protected config：

```text
motor_ids
motor_signs
motor_limits_min
motor_limits_max
```

明确区分：

- 物理机械映射；
- config list ordering；
- software sign；
- soft limit。

不得把 CAN ID 当作 Flight algorithm 的公开逻辑 key。

## IMU mounting/frame

迁移：

```text
X+ -> 机器人正面
Y+ -> 机器人左侧/左臂方向
Z+ -> 垂直向上
```

如果当前代码/README 对 frame 有更精确的定义，以当前代码/正式契约为准。

明确：

- 这是硬件安装/坐标契约；
- `relative_roll/pitch` 的算法语义继续以 Flight API 为准；
- 不新增未经验证的 yaw reference。

## Fan wiring

记录当前仓库配置：

```text
left fan  -> GPIO12 / physical pin 32
right fan -> GPIO13 / physical pin 33
GND       -> physical pin 34 or other GND
```

必须保留当前事实边界：

- GPIO12 来自原单风扇已验证连接；
- GPIO13 是当前第二路默认配置；
- 若仓库当前文档仍标记 GPIO13 需首次带电前物理确认，不得把它改写成“已经实机确认”。

## Measurement limitations

明确：

- 没有经过验证的 `current_a`；
- 不能从 torque 推导 current；
- fan 没有真实 RPM readback；
- normalized fan command 不是 thrust fraction；
- `flight_takeover_enabled=false` 默认；
- Task 4/4.1 Flight takeover 尚未完成真实硬件验证。

文档只记录长期硬件事实/边界，不写一次性 Task 流程。

---

# Deliverable 2 — Remove `docs/FIRST_COMMAND.md`

只有在 Deliverable 1 完成并逐项确认唯一有价值的信息已经迁移后，
删除：

```text
docs/FIRST_COMMAND.md
```

删除前必须用仓库搜索确认没有仍然依赖它的：

- README link；
- AGENTS authority reference；
- docs link；
- test；
- script；
- CI；
- launch/config。

不要为了保留历史聊天/任务背景继续把它当产品文档。

Git history 已经保存历史内容，不需要另建 archive copy。

---

# Deliverable 3 — Remove `docs/MANUAL_VERIFICATION.md`

审计 `docs/MANUAL_VERIFICATION.md` 的长期内容。

已知长期有效内容主要包括：

- 带电测试必须先获得明确授权；
- 测试前记录设备/限制/急停/停止条件；
- pure/mock test 不等于真实硬件验证。

这些规则应由：

```text
AGENTS.md
```

作为最高安全来源，而不是继续由一个“最新人工验证”历史任务文件承担。

在确认没有唯一且仍适用的信息丢失后，删除：

```text
docs/MANUAL_VERIFICATION.md
```

本任务**不要**创建新的 v0.4.0 hardware verification checklist。

真正的 v0.4.0 hardware verification protocol 留给后续 Task 6。

---

# Deliverable 4 — Preserve Historical Release Evidence

明确保留：

```text
docs/RELEASE_NOTES_v0.3.2.md
docs/V0.3.2_RC_HARDWARE_CHECKLIST.md
```

这些是 v0.3.2 历史发布记录/验证证据，不属于过期工作流文档。

不得因 Task 5 cleanup 修改其历史结论，
除非仅修复明显 broken link / typo 且不改变历史含义。

不得修改：

- v0.3.0 tag；
- v0.3.1 tag；
- v0.3.2 tag。

---

# Deliverable 5 — Preserve Workflow Documents

保留：

```text
docs/NEXT_COMMAND.md
docs/LATEST_FEEDBACK.md
```

并把其语义正式写入 `AGENTS.md`：

```text
docs/NEXT_COMMAND.md
    只保存当前最新任务

docs/LATEST_FEEDBACK.md
    只保存当前最新任务反馈
```

本任务执行期间：

- 不修改用户提供的当前 `docs/NEXT_COMMAND.md`；
- 最后只更新 `docs/LATEST_FEEDBACK.md`。

不要把长期架构重新塞入 NEXT_COMMAND/LATEST_FEEDBACK。

---

# Deliverable 6 — Update `AGENTS.md`

这是本任务最重要的文档修正之一。

## Stable baseline

将过期的：

```text
v0.3.1 是当前稳定发布基线
```

修正为：

```text
v0.3.2 是当前正式稳定发布基线
```

同时说明当前开发分支正在推进 v0.4.0，
但稳定 tag 仍以 v0.3.2 为准。

不要把当前未发布 HEAD 称为 stable release。

## Authoritative sources

移除 `FIRST_COMMAND.md`。

建议权威来源整理为：

1. `AGENTS.md` — 最高硬件安全与 Git/协作规则；
2. `README.md` — 当前用户安装、运行、公开接口与状态概览；
3. `docs/HARDWARE_REFERENCE.md` — 硬件布局、机械/坐标/接线契约；
4. `docs/FLIGHT_CONTROL_ARCHITECTURE.md` — Flight 长期架构 source of truth；
5. `docs/FLIGHT_CONTROL_API.md` — 算法开发 API source of truth；
6. `src/` + config/launch/tests — 实际行为最终依据；
7. release notes/checklist — 仅作为对应历史版本证据。

并明确 `NEXT_COMMAND/LATEST_FEEDBACK` 是工作流状态，而不是长期产品架构来源。

## Five-package software CI

AGENTS 当前默认 `colcon test --packages-select` 列表如果仍只有三个 package，
更新为当前五包：

```text
imu_cybergear_ros2
windarmor_fan_controller
windarmor_interfaces
windarmor_flight_control
windarmor_bringup
```

优先把：

```text
./scripts/ci_software.sh
```

说明为当前仓库完整无硬件软件 CI 的统一入口。

仍保留：

> 新增/修改测试后必须重新确认不会触碰真实硬件。

## Documentation wording

新增长期规则：

> 源代码注释、README、正式技术文档、测试说明和发布文档应描述工程设计、
> 行为、约束与验证结果，不记录生成工具、实现助手或模型身份作为实现来源。

该规则不得影响必要的第三方许可证、依赖名称或技术产品名称。

---

# Deliverable 7 — README Targeted Cleanup

不要大规模重写 README。

目标是：

- 保留用户真正需要的安装、硬件警告、运行、接口和 v0.3.2 稳定状态；
- 减少与 `FLIGHT_CONTROL_ARCHITECTURE.md` /
  `FLIGHT_CONTROL_API.md` 重复的大段 Task 1~4 内部实现叙述；
- 当前 Flight 状态用较短 summary + 正式文档链接表达；
- 保留 `flight_takeover_enabled=false` 和“尚未实机验证”的醒目边界；
- 删除对 `MANUAL_VERIFICATION.md` 的链接；
- hardware verification 尚未规划完成时，直接指向 `AGENTS.md` 的带电授权门槛，
  不虚构不存在的新 checklist；
- 添加 `HARDWARE_REFERENCE.md` 链接；
- 不删除仍然需要的 v0.3.2 操作说明和安全警告。

如果某段 README 与 architecture/API 内容完全重复，优先让长期详细说明只存在于正式文档，
README 保留摘要和入口。

---

# Deliverable 8 — Algorithm Developer Quick Start

不要再新增一个与 `FLIGHT_CONTROL_API.md` 重复的大型文档。

直接在：

```text
docs/FLIGHT_CONTROL_API.md
```

顶部或“算法入口”前增加一个简洁的 **Quick Start / Handoff** 小节。

目标：新算法成员只阅读这一小节即可知道从哪里开始。

至少说明：

1. 主要修改范围是 `windarmor_flight_control` 的 algorithm implementation 区域；
2. 不修改 hardware driver / runtime / authority / safety package，除非另行协作；
3. 实现 `FlightController.reset()` / `update(state, dt)`；
4. 输入只使用 `FlightState`；
5. 输出只返回 `FlightCommand`；
6. 不 import ROS/hardware libraries；
7. 使用 fake state 做普通 Python unit test；
8. normal command 必须完整，safe-stop 使用 `FlightCommand.safe_stop()`；
9. algorithm 不 arm、不 reset E-STOP/ERROR、不 set-zero；
10. 当前 takeover 默认关闭，实机验证不属于算法开发默认流程。

给出**当前仓库真实可运行**的最小离线测试命令，
执行端必须先检查 package/test 结构后再写，不凭想象编造。

---

# Deliverable 9 — Root README Algorithm Handoff Entry

README 增加一个简洁的“飞控算法开发”入口，内容只需：

```text
先读 FLIGHT_CONTROL_API.md
需要理解系统边界再读 FLIGHT_CONTROL_ARCHITECTURE.md
硬件映射读 HARDWARE_REFERENCE.md
```

再给出算法目录位置和无硬件 unit-test 入口。

不要把整份 Flight API 复制进 README。

---

# Deliverable 10 — Repository Documentation Inventory

对 tracked docs 做完整审计，并在最终反馈中分类：

```text
KEEP
MIGRATE
DELETE
REWRITE
```

至少包含当前 `docs/` 全部文件。

目标状态预期为：

```text
docs/
├── FLIGHT_CONTROL_API.md
├── FLIGHT_CONTROL_ARCHITECTURE.md
├── HARDWARE_REFERENCE.md
├── LATEST_FEEDBACK.md
├── NEXT_COMMAND.md
├── RELEASE_NOTES_v0.3.2.md
└── V0.3.2_RC_HARDWARE_CHECKLIST.md
```

如果执行端发现仍有合理原因保留 FIRST_COMMAND 或 MANUAL_VERIFICATION，
不要强行删除，但必须停止该删除项并在反馈中给出具体唯一信息/依赖证据。

---

# Deliverable 11 — Stale Version / Status Audit

对 tracked source/docs/config/test 做搜索。

区分：

## Historical references

例如：

```text
v0.3.0 changes
v0.3.1 release history
v0.3.2 release notes
```

这些不应因为“版本旧”而删除。

## Stale current-state claims

例如：

```text
v0.3.1 is current stable
Task 2 currently has no actuator path
Task 3 production can never...
```

如果与当前 HEAD 明显冲突，应修正。

不要机械替换版本字符串。

---

# Deliverable 12 — Stale TODO / Comment Audit

审计：

- TODO
- FIXME
- XXX
- obsolete task comments
- stale docstring
- comments that refer to old Task-number behavior
- comments that no longer match current Runtime capability

只修明显已过期的描述。

不要删除仍代表真实未完成工作的 TODO；
这类内容在反馈中列为 future work。

注释应描述当前工程行为，而不是某次临时任务历史。

---

# Deliverable 13 — Tool/Assistant Identity Wording Audit

对 tracked source、comments/docstrings、README、docs、tests、package metadata 做文本审计。

如果某段只是记录生成工具/实现助手身份或把工具身份当作代码来源，
改为工程化措辞或删除 provenance 描述。

不要：

- 修改 Git history；
- 修改第三方 license；
- 删除真实依赖/产品名称；
- 因普通单词中的短字符串造成误报。

最终反馈只需说明：

```text
found / cleaned / intentionally retained with reason
```

不要在新正式文档中继续列举具体工具名称作为反例。

---

# Deliverable 14 — File / Code / Config Redundancy Audit

这是**审计优先、删除保守**的任务。

对 tracked repository 检查：

- 未引用 Python module；
- 未使用 script；
- 未引用 launch；
- 未引用 YAML/config；
- package data 中遗留文件；
- 未使用 ROS entry point；
- 重复 helper；
- obsolete compatibility shim；
- dead test fixture；
- orphan docs/link。

## Before declaring something dead

必须检查：

- import / dynamic import；
- `setup.py` entry points；
- package data；
- `package.xml` / `CMakeLists.txt`；
- launch include；
- YAML path；
- CI script；
- shell script；
- tests；
- README/docs；
- ROS plugin/factory string；
- controller factory dynamic loading；
- public ROS compatibility contract。

## Allowed deletion

只有同时满足：

1. 确实无 runtime/build/test/docs/dynamic-loader 引用；
2. 不是 public ROS compatibility interface；
3. 不是 safety fallback；
4. 不是 release evidence；
5. 删除后五包 build + tests + CI 全通过；
6. 删除理由可在反馈中具体说明。

## Report-only candidates

以下只报告，不删除：

- 可能属于兼容接口；
- 动态加载难以证明未使用；
- 与 safety/recovery 有关；
- 删除会改变 public topic/service/parameter；
- 删除会减少故障注入覆盖；
- 需要用户做产品取舍。

不要为了“减少文件数量”做高风险重构。

---

# Deliverable 15 — Test Helper Deduplication

允许合并**明显完全重复、且不降低覆盖**的 test helper。

但：

- 不减少 safety scenario 数量；
- 不删除独立 fault-injection test；
- 不把 motor/fan/flight package 的测试强行放到同一个顶层 `test` Python package；
- 如果收益不明显，保持现状并在反馈中说明“不做”。

---

# Deliverable 16 — Broken Link / Reference Audit

检查：

- README markdown links；
- docs 相对链接；
- 删除 FIRST_COMMAND/MANUAL_VERIFICATION 后的残留引用；
- AGENTS links/path references；
- launch/config path examples；
- package names；
- current topic/service names。

所有删除文档的引用必须清零。

可以使用 `git grep` / `rg` 和轻量 link check，
但不要求联网验证外部第三方链接。

---

# Deliverable 17 — Package / Version Metadata Audit

检查五个 ROS package 的：

- package name；
- version；
- description；
- dependencies；
- maintainer metadata；
- setup entry points。

本任务主要做一致性审计。

不要为了“统一看起来更整齐”擅自把现有 subsystem package version 全部改成 0.4.0。

v0.4.0 RC 前会单独审核版本。

只有明显错误/过期 description 且不影响行为时才允许修正文案。

---

# Deliverable 18 — CI / AGENTS Consistency Audit

确认：

```text
AGENTS.md
README.md
scripts/ci_software.sh
.github/workflows/*
```

对纯软件 CI 的描述一致。

重点：

- 当前是五个 package；
- Hosted runner only；
- no self-hosted hardware CI；
- no `/dev`；
- no SocketCAN setup；
- no GPIO/PWM；
- no real hardware launch；
- `scripts/ci_software.sh` 是统一入口。

不得为了 cleanup 放宽 CI safety checker。

---

# Deliverable 19 — No Control Logic Changes

本任务原则上不应修改核心控制行为文件。

如果仅为删除明显 stale comment/docstring 可以修改；
除此之外不得改变逻辑。

若 redundancy audit 在 motor/fan/Flight 核心逻辑中发现候选 dead code，
默认只在反馈中记录，留给后续独立重构任务。

---

# Deliverable 20 — Preserve Flight API Compatibility

Task 5 不得破坏：

```text
FlightState
FlightCommand
FlightController
CommandAuthority
authority_epoch/generation
FlightCommandEnvelope
owner services
ownership readback
```

算法 quick-start 只能解释现有 API，不能为了文档更简单而改 API。

---

# Deliverable 21 — Software Verification

本任务仍只允许无硬件验证。

至少执行仓库当前统一入口：

```bash
source /opt/ros/jazzy/setup.bash
./scripts/ci_software.sh
```

并按当前仓库实际需要执行五包 build/test。

不得访问真实：

- `/dev/*`
- CAN
- USB-CAN
- CyberGear
- IMU serial
- GPIO
- PWM
- ESC
- fan

---

# Deliverable 22 — Cleanup Verification

最终反馈中记录用于确认 cleanup 的只读命令，例如：

```bash
git status --short --branch
git diff --check
git grep ...
rg ...
git ls-files ...
```

至少证明：

- no `FIRST_COMMAND.md` reference；
- no `MANUAL_VERIFICATION.md` reference；
- no stale “v0.3.1 current stable” claim；
- docs links 指向存在的 tracked files；
- deleted files 不再被 package/build/runtime 引用。

---

# Expected Result

Task 5 完成后：

1. `AGENTS.md` 正确声明 v0.3.2 为当前稳定发布；
2. `AGENTS.md` 权威来源不再依赖 FIRST_COMMAND；
3. `AGENTS.md` 正确覆盖五包 software CI；
4. `docs/HARDWARE_REFERENCE.md` 成为硬件布局/坐标长期文档；
5. `docs/FIRST_COMMAND.md` 删除；
6. `docs/MANUAL_VERIFICATION.md` 删除；
7. v0.3.2 Release Notes / RC checklist 保留；
8. NEXT_COMMAND / LATEST_FEEDBACK 工作流语义明确；
9. README 不再链接被删除文档；
10. README Flight 部分减少与 Architecture/API 的重复；
11. `FLIGHT_CONTROL_API.md` 有清晰算法开发 Quick Start；
12. 新算法成员能快速定位 algorithm 区域并离线测试；
13. 正式工程内容不记录无关实现工具/助手身份；
14. stale current-state wording 被修正；
15. dead/redundant file/code/config 完成保守审计；
16. 高风险或不确定 cleanup 只报告、不删除；
17. Flight API / ROS public interface / safety behavior 不变；
18. `flight_takeover_enabled=false` 默认不变；
19. 全软件 CI 通过；
20. 未执行任何真实硬件操作；
21. 仓库可以进入 Task 6 — v0.4.0 Hardware Verification Planning。

---

# Out of Scope

明确不做：

- Flight control logic change；
- algorithm/PID 实现；
- Flight API breaking change；
- owner/authority redesign；
- real hardware test；
- real Flight takeover；
- hardware timing measurement；
- IMU calibration；
- fan RPM/thrust characterization；
- current measurement research；
- `windarmor_bringup` 默认启用 Flight；
- v0.4.0 hardware checklist；
- v0.4.0 RC；
- version tag；
- release；
- GitHub Release；
- commit；
- push；
- tag。

---

# Stop Conditions

遇到以下任一情况必须停止对应 cleanup 项并报告：

- 删除文件需要破坏 public ROS interface；
- 删除代码可能属于 safety fallback；
- 无法证明 dynamic import / controller factory 未使用；
- 删除 config 需要改变 runtime default；
- 必须修改 motor/fan/Flight 控制逻辑；
- 必须弱化 AGENTS hardware gate；
- 必须访问真实硬件验证“是否没用”；
- FIRST_COMMAND 中发现仍有无法安全迁移但仍是唯一权威的信息；
- MANUAL_VERIFICATION 中发现 AGENTS/其他长期文档没有覆盖的当前必要安全规则；
- cleanup 开始扩展到 Task 6 hardware verification。

---

# Final Report

完成后只更新：

```text
docs/LATEST_FEEDBACK.md
```

至少包含：

## Scope

- 修改/新增/删除文件；
- docs 最终 inventory；
- README/AGENTS/API 变化；
- 是否修改任何 source/config/package metadata。

## Documentation Classification

逐项给出：

```text
KEEP
MIGRATE
DELETE
REWRITE
```

并说明 FIRST_COMMAND / MANUAL_VERIFICATION 的迁移与删除结果。

## Hardware Reference

说明：

- motor mechanical mapping；
- IMU frame；
- fan wiring；
- 哪些是 current config；
- 哪些仍需未来实机确认；
- 没有新增未经验证的物理量。

## Algorithm Handoff

说明：

- Quick Start 位置；
- algorithm 主要修改目录；
- offline test command；
- API 是否变化（预期：否）。

## Redundancy Audit

列出：

- 实际删除的 dead/redundant items；
- 保留的疑似候选及理由；
- report-only candidates；
- public compatibility/safety items 未删除说明。

## Wording Audit

说明：

- stale current-state claims；
- stale TODO/comment；
- implementation provenance wording；
- intentionally retained cases and reason。

## Safety Boundary

明确：

- 无控制逻辑变化；
- 无 public ROS breaking change；
- `flight_takeover_enabled=false` 不变；
- `motor_feedback_timeout_sec=0.0` 不变；
- 未执行真实硬件；
- 未改变 ERROR/E-STOP/reconnect/ownership/lease semantics。

## Tests

- exact commands；
- pass/fail；
- warnings/skipped；
- CI result；
- 是否存在 Task 6 前 blocker。

## Git 状态（反馈生成时）

- HEAD；
- branch；
- working tree；
- implementation/verification 阶段是否 commit；
- push/tag；
- remote 是否核验；
- v0.3.0 / v0.3.1 / v0.3.2 stable tags 是否保持。

本任务默认不授权 commit / push / tag。

工程文档继续使用工具无关措辞。
