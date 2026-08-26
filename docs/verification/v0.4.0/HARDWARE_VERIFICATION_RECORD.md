# WindArmor v0.4.0 硬件与功能验证记录

> **版本化验证记录。** 本文是 v0.4.0 发布候选当前最终硬件与功能验证结论的
> 长期来源。它记录已经完成的验证，不是新的带电授权、现场 runbook 或操作命令。
> 任何后续实机操作仍须遵守仓库根目录 `AGENTS.md` 的硬件安全规则和逐场景授权门槛。

## 1. 文档状态

| 项目 | 结论 |
| --- | --- |
| 记录版本 | v0.4.0 |
| 验证范围 | Gate B、Gate C、Gate D |
| 硬件/功能验证 | **COMPLETE** |
| Gate B | **COMPLETE** |
| Gate C | **COMPLETE** |
| Gate D | **FUNCTIONAL REGRESSION PASS / COMPLETE** |
| v0.4.0 发布状态 | **尚未发布；发布准备状态仍待后续收口** |
| 当前稳定版本 | v0.3.2 |

完整逐次执行过程、现场命令、失败尝试和修复推导保留在
[v0.4.0 硬件验证执行计划](../../V0.4.0_HARDWARE_VERIFICATION_PLAN.md) 中。
本文只固化最终判定及其必要证据边界。

## 2. 验证范围与硬件边界

本轮验证覆盖：

- 4 个 CyberGear 微电机的受限保持、单电机小角度动作、失权和急停行为；
- 左侧涵道风扇的受限低 PWM 动作、失权和急停行为；
- Runtime 进程停止、优雅退出/重启、motor lifecycle deactivate、全局
  `/e_stop` 等故障注入；
- v0.3.2 既有操作路径在 v0.4.0 安全机制下的功能回归确认。

固定硬件映射为：

| 名称 | CAN ID / GPIO | 说明 |
| --- | --- | --- |
| `left_lift` | CAN ID 4 | 左升降电机 |
| `left_pitch` | CAN ID 3 | 左俯仰电机 |
| `right_pitch` | CAN ID 2 | 右俯仰电机 |
| `right_lift` | CAN ID 1 | 右升降电机 |
| LEFT fan | GPIO12，物理引脚 32 | 本轮带电风扇 |
| RIGHT fan | GPIO26，物理引脚 37 | Flight 验证期间 ESC 保持断电 |
| CAN HAT INT_1 | GPIO13 | 保留给 Waveshare 2-CH CAN HAT+ |

机械、接线、方向和限制的当前权威来源是
[硬件参考](../../HARDWARE_REFERENCE.md)。

## 3. Gate B：基础硬件能力

### 3.1 最终结论

Gate B 为 **COMPLETE**。

| 项目 | 结果 | 结论摘要 |
| --- | --- | --- |
| A0/A1 | PASS | 基础环境和映射检查通过 |
| A2 | 不适用 | 当前硬件不支持被动零发送观察；不是本版本发布要求 |
| feedback baseline | PASS | 四电机反馈基线可用 |
| B0 | PASS | 冷启动以测得位置建立保持目标，不隐式归零 |
| B1 | PASS | `left_pitch` 受限 `+0.05 rad`，其余三电机保持基线，风扇为 0/0 |
| B2 | PASS | LEFT fan `0.05`、RIGHT fan `0.0`，电机保持基线 |

B1 的现场观察为 `left_pitch` 从捕获基线执行小幅正向动作；该观察不被表述为
肉眼精确确认 `+0.05 rad`。B1 当时遗留的“失权停止小于 3 秒”程序性证据，后来由
Gate C4b 的 `2.021444233 s` 结果闭合。

B2 中 LEFT 风扇有低速响应并按预期停止；记录器显示 LEFT PWM 上限约 1210、
RIGHT 为 800。RIGHT ESC 在该场景中保持断电，因此 RIGHT 侧只验证了软件命令和
PWM 停止路径，没有形成带电旋转证据。

