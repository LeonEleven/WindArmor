# 最新反馈：Gate C / C4b HARDWARE PASS，Gate C COMPLETE

> 日期：2026-08-24
> 任务起点：`master` / `d0b3ed088680b9bf47b394e3afc4df083d73a7c3`
> 本轮性质：C4b final authoritative session 与 Gate C offline closure（仅文档）
> production code changed：`NO`
> test/script/config/launch changed：`NO`
> real hardware executed during this docs task：`NO`
> C4b 结论：`HARDWARE PASS`
> Gate C：`COMPLETE`

## 正式状态

```text
Gate B: COMPLETE
Gate C / C1: HARDWARE PASS
Gate C / C2: HARDWARE PASS
Gate C / C3: HARDWARE PASS
Gate C / C4a: HARDWARE PASS
Gate C / C4b: HARDWARE PASS
Gate C / C4: HARDWARE PASS
Gate C: COMPLETE
Gate D: PLANNED / NOT AUTHORIZED / NOT EXECUTED
```

C1/C2/C3/C4a/C4b 均为 `HARDWARE PASS`，因此 C4 为 `HARDWARE PASS`、Gate C 为
`COMPLETE`。这不授权 Gate D，不代表 recovery 已验证，也不允许 unrestricted hardware
operation。本轮只离线阅读既有证据并同步文档；没有运行 Runtime、ROS node、launch、watchdog
或硬件，没有访问 CAN、GPIO、PWM、串口，也没有发布 E-STOP 或 actuator command。

## Final authoritative C4b session

authoritative powered session：

```text
/home/h-goal/windarmor_evidence/
  gate-evidence-20260824T030542.834602Z-1754254
```

manifest 为 `COMPLETED / SIGINT`、`abnormal_child=null`、`cleanup_timed_out=false`，8/8
required topics 均为 `SAMPLES CAPTURED`。continuous recorder 是 transient ROS history 的
authoritative evidence。

### Software preflight retained

powered session 前为 `HEAD=d0b3ed0`、`master...origin/master` 且无额外工作区修改；installed
config 为 `C4B_CONFIG_MATCH`。完整 software CI 结果为：hardware verification tooling
`26 passed`、motor `431 passed`、fan `159 passed`、Flight/interfaces `304 passed`，full colcon
`925 tests, 0 errors, 0 failures, 0 skipped`。这些是 execution preflight/software evidence，
不是 C4b hardware PASS evidence 本身。

### Watchdog timing evidence

```text
WATCHDOG READY
WATCHDOG_READY_MONOTONIC=501371.112514595
ACTIVE DETECTED
E-STOP TIMER START
ACTIVE_DETECTED_MONOTONIC=501376.383183235
E-STOP PUBLISHED
ESTOP_PUBLISHED_MONOTONIC=501378.404627468
ACTIVE_TO_PUBLISH_SEC=2.021444233
ESTOP OBSERVED BY FLIGHT
PUBLISH_TO_INHIBIT_SEC=0.024631484
WATCHDOG_EXIT_STATUS=0
```

全部 required marker 均存在，`ACTIVE_TO_PUBLISH_SEC=2.021444233 < 3.0 s`，因此 timing
contract PASS，也闭合 B1/Gate B 遗留的 procedural timing item。watchdog exit 0 本身不单独
构成 PASS；`PUBLISH_TO_INHIBIT_SEC=0.024631484` 只是本次 observation，不是新的 production
SLA。

### Authoritative authority and command evidence

- 首个 legal ACTIVE stamp 为 `1787540766.501230955`，epoch
  `501315221790256`、generation `1`；state `ACTIVE`、authority `FLIGHT_CONTROL`、
  `actuation_allowed=true`、motor/fan committed、`owner_tokens_match=true`。
- 首个 global E-STOP active 与首个 `INHIBITED` stamp 均为
  `1787540768.549133778`；`actuation_allowed=false`，published/final
  `last_inhibit_reason=fan_ownership_lost`。不虚构其他 inhibit reason；该 reason 与 E-STOP 后
  fan lower-level 先 revoke 的 asynchronous sequence 一致，不是缺陷。
