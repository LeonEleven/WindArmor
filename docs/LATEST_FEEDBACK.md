# WindArmor 当前开发交接

> **INTERNAL DEVELOPMENT HANDOFF — MUTABLE。** 本文件只记录当前任务和对下一工作单元有价值的稳定工程状态。branch、push、PR、CI、merge 和 branch deletion 的实时生命周期状态以 Git / GitHub 为准；本文不是 release evidence source of truth。

## 当前状态

- 日期：2026-09-20
- 当前任务：`v0.5.0-013 — ALG-006 Task Spec + Control Allocation Benchmark Design`
- task branch：`docs/algo-006-spec-benchmark`
- task-start baseline：`develop@31d2a4b84f1cd25065f67704b5ba18b8837b11b5`
- 当前 stable release：**v0.4.0**；previous stable：v0.3.2
- 下一版本研发目标：**v0.5.0 — Balance Recovery；NOT RELEASED**
- ALG-001～005：**QUALIFIED / INTEGRATED**
- M1 software qualification chain：**COMPLETE / INTEGRATED**
- ALG-005 fixed implementation：`4f7e86e7526486e107a451d4332ff33565ce1e42`
- ALG-005 Formal Qualification：**PASS**
- ALG-006 Task Spec：[v1 / FROZEN DESIGN](algorithm_tasks/ALG-006.md)
- ALG-006 Profile：[v1 / FROZEN DESIGN](ALGORITHM_BENCHMARK.md#13-alg-006-profile-v1)
- allocation fixture：`ALG006-NORMALIZED-ALLOCATION-v1`
- ALG-006 Candidate：**NOT IMPLEMENTED**
- ALG-006 Candidate Result：**NOT CREATED**
- hardware access：**NO**
- hardware authorization：**NONE**
- hardware validation / Level F：**NOT AUTHORIZED / NOT EXECUTED**
- real actuator safety：**NOT VERIFIED**
- real Balance Recovery：**NOT VERIFIED**

## ALG-006 capability 与 contract

ALG-006 v1 只处理 **Normalized Actuator Coordination / Control Allocation**：保留 ALG-005
process outcome 的 timeout/fail-close 语义，把合法 ordinary final recovery intent `u` 归一化为
`r=u/0.10`，再分配到 task-local `motor_pitch_group`、`left_fan`、`right_fan` 和 signed
`residual`。`0.10` 继承 ALG-004 abstract software envelope，不是 actuator capability。

输入必须区分 ordinary STABLE zero 与 ALG-005 `TIMED_OUT` exact-zero sentinel；后者旁路
ordinary allocator、保留 latch 并走精确 `FlightCommand.safe_stop()`。external invalid/stale/
unhealthy/unknown/illegal-dt 同样在 ordinary allocation 前拒绝。out-of-contract ordinary `u`
不允许 silent clamp。

`ALG006-NORMALIZED-ALLOCATION-v1` 使用三个 dimensionless `[0,1]` synthetic authority：
`motor_authority`、`left_fan_authority`、`right_fan_authority`。对合法 ordinary input：

```text
r = u / 0.10
q = min(abs(r), motor_authority, left_fan_authority, right_fan_authority)
motor_pitch_group = sign(r) * q
left_fan = right_fan = q
residual = r - sign(r) * q
```

状态冻结为 `NEUTRAL / ALLOCATED / SATURATED / INFEASIBLE / FAIL_CLOSED`。该模型只表达
所有必需 normalized resources 共同可承载的 magnitude，不表示 motor/fan effectiveness 相同、
可以互相等效替代，也不表示 torque、thrust、RPM、PWM 或真实 recovery capability。

ALG-006 v1 不重新设计 ALG-005，不重调 gains，不新增 filter/output shaping；不处理 roll、
multi-axis、axis coupling、combined saturation、axis priority 或 differential fan，这些属于
ALG-007。allocator 保持 stateless，不增加 moving average、hysteresis、slew limiter 或 prior
command fallback。

## Benchmark 与 Level 决策

- Level A：**HARD GATE**，直接评分 normalized allocation seam、status、residual 和
  timeout/fail-close disposition；
- Level B：**HARD GATE**，评分 factory、state/command validation、完整 motor frame、fan frame
  和 exact safe-stop；当前没有 normalized motor request → absolute rad projection contract，
  ordinary payload 继续保持 ALG-005 的当前完整 motor position hold 与 fan-zero；
- Level C：optional preview only；
- Level D：**HARD GATE**，`ALG006-D00`～`D12` 覆盖 neutral、正负/full request、motor/fan
  bottleneck、known-zero authority、reversal、zero crossing、invalid request/authority、ALG-005
  timeout sentinel、reset replay 和至少三次 repeatability；
- Level E：**inheritance HARD GATE only**，未来 Candidate 原样重跑 ALG-005 Profile v1 Level E；
  ALG-006 v1 不新增没有 characterization 依据的 actuator dynamic plant；
- Level F：**NOT AUTHORIZED / NOT EXECUTED**。

未来 ALG-006 Candidate qualification 还必须在自身最终路径重新运行 ALG-001～005 全部 frozen
inheritance；历史 Result 不替代本轮 execution。ALG-005 Level E PASS 不能证明 ALG-006
allocation 的真实动态效果。

## Projection 与 hardware evidence gaps

现有 `motor_ids`、`motor_signs` 和 position soft limits 是 mapping/safety configuration，不是
recovery direction/effectiveness evidence。当前没有依据冻结 normalized motor group 到实际 rad
target 的 projection；若未来要求非零 executable payload，必须先独立建立 projection contract，
不能任意选择 rad scale、motor sign 或 fan PWM。

以下保持 **UNKNOWN / NOT VERIFIED**：real motor torque effectiveness、motor recovery
direction、normalized motor request → position rad projection、fan RPM/thrust/direction/moment
arm、left/right fan physical symmetry、motor/fan relative authority、actuator latency/rate/deadband/
cross-coupling、safe actuator recovery envelope、maximum recoverable disturbance、real closed-loop
Balance Recovery 和 sim-to-real equivalence。

## ALG-005 integrated evidence 保留

[ALG-005 Candidate Result](algorithm_results/ALG-005_CANDIDATE_A.md) 保持不变。ALG-005 fixed
implementation SHA `4f7e86e7526486e107a451d4332ff33565ce1e42` 的 Formal Qualification 为
PASS；Level A/B/D/E 均 PASS，targeted 为 639 passed，历史 ALG-001～004 regression 为
736 passed，完整 Software CI 的 `colcon test-result` 为 2354 tests、0 errors、0 failures、
0 skipped。该证据保持 hardware access `NO`、authorization `NONE`，不证明 real actuator
safety、maximum recoverable disturbance、sim-to-real 或 real Balance Recovery。

ALG-001 / ALG-002 / ALG-003 / ALG-004 Candidate A 固定 implementation commits 分别为
`fe575c9589013138d238e567e93dac2925384ab7`、`77e7b4f98e60602d3b224618225e11e9fecc8fe8`、
`240cda9f1c2b73dad7ae70bf0c2c9205a76f0364`、`5e78f7986ae6450596abd511b3d8c6d10b8881e8`；
相应正式 Results 保持不变。

## 下一工作单元边界

本工作单元只冻结 ALG-006 Task Spec/Profile 与持久状态，不实现 ALG-006 Candidate、不创建
Candidate Result、不修改 Flight API/Runtime/authority/ownership/hardware mapping/safety
mechanisms，也不访问 CAN、串口、GPIO/PWM、电机或风扇。Task Spec/Profile review 完成后，
Candidate implementation 必须作为独立工作单元启动；PR、merge、release 与硬件验证均不由
本文授权。

v0.4.0 的 Gate B/C/D、接线映射、release blocker、安全结论与证据等级保存在
[硬件与功能验证记录](verification/v0.4.0/HARDWARE_VERIFICATION_RECORD.md)、
[硬件验证历史执行计划](V0.4.0_HARDWARE_VERIFICATION_PLAN.md) 和
[发布说明](RELEASE_NOTES_v0.4.0.md)。本任务不改变历史证据，不授权新硬件操作。
