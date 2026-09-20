# WindArmor 当前开发交接

> **INTERNAL DEVELOPMENT HANDOFF — MUTABLE。** 本文件只记录当前任务和对下一工作单元有价值的稳定工程状态。branch、push、PR、CI、merge 和 branch deletion 的实时生命周期状态以 Git / GitHub 为准；本文不是 release evidence source of truth。

## 当前状态

- 日期：2026-09-20
- 当前任务：`v0.5.0-015 — ALG-006 Candidate A Formal Qualification + Candidate Result`
- task branch：`feature/algo-006-candidate-a`
- task-start baseline：`develop@ef5d70b90809b4668e1eeaab3a2dd1059b72727c`
- 当前 stable release：**v0.4.0**；previous stable：v0.3.2
- 下一版本研发目标：**v0.5.0 — Balance Recovery；NOT RELEASED**
- ALG-001～005：**QUALIFIED / INTEGRATED**
- ALG-006 Task Spec：[v1 / FROZEN](algorithm_tasks/ALG-006.md)
- ALG-006 Profile：[v1 / FROZEN](ALGORITHM_BENCHMARK.md#13-alg-006-profile-v1)
- ALG-006 fixed implementation：`9a7a624713010eff48cf7112b0501266eb24521e`
- ALG-006 Candidate Result：[Formal Qualification PASS](algorithm_results/ALG-006_CANDIDATE_A.md)
- ALG-006 engineering status：**QUALIFIED / NOT INTEGRATED**
- allocation fixture：`ALG006-NORMALIZED-ALLOCATION-v1`
- inherited dynamic fixture：`ALG005-SYNTHETIC-PLANT-v1`
- hardware access：**NO**
- hardware authorization：**NONE**
- hardware validation / Level F：**NOT AUTHORIZED / NOT EXECUTED**
- real actuator safety：**NOT VERIFIED**
- real Balance Recovery：**NOT VERIFIED**

## Formal Qualification 稳定结论

固定 implementation SHA 上 fresh 执行的 ALG-006 Level A/B/D、ALG-001～005 final-path
inheritance 和 ALG-005 Level E inheritance 全部通过：

- Formal ALG-006 targeted：289 passed，0 errors/failures/skipped；
- historical ALG-001～005 regression：1375 passed，0 errors/failures/skipped；
- D00～D12 全部 scenario/variant 与三轮 repeatability：PASS；
- maximum allocation mirror error：0.0；
- maximum repeatability delta：0.0；
- finite/status/disposition/prior-reuse violations：0；
- ALG-005 Level E E00/E01/E02/E03/E04/E90 P/N：PASS；
- full Software CI：2643 tests，0 errors、0 failures、0 skipped。

这些是 pure software、in-memory、fake/mock 和 normalized synthetic evidence，不是硬件验证。
Level C optional preview 未执行；Level F 未授权、未执行。

## ALG-006 capability 与 contract

ALG-006 Candidate A 保留 ALG-005 structured process outcome 的 timeout/fail-close 语义，把合法
ordinary final recovery intent `u` 归一化为 `r=u/0.10`，再按 common-`q` 分配到 task-local
`motor_pitch_group`、`left_fan`、`right_fan` 和 signed `residual`：

```text
q = min(abs(r), motor_authority, left_fan_authority, right_fan_authority)
motor_pitch_group = sign(r) * q
left_fan = right_fan = q
residual = r - sign(r) * q
```

`motor_authority/left_fan_authority/right_fan_authority` 只属于 Level A/D dimensionless synthetic
fixture；它们不是 `FlightState` field、Candidate configuration、Runtime hardware authority、
measured capability 或 health-to-effectiveness mapping。普通 Controller observation 固定使用
nominal `(1,1,1)`，唯一语义是 no extra synthetic benchmark bottleneck，不表示 physical
authority、full torque/thrust、hardware margin 或 safety evidence。

ordinary Level B 仍逐帧复制当前完整 motor feedback position hold，左右 fan 为 `0.0`；timeout、
internal allocation failure 与 external fault 均 exact safe-stop。ordinary zero 与 TIMED_OUT exact
zero sentinel 保持不同 disposition。五类 status、signed residual、左右对称、D04 fan exchange、
known-zero authority、reversal、zero crossing、reset 与 no-prior-reuse 均已通过 frozen Profile。

## ALG-001～005 inheritance

本轮 inheritance 经 ALG-006 final ordinary/fail-close path fresh 执行，不以历史 Result 代替：

- ALG-001 neutral/direction/proportional/symmetry/repeatability/reset/fail-close/Level B：PASS；
- ALG-002 zero-rate、diverging/recovering、signed damping、zero-pitch moving、dt 与 Level B：PASS；
- ALG-003 noise/signal、D00A/B/C、history/reset/mirror/repeatability/fail-close：PASS；
- ALG-004 envelope、current-dt slew、directed transition、steady/step/saturation/reversal、
  variable/invalid dt、history/reset：PASS；
- ALG-005 A/B/D/E、phase/timers/dwell/timeout latch、reset/fail-close：PASS。

ALG-005 Level E 仍是 `ALG005-SYNTHETIC-PLANT-v1` normalized software plant，不含 ALG-006
actuator dynamics，不能证明 motor/fan allocation 的真实动态效果。

## Projection 与 hardware evidence gaps

- normalized motor allocation → absolute rad projection：**NOT DEFINED / NOT IMPLEMENTED**；
- runtime actuator availability → normalized authority contract：**NOT DEFINED / NOT VERIFIED**；
- real motor torque effectiveness 与 motor recovery direction：**NOT VERIFIED**；
- fan RPM/thrust/direction/moment arm 与 left/right physical fan symmetry：**NOT VERIFIED**；
- motor/fan relative physical authority：**NOT VERIFIED**；
- actuator latency/rate/deadband/cross-coupling：**NOT VERIFIED**；
- safe actuator recovery envelope、maximum recoverable disturbance：**NOT VERIFIED**；
- sim-to-real equivalence、real actuator safety、dynamic closed-loop hardware recovery 与 real
  Balance Recovery：**NOT VERIFIED**。

不能任意选择 rad scale、`motor_signs`、fan PWM 或 synthetic actuator model 填补这些缺口。
若未来需要 availability/degraded/substitution 或 executable projection，必须先冻结独立 contract，
说明来源、单位、validity、fail-close 与真实 characterization 关系。

## 下一工作单元边界

当前持久结论是 ALG-006 **QUALIFIED / NOT INTEGRATED**。下一步是 Candidate Result remote
review；创建 PR、合入 `develop`、分支清理、release 与硬件验证均需要各自授权。不得把本轮
软件资格写成 M2 physical recovery complete、v0.5.0 released、real actuator safety verified
或 real Balance Recovery verified。

PR / merge：未由本任务授权。v0.5.0：**NOT RELEASED**。
