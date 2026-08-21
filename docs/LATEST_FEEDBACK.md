# 最新反馈：Gate C / C3 Flight Runtime graceful signal shutdown 修复

> 日期：2026-08-21
> 任务起点：`master` / `f1df97b22e36525cca6e52e49f58225c9732e713`
> 本轮性质：production graceful-shutdown 修复、pure/mock regression 与 C3 evidence 归档
> C3 结论：`HARDWARE NOT VERIFIED / SOFTWARE FIX COMPLETE / RETRY NOT AUTHORIZED`
> Gate C：`IN PROGRESS / NOT COMPLETE`

## 正式状态

```text
Gate B: COMPLETE
Gate C / C1: HARDWARE PASS
Gate C / C2: HARDWARE PASS
Gate C / C3: HARDWARE NOT VERIFIED / SOFTWARE FIX COMPLETE / RETRY NOT AUTHORIZED
Gate C / C4: NOT AUTHORIZED / NOT EXECUTED
Gate C: IN PROGRESS / NOT COMPLETE
```

C1/C2 的硬件 PASS 继续有效。本轮没有执行 C4，也不把 C3 已结束 session 的授权延伸到 retry。
本次软件修复没有启动 Flight Runtime、ROS graph、hardware node 或 launch，没有调用 prepare/
E-STOP，没有向真实进程发送 signal，也没有访问 CAN、GPIO、PWM、串口、IMU、motor 或 fan。

## C3 session classification

本轮归档的完整 C3 evidence session 为：

```text
/home/h-goal/windarmor_evidence/
  gate-evidence-20260821T021811.696548Z-1220232
```

正式分类为 `C3 NOT VERIFIED`，不是 C3 FAIL。以下正向证据保留：

- continuous legal ACTIVE 到 exact-PID SIGINT 为 `3.010030905 s`；
- helper `C3_STOP_RESULT=PASS`、exit 0；
- motor/fan physical stop，owners fail closed；
- NEW PID 与 `authority_epoch` fresh；
- NEW 持续 `DRY_RUN/NONE`、owners NONE、PWM `[800,800]`；
- restart 后没有 movement，也没有错误轴、错侧 fan、异常声音、振动、气味或温升；
- 最终 actuator power 已物理断开。

operator 在 `OLD_RUNTIME_EXIT_STATUS=1` 后仍启动了 NEW Runtime。NEW-half evidence 可作为
supplemental positive evidence 保留，但不能覆盖 OLD graceful-exit blocker，也不能使整体 C3
成为 PASS。

唯一 blocker 是 OLD Runtime 收到 exact-PID SIGINT 后非零退出：

```text
OLD_RUNTIME_EXIT_STATUS=1
RuntimeError: Unable to convert call argument '0' to Python object
Failed to publish log message to rosout: publisher's context is invalid
```

原 rclpy default SIGINT handler 先 invalidated context。`finally -> destroy_node()` 与
`runtime_shutdown` rollback 确实运行，actuator command gate、owners 与 PWM 均正确 fail-close；
但 executor 在 subscription `take_message` 抛出 RuntimeError，cleanup logging 也遇到 invalid
context。因此 blocker 是 graceful process shutdown，不是 actuator fail-close。

更早的 `/proc` false-positive preflight session 已归档到
`docs/V0.4.0_HARDWARE_VERIFICATION_PLAN.md`，不在本反馈重复展开。

## Python-controlled SIGINT/SIGTERM contract

Flight Runtime `main()` 现在显式使用：

```python
rclpy.init(
    args=args,
    signal_handler_options=SignalHandlerOptions.NO,
)
```

Runtime 在 init 前安装自己的 Python SIGINT/SIGTERM handler。首次 signal 到达时，handler 先把
SIGINT 与 SIGTERM 都设为 ignore，再抛出 `KeyboardInterrupt`，把控制权交给 `main()` 的
graceful cleanup；cleanup 入口再次确保两种 signal 均被忽略，因此第二个 signal 不能中断
rollback。退出顺序为：

```text
SIGINT or SIGTERM
-> Python KeyboardInterrupt
-> ROS context remains valid
-> FlightControlRuntimeNode.destroy_node()
-> runtime_shutdown rollback and local command gate close
-> best-effort motor/fan revoke
-> node destruction
-> rclpy.shutdown()
-> restore previous Python signal handlers
-> clean return
```

该修复没有吞掉 context-invalid `RuntimeError` 来伪造成功。只有 `KeyboardInterrupt` 进入正常
signal-shutdown path；普通 executor/Runtime `RuntimeError` 仍在 ordered cleanup 后传播并产生
nonzero。`destroy_node()` 自身异常也不会阻止 `rclpy.shutdown()` 尝试，异常仍不会被吞掉。

## Pure/mock validation

新增 `test_runtime_shutdown.py`，全部 mock `rclpy`、node 与 Python signal registration，不发真实
signal、不初始化 ROS context。3 项 focused tests 覆盖：

- `rclpy.init` 使用 `SignalHandlerOptions.NO`；
- SIGINT 与 SIGTERM 都进入 custom `KeyboardInterrupt` path并 clean return；
- cleanup 期间 context 仍 valid；
- `destroy_node()` 严格先于 `rclpy.shutdown()`；
- cleanup 中两种 signal 均为 ignored，第二个 signal不能中断；
- previous handlers 最终恢复；
- unexpected executor `RuntimeError` 仍传播。

已执行相关 Runtime/C1/C2 pure/mock regression：

```text
test_runtime_shutdown.py
test_runtime_node.py
test_runtime_handoff.py
test_runtime_safety_boundary.py
test_runtime_config.py
test_fan_estop_rollback_integration.py
结果：97 passed
```

既有 ACTIVE shutdown、owner service unavailable、runtime restart fresh epoch、required-input
stale rollback、E-STOP dominance 和 strict fan safety adapter 测试全部保持 PASS。该结果是
纯软件证据，不是 C3 hardware re-verification。

完整纯软件 CI 已执行：

```text
source /opt/ros/jazzy/setup.bash
./scripts/ci_software.sh

CI safety / whitespace / Python compile                            PASS
hardware verification tooling                                      26 passed
five-package colcon build                                           PASS
motor package pytest                                               431 passed
fan safety regression                                              159 passed
Flight and interface software tests                                304 passed
full workspace colcon test                    924 tests, 0 errors, 0 failures
```

所有测试均为 pure/fake/mock 或未连接 backend；未实例化真实 CAN、GPIO、PWM 或串口硬件。

## 修改范围与下一步

production 修改仅限 Flight Runtime process signal/shutdown orchestration，没有改变 ROS topic、
service、parameter、authority、ownership、command envelope、lease、E-STOP 或 actuator mapping。
README 与 hardware verification plan 已同步 C3 `NOT VERIFIED`、software blocker 与 retry boundary。

C3 仍需在软件修复完成后重新满足十项授权门槛并取得单独授权，再重跑 OLD graceful exit 与
NEW isolation。当前不得执行 wrapper/helper、不得启动真实 Runtime、不得供电或 prepare，
不得发送真实 signal，也不得进入 C4。
