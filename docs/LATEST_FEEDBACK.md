# 最新反馈：Gate C / C1 硬件验证闭合

> 日期：2026-08-20
> 基线：`master` / `e327517ea025d609c8e0f6dabd27b3f031541239`
> 本轮工作性质：只读离线证据审查与文档同步
> 最终结论：`C1 HARDWARE PASS`
> Gate C：`IN PROGRESS / NOT COMPLETE`

## 状态摘要

```text
Gate A: COMPLETE
Gate B: COMPLETE
Gate C / C1: HARDWARE PASS
Gate C / C2: NOT AUTHORIZED / NOT EXECUTED
Gate C / C3: NOT AUTHORIZED / NOT EXECUTED
Gate C / C4: NOT AUTHORIZED / NOT EXECUTED
Gate C: IN PROGRESS / NOT COMPLETE
Gate D: PLANNED / NOT AUTHORIZED
```

C1 PASS 不授权 C2、C3、C4、Gate D 或任何新的硬件操作。B1 closure run 遗留的
`ACTIVE <=3.0 sec` E-STOP procedural timing 也没有被 C1 的 IMU-deactivate timing
替代，仍等待对应 Gate C E-STOP 子场景。

## 本轮边界

本轮没有启动 ROS 2、没有访问 CAN、GPIO、PWM、串口或真实 IMU，也没有改变树莓派或
执行器状态。只读取用户已经提供的本地 evidence，人工交叉核对 recorder manifest、trigger
helper、IMU lifecycle/raw、authority/command、motor/fan ownership/safety、fan PWM 和
motor feedback，然后同步 README 和硬件验证计划。

没有创建 C1 analyzer，没有修改 production code、参数、launch 或测试，也没有执行构建、
测试、commit、push 或 tag。

## 最终 evidence session

```text
/home/h-goal/windarmor_evidence/
  gate-evidence-20260820T024541.024256Z-924522
```

manifest 记录：

- `started_at=2026-08-20T02:45:41.024Z`；
- `stopped_at=2026-08-20T02:50:23.850Z`；
- `status=COMPLETED`、`stop_reason=SIGINT`；
- 10 个 required topic 均有日志，所有 stderr 为空；
- `abnormal_child=null`、`cleanup_timed_out=false`；
- recorder 子进程退出均被分类为正常 cleanup，不存在证据采集器异常终止。

## C1 四类闭合证据

### 1. Trigger 与 IMU lifecycle

pre-armed helper 完整记录：

```text
C1_TRIGGER_READY
C1_TRIGGER_ARMED
ACTIVE_TO_DEACTIVATE_SEC=3.023377119
DEACTIVATE_SERVICE_SUCCESS=true
C1_TRIGGER_RESULT=PASS
C1_TRIGGER_EXIT_STATUS=0
```

`3.023377119 s` 低于该场景批准的 `10 s` 最大 ACTIVE 持续时间。IMU lifecycle history
只出现：

```text
active -> deactivating -> inactive
```

`imu_raw.log` 共 366 条 sample，第一条 stamp 为 `1787193950.513528585`，最后一条为
`1787193986.822868824`；deactivate 后没有新 sample，也没有 `inactive -> activating ->
active` 自动恢复。

### 2. Runtime、command 与 ownership

authority 因果链为：

```text
1787193983.818789482:
  ACTIVE / FLIGHT_CONTROL / generation 1 / actuation_allowed=true

1787193986.968290806:
  INHIBITED / NONE / generation 0
  last_inhibit_reason=required_inputs_stale
  actuation_allowed=false
```

`flight_command.log` 只有 152 帧，sequence 为 0–151。最后一帧 stamp
`1787193986.926113605`，早于 stale；stale 后新 command 数为 0，没有旧 target replay。

ownership history 显示两域均完成 `FLIGHT_RESERVED -> FLIGHT_CONTROL -> NONE`：

- fan 在 `1787193986.978000402` 回到 `NONE`；
- motor 在 `1787193986.987437010` 回到 `NONE`；
- 两域最后接受的 command sequence 均为 151。

fault 后 recorder 继续保留约 235 秒 history。期间 11,766 条 authority sample 中没有
`ACTIVE`，没有 `actuation_allowed=true`，也没有新 Flight command，因此 no-automatic-
recovery 证据闭合。

