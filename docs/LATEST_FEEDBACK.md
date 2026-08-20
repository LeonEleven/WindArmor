# 最新反馈：Gate C / C2 contract 与 local-only preparation

> 日期：2026-08-20
> 任务起点：`master` / `a6583069d90012442e71153752b72650852af9c2`
> 本轮工作性质：source/config/test review、文档校准、local-only operator bundle 准备
> C2 结论：`DESIGN/PREPARATION COMPLETE, NOT AUTHORIZED / NOT EXECUTED`
> Gate C：`IN PROGRESS / NOT COMPLETE`

## 状态摘要

```text
Gate A: COMPLETE
Gate B: COMPLETE
Gate C / C1: HARDWARE PASS
Gate C / C2: DESIGN/PREPARATION COMPLETE, NOT AUTHORIZED / NOT EXECUTED
Gate C / C3: NOT AUTHORIZED / NOT EXECUTED
Gate C / C4: NOT AUTHORIZED / NOT EXECUTED
Gate C: IN PROGRESS / NOT COMPLETE
Gate D: PLANNED / NOT AUTHORIZED
```

C1 的最终 `HARDWARE PASS` 已完整归档在
`docs/V0.4.0_HARDWARE_VERIFICATION_PLAN.md`，本轮没有覆盖或降级该结论。C1 PASS 和
C2 preparation 都不授权 C2/C3/C4、Gate D、prepare、SIGSTOP、E-STOP、lifecycle
hardware transition 或任何带电动作。

## 本轮安全与修改边界

本轮没有启动 WindArmor launch、Flight Runtime 或任何 ROS hardware node，没有访问或
改变 CAN、GPIO、PWM、串口、IMU、motor、ESC/fan 或树莓派系统硬件状态，也没有执行
prepare、lifecycle transition、E-STOP、SIGSTOP、C2/C3/C4。只进行了源码/配置/测试审查、
repository 文档修改、local-only helper 准备和不连接 ROS graph/不发送真实 signal 的纯测试。

production Runtime、lower-level actuator behavior、配置、launch、message、service 和测试均
未修改；没有新增 repository analyzer 或永久 C2 helper。没有 commit、push、tag 或 release。

## C2 实际软件 contract 审查

当前 source/config 与 C2 预期一致：

- Flight Runtime control rate 为 `50 Hz`。Runtime process 被 `SIGSTOP` 后，Linux 冻结其
  用户态执行，因此它不能继续 control tick、rollback、best-effort revoke 或发布新的
  `INHIBITED` authority sample；冻结后的 command 和 authority publication cessation 才是
  正确预期。
- motor `motor_flight_command_timeout_sec=0.25`。最后合法 Flight command 把 deadline 设为
  receipt monotonic `+0.25 s`；`0.02 s` motion tick 调用 `timed_out()`，超时后 owner 先释放
  为 `NONE`，再 `halt_motion()`、退出 Flight `AUTO_RUNNING` 并发布 ownership。
- fan `fan_flight_command_timeout_sec=0.25`。`0.05 s` manager control tick 调用
  `timed_out()`，超时后 `force_safe_stop()` 将 command PWM 立即设为 `[800,800]`、发布停止值
  并保持 owner `NONE`。
- 两条 lease 都只由合法、递增且 token 匹配的 normal Flight envelope 刷新；invalid command
  和 safe-stop 不会成为 heartbeat。
- timeout 后 motor controller 返回 `MANUAL_RUNNING`/公开 `MANUAL` label，不等于自动
  legacy/manual recovery。C2 必须同时证明 ownership 保持 `NONE`，且没有普通 command 或
  movement。

因此 C1 与 C2 的 safety proof 已明确区分：C1 中 Runtime 仍活着，可自身 fail-close 到
`INHIBITED`；C2 中 Runtime 完全冻结，proof 来自 motor/fan lower-level independent leases，
不得要求被冻结的 Runtime 自己进入或发布 `INHIBITED`。

## C2 candidate 边界（未授权）

为减少新变量，下一次 C2 authorization review candidate 与最终 C1 使用相同 bounded
operating point：

```text
motor:
  left_pitch = captured baseline +0.05 rad
  other 3 motors = captured baseline hold

fans:
  LEFT = 0.05
  RIGHT = 0.0

power candidate:
  motor bus ON
  LEFT ESC ON
  RIGHT ESC OFF

IMU:
  normal default auto activation

pre-fault stabilization:
  legal ACTIVE 后约 3.0 s 自动 SIGSTOP

candidate max ACTIVE:
  10 s
```

这些值只是等待用户审查的 candidate，不是 C2 或任何硬件操作授权。

## Local-only C2 bundle

已准备且不进入 repository：

```text
/home/h-goal/windarmor_test_sessions/c2/
  RUNBOOK.md
  run_c2_runtime.sh
  c2_sigstop_on_active.py
```

目标目录在本轮开始时不存在，没有覆盖用户已有 local 文件。

### Exact PID strategy

`run_c2_runtime.sh` 先用 `ros2 pkg prefix windarmor_flight_control` 定位安装后的：

```text
lib/windarmor_flight_control/flight_control_runtime_node
```

source/package metadata 和当前安装结果均确认该路径存在。wrapper 在 `exec` 前将自身 PID
原子写入 local pidfile，再 `exec` 真正 Runtime executable；PID 保持不变，所以 pidfile
指向 actual Runtime process，而不是 `ros2 run` CLI wrapper。它保持 Terminal B 前台
stdout/stderr，不 daemonize、不 prepare。candidate 参数固定为 `left_pitch +0.05`、LEFT fan
`0.05`、RIGHT fan `0.0`、`flight_takeover_enabled=true`。本轮没有执行该 wrapper。

