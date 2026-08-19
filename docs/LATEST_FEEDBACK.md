# 最新反馈：C1 stale-input contract audit

> 本文件只保留当前最新任务反馈。
>
> 日期：2026-08-19

## Result

```text
task-start branch: master
task-start HEAD: 7b3f7d77c27f220f26f8f5f28b67f6a32a2ececb
Gate B: COMPLETE
Gate C: NOT EXECUTED / NOT AUTHORIZED
```

本次只完成 Gate C / C1 stale required input 的 software/document contract audit，不构成
C1 hardware PASS，也不授权任何 Gate C trigger。

## Confirmed Runtime contract

当前 ACTIVE stale-input 的实际路径为：

```text
build_runtime_snapshot()
→ IMU freshness 参与 required_inputs_fresh
→ _active_gate_reason()
→ _handoff_safety_reason() returns required_inputs_stale
→ _rollback_handoff()
→ local executable dispatch/tracking/authority/sequencer fail closed
→ best-effort motor and fan owner revoke
→ control tick returns before controller.update()
```

`_rollback_handoff()` 在调用任何外部 revoke 前，先关闭 command dispatch、使 handoff 和
command tracking 失效、清除 committed owner tracking、进入 Runtime INHIBITED，并通过
`_inhibit()` 使 envelope sequencer 失效。随后才分别尝试 motor/fan revoke；即使 cleanup
异常，lower-level command lease/backstop 仍承担 fail-closed 后盾。

C1 因此不再要求 controller 返回 `FlightCommand.safe_stop()`，也不要求 executable command
topic 额外出现 `request_safe_stop=true` frame。controller 主动 safe-stop 与 Runtime safety
gate 在 controller update 前 rollback 是两条不同安全路径。

C1 required evidence 已校准为：ACTIVE 前存在合法 bounded command；IMU lifecycle transition
和 `/imu/data_raw` cessation 证明 trigger；required input 变 stale；stale 后 command cutoff、
无旧 target 生成/replay；Runtime `ACTIVE → INHIBITED`；motor/fan owner
`FLIGHT_CONTROL → NONE`；actuator software/physical state 回到安全状态。
`flight_imu_freshness_sec=0.2` 仅作为 freshness threshold，不扩展为新的精确 hardware timing
SLA。

## Regression coverage

审查发现原有测试分别覆盖 IMU freshness aggregation、稳定的 `required_inputs_stale`
preflight reason、controller 主动 safe-stop transport，以及泛化 ACTIVE safety failure
rollback，但没有精确锁定以下完整不变量：

```text
ACTIVE + required_inputs_fresh=false
→ rollback before controller.update
→ no new executable envelope
```

因此在现有 `test_runtime_handoff.py` 中增加一个最小 pure software regression test，明确
验证：controller update count 不增加；不新增 executable envelope/safe-stop frame；authority
INHIBITED；command dispatch、command tracking 和 envelope sequencer 失效；两路 owner
revoke 都被尝试。没有新增 framework 或 integration harness。

## Modified files

```text
docs/V0.4.0_HARDWARE_VERIFICATION_PLAN.md
docs/LATEST_FEEDBACK.md
src/windarmor_flight_control/test/test_runtime_handoff.py
```

Runtime production code changes：`NONE`。

任务开始时已有的 `docs/NEXT_COMMAND.md` 修改属于用户工作区内容，本次按其执行但不覆盖
或回退。

## Validation

本次只运行 pure/fake/mock/static validation：

```bash
git diff --check
python3 -m pytest src/windarmor_flight_control/test/test_runtime_handoff.py -q
./scripts/ci_software.sh
```

结果：PASS。

```text
git diff --check: PASS
C1 targeted runtime handoff tests: 27 passed
CI safety check: PASS
Git whitespace check: PASS
Python compile: PASS
hardware verification tooling tests: 26 passed
colcon build: 5 packages PASS
motor package pytest: 431 passed
fan safety regression: 159 passed
Flight and interface software tests: 301 passed
full workspace colcon test: 919 tests, 0 errors, 0 failures, 0 skipped
```

这些检查均不构成硬件验证。

## Hardware and next step

- 没有启动硬件 node/launch，没有配置 CAN，没有访问真实 IMU/串口，没有 lifecycle 操作
  真实 IMU，没有操作 GPIO/PWM/CyberGear/ESC/fan，没有 authority prepare，没有 publish
  `/e_stop`，也没有执行任何 Gate C trigger。
- C1 motor axis、offset、fan command、powered actuator combination 和最大 ACTIVE duration
  继续保持 `TO BE SET BEFORE EXECUTION`，均未授权。
- 下一步仍是用户审查本次 C1 contract 修改后，再讨论 C1 hardware boundary；本任务不执行
  C1。

## Git limits

本次不创建或切换 branch，不 commit、push、tag，也不创建 GitHub Release。