- continuous recorder 共记录 100 条 executable Flight command，sequence `0..99`，全部属于
  epoch/generation `501315221790256 / 1`，fan command 始终为 `LEFT=0.05 / RIGHT=0.0`。
  首条 stamp `1787540766.519898891`，末条 stamp `1787540768.518891096`；E-STOP 后
  `commands_after_estop=0`。
- 首个 motor target vector 为 `left_lift=-0.00019175052436715134`、
  `left_pitch=0.04980824947563285`、`right_pitch=-0.00019175052436715134`、
  `right_lift=-0.00019175052436715134`，符合 approved `left_pitch baseline +0.05 rad`、其他
  三轴 baseline hold candidate。

### Ownership, lower-level E-STOP, and PWM evidence

- motor owner：首个 `FLIGHT_CONTROL` 为 `1787540766.482691050`，E-STOP 后首个 `NONE` 为
  `1787540768.557705879`；fan owner 对应为 `1787540766.482271194` 与
  `1787540768.530885696`。
- `motor_reacquire=0`、`fan_reacquire=0`、`ACTIVE_after_estop=0`，没有 automatic authority
  recovery 或 ownership reacquisition。
- fan controller 在 `1787540768.532819442` 记录收到系统 E-STOP 并立即停止、停用双 fan；
  motor controller 在 `1787540768.544186365` 收到 topic E-STOP，随后四 motor stop completed，
  `AUTO_RUNNING -> EMERGENCY_STOP`，`reason=topic_estop / source=topic`。
- continuous safety 首个 fan/motor E-STOP latch 分别为 `1787540768.530710697` 和
  `1787540768.558001518`；post-fault motor 为 `EMERGENCY_STOP / e_stop_latched=true`，fan 为
  `EMERGENCY_STOP / e_stop_latched=true / enabled=false`。
- fan PWM 首尾均为 `[800,800]`；`MAX_LEFT=1200`、LEFT non-800 samples `40`，
  `MAX_RIGHT=800`。这证明 approved LEFT `0.05` command path 确实执行、RIGHT 始终保持停止
  baseline，E-STOP 后 LEFT 回到 `800`。

### Operator physical evidence and causal closure

operator 在 E-STOP 前**未观察到 LEFT fan 明显转动**；不得写成 physically observed rotating。
recorder 仅证明 LEFT command `0.05`、PWM 最大 `1200`、40 个 non-800 samples。该观察与短约
2 秒 ACTIVE 窗口/有限 PWM ramp 一致，但未单独证明具体机械启动阈值，也不推断确切原因。

E-STOP 后 operator 确认 motor 停止 Flight-induced movement、LEFT fan 处于停止状态，无异常
声音、振动、气味或温升；最终 LEFT ESC 与 motor bus physically OFF。RIGHT ESC 在整个
scenario 中始终 physically OFF。

最终因果链为：legal ACTIVE → approved bounded motor/fan commands → prewarmed watchdog 约
2.02 秒发布 `/e_stop=true` → fan/motor lower-level E-STOP latch → fan owner `NONE` → Runtime
`INHIBITED / actuation_allowed=false` → motor owner `NONE` → executable Flight commands 停止
→ no ACTIVE recovery → no owner reacquire → stable fail-closed。各 asynchronous topic 不要求
单一固定微观发布顺序。

本 session 未发布 `/e_stop=false`，未 reset E-STOP latch/Runtime inhibit，未 reprepare、restart
Runtime 或 reclaim authority；C4b 只验证 latched fail-close，不验证 recovery。recovery/startup/
re-entry 若属于 Gate D，必须作为新的独立授权范围。

### Shutdown observation

既有 `Cannot shutdown a ROS adapter that is not running` 继续分类为
`LOW-PRIORITY / NON-GATE-C-BLOCKING shutdown cleanup observation`：它出现在验证完成后的
software shutdown，actuator 已 fail closed、动力已 physically OFF、relevant children clean
exit，因此不降级 C4b 或 Gate C，本轮不修复。