### Trigger/helper behavior

`c2_sigstop_on_active.py` 必须在 prepare 前启动。它先验证 pidfile、process existence、当前
UID、`/proc/<pid>/cmdline`、start time 和非 stopped/zombie/dead state；PID missing、reuse、
ambiguity 或 mismatch 都在 arm 前 fail。它先观察 non-ACTIVE，完成 subscription 后才输出：

```text
C2_TRIGGER_READY
C2_TRIGGER_ARMED
```

legal ACTIVE 要求 `ACTIVE / FLIGHT_CONTROL / actuation_allowed=true`，同时 motor/fan committed
且 owner token 匹配。约 `3.0 s` 后 helper 仅向 exact PID 发送一次 `SIGSTOP`，轮询
`/proc/<pid>/status` 确认 `T/t`，之后只读观察 command cessation、两 owner `NONE` 和 fan
`[800,800]`，并输出 monotonic marker/delta。helper 永不发送 `SIGCONT`，不 prepare、不发布
Flight command/E-STOP、不控制 motor/fan、不 kill 或 restart Runtime。helper PASS 只是辅助
trigger/transition evidence，不等于 C2 HARDWARE PASS。

## Recorder 与 timing acceptance 建议

默认 `record_gate_evidence.py` 的八个 topic 已覆盖 authority、Flight command、motor
feedback/safety/ownership 和 fan PWM/safety/ownership，C2 直接复用默认 recorder，不创建
C2 JSON config。Runtime SIGSTOP 后 authority publisher 没有新 frame 是 expected，不得误判
为 recorder failure；continuous ownership/PWM history 仍是 authoritative ROS evidence。

当前 timeout predicate 为 `now > last_valid_receipt + 0.25 s`。结合 motor `0.02 s` 与 fan
`0.05 s` control period，nominal core detection 上界约为 motor `0.27 s`、fan `0.30 s`，再加
ROS/DDS scheduling 和 observation latency。建议用户在 C2 执行前审查以下 candidate timing
acceptance window：

```text
以 continuous history 最后一帧 command 的 ROS stamp 为共同基准：
  motor owner NONE: >=0.25 s and <=0.40 s
  fan owner NONE:   >=0.25 s and <=0.40 s
  fan [800,800]:    >=0.25 s and <=0.40 s
```

`0.40 s` 只是基于现有 period 的 execution-review candidate，不是 production hardware SLA，
也没有擅自创造 `0.250000 +/- N ms` contract。超过该 window 应先归类为 timing review/
`NOT VERIFIED`，不能自动放宽。helper receipt monotonic 与 lower-level receipt 属于不同 DDS
subscriber，可能存在 delivery skew，所以 helper delta 只作辅助交叉核对，不单独执行
`>=0.25 s` 下界判定；略小于 `0.25 s` 时必须组合共同 ROS stamp、command sequence、
OwnershipState history、timeout 前的 `last_valid_flight_command_age_sec` 和 continuous recorder
审查。单一时间源不独立宣布 hardware PASS。

## Candidate safe exit review

future C2 candidate 应在 lower-level fail-close 和 operator physical stop 确认后继续 recorder，
先物理断开 LEFT ESC 与 motor actuator power，old Runtime 始终保持 STOPPED。只有 operator
确认 actuator power OFF 后，才允许对 exact frozen PID 使用 `SIGKILL`，不得 `SIGCONT`/`fg`。

Linux 下 `SIGTERM` 在 SIGSTOP-frozen process 上只能保持 pending，无法在不恢复用户态执行的
情况下完成 graceful cleanup。因此，在 actuator power 已物理断开后，对验证过 identity 的
exact PID 使用不可捕获的 `SIGKILL` 是不恢复旧 Runtime 的确定性终止方案。Runtime graceful
shutdown/restart 和 new epoch isolation 属于 C3，本场景不执行 restart。本轮没有执行任何
上述 safe-exit 动作。

## 本轮验证

已执行且通过：

```text
git status --short --branch
git branch --show-current
git rev-parse HEAD
source /opt/ros/jazzy/setup.bash
source install/setup.bash
ros2 pkg prefix windarmor_flight_control
test -x <prefix>/lib/windarmor_flight_control/flight_control_runtime_node
bash -n ~/windarmor_test_sessions/c2/run_c2_runtime.sh
python3 -m py_compile ~/windarmor_test_sessions/c2/c2_sigstop_on_active.py
python3 ~/windarmor_test_sessions/c2/c2_sigstop_on_active.py --self-test
git diff --check
```

helper pure self-test 覆盖 PID missing、cmdline mismatch、already stopped、starts ACTIVE、
valid ACTIVE、delay boundary、mock SIGSTOP、无 SIGCONT 和 observation success/failure；不连接
真实 ROS graph、不发送真实 signal。repository production Python/test 没有修改，因此未运行
900+ 完整 CI；硬件验证未执行，等待未来单独授权。

## 下一步

下一步只建议用户审查 local bundle、candidate powered boundary、`3.0 s` delay、`10 s` max
ACTIVE、`0.40 s` timing review window 和 safe-exit procedure，再决定是否单独授权 C2。当前
不得执行 C2，也不得进入 C3。
