# WindArmor 当前开发交接

> **INTERNAL DEVELOPMENT HANDOFF — MUTABLE。** 本文件只记录当前任务和对下一工作单元有价值的稳定工程状态。branch、push、PR、CI、merge 和 branch deletion 的实时生命周期状态以 Git / GitHub 为准；本文不是 release evidence source of truth。

## 当前状态

- 日期：2026-09-18
- 当前任务：`v0.5.0-012 — ALG-005 Candidate A Formal Qualification`
- task branch：`feature/algo-005-candidate-a`
- task-start baseline：`develop@9d54137e003b6c95bb8bfb2e4df43556faf14adc`
- fixed implementation / formal qualification tree：`4f7e86e7526486e107a451d4332ff33565ce1e42`
- implementation Remote Review：**PASS**
- 当前 stable release：**v0.4.0**；previous stable：v0.3.2
- 下一版本研发目标：**v0.5.0 — Balance Recovery；NOT RELEASED**
- ALG-001～004：**QUALIFIED**；M1 software qualification chain：**COMPLETE / INTEGRATED**
- ALG-005 Task Spec：[v1 / INTEGRATED](algorithm_tasks/ALG-005.md)
- ALG-005 Profile：[v1 / INTEGRATED](ALGORITHM_BENCHMARK.md#12-alg-005-profile-v1)
- `ALG005-FIXTURE-v1` / `ALG005-SYNTHETIC-PLANT-v1`：**INTEGRATED / UNCHANGED**
- ALG-005 Candidate A：**QUALIFIED / awaiting integration**
- Formal Qualification：**PASS**
- Candidate Result：[**CREATED**](algorithm_results/ALG-005_CANDIDATE_A.md)
- hardware access：**NO**
- hardware authorization：**NONE**
- hardware validation / Level F：**NOT AUTHORIZED / NOT EXECUTED**
- real actuator safety：**NOT VERIFIED**
- real Balance Recovery：**NOT VERIFIED**

## Candidate architecture 与行为

[Candidate module](../src/windarmor_flight_control/windarmor_flight_control/algorithms/alg005_candidate_a.py)
复用 `Alg004CandidateACore`，ordinary final process intent 为 **transparent ALG-004 pass-through**。
没有新 recovery control law，没有增益、输入 filter 或 output envelope 调整。固定配置继承
`Kp=1.0`、`Kd=0.1`、`window_size=2`、`max_abs_intent=0.10`、`max_slew_rate=2.0`，并稳定
序列化全部冻结过程阈值、`0.300 s` dwell 和 `3.000 s` timeout。配置不可变，拒绝 unknown key、
bool、string、None、NaN/Inf 与非 frozen 值。

Task-local immutable observation 表达 `STABLE`、`DISTURBED`、`RECOVERING`、`SETTLING`、
`TIMED_OUT`、final intent、episode elapsed、stable dwell、latch、首次 SETTLING 与 phase-entry
elapsed。首次 disturbance update 可观察 DISTURBED，并计入当前合法 dt。补偿 interval 求和
不使用 threshold tolerance 或 wall clock；setback 仅重置 dwell，不重置 episode/scoring origin。
完整 dwell 且 elapsed 小于 timeout 才能确认 STABLE；timeout 优先于同帧 dwell completion。

TIMED_OUT 精确输出 `u=0.0` 和 `FlightCommand.safe_stop()`，不再调用 ordinary core，不累计
后续 episode/dwell。只有显式 reset 清除 latch；reset 同时清除 ALG-001～005 全部 task-local
history。外部 fail-close 在未 timeout 时清除全部 history、下一合法输入与 fresh cold start
等价；已有 timeout 时清除 inherited ordinary history，冻结 process observation 并保留 latch。
validation-layer reject 仍前置拒绝，不冒充 controller safe-stop，由 harness 显式 reset 检查恢复。

普通 Level B 仍只返回当前合法完整 motor feedback position hold 和左右 fan-zero。
Factory 保持 `windarmor_flight_control.algorithms.alg005_candidate_a:create_controller`。
Candidate 不是 default controller，不实现 allocation，不改变 Flight API、Runtime、authority、
ownership、adapters、hardware mapping、E-STOP、watchdog、lease 或 soft limits。

## 本轮正式资格证据

全部正式命令在上述 exact implementation SHA 和干净工作区重新执行；
implementation-stage 旧日志未作为 Formal Qualification evidence。
[Candidate Result](algorithm_results/ALG-005_CANDIDATE_A.md) 保留本轮 metadata、实际环境、
13 字段稳定 JSON、命令、逐场景 metrics、gates、inheritance 与限制；本轮唯一原始证据目录为
`/tmp/windarmor-alg005-formal.zmtwCg`，所有 logs/JUnit/metrics/reporting scripts 均未加入 Git。

Formal targeted：**639 passed**；historical ALG-001～004 regression：
**47 + 84 + 172 + 433 = 736 passed**。两项均 exit 0、0 errors/failures/skipped。
ALG-005 inheritance 正式结论来自最终 process path 的新 Candidate 测试；
历史 Candidate 自身回归仅作额外 regression，四项 ALG-001/002/003/004 inheritance 均 PASS。
ALG-004 requested-intent fixture 只注入 inherited request source，production shaper 与真实
ALG-005 manager 均执行，不 stub process path。

Level A/B/D/E：**EXECUTED / PASS**。D00/D01/D02/D03/D04/D90 P/N、R01/R02、
F01、I01–I04、O01 均 PASS。D02 第 14/15 stable-confirmation updates 为
0.280 s / SETTLING 与 0.300 s / STABLE；D03 setback 清 dwell、保留 episode/first-settling
origins，recovery/settling-completion/final-local 为 0.800/0.700/0.400 s，setback count=1；
D90 第 149/150 active updates 为 2.980 s / NOT TIMED_OUT 与 3.000 s / TIMED_OUT，
随后 neutral 输入仍 u=0、exact safe-stop、latch 保持。

Level E 全部 11 scenarios 各三轮 complete runs，Recovery/Settling/Timeout/Overshoot/
Oscillation Gates 均 PASS。E01/E02/E03/E04 P/N recovery 分别为
1.380/1.680/1.720/1.760 s，overshoot ratios（E01～03）分别为
0.05897369503153988/0.09085088367664404/0.34910468559886176，effective pitch reversal
counts 为 0/0/1/0；所有 recoverable scenarios 末 25 帧/0.500 s stable tail PASS。
E00 无 episode、全程零值 STABLE；E90P/N NOT RECOVERED，在 3.000 s timeout 并 safe-stop。
maximum mirror delta=0.0，maximum three-run repeatability delta=0.0，finite violation count=0。
显示舍入不参与 gate；全部完整 metrics 与 phase timeline 见 Result。

factory、13 字段 frozen configuration serialization/rejection、non-default Candidate、
当前完整 feedback hold/fan-zero、command validation、reset、external fail-close 和 timeout
latch tests 均 PASS。stable-only exit 清 dwell、保持 SETTLING；timeout 优先于同帧 dwell completion。
Flight API、Runtime、hardware mapping 和既有 safety mechanisms 均未改变。

完整 `scripts/ci_software.sh`：**PASS / exit 0**，fresh build/test 输出在上述目录的
`ci-output`。tooling **26**、motor **431**、fan **159**、
Flight/interfaces **1733 passed**；五包 build/test PASS，
`colcon test-result` 为 **2354 tests、0 errors、0 failures、0 skipped**。
固定树 safety checker、whitespace checker 与 diff check PASS。
所有正式命令完成后、文档生成前，fixed SHA post-check 仍相同，working tree clean。

## 剩余边界与下一工作单元

**ALG-005 QUALIFIED** 仅指 fixed SHA + Profile v1 + fixture v1 + synthetic plant v1 的
软件资格。Level E 不证明可信真实机器人动力学、sim-to-real、执行器效果/安全、
最大可恢复真实扰动或真实 Balance Recovery。Level C optional preview 未执行，不属 Hard Gate；
Level F/真实硬件未授权且未执行。冻结 Task Spec/Profile 的设计时 Candidate metadata 保持不变。

下一步是 **Candidate Result Remote Review**；Result review PASS 后，由用户单独授权创建 PR。
本轮停在 Result review checkpoint，不自动 PR/merge/integration/release；
ALG-006 allocation、ALG-007 multi-axis、ALG-008 full disturbance recovery 均 NOT IMPLEMENTED，
ALG-006 不自动启动。硬件访问须另行明确授权。

## 历史证据保留

ALG-001 / ALG-002 / ALG-003 / ALG-004 Candidate A 固定 implementation commits 分别为
`fe575c9589013138d238e567e93dac2925384ab7`、`77e7b4f98e60602d3b224618225e11e9fecc8fe8`、
`240cda9f1c2b73dad7ae70bf0c2c9205a76f0364`、`5e78f7986ae6450596abd511b3d8c6d10b8881e8`。
相应正式 Result 保持不变。

v0.4.0 的 Gate B/C/D、PASS/FAIL/NOT VERIFIED、接线映射、release blocker、安全结论与证据
等级保存在 [硬件与功能验证记录](verification/v0.4.0/HARDWARE_VERIFICATION_RECORD.md)、
[硬件验证历史执行计划](V0.4.0_HARDWARE_VERIFICATION_PLAN.md) 和
[发布说明](RELEASE_NOTES_v0.4.0.md)。本任务不改变历史证据，不授权新硬件操作。