## C4a remains archived HARDWARE PASS

C4a 最终 session 继续为
`gate-evidence-20260824T013006.286027Z-1631895`，结论保持 `HARDWARE PASS`，不重跑；更早
`gate-evidence-20260821T075236.156225Z-1454804` 的
`NOT VERIFIED / POWERED ATTEMPT INVALIDATED` 历史也继续保留。

## Final authoritative C4a session

authoritative session：

```text
/home/h-goal/windarmor_evidence/
  gate-evidence-20260824T013006.286027Z-1631895
```

recorder manifest 为 `COMPLETED / SIGINT`，`abnormal_child=null`、
`cleanup_timed_out=false`，8/8 required topics 均为 `SAMPLES CAPTURED`，所有 recorder
stderr 均为空。trigger helper 已预热并在 continuous legal ACTIVE 后只请求一次 deactivate：

```text
C4A_TRIGGER_READY
C4A_TRIGGER_ARMED
C4A_LEGAL_ACTIVE_DETECTED
ACTIVE_TO_DEACTIVATE_SEC=3.007615236
DEACTIVATE_SERVICE_SUCCESS=true
C4A_TRIGGER_RESULT=PASS
C4A_TRIGGER_EXIT_STATUS=0
```

trigger log 只作为 fault timing/supporting evidence；continuous recorder 仍是 authoritative
transient history。该唯一请求没有超过 `10 s` absolute ACTIVE limit，没有迟到 deactivate，
helper 也没有执行 recovery 或 retry。

### Authoritative causal sequence

1. 首个 legal ACTIVE 在 stamp `1787535089.849424648`、epoch
   `495604390791197`：state `ACTIVE`、authority `FLIGHT_CONTROL`、generation `1`，motor/fan
   均 committed，`actuation_allowed=true`、`global_e_stop_active=false`。
2. executable Flight command 共 `150` 条，epoch/generation 始终为
   `495604390791197 / 1`，sequence `0..149`。最后一条在
   `1787535092.849045387`，target 为 `LEFT=0.05 / RIGHT=0.0`、
   `request_safe_stop=false`；之后没有 executable command。C4a 不要求最后一条 command 必须是
   safe-stop envelope，因此该字段不是缺陷。
3. 首个 motor `node_active=false` 在 `1787535092.860485204`，同时
   `controller_state=AUTO_RUNNING`、public `control_mode=DISABLED`，command stream 随即停止。
4. fan owner 首次 `NONE` 在 `1787535092.864463582`，authority 不再存在，epoch/generation
   清零。
5. Runtime 首次 post-ACTIVE `INHIBITED` 在 `1787535092.870926811`：authority `NONE`、
   generation `0`、`actuation_allowed=false`、`global_e_stop_active=false`，发布的
   `last_inhibit_reason=fan_ownership_lost`。此时 `motor_committed=true` 是异步 rollback 的中间
   状态，后续稳态 motor/fan 均为 false。
6. motor owner 首次 `NONE` 在 `1787535092.873340938`，authority 不再存在，epoch/generation
   清零；之后保持 fail closed，无自动 re-activate 或 ownership reacquire。

因此闭合的因果链是：legal ACTIVE → helper 约 3 秒后单次 lifecycle deactivate → motor
`node_active true -> false` → public mode `DISABLED` → executable command stream 停止 → fan
owner `NONE` → Runtime `INHIBITED` / actuation false → motor owner `NONE` → stable fail-closed。
authoritative recorder 中最终 inhibit reason 只有 `fan_ownership_lost`，不虚构
`motor_lower_level_safety_loss`。motor `node_active=false` 先于 fan owner `NONE`，没有证据支持
“独立 fan fault 恰好触发 inhibit”；C4a 验收依据是完整的因果时序，不要求最终发布一个特定的
motor-specific reason。

以下 delta 仅是本次 recorder 的辅助观测，不是 production SLA：last command →
`node_active=false` 约 `11.44 ms`；`node_active=false` → fan owner `NONE` 约 `3.98 ms`；
`node_active=false` → `INHIBITED` 约 `10.44 ms`；`node_active=false` → motor owner `NONE`
约 `12.86 ms`。

