# 最新反馈：Gate C / C4a powered attempt 失效与 software/preparation 重开

> 日期：2026-08-21
> 任务起点：`master` / `7b440ddcb7b81232138ac851b9188bc3cde74e84`
> 本轮性质：C4a invalidated attempt offline closure + lifecycle launch fix + retry preparation
> production launch changed：`YES`
> tests changed：`YES`
> local-only helper changed：`YES / NOT REPOSITORY ARTIFACT`
> real hardware executed：`NO`
> C3 结论：`HARDWARE PASS`
> Gate C：`IN PROGRESS / NOT COMPLETE`

## 正式状态

```text
Gate B: COMPLETE
Gate C / C1: HARDWARE PASS
Gate C / C2: HARDWARE PASS
Gate C / C3: HARDWARE PASS
Gate C / C4a: NOT VERIFIED / POWERED ATTEMPT INVALIDATED
Gate C / C4a: SOFTWARE/PREPARATION REOPENED
Gate C / C4a: RETRY NOT AUTHORIZED
Gate C / C4b: DESIGN/PREPARATION COMPLETE
Gate C / C4b: NOT AUTHORIZED / NOT EXECUTED
Gate C / C4: NOT COMPLETE
Gate C: IN PROGRESS / NOT COMPLETE
```

C3 继续保持 `HARDWARE PASS`，不需要重跑。本轮只进行 offline evidence review、repository
software/test/docs 修改和 local-only fake helper preparation；没有启动 Runtime、ROS node、
launch 或真实 helper，没有访问 CAN、GPIO、PWM、串口或硬件，也没有发送 lifecycle、prepare、
E-STOP、ownership 或 actuator command。

## C4a powered attempt classification

authoritative session：

```text
/home/h-goal/windarmor_evidence/
  gate-evidence-20260821T075236.156225Z-1454804
```

正式分类为 `C4a NOT VERIFIED / POWERED ATTEMPT INVALIDATED`，不是 actuator safety FAIL。
recorder manifest 为 `COMPLETED / SIGINT`，`abnormal_child=null`、
`cleanup_timed_out=false`，8/8 required topics 均有 samples。

### Blocker 1 — ACTIVE boundary overrun

```text
motor Flight ownership commit: 1787298933.545647640
Flight ownership revoke:       1787298948.513963905
ACTIVE ownership exposure:     about 14.97 s
approved absolute max ACTIVE:  10.0 s

Runtime required_inputs_stale inhibit: 1787298948.612308890
intended lifecycle deactivate start:   1787298950.757950629
```

intended deactivate 前 Runtime 已因 `required_inputs_stale` fail closed，所以该 attempt 无法证明
`motor lifecycle deactivate -> lower-level safety loss -> Runtime rollback` 的因果链。人工盯
`/flight_control/authority/status` 高速滚屏并估算 3 秒不再允许作为 C4a trigger timing。

### Blocker 2 — production launch automatic re-activate

```text
deactivate start:  1787298950.757950629
deactivate done:   1787298950.760079915
reactivate start:  1787298950.773456363
reactivate done:   1787298950.782525330
final lifecycle:   active [3]
motor node_active: true
```

根因是 controller startup `OnStateTransition` 只有 `goal_state="inactive"`，会同时匹配首次
`configuring -> inactive` 和显式 `deactivating -> inactive`。IMU handler 具有同一 latent
issue。本轮把两者都限定为 `start_state="configuring" / goal_state="inactive"`；正常
cold-start auto activation 保持不变，manual deactivate 后保持 inactive，
`imu_auto_activate=false` 语义不变。

### Positive evidence retained, but not causal C4a evidence

- Runtime 因 `required_inputs_stale` fail closed；
- motor/fan owner 均为 NONE；
- fan PWM 最终 `[800,800]`；
- operator 确认 physical motor/fan stop；
- 无异常声音、振动、气味或温升；
- final LEFT ESC 与 motor bus physically OFF；
- Runtime exit 0。

这些证据只证明该次 session 安全终止，不是 intended lifecycle-deactivate causal evidence，
不能升级为 C4a PASS。

## C4a retry preparation

