# 最新反馈：Gate C / C3 最终硬件验证 PASS

> 日期：2026-08-21
> 任务起点：`master` / `96a23a9a0f23d45261a13c92ae1a67050919f8b4`
> 本轮性质：最终 C3 evidence 的 offline documentation closure
> C3 结论：`HARDWARE PASS`
> Gate C：`IN PROGRESS / NOT COMPLETE`

## 正式状态

```text
Gate B: COMPLETE
Gate C / C1: HARDWARE PASS
Gate C / C2: HARDWARE PASS
Gate C / C3: HARDWARE PASS
Gate C / C4: NOT AUTHORIZED / NOT EXECUTED
Gate C: IN PROGRESS / NOT COMPLETE
```

C3 已闭合，不需要为重复确认而重跑。C3 PASS 不授权 C4，也不把 Gate C 整体提升为
COMPLETE。本轮只离线审查现有 evidence 并更新文档，没有启动任何 Runtime、ROS node、
launch、helper 或硬件，也没有发送 signal、prepare、E-STOP、ownership 或 actuator command。

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

本轮 repository 修改仅为 C3 最终状态文档同步；production code changes：`NONE`；test code
changes：`NONE`；本轮 real hardware executed：`NO`。

C3 不需要重跑。下一步只能审查 C4 的独立边界、证据需求和十项授权门槛；C4 仍为
`NOT AUTHORIZED / NOT EXECUTED`，本轮不执行。