### Actuator and physical evidence

- LEFT PWM 从 `800` 有界上升到最高 `1210` 后回到 `800`；RIGHT 始终为 `800`，与
  `LEFT=0.05 / RIGHT=0.0` 一致。
- operator 在 fault 前观察到 LEFT fan 低速旋转；fault 后 motor 停止 Flight-induced
  movement、LEFT fan 停止，且无自动恢复或 ownership reacquire。
- 没有异常声音、振动、气味或温升；最终 LEFT ESC 与 motor bus 均 physically OFF。
- `left_pitch +0.05 rad` 来自 recorder/motor feedback，不表述为肉眼精确测量。

### E-STOP separation, launch fix, and recovery boundary

operator 后续发布 `/e_stop=true` 的首个 GLOBAL E-STOP ACTIVE stamp 为
`1787535156.864039428`，约在 motor lifecycle fault 后 `64 s`。它仅用于保守 shutdown，未触发
最初 C4a fail-close；上述因果链闭合期间 `global_e_stop_active=false`。

本次 powered session 还确认提交 `daa51ee` 的 production launch 修复：manual lifecycle
deactivate 后 `ros2 lifecycle get` 为 `inactive [2]`，没有
`inactive -> activating -> active`；controller/IMU startup handler 的
`start_state="configuring", goal_state="inactive"` 限定在真实运行中生效。这是 C4a 的修复
确认，不升级为独立 Gate。

C4a 未测试 recovery：没有 reactivate controller、reset Runtime inhibit、重新 prepare、restart
Runtime 或 reclaim authority；recovery 属于未来独立范围。normal shutdown 后的
`Cannot shutdown a ROS adapter that is not running` 继续分类为
`LOW-PRIORITY / NON-C4a-BLOCKING`：它发生在验证完成、actuator fail-closed、动力物理断开且
child processes clean 之后，本轮不扩大范围修复。

## Historical invalidated C4a attempt retained

2026-08-21 session：

```text
/home/h-goal/windarmor_evidence/
  gate-evidence-20260821T075236.156225Z-1454804
```

该 attempt 保持 `C4a NOT VERIFIED / POWERED ATTEMPT INVALIDATED`，不是 actuator safety FAIL，
也不因最终 PASS 被覆盖或改写：ACTIVE exposure 约 `14.97 s`，超过批准的 `10.0 s`；intended
fault 前 Runtime 已因 `required_inputs_stale` fail closed；旧 launch 又在 manual deactivate 后
自动 re-activate。其 Runtime fail-close、owners NONE、PWM 回到 `[800,800]`、physical stop、
无异常和最终 power OFF 等正向安全证据继续保留，但不构成该次 intended causal C4a PASS。

## Software/preparation evidence retained

- production launch fix：commit `daa51ee`，controller/IMU handler 均限定
  `configuring -> inactive`；
- targeted launch regression：`7 passed`；
- local C4a fake ROS/messages/clock/service self-test：`6 passed`；
- 完整纯软件 CI：motor `431 passed`、fan `159 passed`、Flight/interfaces `304 passed`，最终
  colcon `925 tests, 0 errors, 0 failures, 0 skipped`。

这些结果是既有 software/preparation evidence，不代替上述实机证据，也不授权 C4b。

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

本轮 repository 修改仅限 README、hardware verification plan 与本文件。production code、
launch、test、script、config、interface、recorder、watchdog 和 local-only helper 均未修改；
本轮没有执行真实硬件操作。

C4a/C4b 均不需要重跑。C4 为 `HARDWARE PASS`，Gate C 为 `COMPLETE`。Gate D 继续为
`PLANNED / NOT AUTHORIZED / NOT EXECUTED`；Gate C COMPLETE 不授权 Gate D，也不代表 recovery
已验证。下一步只能是 assistant/user 对 Gate D 的 design/authorization review，不得直接执行
Gate D hardware。