C4a 当前为 `SOFTWARE/PREPARATION REOPENED / RETRY NOT AUTHORIZED`。已在 local-only
`~/windarmor_test_sessions/c4a/` 准备 pre-armed trigger、runbook 和 fake self-test；它们不属于
repository artifact。helper 在 prepare 前创建 authority subscriber 和 motor lifecycle
change-state client，输出 READY/ARMED，只在 continuous legal ACTIVE
（ACTIVE、FLIGHT_CONTROL、actuation allowed、motor/fan committed、owner tokens match）后约
3 秒请求一次 `TRANSITION_DEACTIVATE`。contract 提前丢失或 status 不新鲜即 latch abort，不
发送迟到 deactivate；absolute ACTIVE max 保持 10 秒。它不 activate/reactivate、prepare、
reset、publish E-STOP/actuator command、retry 或访问硬件。continuous recorder 仍是
authoritative evidence。

C4b 继续为 `DESIGN/PREPARATION COMPLETE / NOT AUTHORIZED / NOT EXECUTED`。C4a 尚未取得
有效 PASS，禁止进入 C4b。

## Pure software validation

- targeted launch regression：`7 passed`；
- local C4a fake ROS/messages/clock/service self-test：`6 passed`；
- `./scripts/ci_software.sh`：PASS；motor `431 passed`，fan `159 passed`，Flight/interfaces
  `304 passed`，最终 colcon `925 tests, 0 errors, 0 failures, 0 skipped`；
- `git diff --check`：PASS。

以上均为纯软件证据，不是 C4a hardware PASS，也不授权 retry。

## Final authoritative C3 session

最终 authoritative continuous-recorder session：

```text
/home/h-goal/windarmor_evidence/
  gate-evidence-20260821T062508.750044Z-1360504
```

recorder manifest：

```text
status: COMPLETED
stop_reason: SIGINT
abnormal_child: null
cleanup_timed_out: false
required topics: 8/8 SAMPLES CAPTURED
recorder child exit: EXPECTED RECORDER CLEANUP EXIT
```

recorder child 的 SIGINT exit code 属于 recorder 自身的预期统一清理，不是被测 Runtime 的
exit status，也不构成 topic evidence 缺口。瞬态人工 `topic echo` 只作现场辅助；正式历史以
continuous recorder 为准。

## OLD Runtime graceful stop

OLD Runtime：

```text
PID: 1360007
authority_epoch: 254107543912471
authority_generation: 1

ACTIVE_DETECTED_MONOTONIC=254150.764401440
SIGINT_SENT_MONOTONIC=254153.769796950
ACTIVE_TO_SIGINT_SEC=3.005395510

OLD_RUNTIME_EXIT_CONFIRMED_MONOTONIC=254154.544579109
LAST_OLD_COMMAND_RECEIVED_MONOTONIC=254153.750120267
MOTOR_OWNER_NONE_MONOTONIC=254153.826780042
FAN_OWNER_NONE_MONOTONIC=254153.843605997
FAN_PWM_STOP_MONOTONIC=254153.912634769

C3_STOP_RESULT=PASS
C3_STOP_OBSERVER_EXIT_STATUS=0
OLD_RUNTIME_EXIT_STATUS=0
```

### Continuous ROS evidence

- 149 条 executable `FlightCommandEnvelope` 全部属于
  `authority_epoch=254107543912471 / generation=1`，sequence 为 `0–148`；
- payload 始终保持批准的 bounded candidate：`left_pitch = captured baseline +0.05 rad`，
  其他三轴 baseline hold，LEFT/RIGHT fan `0.05/0.0`；
- 所有 command 均为 `request_safe_stop=false`。C3 shutdown contract 不依赖 final
  safe-stop envelope，因此这不是缺陷；
- exact-PID SIGINT 后 command stream 停止，没有新的 executable command；
- motor owner 与 fan owner 均从 `FLIGHT_CONTROL` 回到 `NONE`，authority token 清零；
- LEFT PWM 为 `800 -> 10 us ramp -> 1210 -> 800`，`MAX_LEFT=1210`；
- RIGHT 始终为 800，`MAX_RIGHT=800`，最终 PWM 为 `[800,800]`；
- OLD log 没有 traceback、`publisher's context is invalid`、
  `Unable to convert call argument` 或 unexpected `RuntimeError`。

helper monotonic timestamp 是 trigger/observation evidence，不创建新的 production actuator SLA。

### Operator physical evidence

- OLD ACTIVE 时 LEFT fan 低幅旋转；
- OLD SIGINT 后 motor 停止，LEFT fan 停止；
- 没有错误轴、错侧 fan、异常声音、振动、气味或温升。

精确 command payload、epoch/generation 和 timestamp 来自 software/ROS evidence；物理停止与
现场异常观察来自 operator，不互相冒充。