### 3. Bounded command 与软件执行器反馈

全部 Flight command 保持相同 bounded target：

```text
left_lift   baseline hold
left_pitch  baseline +0.05 rad
right_pitch baseline hold
right_lift  baseline hold
fan_left    0.05
fan_right   0.0
```

motor feedback 在 ACTIVE 窗口内显示 `left_pitch` 从约 `-0.00019 rad` 到约
`+0.05081 rad`；其他三轴仅在约 `±0.001 rad` 的反馈量化范围内变化，支持 selected axis
target 与其他三轴 baseline hold。stale 后没有新 command，feedback 没有显示旧 target
被重新下发。

fan continuous PWM history 为：

- 初始 `[800,800]`；
- LEFT 以 10 us 阶梯从 810 上升到 1210；
- 随后回到 `[800,800]` 并保持；
- RIGHT 所有 sample 均为 800。

motor safety 从 `AUTO_RUNNING / AUTO` 回到 `MANUAL_RUNNING / MANUAL`；fan safety 从
`FLIGHT_ACTIVE` 回到 `SAFE_STOP`，reason 为 Flight ownership revoked。

### 4. Operator physical evidence 与最终安全状态

用户确认：

- ACTIVE 期间 LEFT fan 有低幅旋转；
- `left_pitch` 的批准幅度很小，肉眼不作为精确角度判据；软件 target/feedback 提供角度
  证据；
- 其他三台电机确实没有运动；
- 没有错误轴、错侧 fan、异常大幅运动、机械干涉、异常振动、异常声音、异味或异常温升；
- stale 后 motor 与 LEFT fan 均停止；
- LEFT fan 在 motor 通电时已经处于批准的 powered 边界，RIGHT ESC 全程断电；该先后
  顺序不超出最终 C1 授权边界，也不是 PASS 所需的精确上电顺序；
- session 结束后 LEFT ESC 与 motor 动力总线均已物理断电。

final session 的 motor/fan safety history 全程为 `e_stop_latched=false`，并且没有独立的
`/e_stop=true` 发布 transcript。因此本记录不声称执行或证实了 E-STOP；safe-exit 证据是
stale rollback 已使 motor/LEFT fan 停止、没有自动恢复，以及最终物理断电。C4 的 E-STOP
能力仍须单独授权和验证。

## Attempt history

1. 2026-08-19 初次 C1 attempt：`NOT VERIFIED`。ACTIVE exposure 约 16.385 秒，超过
   批准的 10 秒；normal launch 自动重新 activate IMU；LEFT ESC powered sequence 与批准
   步骤不完全一致；肉眼精确确认 `left_pitch +0.05 rad` 也不是可靠判据。该 session 的
   局部 fail-closed 证据不改变分类。
2. 2026-08-20 约 1 秒 retry：session
   `gate-evidence-20260820T020508.332840Z-886665`。helper 在 1.001164579 秒请求
   deactivate 并成功退出，但 LEFT PWM 最高仅 1020，bounded physical response 证据不足，
   分类保持 `NOT VERIFIED`。
3. 2026-08-20 计划 3 秒的 helper-aborted session：
   `gate-evidence-20260820T023505.409661Z-915048`。helper 未检测到 ACTIVE，以
   `ACTIVE_WAIT_TIMEOUT / exit 4` 结束；PWM 始终 `[800,800]`，不构成 C1 attempt。
4. 2026-08-20 最终 3 秒 retry：session
   `gate-evidence-20260820T024541.024256Z-924522`。trigger、continuous ROS、operator
   physical 和 no-automatic-recovery 四类证据全部闭合，分类为 `HARDWARE PASS`。

旧 session 保持各自原始分类；最终 PASS 只属于第 4 个 session。

## 文档同步与验证

本轮同步：

- `README.md`：更新 C1 与 Gate C 总体状态；
- `docs/V0.4.0_HARDWARE_VERIFICATION_PLAN.md`：归档完整证据链、批准边界、最终安全状态和
  remaining gates；
- `docs/LATEST_FEEDBACK.md`：覆盖为本次 closure 记录。

仅需执行文档级检查：`git diff --check` 和 `git status --short --branch`。构建与测试未执行，
因为本轮没有修改代码、配置、launch 或测试，且任务明确限定为离线证据审查与文档同步。