当前历史执行计划的 B1/B2 最终摘要没有给出可作为权威引用的 session ID；本文不
推测或补造标识。相关事实以执行计划中的原始摘要和后续 Gate C 证据为准。

## 4. Gate C：故障注入与安全闭环

Gate C 为 **COMPLETE**。以下 session 是各场景最终有效证据：

| Gate | 最终 session | 故障/场景 | 结果 |
| --- | --- | --- | --- |
| C1 | `gate-evidence-20260820T024541.024256Z-924522` | IMU 数据过期 | PASS |
| C2 | `gate-evidence-20260820T070959.631365Z-1037382` | Runtime `SIGSTOP` / lease 失效 | PASS |
| C3 | `gate-evidence-20260821T062508.750044Z-1360504` | Runtime 优雅退出与重启隔离 | PASS |
| C4a | `gate-evidence-20260824T013006.286027Z-1631895` | motor lifecycle deactivate | PASS |
| C4b | `gate-evidence-20260824T030542.834602Z-1754254` | 全局 `/e_stop` / watchdog | PASS |

### 4.1 C1 — IMU 数据过期

- 受限目标：`left_pitch` 为捕获基线 `+0.05 rad`，其余三电机保持基线；
  LEFT fan `0.05`，RIGHT fan `0.0`。
- 供电边界：四电机和 LEFT ESC 参与；RIGHT ESC 断电。
- 操作者观察到 LEFT 风扇低速旋转并停止；电机动作只记录为小幅正向动作，不能把
  软件反馈值改写成肉眼精确角度。
- IMU 数据过期后控制权按预期撤销，电机和风扇回到安全状态。
- 最终结论：**PASS**。

### 4.2 C2 — Runtime `SIGSTOP`

- 受限目标和供电边界与 C1 相同。
- 连续记录器记录命令序号 0–130，共 131 条。
- Runtime 停止后，以最后 command ROS stamp 为共同基准，motor owner 在
  `0.260380983 s` 时变为 `none`，fan owner 在 `0.293756485 s` 时失效。
- 上述 helper/recorder 差值是可重复的观察值，不单独定义新的实时 SLA。
- 最终结论：**PASS**。

### 4.3 C3 — 优雅退出与重启隔离

- 连续记录器记录旧实例命令序号 0–148，共 149 条。
- 旧 Runtime epoch 为 `254107543912471`、generation 1，并以退出码 0 正常结束。
- 新 Runtime epoch 为 `254214835192101`；新实例启动后保持 DRY_RUN，未接收旧实例
  命令，证明旧命令没有跨 epoch 继承。
- 操作者观察到 LEFT 风扇低速旋转并在故障后停止。
- 最终结论：**PASS**。

### 4.4 C4a — 电机生命周期停用

- 连续记录器记录命令序号 0–149，共 150 条；Runtime epoch 为
  `495604390791197`。
- motor controller 被 deactivate 后，`node_active=false`，Runtime 权限闭锁，
  故障路径 fail closed。
- 最终 authoritative reason 为 `fan_ownership_lost`，不是 motor safety reason；
  这是最终记录中的实际分类，不应被改写。
- 操作者观察到 LEFT 风扇低速旋转并在故障后停止。该场景稍后触发的 E-stop 只用于
  安全收尾，不是 C4a 的故障触发源。
- 最终结论：**PASS**。

### 4.5 C4b — 全局 E-stop / 看门狗

- 连续记录器记录命令序号 0–99，共 100 条；Runtime epoch 为
  `501315221790256`、generation 1。
- 受限目标为 `left_pitch` 基线 `+0.05 rad`、其余电机保持基线，LEFT fan `0.05`、
  RIGHT fan `0.0`。
- 从首个 legal ACTIVE detection 到有效 E-stop publish 的测得时间
  `ACTIVE_TO_PUBLISH_SEC` 为 **`2.021444233 s`**，满足本轮小于 3 秒的程序性验收要求。