## NEW Runtime restart isolation

NEW Runtime：

```text
PID: 1363429
authority_epoch: 254214835192101
NEW_RUNTIME_EXIT_STATUS=0
```

明确满足：

```text
NEW PID 1363429 != OLD PID 1360007
NEW authority_epoch 254214835192101 != OLD authority_epoch 254107543912471
```

continuous recorder 在 NEW 阶段持续记录：

```text
authority_state: DRY_RUN
command_authority: NONE
authority_generation: 0
attempt_present: false
actuation_allowed: false
motor_committed: false
fan_committed: false

motor/fan ownership_phase: NONE
authority_present: false
authority_epoch: 0
generation: 0

fan PWM: [800,800]
```

NEW 启动后没有属于 NEW epoch 的 executable `FlightCommandEnvelope`。operator 确认 NEW
startup/观察窗口内 motor 与 fan 完全无动作、没有异常；最终 LEFT ESC physically OFF，
motor bus physically OFF。

## 三层 evidence closure

1. **Production software fix：**提交 `96a23a9` 使用 Python-managed SIGINT/SIGTERM、
   `SignalHandlerOptions.NO`，并在 `rclpy.shutdown()` 前完成 `destroy_node()`；
2. **Real rclpy software-only smoke：**真实 Linux process + Jazzy executor 的 exact-PID
   SIGINT、SIGTERM 均 exit 0，无 traceback/context-invalid/conversion RuntimeError；随后
   targeted Runtime/C1/C2 pure/mock regression 为 `97 passed`；
3. **Final powered C3 retry：**上述 final authoritative session 同时闭合 OLD graceful exit、
   actuator fail-close、fresh NEW DRY_RUN/NONE isolation、continuous ROS history 与 operator
   physical evidence，因此 C3 正式为 `HARDWARE PASS`。

software-only smoke 和 pure/mock regression 本身不是硬件 PASS；最终结论由三层证据共同
闭合。

## Historical C3 sessions retained

### Pre-flight aborted

```text
/home/h-goal/windarmor_evidence/
  gate-evidence-20260821T014852.009218Z-1200735
```

分类保持 `C3 PRE-FLIGHT ABORTED / HARDWARE ATTEMPT NOT STARTED`。旧 helper 非原子比较
`/proc/<pid>/status State` 与 `/proc/<pid>/stat state`，把正常 S/R scheduling race 误报；该
session 没有 prepare、ACTIVE 或 SIGINT，不改写为 FAIL。

### First powered session — NOT VERIFIED

```text
/home/h-goal/windarmor_evidence/
  gate-evidence-20260821T021811.696548Z-1220232
```

历史分类保持 `C3 NOT VERIFIED`：OLD Runtime 的原 rclpy default signal handling 先使 context
失效，executor 随后抛出 RuntimeError，`OLD_RUNTIME_EXIT_STATUS=1`。该 session 的 actuator
fail-close 与 NEW restart isolation 正向 evidence 继续作为 supplemental history，但不是最终
PASS session，也不因后续 PASS 被覆盖或改写。

## Normal launch cleanup observation

C3 验证完成后的 normal system shutdown 中，`imu_driver_node`、
`imu_motor_controller_node`、`fan_command_manager` 和 `fan_controller` 四个 launch child 均报告
`process has finished cleanly`；随后 launch 输出：

```text
Cannot shutdown a ROS adapter that is not running
```

该项分类为 `LOW-PRIORITY / NON-C3-BLOCKING shutdown cleanup observation`。它发生在 C3
完成后的 normal shutdown，且 OLD/NEW Runtime 均 exit 0、actuator 已 fail-close、最终动力已
物理断开，因此不降级 C3 PASS、不触发 C3 重跑，也不在本任务扩大范围修复。

## 修改范围与下一步

本轮 repository 修改范围：low-level lifecycle launch、对应 pure launch regression、README、
hardware verification plan 与本文件。production node/control algorithm、interface、config、
recorder 和 watchdog 均未修改。local-only `~/windarmor_test_sessions/c4a/` helper/runbook/test
不进入 repository。real hardware executed：`NO`。

C3 不需要重跑。下一步只能由 assistant/user 审查本次 lifecycle fix、pure test、local trigger
preparation 和 C4a 新的独立十项 retry authorization boundary；C4a retry 仍未授权，不得执行。
C4a 有效 PASS 前禁止进入 C4b。Gate C 继续 `IN PROGRESS / NOT COMPLETE`。
