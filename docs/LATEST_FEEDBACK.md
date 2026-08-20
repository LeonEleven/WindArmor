# 最新反馈：Gate C / C2 HARDWARE PASS 收口

> 日期：2026-08-20
> 任务起点：`master` / `25de37cdf74c3d39d62f71d774e077db7ba1b09d`
> 本轮工作性质：已有实机 evidence 的只读离线复核与文档归档
> 最终结论：`Gate C / C2: HARDWARE PASS`
> Gate C：`IN PROGRESS / NOT COMPLETE`

## 状态摘要

```text
B0: PASS
B1: FUNCTIONAL HARDWARE PASS
B2: HARDWARE PASS
Gate B: COMPLETE

Gate C / C1: HARDWARE PASS
Gate C / C2: HARDWARE PASS
Gate C / C3: NOT AUTHORIZED / NOT EXECUTED
Gate C / C4: NOT AUTHORIZED / NOT EXECUTED
Gate C: IN PROGRESS / NOT COMPLETE
```

C2 PASS 不授权 C2 retry、C3/C4、Gate D 或任何新的硬件操作。下一步只能进入 C3 的
design/review；C3 仍须单独确定边界并满足十项带电授权门槛。

## 本轮边界

本轮只读取用户已完成的 C2 raw evidence，交叉核对 recorder manifest、pre-armed helper、
authority/command、motor/fan ownership/safety、fan PWM 和 motor feedback，再同步 README、
硬件验证计划和本文件。

本轮没有启动 ROS 2、WindArmor launch、Flight Runtime 或 hardware node，没有访问 CAN、
GPIO、PWM、串口、IMU、motor、ESC/fan，没有执行 prepare、E-STOP、SIGSTOP/SIGCONT/SIGKILL、
C2 retry 或 C3/C4。production code、config、launch、message、service 和 test 均未修改；没有
新增 analyzer 或 permanent C2 helper，也没有 commit、push、tag 或 release。

## Final evidence session 与 recorder 完整性

```text
/home/h-goal/windarmor_evidence/
  gate-evidence-20260820T070959.631365Z-1037382
```

manifest 复核结果：

- `status=COMPLETED`、`stop_reason=SIGINT`；
- `abnormal_child=null`、`cleanup_timed_out=false`；
- 默认 8/8 C2 topic 均为 `SAMPLES CAPTURED`；
- 8 个 stderr 文件均为空，recorder children 都是 expected cleanup exit。

authority 与 fan ownership stdout 开头各有一次 DDS lost notice，但都位于 recorder 起始的
DRY_RUN/NONE history。关键 fault 边界完整：motor ownership observation sequence
`1153 -> 1154`、fan ownership `9407 -> 9408` 连续，因此这两个 startup notice 不构成 C2
required evidence 缺口。

## Trigger / exact Runtime evidence

`c2_sigstop_on_active.log` 原始记录确认：

```text
C2_RUNTIME_PID=1036555
C2_TRIGGER_READY
C2_TRIGGER_ARMED
ACTIVE_DETECTED_MONOTONIC=170510.978304214
SIGSTOP_SENT_MONOTONIC=170513.982496759
ACTIVE_TO_SIGSTOP_SEC=3.004192545
RUNTIME_STOP_CONFIRMED_MONOTONIC=170513.988818302
C2_TRIGGER_RESULT=PASS
C2_TRIGGER_EXIT_STATUS=0
```

helper cmdline 明确对应安装后的真实 `flight_control_runtime_node`，参数为 selected
`left_pitch +0.05 rad`、LEFT/RIGHT fan `0.05/0.0`、takeover enabled。helper 在 prepare 前
READY/ARMED，legal ACTIVE 到 SIGSTOP 为 `3.004192545 s`，低于批准的 `10 s` max ACTIVE；
SIGSTOP 后 `0.006321543 s` 确认 process state `T/t`。helper 本身没有 SIGCONT、prepare、
E-STOP、actuator command、kill 或 restart 路径。helper PASS 是辅助 trigger/observation
evidence，不单独宣布 hardware PASS。

## Flight command 与 frozen authority

continuous command history 共 131 帧，sequence `0-130` 连续，全部使用同一 epoch/generation
和唯一 approved bounded payload：

```text
left_lift:   captured baseline hold
left_pitch:  captured baseline +0.05 rad
right_pitch: captured baseline hold
right_lift:  captured baseline hold
fan_left:    0.05
fan_right:   0.0
request_safe_stop: false
```

最后 command sequence 为 130；之后没有新 Flight command、safe-stop frame 或 stale replay。
C2 不要求 `request_safe_stop=true`：Runtime 被 SIGSTOP 后 publisher ceases，motor/fan lower-level
lease 独立 fail-close。

authority history 完整经过 `DRY_RUN -> ARMING -> READY_TO_TAKEOVER -> ACTIVE`，最后仍为：

```text
authority_state: ACTIVE
command_authority: FLIGHT_CONTROL
actuation_allowed: true
motor_committed: true
fan_committed: true
owner_tokens_match: true
```