- 记录器显示 LEFT PWM 曾达到 1200，累计 40 个非 800 样本，之后回到停止值。
- 操作者在 E-stop 前没有观察到明显风扇旋转。因此该项证明控制路径、PWM 输出记录和
  停止行为，但不把它表述为本场景的肉眼旋转确认。
- 最终 authoritative reason 为 `fan_ownership_lost`。
- 最终结论：**PASS**。

## 5. 无效或中止的尝试

以下历史不能作为最终 PASS 证据，但保留它们对于理解判定边界和生产修复是必要的：

| 场景/session | 分类 | 原因与处置 |
| --- | --- | --- |
| C1 `gate-evidence-20260819T085722.750971Z-709316` | NOT VERIFIED | ACTIVE 约 16.385 s，超过 10 s；launch 自动重新激活且供电顺序不符；还存在把软件角度当肉眼精确观察的问题。改为手动 IMU lifecycle 和预热 helper 后重测。 |
| C1 `gate-evidence-20260820T020508.332840Z-886665` | NOT VERIFIED | 风扇响应证据不足；未用于最终判定。 |
| C1 `gate-evidence-20260820T023505.409661Z-915048` | PREFLIGHT ABORT | 未进入 ACTIVE，不算带电尝试。 |
| C2 `gate-evidence-20260820T065345.667453Z-1018147` | PREFLIGHT ABORT | stdout buffering 使观测不可靠；未进入 prepare/ACTIVE。helper 改为无缓冲/显式 flush 后重试。 |
| C3 `gate-evidence-20260821T014852.009218Z-1200735` | PREFLIGHT ABORT | helper 进程采样竞态导致误判；未进入 prepare，不算带电尝试。 |
| C3 `gate-evidence-20260821T021811.696548Z-1220232` | NOT VERIFIED | 旧 Runtime `SIGINT` 后退出码 1，出现 ROS context invalid；硬件 fail-close 为正面证据，但不满足优雅退出标准。修复信号管理后重测。 |
| C4a `gate-evidence-20260821T075236.156225Z-1454804` | POWERED ATTEMPT INVALIDATED | ACTIVE 约 14.97 s，超过 10 s；预定 lifecycle 故障前 Runtime 已 stale，且 controller 被自动重新激活。限制自动激活只发生在启动转换后重测。 |

B1 的早期三次过程分别因未进入 prepare、缺少 ACTIVE 的 E-stop 证据，以及 fan
状态 allowlist 导致的 fail-closed 而停止/不具结论。原计划没有为这些过程列出可引用
session ID，因此本文只保留分类，不补造标识。

## 6. 验证过程中形成的生产修复

硬件验证不是只收集 PASS；无效尝试暴露的问题形成了以下生产修复，并在后续有效
session 中重新验证：

- 电机冷启动以实测位置为保持目标，显式 set-zero 才改变参考零点；
- fan passive startup 等待第一份有效状态，不以未观测状态冒充安全状态；
- fan E-stop 优先级高于普通状态更新；
- fan 安全状态允许 `FLIGHT_WAITING`，避免正常等待阶段被错误判成故障；
- Runtime 采用受控的 `SIGINT`/`SIGTERM` 管理，修复提交为 `96a23a9`；
- lifecycle 自动激活只绑定启动阶段的预期转换，修复提交为 `daa51ee`。

stdout flush、无缓冲输出和进程采样竞态修正属于验证 helper/程序改进，不属于生产
控制逻辑修复。

## 7. 程序性时序

C4b 的预热 watchdog/recorder 测得 `ACTIVE_TO_PUBLISH_SEC=2.021444233`，满足本轮
`<3.0 s` 的 procedural requirement，因此同时闭合 B1 遗留的时序项。

