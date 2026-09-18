# ALG-005 Candidate A Result

本文记录固定 implementation commit `4f7e86e7526486e107a451d4332ff33565ce1e42` 上重新执行的
[Algorithm Benchmark v1 / ALG-005 Profile v1](../ALGORITHM_BENCHMARK.md#12-alg-005-profile-v1)
正式纯软件资格验证。Level D 使用 `ALG005-FIXTURE-v1`；Level E 使用
`ALG005-SYNTHETIC-PLANT-v1`，属于 normalized synthetic software closed-loop benchmark。
implementation-stage 旧日志未用作本轮正式证据；全部正式执行完成并复核固定树后才创建本文。

## Metadata 与 fixed implementation

| 字段 | 实际值 |
| --- | --- |
| Candidate | Candidate A |
| Task | v0.5.0-012 — ALG-005 Candidate A Formal Qualification + Candidate Result |
| Task Spec | ALG-005 / [Task Spec v1](../algorithm_tasks/ALG-005.md) |
| Benchmark | Algorithm Benchmark v1 / ALG-005 Profile v1 |
| Fixture | ALG005-FIXTURE-v1 |
| Dynamic Model | ALG005-SYNTHETIC-PLANT-v1 |
| Lineage | ALG-004 Candidate A inherited ordinary intent + ALG-005 Candidate A Recovery Process manager |
| Qualification branch | `feature/algo-005-candidate-a` |
| Task-start develop baseline | `9d54137e003b6c95bb8bfb2e4df43556faf14adc` |
| Implementation commit / formal qualification tree | `4f7e86e7526486e107a451d4332ff33565ce1e42` |
| Implementation Remote Review | PASS（本任务给定前置结论） |
| Benchmark date | 2026-09-18 |
| Hardware access | NO |
| Hardware authorization | NONE |
| Hardware validation | NOT AUTHORIZED / NOT EXECUTED |

以下 13 字段 JSON 来自本轮 fresh Candidate 的实际 configuration，按键稳定序列化；
本轮未改变任何字段或按场景调参：

```json
{"disturbance_pitch_rad": 0.04, "disturbance_pitch_rate_rad_s": 0.2, "kd_intent_per_rad_s": 0.1, "kp_intent_per_rad": 1.0, "max_abs_intent": 0.1, "max_slew_rate": 2.0, "recovery_timeout_sec": 3.0, "settling_pitch_rad": 0.02, "settling_pitch_rate_rad_s": 0.1, "stable_dwell_sec": 0.3, "stable_pitch_rad": 0.01, "stable_pitch_rate_rad_s": 0.05, "window_size": 2}
```

`git fetch origin` 后，本地 HEAD、origin task tracking ref 与
`git ls-remote --heads origin feature/algo-005-candidate-a` 均为固定 implementation SHA；
origin/develop 为上述 baseline。正式 targeted、历史回归、metrics 与完整 Software CI 前后，
HEAD 一致且工作区干净。创建 Result 之前执行的 `git diff` 与 `git diff --cached` 均为空，
无 tracked/untracked qualification artifact。记录见本轮 `preflight.txt`、
`pre-ci-fixed-tree.txt` 与 `fixed-sha-post-check.txt`。

## Environment / safety boundary

| 项目 | 本轮实际值 |
| --- | --- |
| OS | Ubuntu 24.04.4 LTS / Noble Numbat |
| Kernel / platform | Linux 6.8.0-1064-raspi aarch64 GNU/Linux |
| Architecture | arm64（dpkg 实际输出） |
| ROS distro | jazzy |
| Python | 3.12.3 |
| pytest / pluggy | 7.4.4 / 1.4.0 |
| pytest-cov | 4.1.0 |
| colcon-core / colcon-ros | 0.20.1 / 0.5.0 |
| colcon-cmake / colcon-python-setup-py | 0.2.29 / 0.2.9 |
| Qualification output | `/tmp/windarmor-alg005-formal.zmtwCg` |
| Fresh CI build/install/log | `/tmp/windarmor-alg005-formal.zmtwCg/ci-output` |

环境由本轮 `cat /etc/os-release`、`uname -srmo`、`dpkg --print-architecture`、
`python3 --version`、ROS setup 后的 `ROS_DISTRO` 和 `importlib.metadata.version()`
实际采集，保存于 `environment.txt`；没有新增依赖。version capture 覆盖 pytest、pluggy、
pytest-cov、colcon-core、colcon-ros、colcon-cmake、colcon-python-setup-py。

只读复核 [production module](../../src/windarmor_flight_control/windarmor_flight_control/algorithms/alg005_candidate_a.py)、
[benchmark helper](../../src/windarmor_flight_control/test/alg005_benchmark.py)、
[Candidate tests](../../src/windarmor_flight_control/test/test_alg005_candidate_a.py)、依赖与统一 CI
入口后，确认使用纯函数、in-memory state、fake/mock 和隔离的软件构建测试，不访问真实
CAN、串口、GPIO/PWM，不初始化 CyberGear、ESC 或 fan，不启动 hardware node/launch。
safety checker、Git whitespace checker 与 `git diff --check` 均 PASS。
Hardware access 为 NO，authorization 为 NONE；断电状态不作为启动硬件输出的授权。

## Candidate architecture

ordinary final process intent 为 **transparent ALG-004 pass-through**：复用 ALG-004
composite core 的 ALG-001 proportional、ALG-002 damping、ALG-003 两样本输入 history，
以及 ALG-004 clamp/slew。继承配置保持 Kp=1.0、Kd=0.1、window_size=2、U=0.10、S=2.0。

新增 recovery episode、STABLE/DISTURBED/RECOVERING/SETTLING/TIMED_OUT phase semantics、
valid-dt timers、continuous stable dwell、settling setback semantics 与 timeout latch。
immutable task-local observation 提供 final intent、episode elapsed、dwell、latch、首次
SETTLING entry 和当前 phase-entry elapsed；这些 seam 不是新公开 Flight API。
interval 以已接受正有限 dt 累计，补偿求和不使用 wall clock 或 threshold tolerance。
首次 disturbance update 计入当前 interval；timeout 优先于同帧 dwell completion。

没有 new control law、Kp/Kd retuning、新 input filter、integral/anti-windup 或 actuator
allocation。普通 Level B 命令仍复制当前完整合法 motor feedback position hold，左右 fan=0.0；
外部 fail-close 与内部 timeout 返回精确无载荷 `FlightCommand.safe_stop()`。
TIMED_OUT 的 final intent 精确为 0.0，且不继续调用 ordinary core。

## Verification Levels

| Level | 本轮状态 | 证据边界 |
| --- | --- | --- |
| A | EXECUTED / PASS | 最终 process intent、phase/timer/dwell、继承数值与 history |
| B | EXECUTED / PASS | factory、configuration、state/command validation、当前 hold 与 safe-stop |
| C | OPTIONAL PREVIEW / NOT EXECUTED | 非 Profile Hard Gate；不替代 A/B/D/E |
| D | EXECUTED / PASS | deterministic scripted process replay |
| E | EXECUTED / PASS | normalized single-axis synthetic closed-loop trajectories |
| F | NOT AUTHORIZED / NOT EXECUTED | 真实硬件未获授权 |

## Level D evidence

全部 D 场景完整执行三轮；独立 interval-list oracle 逐帧重算 phase、elapsed、continuous
dwell、first SETTLING entry 与 phase-entry elapsed，不复用 Candidate timer 作为 oracle。
普通最终 intent 同时检查 finite、U/S envelope 与 relative-to-inherited-target directed transition。

| Scenario / Gate | 本轮观测 | 结果 |
| --- | --- | --- |
| ALG005-D00 | 30 帧均 STABLE，无 active episode / timeout | PASS |
| ALG005-D01P/N | 15 neutral updates 后首次扰动帧 DISTURBED，下一帧 RECOVERING；entry dt 已计入 | PASS |
| ALG005-D02P/N | stable-confirmation 第 14 次 dwell=0.280 s / SETTLING，NOT STABLE；第 15 次 dwell=0.300 s / STABLE | PASS |
| ALG005-D03P/N | SETTLING → RECOVERING → SETTLING → STABLE；setback 清 dwell 且保留计时起点 | PASS |
| ALG005-D04P/N | (0.039,0.199) 不触发 episode；reset 后 rate=0.200 触发 DISTURBED；(0.020,0.100) inclusive SETTLING；(0.010,0.050) 满连续 dwell 后 STABLE | PASS |
| ALG005-D90P/N | active update 149 elapsed=2.980 s / NOT TIMED_OUT；150 elapsed=3.000 s / TIMED_OUT；随后稳定合法输入仍 latch / u=0 / exact safe-stop | PASS |
| ALG005-R01 | 非 timeout episode 后 reset 清全部 history 与 observation，后续等价 fresh | PASS |
| ALG005-R02 | timeout 后 explicit reset 清 latch 与全部 history，后续等价 fresh | PASS |
| ALG005-F01 | invalid/stale IMU、aggregate freshness、motor unavailable/stale/invalid/unhealthy、E-STOP unknown/active 的合法 variants 均 exact safe-stop | PASS |
| ALG005-I01–I04 | dt=0、-0.01、NaN、+Inf/-Inf 均 fail-close；未 latch 时清 history，已 latch 时保留 timeout | PASS |
| ALG005-O01 | D01/D02/D03/D04/D90 P/N 正序与反序重复，reset 后与 reference 相同；phase/timers/counts/metrics 对应 | PASS |

D02 的上述第 14/15 次 stable-confirmation update 对应完整 run 的 zero-based samples 37/38：
episode elapsed=0.460/0.480 s；first SETTLING entry 一直为 0.120 s。

D03 first disturbance 在 sample 15；首次 SETTLING sample 20 的 episode elapsed=0.120 s。
sample 29 dwell=0.100 s；sample 30 返回 RECOVERING，dwell=0.000 s、episode elapsed=0.320 s，
首次 SETTLING entry 仍为 0.120 s；sample 35 再次 SETTLING，elapsed=0.420 s 且同一 first entry。
sample 54 STABLE，elapsed=0.800 s、dwell=0.300 s。原 episode/recovery/first-settling origins
未重置；recovery_time=0.800 s、settling_completion_time=0.700 s、
final_settling_interval=0.400 s、settling_setback_count=1。first origin 不是后一次局部 entry。

D90 active update 149/150 对应完整 run samples 163/164；timeout 后 observation 冻结，
包含初始 disturbance update 的 150 个 0.020 s intervals。随后 5 个 neutral updates 均保持
TIMED_OUT、elapsed=3.000 s、u=0.0、exact safe-stop；只有 explicit reset 清 latch。
同帧 timeout/dwell completion precedence 与 stable-only envelope exit 额外测试均 PASS。

## Level E scenario evidence

每个 E 场景执行三次 **complete run**，不在 gate 达成时提前退出；本轮 reporting 独立产生
全部 33 条完整 trajectory，并调用 frozen `metrics()`。原始未舍入值与三轮全部样本保存在
`alg005-metrics.json`，`metrics-capture.log` 保存 readable capture。
下表显示时间为 s、pitch 为 rad、rate 为 rad/s、effort 为 abstract intent-unit·s。
稳态误差是末 25 帧 pitch 有符号均值的绝对值；overshoot 为首次 zero-crossing 后反向 peak。
显示舍入不参与 gate 比较；undefined 使用 —。E04 theta0=0，overshoot ratio 未定义且不评分；
E90 ratio 为 helper 的诊断值，不属于 Overshoot Hard Gate。

| Scenario | Recovery time | Settling completion | Final settling interval | Setback count | Peak abs pitch | Peak abs pitch rate | Final steady-state error | Control effort | Overshoot | Overshoot ratio | Oscillation count | Timeout | Result |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| ALG005-E00 | — | — | — | 0 | 0.000000000 | 0.000000000 | 0.000000000 | 0.000000000 | 0.000000000 | — | 0 | — | PASS / neutral |
| ALG005-E01P | 1.380 | 0.480 | 0.480 | 0 | 0.080000000 | 0.085665575 | 0.000263709 | 0.049626630 | 0.004717896 | 0.058973695 | 0 | — | PASS / recovered |
| ALG005-E01N | 1.380 | 0.480 | 0.480 | 0 | 0.080000000 | 0.085665575 | 0.000263709 | 0.049626630 | 0.004717896 | 0.058973695 | 0 | — | PASS / recovered |
| ALG005-E02P | 1.680 | 0.480 | 0.480 | 0 | 0.077034133 | 0.200000000 | 0.000161640 | 0.072172897 | 0.004542544 | 0.090850884 | 0 | — | PASS / recovered |
| ALG005-E02N | 1.680 | 0.480 | 0.480 | 0 | 0.077034133 | 0.200000000 | 0.000161640 | 0.072172897 | 0.004542544 | 0.090850884 | 0 | — | PASS / recovered |
| ALG005-E03P | 1.720 | 1.400 | 1.400 | 0 | 0.050000000 | 0.200000000 | 0.000168038 | 0.022873217 | 0.017455234 | 0.349104686 | 1 | — | PASS / recovered |
| ALG005-E03N | 1.720 | 1.400 | 1.400 | 0 | 0.050000000 | 0.200000000 | 0.000168038 | 0.022873217 | 0.017455234 | 0.349104686 | 1 | — | PASS / recovered |
| ALG005-E04P | 1.760 | 0.540 | 0.540 | 0 | 0.050344693 | 0.250000000 | 0.000003986 | 0.053475729 | 0.000000000 | — | 0 | — | PASS / recovered |
| ALG005-E04N | 1.760 | 0.540 | 0.540 | 0 | 0.050344693 | 0.250000000 | 0.000003986 | 0.053475729 | 0.000000000 | — | 0 | — | PASS / recovered |
| ALG005-E90P | — | — | — | 0 | 0.530037980 | 0.392044196 | 0.448682423 | 0.282015253 | 0.000000000 | 0.000000000 | 0 | 3.000 | PASS / TIMED_OUT / NOT RECOVERED |
| ALG005-E90N | — | — | — | 0 | 0.530037980 | 0.392044196 | 0.448682423 | 0.282015253 | 0.000000000 | 0.000000000 | 0 | 3.000 | PASS / TIMED_OUT / NOT RECOVERED |

下面 phase timeline 使用从完整 run 开始累计、包含当前 update interval 的有效时间。
它与 sample input timestamp `k*dt` 相差当前 interval；recovery 指标则从首次 DISTURBED
interval 起评分，包含 entry 与 confirmation。E04 先完成 25 neutral pre-steps，在 sample 25
注入 ±0.250 rad/s；首次 DISTURBED 的累计时间为 0.520 s，恢复时间为 1.760 s。

| Scenario | Samples / complete run | Phase timeline（累计有效时间 s） |
| --- | ---: | --- |
| ALG005-E00 | 200 | 0.020 STABLE |
| ALG005-E01N | 200 | 0.020 DISTURBED → 0.040 RECOVERING → 0.920 SETTLING → 1.380 STABLE |
| ALG005-E01P | 200 | 0.020 DISTURBED → 0.040 RECOVERING → 0.920 SETTLING → 1.380 STABLE |
| ALG005-E02N | 200 | 0.020 DISTURBED → 0.040 RECOVERING → 1.220 SETTLING → 1.680 STABLE |
| ALG005-E02P | 200 | 0.020 DISTURBED → 0.040 RECOVERING → 1.220 SETTLING → 1.680 STABLE |
| ALG005-E03N | 200 | 0.020 DISTURBED → 0.040 RECOVERING → 0.340 SETTLING → 1.720 STABLE |
| ALG005-E03P | 200 | 0.020 DISTURBED → 0.040 RECOVERING → 0.340 SETTLING → 1.720 STABLE |
| ALG005-E04N | 225 | 0.520 DISTURBED → 0.540 RECOVERING → 1.740 SETTLING → 2.260 STABLE |
| ALG005-E04P | 225 | 0.520 DISTURBED → 0.540 RECOVERING → 1.740 SETTLING → 2.260 STABLE |
| ALG005-E90N | 175 | 0.020 DISTURBED → 0.040 RECOVERING → 3.000 TIMED_OUT |
| ALG005-E90P | 175 | 0.020 DISTURBED → 0.040 RECOVERING → 3.000 TIMED_OUT |

E00 全程 theta=omega=u=0、STABLE，无 episode/timeout，不能把未定义 recovery 填成 0。
E90P/N 未恢复，在 active update 150 首次 timeout elapsed=3.000 s；之后所有帧 u=0.0、
exact safe-stop、observation/latch 保持，plant 仍按冻结规则推进，不能把 fail-close 称为 recovery。

## Recovery / Settling / Timeout Gates

| Gate | 冻结要求与本轮实际证据 | 结果 |
| --- | --- | --- |
| Recovery | E01/E02/E03/E04 P/N 均观察 DISTURBED、RECOVERING、SETTLING、final STABLE；max recovery_time=1.760 s ≤ 2.500+1e-9 s；末 25 帧/0.500 s 均在 stable envelope 内，无 TIMED_OUT | PASS |
| Settling | inclusive envelope、continuous 0.300 s dwell、无 early STABLE；stable-only exit 清 dwell 且保持 SETTLING，settling exit 回 RECOVERING；setback 保留 first origins，final 连续 SETTLING 进入 STABLE | PASS |
| Timeout | E90P/N 首次 timeout=3.000 s，满足 [3.000,3.020)；NOT RECOVERED、u=0、exact safe-stop，latch 至 explicit reset | PASS |

settling_completion_time 从首次 SETTLING 到 final confirmation 的 intervals 计算；
final_settling_interval 只记录 final 连续 SETTLING 段，setback count 记录至 final confirmation。
后两者为 Profile 诊断指标，未自行增加门槛。D03 和额外多 episode origin 测试证明不得改选更晚
origin 缩短 recovery/settling 指标；stable-only exit 清 dwell 不重选首次 SETTLING origin。

## Overshoot / Oscillation Gates

| Gate | 本轮实际值 / 冻结门槛 | 结果 |
| --- | --- | --- |
| E01P/N Overshoot | 0.05897369503153988 ≤ 0.50+1e-9 | PASS |
| E02P/N Overshoot | 0.09085088367664404 ≤ 0.50+1e-9 | PASS |
| E03P/N Overshoot | 0.34910468559886176 ≤ 0.50+1e-9 | PASS |
| E01/E02/E03/E04 P/N Oscillation | effective pitch sign reversal counts 分别 0/0/1/0，均 ≤ 2 | PASS |

Oscillation 使用 frozen metric 的 pitch significant-sign threshold `abs(theta)>0.005 rad`，
不是 Candidate 新增 deadband，也不是历史 ALG-004 intent reversal threshold 的替代。

## Mirror / repeatability / finite

| 指标 | 本轮实际值 | 结果 |
| --- | ---: | --- |
| Maximum theta / omega / u mirror delta | 0.0 / 0.0 / 0.0 | PASS |
| Maximum requested / alpha / external-acceleration mirror delta | 0.0 / 0.0 / 0.0 | PASS |
| Maximum aligned samples / observation / timers mirror delta | 0.0 | PASS |
| Maximum dynamic/scripted metrics mirror delta | 0.0 | PASS |
| Maximum three-complete-run pairwise repeatability delta | 0.0 | PASS |
| Finite violation count（D/E 三轮样本、observations、payload、metrics） | 0 | PASS |

D01/D02/D03/D04/D90 与 E01/E02/E03/E04/E90 共 10 对 P/N，phase transition sample、
timer、dynamic metrics、integer counts 和 Level B command 均对应；phase/boolean/counts 精确相同。
全部 11 个 D 和 11 个 E 场景各完整重复三次；所有采集到的有效数值 finite。
三轮 metrics 也相同；None 仅用于合法 undefined observation/metrics，不计作 non-finite violation。

## Reset / fail-close / timeout latch

R01/R02、外部 14 种 fault/dt variants × latched/unlatched 共 28 cases、core invalid-input、
validation reject、legal variable dt、stable-only exit 和 simultaneous timeout/dwell tests 均 PASS。
explicit reset 清 ALG-001～005 task-local history、episode/dwell/entry observations 和 latch。
未 timeout 的外部 transient fault cold-start 等价 fresh；已有 timeout 的 transient fault
清 inherited history 而保留 process observation/latch。latched 合法输入不调用 ordinary core；
only explicit reset clears timeout。validation-layer 非法完整测量由 validation 拒绝、
不调用 controller；harness explicit reset 后再验证恢复，不冒充 controller-layer safe-stop。
reset 不改变 Runtime authority、E-STOP、真实 IMU zero 或硬件状态。

## ALG-001～004 inheritance

下列四项都来自本轮 `test_alg005_candidate_a.py` 的真实 **ALG-005 final process path**，
没有用历史 Candidate 自身 PASS 代替：

| Inheritance | 本轮覆盖 | 结果 |
| --- | --- | --- |
| ALG-001 | neutral、direction、proportional relationship、symmetry、repeatability、fail-close、reset、factory / Level B；六帧保持、首帧方向/finite 与末三帧关系 | PASS |
| ALG-002 | zero-rate、diverging/recovering trend、signed damping、zero-pitch moving、symmetry、dt、fail-close/reset、Level B | PASS |
| ALG-003 | Q noise、meaningful signal/trend preservation、D00A/B/C、history/reset、fail-close、mirror/repeatability | PASS |
| ALG-004 | 最终 ordinary u envelope、current-dt slew、directed transition、neutral、steady、step、saturation、full/high-frequency reversal、variable/invalid dt、reset/history、mirror/repeatability | PASS |

ALG-004 requested-intent fixture 的 adapter 只注入 inherited request source；
真实 production ALG-004 shaper 和 ALG-005 process manager 仍执行，manager 输入 (0,0) 的合法
inactive ordinary context，不 stub final process manager。普通最终 u 满足 abs(u)≤0.10
及 slew≤2.0*current dt（按冻结容差），方向相对 inherited clamped target。
D00A=0.020 s、D00B=0.037 s、D00C=0.020/0.037 s 交替；跨 segment 不重启 schedule。
另外重新执行的历史 ALG-001～004 regression 为 736 passed，属于独立额外 regression evidence。

## Level B / factory / configuration

Factory：`windarmor_flight_control.algorithms.alg005_candidate_a:create_controller`。
default/explicit frozen configuration loader PASS，Candidate A 为 non-default；
default NeutralExampleController 与 teaching ExampleAlgorithmController 保持独立。
13 字段稳定 JSON serialization、immutable configuration/observation、unknown key、
bool/string/None/NaN/±Inf/non-frozen **字段值**拒绝全部 PASS；省略 configuration 允许冻结默认值。
non-mapping 配置拒绝按实际 factory/config contract 检查，不把省略默认配置说成非法输入。

普通 command 精确复制每帧当前合法完整四电机 position hold，左右 fan=0.0；
不同 motor baseline、正常 fixture、外部 fail-close 和 timeout command validation 均 PASS。
所有 controller fail-close/timeout 均精确 `FlightCommand.safe_stop()`，无 actuator payload。
actuator allocation：NOT IMPLEMENTED，abstract intent 不编码为 motor/fan direction。

## Comparative implementation metrics

按 [ALG-005 Profile v1 §12.11](../ALGORITHM_BENCHMARK.md#1211-comparative-metrics-与版本边界)
补充以下 comparative metrics。Configuration clarity 的依据是本文已有固定 implementation
SHA 的配置序列化、默认值和拒绝测试证据；本次文档补充没有重新执行或替换 Formal Qualification。

| Metric | Result / method |
| --- | --- |
| Production physical LOC | 235 lines |
| LOC method | 对下方 fixed implementation Git object 执行 `git show … \| wc -l`；仅 production ALG-005 module，包含 code、blank lines、comments、docstrings |
| Cyclomatic complexity | NOT MEASURED；本次未安装工具或依赖 |
| Configuration fields | 13 frozen fields |
| Stable serialization | PASS；使用 Metadata 中原有稳定 JSON，值未改变 |
| Frozen defaults | PASS；省略 configuration 时使用唯一冻结默认配置 |
| Units / semantics documented | PASS；逐字段见下表 |
| Invalid / unknown / non-frozen rejection | PASS；沿用已有正式配置验证证据 |
| Scenario-specific tuning | NO |
| dt-specific tuning | NO |
| Post-result tuning | NO |
| Configuration clarity | PASS |

Physical LOC 精确测量命令与实际输出：

```bash
git show \
  4f7e86e7526486e107a451d4332ff33565ce1e42:src/windarmor_flight_control/windarmor_flight_control/algorithms/alg005_candidate_a.py \
  | wc -l
# 实际输出：235
```

该 `wc -l` 口径与 ALG-004 Result 一致，仅计 fixed implementation SHA 的 ALG-005 production
module；不计 benchmark helper、tests、inherited ALG-004 module、README 或 docs。
Cyclomatic complexity: NOT MEASURED。上述指标不合成总分，不用于未定义的候选排名。

| Configuration field | Frozen value | Unit | Semantics |
| --- | ---: | --- | --- |
| `kp_intent_per_rad` | 1.0 | intent unit / rad | inherited proportional feedback gain |
| `kd_intent_per_rad_s` | 0.1 | intent unit / (rad/s) | inherited signed damping gain |
| `window_size` | 2 | samples | inherited two-sample input moving average |
| `max_abs_intent` | 0.10 | intent unit | inherited ordinary intent clamp magnitude U |
| `max_slew_rate` | 2.0 | intent unit / s | inherited current-dt ordinary output slew limit S |
| `disturbance_pitch_rad` | 0.040 | rad | inclusive absolute pitch disturbance threshold；与 rate guard 为 OR |
| `disturbance_pitch_rate_rad_s` | 0.200 | rad/s | inclusive absolute pitch-rate disturbance threshold |
| `settling_pitch_rad` | 0.020 | rad | inclusive absolute pitch settling threshold；与 rate guard 为 AND |
| `settling_pitch_rate_rad_s` | 0.100 | rad/s | inclusive absolute pitch-rate settling threshold |
| `stable_pitch_rad` | 0.010 | rad | inclusive absolute pitch stable-confirmation threshold；与 rate guard 为 AND |
| `stable_pitch_rate_rad_s` | 0.050 | rad/s | inclusive absolute pitch-rate stable-confirmation threshold |
| `stable_dwell_sec` | 0.300 | s | stable envelope 内连续有效 dt 的确认时长 |
| `recovery_timeout_sec` | 3.000 | s | active episode 有效 dt timeout threshold；优先于同帧 dwell completion |

Candidate v1 的 legal policy 是 13 个字段仅接受各自 frozen exact value，`window_size` 须为
integer 2；这不是开放 numeric range 或调参接口。字段值 bool、string、None、NaN/±Inf、
non-frozen value，以及 unknown key、non-mapping configuration 均拒绝；省略 configuration
合法并选择 frozen defaults，不将省略配置与非法字段值 None 混淆。
Benchmark / Formal Qualification 使用同一固定 configuration：NO scenario-specific tuning、
NO dt-specific tuning、NO post-result tuning；本次补充没有改变原有 JSON 或任何配置值。
**Configuration clarity: PASS**，依据为参数数量、稳定序列化、唯一默认值、明确单位/语义、
frozen legal-value policy 与已有非法配置拒绝证据齐全。

## Future-task boundary

ALG-006 allocation：NOT IMPLEMENTED；ALG-007 multi-axis：NOT IMPLEMENTED；
ALG-008 full disturbance recovery：NOT IMPLEMENTED。Flight API、Runtime、default controller、
hardware mapping 均 UNCHANGED；authority、ownership、adapters、E-STOP、watchdog、lease、
soft limits 和硬件安全退出机制均未改动。ALG-006 未自动启动，v0.5.0 NOT RELEASED。

## Actual commands and test statistics

以下命令在创建任何 tracked Result/status 修改之前、固定 SHA 上实际执行。
各日志/JUnit/metrics/环境证据和 reporting scripts 均在唯一 output directory 内。
环境捕获和 preflight 详见前文；测试 pipe 保留真实退出状态，全部 exit 0。

```bash
QUAL_DIR="/tmp/windarmor-alg005-formal.zmtwCg"
source /opt/ros/jazzy/setup.bash
set -o pipefail

python3 scripts/check_ci_safety.py
python3 scripts/check_git_whitespace.py
git diff --check

PYTHONPATH=src/windarmor_flight_control python3 -m pytest -p no:cacheprovider \
  src/windarmor_flight_control/test/test_alg005_candidate_a.py -q \
  --junitxml="$QUAL_DIR/alg005-targeted.xml" 2>&1 | tee "$QUAL_DIR/alg005-targeted.log"

PYTHONPATH=src/windarmor_flight_control python3 -m pytest -p no:cacheprovider \
  src/windarmor_flight_control/test/test_alg001_candidate_a.py \
  src/windarmor_flight_control/test/test_alg002_candidate_a.py \
  src/windarmor_flight_control/test/test_alg003_candidate_a.py \
  src/windarmor_flight_control/test/test_alg004_candidate_a.py -q \
  --junitxml="$QUAL_DIR/alg001-004-regression.xml" 2>&1 | tee "$QUAL_DIR/alg001-004-regression.log"

PYTHONPATH=src/windarmor_flight_control python3 "$QUAL_DIR/capture_metrics.py" \
  2>&1 | tee "$QUAL_DIR/metrics-capture.log"

WINDARMOR_CI_OUTPUT_ROOT="$QUAL_DIR/ci-output" ./scripts/ci_software.sh \
  2>&1 | tee "$QUAL_DIR/software-ci.log"

git status --short --branch
git rev-parse HEAD
git diff
git diff --cached
```

| 本轮 fixed-tree 执行 | 实际统计 | 结果 |
| --- | --- | --- |
| Formal ALG-005 targeted | 639 passed；0 errors/failures/skipped | PASS / exit 0 |
| Historical ALG-001～004 regression | 47 + 84 + 172 + 433 = 736 passed；0 errors/failures/skipped | PASS / exit 0 |
| Frozen D/E reporting | 11 D + 11 E scenarios，各三轮 complete runs；原始 JSON、mirror/repeatability/finite 采集 | PASS / exit 0 |
| CI tooling | 26 passed | PASS |
| CI motor | 431 passed | PASS |
| CI fan | 159 passed | PASS |
| CI Flight/interfaces | 1733 passed | PASS |
| CI Python compile / five-package build | 通过 | PASS |
| CI full workspace colcon test | five packages finished | PASS |
| CI colcon test-result | 2354 tests、0 errors、0 failures、0 skipped | PASS |
| Full Software CI | 上述统一入口全部完成 | PASS / exit 0 |
| Fixed SHA post-check | HEAD=4f7e86e7526486e107a451d4332ff33565ce1e42；tracked/untracked working tree clean | PASS |

JUnit 与原始 CI log 核对以上数量；`junit-summary.json`、`software-ci-stats.json` 与
`evidence-provenance.json` 保存提取统计及原始证据 SHA-256。2354 是 colcon 汇总，
不与重复执行的 targeted/历史回归/分包 pytest 合并为虚构 unique-test 总数。
文档修改后单独检查 whitespace 和内部 Markdown link/anchor，不重新执行改后树测试冒充
上述 exact implementation evidence。临时原始证据未加入 Git，Result 保留稳定工程结果。
仓库未发现独立 Markdown scanner；本轮使用 output directory 内的 local 只读 scanner，
检查这四份文档的内部 link targets 与 GitHub heading fragments：77 targets、0 failures。

## Tests not executed

- Level C optional synthetic DRY_RUN preview：NOT EXECUTED；不是 Profile v1 Hard Gate。
- Level F / hardware validation：NOT AUTHORIZED / NOT EXECUTED，原因是硬件授权 NONE。
- 真实 CAN、真实 IMU 串口、GPIO/PWM、电机/风扇、powered scenario、Runtime hardware launch：
  未执行；本轮没有设备访问或硬件状态变更。
- Trusted robot simulation、actuator effectiveness、maximum recoverable physical disturbance、
  sim-to-real 与真实 Balance Recovery：未执行/未验证，不由本次 synthetic plant 代替。

## Known limitations

Level E 是 normalized synthetic software plant，使用冻结
`alpha=1.0*theta+6.0*u-2.4*omega+a_ext` 与 dt=0.020 s 的 semi-implicit Euler，
先更新 omega 再更新 theta；完整 step order 和 E04 impulse placement 独立测试 PASS。
它不能证明 trusted real robot model、sim-to-real equivalence、actuator effectiveness、
real actuator safety、maximum recoverable disturbance 或 real Balance Recovery。
Level D 只是 deterministic scripted replay，不是 dynamic simulation 或 hardware replay。
U/S 是 abstract software envelope，不是 CyberGear/PWM/thrust 的真实安全包线。
真实执行器方向、分配、受限 powered hardware 验证仍需独立设计、评审与明确授权。

## Overall

**Formal Qualification: PASS**

**Overall: ALG-005 QUALIFIED**

资格只限定于固定 implementation SHA `4f7e86e7526486e107a451d4332ff33565ce1e42` +
Algorithm Benchmark v1 / ALG-005 Profile v1 + ALG005-FIXTURE-v1 +
ALG005-SYNTHETIC-PLANT-v1 的软件行为。real actuator safety：NOT VERIFIED；
real Balance Recovery：NOT VERIFIED；hardware access：NO；authorization：NONE；
hardware validation：NOT AUTHORIZED / NOT EXECUTED；v0.5.0：NOT RELEASED。