最后 authority sample 只比最后 command 晚 `0.000360727 s`，之后两条 Runtime publication
stream 一起停止。C1 中 Runtime 仍活着，可 rollback 并发布 `INHIBITED`；C2 中 Runtime 被
SIGSTOP-frozen，不能 tick、rollback、revoke 或发布新 authority，故 authority 停在 ACTIVE
且随后 cessation 是预期 freeze evidence，不是 anomaly。

## Lower-level lease、ownership 与 timing

helper monotonic 辅助 timing：

```text
last command receipt -> motor owner NONE: 0.258244544 s
last command receipt -> fan owner NONE:   0.291357200 s
last command receipt -> fan PWM stop:     0.292747309 s
```

continuous message stamp/history 交叉核对：

- motor ownership：`MANUAL -> FLIGHT_RESERVED -> FLIGHT_CONTROL -> NONE`；最后 command
  ROS stamp 到 NONE 为 `0.260380983 s`；
- fan ownership：`NONE -> FLIGHT_RESERVED -> FLIGHT_CONTROL -> NONE`；最后 command ROS
  stamp 到 NONE 为 `0.293756485 s`；
- timeout 前最后 ownership age 分别为 motor `0.237991288 s`、fan `0.263708737 s`，与
  motor 50 Hz / fan 20 Hz timeout check period 一致；
- 两 owner 进入 NONE 后没有再出现 FLIGHT_CONTROL、MANUAL 或其他 ordinary owner。

两项 authoritative owner timing 和 helper 的 fan-stop 辅助 timing 均落在本次批准的
`0.25-0.40 s` evidence-review window。helper receipt delta 与 lower-level receipt 属于不同
DDS subscriber；fan PWM `Int32MultiArray` 也没有 header stamp，因此这些值只用于本次
verification review，不创造新的 production timing SLA。

motor timeout 后 controller 返回 `MANUAL_RUNNING / MANUAL`，transition reason 为
`flight_ownership_revoke`；该 label 本身不是 legacy recovery，authoritative ownership 此后
保持 NONE，且没有普通 motor command/movement evidence。

## Fan PWM 与 motor software evidence

fan safety 明确记录 `Flight command timeout；等待显式重新授权`。continuous PWM 完整显示：

```text
LEFT:  800 -> 810 -> ... -> 1200 -> 1210 -> 800 us
RIGHT: 800 us throughout
```

`MAX_LEFT=1210`、`MAX_RIGHT=800`；LEFT 回到 800 后，其余记录只包含 `[800,800]`。这证明
fault 前 bounded LEFT fan 前态已经建立，fault 后 fan lower-level lease 独立回 safe stop。

motor feedback 在 fault window 内显示：selected `left_pitch` 从约 `-0.00019 rad` 到约
`+0.04890 rad`；其他三轴只在约 `-0.00250` 到 `+0.00020 rad` 的反馈量化/保持范围内。
这支持 selected target 与其他三轴 baseline hold，但不表述为 operator 肉眼精确确认
`+0.05 rad`。

## Operator physical evidence 与 safe exit

用户对 final session 明确报告：

- ACTIVE 时 LEFT fan 有明确低幅旋转；
- SIGSTOP/lower-level lease expiry 后 LEFT fan 与 motor 均停止；
- 无错误轴、意外运动、异常声音、振动、气味或温升；
- old Runtime 始终没有 SIGCONT/`fg`，没有恢复执行；
- lower-level fail-close 和 physical stop 确认后 recorder 继续留证；
- LEFT ESC 与 motor actuator power 先物理断开，确认 power OFF 后才 SIGKILL exact frozen
  Runtime；最终 actuator power 已断。

physical stop、现场异常观察、物理断电和 power-OFF-before-SIGKILL 顺序属于
operator-provided evidence；ROS logs 只能证明 publication cessation、owner/PWM/software
state，不能独立证明物理断电。本场景没有 Runtime restart；restart/new epoch isolation 属于
C3。

## Buffered preflight classification

更早的 recorder session：

```text
gate-evidence-20260820T065345.667453Z-1018147
```

helper 实际输出 READY/ARMED，但 Python stdout 经 `tee` 后 block-buffered，operator 未实时看到
marker，因此正确地没有 prepare。raw evidence 只有 DRY_RUN，`flight_command.log` 为 0 字节，
helper 最终 `ACTIVE_WAIT_TIMEOUT`；没有 ACTIVE、SIGSTOP 或 C2 fault injection。正式分类为：

```text
C2 PRE-FLIGHT ABORTED / HARDWARE ATTEMPT NOT STARTED
```

它不是 C2 FAIL，也不是 C2 NOT VERIFIED。未来经 `tee` 运行 timing helper 应使用
`python3 -u` 或显式 flush；不为此修改 production code。

## Final judgement 与验证

trigger、continuous ROS history、lower-level lease/ownership/PWM、operator physical 和
no-automatic-recovery/safe-exit evidence 全部闭合，raw evidence 未发现 contradiction：

```text
Gate C / C2: HARDWARE PASS
Gate C: IN PROGRESS / NOT COMPLETE
```

本轮只修改 Markdown。执行 `git diff --check` 和最终 Git 状态检查；完整 900+ pure software
CI 未执行，因为 production code/config/launch/test 均未修改。C2 hardware 不由本轮执行，
本轮只归档用户已经完成的 final session。

下一步只能建议 C3 design/review，不自动执行 C3。