C2 中 motor/fan ownership 的 `0.260380983 s` / `0.293756485 s` 变化和其它 helper
delta 仅为
对应 session 的 observation。除明确的 `<3.0 s` 验收项外，本记录不从这些值推导新的
硬实时保证、性能包线或通用 SLA。

## 8. Gate D：v0.3.2 功能回归

Gate D 为 **FUNCTIONAL REGRESSION PASS / COMPLETE**。

Gate D 的判定由三类证据组成：

1. v0.3.2 历史操作者功能验证；
2. 用户对当前功能行为的确认；
3. Gate C 对 v0.4.0 新增失权、重启隔离和 E-stop 安全路径的实机交叉验证。

本 Gate 没有增加新的带电会话，也没有为 HOME、E-stop 恢复或显式重新取得控制权生成新的
连续记录器证据。相关矩阵结论为 PASS，但证据等级必须
保持为“历史操作者验证/用户确认 + 当前安全路径交叉验证”，不能升级描述为新的
记录器实机验证。

默认 takeover 仍为 false；既有 LEGACY AUTO 使用路径保持兼容。v0.3.2 的历史发布
边界见 [v0.3.2 RC 硬件检查表](../../V0.3.2_RC_HARDWARE_CHECKLIST.md) 和
[v0.3.2 发布说明](../../RELEASE_NOTES_v0.3.2.md)。

## 9. 证据分类与可接受表述

| 证据 | 能证明什么 | 不能证明什么 |
| --- | --- | --- |
| 连续记录器 | ROS 瞬态历史、命令、控制归属、状态和 PWM 样本 | 操作者是否看见物理运动；未记录的总线/机械事实 |
| 时序辅助工具 | 预定义事件之间的时序和进程状态 | 新的通用实时 SLA；物理效果 |
| 操作者观察 | 现场可见/可听的低速运动、停止和异常 | 软件内部精确角度、精确 PWM 或精确毫秒时间 |
| 软件 CI / fake / mock | 纯软件逻辑、接口、回归和 fail-close 行为 | 真实 CAN、真实串口、GPIO、电调或机械验证 |

软件反馈约为 `+0.05 rad` 只表示测量/控制证据；除非操作者明确报告，否则不得写成
“肉眼精确确认 +0.05 rad”。同样，记录到非 800 PWM 不自动等价于肉眼确认风扇旋转。

## 10. 非阻塞观察

日志中出现过：

```text
Cannot shutdown a ROS adapter that is not running
```

该现象发生在 fail-close 已完成、动力已关闭且子进程已清理之后，分类为
**LOW-PRIORITY / NON-GATE / NON-RELEASE-BLOCKING**。它没有改变 Gate C/D 判定，
也不应被隐去或升级成已经完成修复。

## 11. 已知限制

- RIGHT ESC 在 B2 和 C1–C4 Flight 场景中保持断电；RIGHT 侧仅有命令/PWM 停止
  证据，没有带电物理旋转验证。
- C4b 在 E-stop 前没有观察到明显风扇旋转；该场景的正面证据是控制路径、记录器
  PWM 和停止结果。
- Gate D 的 HOME、E-stop 恢复和显式重新取得控制权等条目含历史操作者/用户确认，
  不是新建连续记录器会话。
- 本轮没有验证性能、RPM、推力、全包线飞行能力或新的硬实时 SLA。
- 本记录不代表 v0.4.0 已发布，也不改变当前稳定版本仍为 v0.3.2 的事实。

## 12. 最终处置

基于 Gate B、C、D 的最终有效证据，v0.4.0 的硬件与功能验证判定为
**COMPLETE**。已知限制均已显式保留，没有仍然阻塞该验证结论的 open Gate。

发布仍是独立流程：需要完成文档整理、发布检查、版本和变更记录确认后，才能改变
“尚未发布”的状态。本文不会随 `docs/LATEST_FEEDBACK.md` 的日常交接更新而重写；若
未来发现影响 v0.4.0 结论的新事实，应以可审查的版本化修订明确记录原因和证据。
