# WindArmor 当前开发交接

> **INTERNAL DEVELOPMENT HANDOFF — MUTABLE。** 本文件只记录当前任务和对下一工作单元有价值的稳定工程状态。branch、push、PR、CI、merge 和 branch deletion 的实时生命周期状态以 Git / GitHub 为准；本文不复制这些瞬时状态，也不是 release evidence source of truth。

## 当前状态

- 日期：2026-09-16
- 当前任务：`v0.5.0-010 — ALG-005 Task Spec + Dynamic Benchmark Design`
- task-start baseline：`origin/develop` / `fac618a58bd1f033ea128559f0a15f68da6a4340`
- 当前阶段：**ALG-005 Task Spec/Profile v1 DESIGN FROZEN / awaiting Remote Review**
- 当前 stable release：**v0.4.0**；previous stable：v0.3.2
- 下一版本研发目标：**v0.5.0 — Balance Recovery；未发布**
- ALG-001：**QUALIFIED**
- ALG-002：**QUALIFIED**
- ALG-003：**QUALIFIED**
- ALG-004：**QUALIFIED**
- M1 software qualification chain：**COMPLETE / INTEGRATED**
- ALG-005 Task Spec：[`v1 / DESIGN FROZEN`](algorithm_tasks/ALG-005.md)
- ALG-005 Profile：[`v1 / DESIGN FROZEN`](ALGORITHM_BENCHMARK.md#12-alg-005-profile-v1)
- Level D fixture：`ALG005-FIXTURE-v1 / DESIGN FROZEN`
- Level E plant：`ALG005-SYNTHETIC-PLANT-v1 / DESIGN FROZEN`
- ALG-005 Candidate：**NOT IMPLEMENTED**
- ALG-005 Candidate Result：**NOT CREATED**
- Level E benchmark：**DESIGN/FROZEN ONLY；NOT EXECUTED AS FORMAL CANDIDATE QUALIFICATION**
- Level F：**NOT AUTHORIZED / NOT EXECUTED**
- hardware access：**NO**
- hardware authorization：**NONE**
- hardware validation：**NOT AUTHORIZED / NOT EXECUTED**
- real actuator safety：**NOT VERIFIED / NOT CLAIMED**
- real Balance Recovery：**NOT VERIFIED / NOT CLAIMED**

## 本工作单元冻结的稳定范围

ALG-005 唯一新增能力定义为 Recovery Process。概念链路保持为 ALG-001 attitude feedback、
ALG-002 damping、ALG-003 input noise robustness、ALG-004 output shaping，再由 ALG-005 管理
recovery episode 并产生 final abstract process intent。资格观测冻结为 `STABLE`、`DISTURBED`、
`RECOVERING`、`SETTLING`、`TIMED_OUT`；这些是 task-local observable semantics，不要求未来
production Candidate 使用特定 FSM，也不改变公开 Flight API。

Profile v1 冻结 inclusive disturbance、settling 和 stable-confirmation thresholds、`0.300 s`
continuous stable dwell、`3.000 s` valid episode timeout，以及 reset、外部 fail-close、timeout
latch 和 ALG-001～005 history isolation。TIMED_OUT 的 abstract output 为零，Level B 使用现有
精确 `FlightCommand.safe_stop()`；普通合法输入不能解除 latch，只有显式 `reset()` 可以。

`ALG005-FIXTURE-v1` 是 Level D deterministic scripted process replay，覆盖 neutral、正负扰动、
正常恢复、settling setback、timeout、reset、fail-close、非法 `dt`、执行顺序、镜像与重复性；
它不是 dynamic simulation。

`ALG005-SYNTHETIC-PLANT-v1` 是 Level E deterministic normalized single-axis closed-loop model：

```text
alpha_k = 1.0 * theta_k + 6.0 * u_k - 2.4 * omega_k + a_ext_k
omega_(k+1) = omega_k + 0.020 * alpha_k
theta_(k+1) = theta_k + 0.020 * omega_(k+1)
```

Profile 冻结 E00、E01P/N、E02P/N、E03P/N、E04P/N、E90P/N，以及 recovery、settling、
timeout、overshoot、oscillation、finite、mirror 和 repeatability Hard Gates。该 plant 不包含
CyberGear、fan thrust、PWM、allocation matrix 或真实机械参数，不是可信真实机器人模型、
sim-to-real evidence 或硬件验证。

未来 ALG-005 Candidate 必须在 final process intent 上重新运行 ALG-001～004 inheritance；历史
PASS 不替代本轮资格。ALG-005 不重调 ALG-001/002 `Kp/Kd`，不替代 ALG-003 filtering，不绕过
ALG-004 envelope；ALG-006 actuator allocation、motor/fan mapping、ALG-007 multi-axis 和 ALG-008
full disturbance recovery 均未实现。Flight API、Runtime、authority、ownership、E-STOP、硬件
mapping 和现有安全机制未改变。

## 下一步

先对 ALG-005 Task Spec v1、Profile v1、`ALG005-FIXTURE-v1` 与
`ALG005-SYNTHETIC-PLANT-v1` 完成 Remote Review。Review PASS 后仍须用户单独授权创建 PR，并在
用户授权合入 `develop` 后，才允许另行启动：

```text
v0.5.0-011 — ALG-005 Candidate A Implementation
```

Candidate implementation、固定 implementation SHA 上的正式 qualification 和 Candidate Result
必须保持可追溯的独立步骤。当前工作单元不创建 Candidate、不创建 Result、不进入 ALG-006，
也不授权真实硬件测试。

## 历史证据保留

ALG-001 Candidate A 固定 implementation commit
`fe575c9589013138d238e567e93dac2925384ab7`；ALG-002 Candidate A 固定 implementation commit
`77e7b4f98e60602d3b224618225e11e9fecc8fe8`；ALG-003 Candidate A 固定 implementation commit
`240cda9f1c2b73dad7ae70bf0c2c9205a76f0364`；ALG-004 Candidate A 固定 implementation commit
`5e78f7986ae6450596abd511b3d8c6d10b8881e8`。相应正式 Result 保持不变。

v0.4.0 的 Gate B/C/D、PASS/FAIL/NOT VERIFIED、接线映射、release blocker、安全结论和证据等级
长期保存在 [硬件与功能验证记录](verification/v0.4.0/HARDWARE_VERIFICATION_RECORD.md)、
[硬件验证历史执行计划](V0.4.0_HARDWARE_VERIFICATION_PLAN.md) 和
[发布说明](RELEASE_NOTES_v0.4.0.md)。本任务不改变这些历史证据，也不授权新硬件操作。
