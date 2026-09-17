# WindArmor 当前开发交接

> **INTERNAL DEVELOPMENT HANDOFF — MUTABLE。** 本文件只记录当前任务和对下一工作单元有价值的稳定工程状态。branch、push、PR、CI、merge 和 branch deletion 的实时生命周期状态以 Git / GitHub 为准；本文不是 release evidence source of truth。

## 当前状态

- 日期：2026-09-17
- 当前任务：`v0.5.0-011 — ALG-005 Candidate A Implementation`
- task branch：`feature/algo-005-candidate-a`
- task-start baseline：`develop@9d54137e003b6c95bb8bfb2e4df43556faf14adc`
- 当前 stable release：**v0.4.0**；previous stable：v0.3.2
- 下一版本研发目标：**v0.5.0 — Balance Recovery；NOT RELEASED**
- ALG-001～004：**QUALIFIED**；M1 software qualification chain：**COMPLETE / INTEGRATED**
- ALG-005 Task Spec：[v1 / INTEGRATED](algorithm_tasks/ALG-005.md)
- ALG-005 Profile：[v1 / INTEGRATED](ALGORITHM_BENCHMARK.md#12-alg-005-profile-v1)
- `ALG005-FIXTURE-v1` / `ALG005-SYNTHETIC-PLANT-v1`：**INTEGRATED / UNCHANGED**
- ALG-005 Candidate A：**IMPLEMENTED FOR REVIEW**
- implementation-stage software verification：**PASS**
- Formal Qualification：**NOT EXECUTED**
- Candidate Result：**NOT CREATED**
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

## 冻结测试与软件证据

[Benchmark helper](../src/windarmor_flight_control/test/alg005_benchmark.py) 编码冻结 Level D
D00/D01/D02/D03/D04/D90 scripted sequences；[Candidate tests](../src/windarmor_flight_control/test/test_alg005_candidate_a.py)
覆盖 R01/R02、F01、I01–I04、O01、全部历史 external-fault variants、timeout 加 transient fault、
validation reject、reset 和合法 variable dt。D02 检查第 14/15 stable-confirmation 帧，D90 检查
第 149/150 active update。独立 interval-list oracle 检查每帧 phase、elapsed、dwell 和 entry。
ALG-001～004 inheritance 在最终 process intent 上重新执行；ALG-004 requested-intent adapter
只替换 inherited request source，真实 production shaper 和最终 process manager 都执行，
process context 为无 active episode 的 `(0,0)`，没有 stub process manager。

Level E 为 **synthetic normalized software dynamic benchmark**，严格使用冻结 semi-implicit
Euler：`alpha=1.0*theta+6.0*u-2.4*omega+a_ext`，`dt=0.020 s`，先推进 omega 再推进 theta。
E00/E01/E02/E03/E04/E90 均完整运行；E04 恰在第 25 pre-step 后施加 rate impulse。
Metric 固定首次 DISTURBED/SETTLING origins，包含 entry 与 confirmation intervals，不因
setback 或后续 episode 改选更晚 origin；final settling interval 和 setback count 仅为诊断。
每帧同时检查 inherited target、envelope、slew、directed transition、合法 hold/safe-stop，
并执行三次完整重复、逐帧镜像、finite 和 final 25-sample stable tail 检查。

本轮仅形成 implementation-stage software evidence，不是 Formal Qualification，不写
`ALG-005 QUALIFIED`，不创建 `ALG-005_CANDIDATE_A.md`。

本轮最终 targeted 为 **639 passed**，ALG-001～005 Candidate regression 为 **1375 passed**；
两者均 0 errors、0 failures、0 skipped。ALG-001/002/003/004 inheritance、factory、configuration
serialization/validation、普通 hold 与 safe-stop command validation 全部 PASS。
`scripts/check_ci_safety.py`、`scripts/check_git_whitespace.py`、`git diff --check` 均 PASS。
仓库未发现独立 Markdown scanner；使用 local `/tmp` scanner 检查 README/本文件内部目标和
heading fragments，48 targets、0 failures。source/test/helper 只读审查确认无 ROS graph、
hardware backend、random 或 wall-clock scoring。

完整 `scripts/ci_software.sh`：**PASS / exit 0**。Python compile、五包 build/test 均 PASS；
tooling 26、motor 431、fan 159、flight/interfaces 1733 passed。最终 `colcon test-result`：
**2354 tests、0 errors、0 failures、0 skipped**。这些统计仅属于 implementation-stage 纯软件验证。

Level E 所有场景 implementation-stage gates PASS；镜像误差与三次重复 delta 为 0，全部
数值 finite。下表 P/N 指标相同，时间单位秒；显示舍入不参与 gate 比较。

| Scenario | recovery_time | settling_completion_time | final_settling_interval | setback count | overshoot ratio | effective pitch reversals |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| E00 | 未定义（无 episode） | 未定义 | 未定义 | 0 | 不评分 | 0 |
| E01P/N | 1.380 | 0.480 | 0.480 | 0 | 0.058974 | 0 |
| E02P/N | 1.680 | 0.480 | 0.480 | 0 | 0.090851 | 0 |
| E03P/N | 1.720 | 1.400 | 1.400 | 0 | 0.349105 | 1 |
| E04P/N | 1.760 | 0.540 | 0.540 | 0 | 不评分 | 0 |
| E90P/N | 未恢复 | 未定义 | 未定义 | 0 | 不评分 | 0 |

E00 全程 STABLE、无 episode/timeout；E90 在 3.000 s 精确 timeout、u=0.0、Level B safe-stop，
后续合法输入保持 latch。D03 setback 场景的 recovery/settling-completion/final-local intervals
分别为 0.800/0.700/0.400 s，setback count 为 1；完整首次起点评分未被局部时间缩短。

## 剩余边界与下一工作单元

实现软件 PASS 仍不能证明真实机器人动力学、真实执行器方向、安全或真实 Balance Recovery。
冻结 Task Spec/Profile 的 Candidate NOT IMPLEMENTED 是设计时 metadata，本轮不回写。
硬件验证未执行，原因是无硬件授权；Level C optional preview 未执行，不属于本轮必需检查。

下一步停在 Remote Review：review PASS 且 production/test 不需修改后，单独固定 exact
implementation SHA，再启动独立 Formal Qualification；若 changes requested，则在同一任务
分支修正、重新验证并创建新的普通 review commit。PR、merge、release 与硬件访问均不在本轮
授权范围内，ALG-006 actuator allocation 尚未启动。

## 历史证据保留

ALG-001 / ALG-002 / ALG-003 / ALG-004 Candidate A 固定 implementation commits 分别为
`fe575c9589013138d238e567e93dac2925384ab7`、`77e7b4f98e60602d3b224618225e11e9fecc8fe8`、
`240cda9f1c2b73dad7ae70bf0c2c9205a76f0364`、`5e78f7986ae6450596abd511b3d8c6d10b8881e8`。
相应正式 Result 保持不变。

v0.4.0 的 Gate B/C/D、PASS/FAIL/NOT VERIFIED、接线映射、release blocker、安全结论与证据
等级保存在 [硬件与功能验证记录](verification/v0.4.0/HARDWARE_VERIFICATION_RECORD.md)、
[硬件验证历史执行计划](V0.4.0_HARDWARE_VERIFICATION_PLAN.md) 和
[发布说明](RELEASE_NOTES_v0.4.0.md)。本任务不改变历史证据，不授权新硬件操作。
