# 最新反馈：Gate C / C4a + C4b 执行准备完成

> 日期：2026-08-21
> 任务起点：`master` / `7cb5322e59c226bcb738a0a40a80384266543a73`
> 本轮性质：C4a/C4b execution-preparation docs-only closure
> production code changed：`NO`
> tests/scripts changed：`NO`
> real hardware executed：`NO`
> C3 结论：`HARDWARE PASS`
> Gate C：`IN PROGRESS / NOT COMPLETE`

## 正式状态

```text
Gate B: COMPLETE
Gate C / C1: HARDWARE PASS
Gate C / C2: HARDWARE PASS
Gate C / C3: HARDWARE PASS
Gate C / C4a: DESIGN/PREPARATION COMPLETE
Gate C / C4a: NOT AUTHORIZED / NOT EXECUTED
Gate C / C4b: DESIGN/PREPARATION COMPLETE
Gate C / C4b: NOT AUTHORIZED / NOT EXECUTED
Gate C / C4: NOT AUTHORIZED / NOT EXECUTED
Gate C: IN PROGRESS / NOT COMPLETE
```

C3 继续保持 `HARDWARE PASS`，不需要为重复确认而重跑。C4a/C4b 的 execution-critical
candidate、timing、evidence、emergency、no-recovery 和独立十项授权边界已经定值，但本轮
不是任何 powered authorization。没有启动 Runtime、ROS node、launch、helper/watchdog 或
硬件，没有访问 CAN、GPIO、PWM 或串口，也没有发送 lifecycle、prepare、E-STOP、ownership
或 actuator command。

## C4 分离执行顺序

固定顺序为：C4a docs ready → C4a 单独授权 → C4a powered session → physical power OFF →
offline evidence review → C4a PASS 后，才可审查 C4b 的新单独授权。C4a/C4b 不得连续执行、
不得共享授权、不得自动 retry；C4a PASS 不授权 C4b。

两项 proposed powered boundary 都是 motor bus ON、LEFT ESC ON、RIGHT ESC physically OFF；
候选 command 都是 `left_pitch = captured legal ACTIVE baseline +0.05 rad`、其余三轴 captured
ACTIVE baseline hold、fan `LEFT=0.05 / RIGHT=0.0`。这些是 execution-preparation 定值，不是
批准值。

## C4a execution-preparation closure

C4a 的唯一 fault trigger candidate 为：

```bash
ros2 lifecycle set /imu_motor_controller_node deactivate
```

稳定 continuous legal ACTIVE 约 `3.0 s` 后只触发一次，absolute max ACTIVE exposure 为
`10.0 s`，fault 后约 `3 s` stable fail-closed observation；10 秒内没有进入预期路径即安全
停止，不等待、不自动 retry。

production semantics 已核对：`on_deactivate()` 令 `node_active=false` 并停止 motion timer，
`stop_motion_timer()` 调用 `halt_motion()`，因此 target progression 停止。C4a 不依赖
deactivate 后继续运行 C2 的 `0.25 s` command-lease timer，也不把该 timing 复制为 C4a SLA。
要验证的独立链路是 lower-level safety loss → Runtime
`motor_lower_level_safety_loss` → authority rollback/inhibit → owner revoke → motor target
progression 停止 → fan fail closed。“motor halt”不代表 CyberGear STO、电气断电或立即零
holding torque。

C4a 不做 recovery：不 reactivate、不 reset Runtime inhibit、不重新 prepare/restart/reclaim。
完成 observation 后保持 controller inactive，LEFT ESC physically OFF → motor bus physically
OFF → 再结束 software processes。

## C4b execution-preparation closure

C4b 只使用现有 `scripts/flight_estop_watchdog.py`，不得新增第二个 watchdog/helper。watchdog
必须在 prepare 前启动并预热，实时看到 `WATCHDOG READY` 后才允许 prepare；它只在 legal
`ACTIVE + FLIGHT_CONTROL + actuation_allowed=true` 后计时，默认 `2.0 s` 后由同一预热
publisher 单次发布 `/e_stop=true`。

正式 timing requirement 是 `ACTIVE_TO_PUBLISH_SEC <3.0 s`，absolute ACTIVE limit 为
`3.0 s`。达到或超过 3 秒仍没有有效 publish 时不能判 PASS，立即安全终止。no-ACTIVE
timeout 为 `10 s`；`NO ACTIVE WITHIN TIMEOUT` + fail-closed E-STOP 是 safe abort，不是 timing
PASS。required markers 是 `WATCHDOG READY`、`ACTIVE DETECTED`、`E-STOP PUBLISHED`、
`ACTIVE_TO_PUBLISH_SEC`、`ESTOP OBSERVED BY FLIGHT`、`PUBLISH_TO_INHIBIT_SEC`；watchdog
exit status 0 不能替代 markers/timing，`PUBLISH_TO_INHIBIT_SEC` 记录审查但不新增 production
SLA。

C4b 不做 E-STOP recovery：不发布 `/e_stop=false`，不 reset latch/Runtime inhibit，不重新
prepare/restart/reacquire。约 `3 s` fail-closed observation 后保持 E-STOP/latch，LEFT ESC
physically OFF → motor bus physically OFF → 再停止 software processes。

## Recorder and emergency policy

两项都使用 `scripts/hardware_verification/record_gate_evidence.py` 默认 continuous recorder，
从 prepare/fault 前持续到 post-fault stable observation 结束；continuous recorder 是
authoritative history，`topic echo --once` 只作辅助稳态抽查。ROS/software evidence 与
operator physical evidence 分开记录，不新增 analyzer。

wrong axis/fan side、超出批准 offset/PWM、owner/token 或 authority recovery 异常、fault 后
继续旧 movement、NEW/unexpected command、异常声音/振动/气味/温升等任一 anomaly 均立即
触发安全终止：ROS 可用时 `/e_stop=true`，同时准备 LEFT ESC/motor-bus physical kill，且
physical kill 优先级不低于 ROS；不自动 retry、不 recovery、不进入另一 C4 scenario。

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

本轮 repository 修改仅为 C4a/C4b execution-preparation 文档同步：
`docs/V0.4.0_HARDWARE_VERIFICATION_PLAN.md` 与 `docs/LATEST_FEEDBACK.md`。production code
changed：`NO`；test/script code changed：`NO`；real hardware executed：`NO`。

C3 不需要重跑。下一步只能由 assistant/user 审查 C4a 的独立十项 authorization boundary；
不得执行 C4a，也不得提前审查或执行 C4b。C4a 与 C4b 都保持
`NOT AUTHORIZED / NOT EXECUTED`，C4 总体未授权、未执行，Gate C 仍未完成。
