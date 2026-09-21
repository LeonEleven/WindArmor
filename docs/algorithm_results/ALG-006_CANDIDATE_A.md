# ALG-006 Candidate A Result

本文记录 ALG-006 Candidate A 在固定 implementation commit
`9a7a624713010eff48cf7112b0501266eb24521e` 上，针对
[Algorithm Benchmark v1 / ALG-006 Profile v1](../ALGORITHM_BENCHMARK.md#13-alg-006-profile-v1)
和 `ALG006-NORMALIZED-ALLOCATION-v1` 执行的正式纯软件资格验证。ALG-005 Level E
inheritance 原样使用 `ALG005-SYNTHETIC-PLANT-v1` 并经过 ALG-006 Candidate 最终路径；它不包含
ALG-006 actuator dynamics，也不是硬件、sim-to-real 或真实 Balance Recovery 证据。

## Metadata 与 fixed implementation

| 字段 | 实际值 |
| --- | --- |
| Candidate | Candidate A |
| Task | v0.5.0-015 — ALG-006 Candidate A Formal Qualification + Candidate Result |
| Task Spec | ALG-006 / [Task Spec v1](../algorithm_tasks/ALG-006.md) |
| Benchmark | Algorithm Benchmark v1 / ALG-006 Profile v1 |
| Fixture | ALG006-NORMALIZED-ALLOCATION-v1 |
| Inherited dynamic fixture | ALG005-SYNTHETIC-PLANT-v1 |
| Qualification branch | `feature/algo-006-candidate-a` |
| Task-start baseline | `ef5d70b90809b4668e1eeaab3a2dd1059b72727c` |
| Implementation commit / formal qualification tree | `9a7a624713010eff48cf7112b0501266eb24521e` |
| Implementation Remote Review | PASS（本任务给定前置结论） |
| Benchmark date | 2026-09-20 |
| Hardware access | NO |
| Hardware authorization | NONE |
| Hardware validation | NOT AUTHORIZED / NOT EXECUTED |

`git fetch origin` 后，本地 HEAD、task tracking ref 与远端 task branch 均精确为上述 fixed SHA，
`origin/develop` 为 task-start baseline。正式测试、metrics 与 Software CI 完成后再次核对，固定
SHA 未变且 tracked working tree 仍干净；随后才创建本文。

## Configuration

以下 JSON 来自本轮 fresh Candidate 实际 configuration，按键稳定序列化，共 13 个 inherited
frozen fields：

```json
{"disturbance_pitch_rad":0.04,"disturbance_pitch_rate_rad_s":0.2,"kd_intent_per_rad_s":0.1,"kp_intent_per_rad":1.0,"max_abs_intent":0.1,"max_slew_rate":2.0,"recovery_timeout_sec":3.0,"settling_pitch_rad":0.02,"settling_pitch_rate_rad_s":0.1,"stable_dwell_sec":0.3,"stable_pitch_rad":0.01,"stable_pitch_rate_rad_s":0.05,"window_size":2}
```

省略 configuration 使用上述唯一冻结默认值；显式提供完整冻结配置可接受。unknown key、非法
字段、non-frozen value、non-mapping configuration 均按实际 factory contract 拒绝。synthetic
`motor_authority/left_fan_authority/right_fan_authority` 不是配置字段。本轮
scenario-specific tuning：NO；dt-specific tuning：NO；post-result tuning：NO。

## Environment / safety boundary

| 项目 | 本轮实际值 |
| --- | --- |
| OS | Ubuntu 24.04.4 LTS / Noble Numbat |
| Kernel / platform | Linux 6.8.0-1064-raspi aarch64 GNU/Linux |
| Architecture | arm64 |
| ROS distro | jazzy |
| Python | 3.12.3 |
| pytest / pluggy | 7.4.4 / 1.4.0 |
| pytest-cov | 4.1.0 |
| colcon-core / colcon-ros | 0.20.1 / 0.5.0 |
| colcon-cmake / colcon-python-setup-py | 0.2.29 / 0.2.9 |
| Qualification output | `/tmp/windarmor-alg006-formal.kDpg2D` |

环境由本轮 `/etc/os-release`、`uname -srmo`、`dpkg --print-architecture`、`python3 --version`、
ROS setup 后的 `ROS_DISTRO` 与 `importlib.metadata` 实际采集；未安装新依赖。只读复核 Candidate、
benchmark helpers、tests、直接依赖、CI 入口与 safety checker 后，确认所有正式命令只使用纯函数、
in-memory state、fake/mock 和隔离的软件构建测试，不连接 CAN 或串口，不访问 GPIO/PWM，不创建
CyberGear driver、ESC、真实 fan controller、hardware node 或 launch，也不使用 `sudo`。

## Candidate architecture / evidence boundary

Candidate 保留 ALG-005 structured process outcome、phase 与 timeout latch，把合法 ordinary final
intent 归一化后执行 common-`q` task-local allocation，输出 signed motor group、对称 fan pair、
signed residual、status 与 disposition。普通 Controller observation 固定使用 nominal
`(1,1,1)`，其唯一语义是 **no extra synthetic benchmark bottleneck**。Level B 仍复制当前完整
motor position hold 并输出 fan-zero；没有 physical projection，且不从运行状态推导 numerical
authority。

## Verification Levels

| Level | 本轮状态 | 结论边界 |
| --- | --- | --- |
| A | EXECUTED / PASS | normalized allocation、status、residual、disposition、fail-close |
| B | EXECUTED / PASS | factory/config、validation、current hold、fan-zero、exact safe-stop |
| C | OPTIONAL PREVIEW / NOT EXECUTED | 非 Hard Gate，不替代 A/B/D/E |
| D | EXECUTED / PASS | `ALG006-NORMALIZED-ALLOCATION-v1` deterministic replay |
| E | ALG-005 INHERITANCE — EXECUTED / PASS | 原样 ALG005 synthetic plant；无 ALG-006 actuator plant |
| F | NOT AUTHORIZED / NOT EXECUTED | 真实硬件未获授权 |

## Level A / D evidence

全部 frozen scenario/variant 至少完整重复三次。下表数值为未舍入计算的可读显示；判定使用
Profile 的 `abs_tol=1e-9`、`rel_tol=1e-6`，exact 项没有使用 tolerance。

| Scenario | r | q / motor / fans | residual | status / disposition | 结果 |
| --- | ---: | --- | ---: | --- | --- |
| D00 | 0 | 0 / 0 / 0,0 | 0 | NEUTRAL / ORDINARY | PASS |
| D01P/N | ±0.25 | 0.25 / ±0.25 / 0.25,0.25 | 0 | ALLOCATED / ORDINARY | PASS |
| D02P/N | ±1.0 | 1.0 / ±1.0 / 1.0,1.0 | 0 | ALLOCATED / ORDINARY | PASS |
| D03P/N | ±0.8 | 0.6 / ±0.6 / 0.6,0.6 | ±0.2 | SATURATED / ORDINARY | PASS |
| D04L/R | +0.8 | 0.4 / +0.4 / 0.4,0.4 | +0.4 | SATURATED / ORDINARY | PASS；fan authority exchange error 0.0 |
| D05 motor/left/right zero | +0.8 | 0 / 0 / 0,0 | +0.8 | INFEASIBLE / ORDINARY | PASS；无 substitution/prior reuse |
| D06 | +0.8 → -0.8 | motor +0.8 → -0.8；fans 0.8 → 0.8 | 0 → 0 | ALLOCATED / ORDINARY | PASS；无 hysteresis/stale reuse |
| D07 | +0.25 → 0 → -0.25 | middle frame exact all-zero | 0 | ALLOCATED → NEUTRAL → ALLOCATED | PASS |
| D08 | NaN、+Inf、-Inf、+0.100001、-0.100001 | exact zero diagnostic payload | 0 | FAIL_CLOSED / INVALID_CONTRACT | PASS；越界未被 tolerance 接受 |
| D09 | 三项 authority 各自取 None、unknown、NaN、±Inf、-0.1、1.1、bool true/false | exact zero diagnostic payload | 0 | FAIL_CLOSED / INVALID_CONTRACT | PASS；27 variants |
| D10 | TIMED_OUT、latched、u=0 | exact zero diagnostic payload | 0 | FAIL_CLOSED / TIMEOUT | PASS；不是 NEUTRAL，latch 保留 |
| D11 | 建立 allocation → reset → D03P replay | replay 与 fresh 三帧逐字段相同 | — | RESET 后 ordinary path | PASS |
| D12 | D00～D10 完整 mixed sequence ×3 | 三轮逐字段相同 | — | status/disposition exact | PASS |

五类状态 `NEUTRAL/ALLOCATED/SATURATED/INFEASIBLE/FAIL_CLOSED` 均实际观察。所有 ordinary
result 满足 common-`q`、左右 fan 对称、output bounds 与 signed residual；timeout、external
fail-close、invalid contract 和 internal failure 的处置保持可区分。

| 汇总指标 | 本轮实际值 | 结果 |
| --- | ---: | --- |
| Maximum P/N allocation mirror error | 0.0 | PASS |
| D04 L/R exchange error | 0.0 | PASS |
| Maximum three-run repeatability delta | 0.0 | PASS |
| Finite violation count | 0 | PASS |
| Status/disposition mismatch count | 0 | PASS |
| Prior-reuse violation count | 0 | PASS |

## Level B / factory / fail-close

Factory `windarmor_flight_control.algorithms.alg006_candidate_a:create_controller` 的 omitted 与显式
冻结配置均加载成功；synthetic authority key、unknown key、invalid/non-frozen field 与 non-mapping
config 均拒绝。正有限 `dt=0.020/0.037 s` 被接受；非法 `dt=0/-0.01/NaN/±Inf` 均 exact
safe-stop 并 cold-reset ordinary history。

两个不同 motor baseline 的 fresh capture 均逐键精确复制当前
`left_lift/left_pitch/right_pitch/right_lift` position，左右 fan 精确为 `0.0`，没有复用上一帧。
普通与 safe-stop command 全部通过 `validate_flight_command()`。IMU invalid/stale、aggregate
stale、motor stale/unhealthy/unobserved、E-STOP unknown/active、internal allocator/process failure
均 exact `FlightCommand.safe_stop()`。TIMED_OUT sentinel 保持 latch 直到 explicit reset；reset 后
ordinary zero 为 NEUTRAL。

## ALG-001～005 inheritance

下列证据来自本轮 ALG-006 targeted suite 对 **ALG-006 final ordinary/fail-close path** 的实际执行，
不是历史 Result 替代：

| Inheritance | 覆盖 | 结果 |
| --- | --- | --- |
| ALG-001 | neutral、direction、proportional relation、symmetry、repeatability、reset、fail-close、Level B | PASS |
| ALG-002 | zero-rate、diverging/recovering、signed damping、zero-pitch moving、mirror、dt、fail-close/reset、Level B | PASS |
| ALG-003 | noise suppression、signal preservation、D00A/B/C、history、reset、mirror、repeatability、fail-close | PASS |
| ALG-004 | final output envelope、current-dt slew、directed transition、neutral/steady/step/saturation、full/high-frequency reversal、variable/invalid dt、history/reset、mirror/repeatability | PASS |
| ALG-005 | structured outcome、phase/timers/dwell、timeout latch、A/B/D/E、reset/fail-close、mirror/repeatability | PASS |

## ALG-005 Level E inherited evidence

每个 E scenario 通过 `Alg006CandidateAController` 最终 integration path 完整运行三次，不在 gate
达成时提前退出。时间单位为 s；显示值不改变未舍入 gate 判定。

| Scenario | Recovery | Settling completion | Peak pitch / rate | Steady error | Effort | Overshoot ratio | Reversals / timeout | 结果 |
| --- | ---: | ---: | --- | ---: | ---: | ---: | --- | --- |
| E00 | — | — | 0 / 0 | 0 | 0 | — | 0 / — | PASS / neutral |
| E01P/N | 1.380 | 0.480 | 0.080000 / 0.085666 | 0.000263709 | 0.049626630 | 0.058973695 | 0 / — | PASS / recovered |
| E02P/N | 1.680 | 0.480 | 0.077034 / 0.200000 | 0.000161640 | 0.072172897 | 0.090850884 | 0 / — | PASS / recovered |
| E03P/N | 1.720 | 1.400 | 0.050000 / 0.200000 | 0.000168038 | 0.022873217 | 0.349104686 | 1 / — | PASS / recovered |
| E04P/N | 1.760 | 0.540 | 0.050345 / 0.250000 | 0.000003986 | 0.053475729 | — | 0 / — | PASS / recovered |
| E90P/N | — | — | 0.530038 / 0.392044 | 0.448682423 | 0.282015253 | diagnostic only | 0 / 3.000 | PASS / TIMED_OUT / NOT RECOVERED |

Recovery、Settling、Timeout、Overshoot、Oscillation、finite、mirror 和 repeatability gates 全部
PASS。Level E maximum mirror error `0.0`，maximum three-run repeatability delta `0.0`，finite
violations `0`，phase/status/count exact mismatches `0`。该 plant 只消费 ALG-005 final abstract
intent，不包含 ALG-006 motor/fan allocation dynamics，不能证明 allocation 已物理执行。

## Comparative implementation metrics

| Metric | Result / method |
| --- | --- |
| Per-scenario r/q/allocation/residual/fraction/bottleneck/status | 见 Level A/D 表；full-allocation fraction 1.0，D03 为 0.75，D04 为 0.5，D05 为 0.0 |
| Maximum mirror error | 0.0 |
| Maximum repeatability delta | 0.0 |
| Production physical LOC | 383 lines |
| LOC method | 对 fixed Git object 的 `alg006_candidate_a.py` 执行 `git show … \| wc -l`；包含 code、blank、comment、docstring，不含 helper/tests/docs/inherited ALG-005 |
| Cyclomatic complexity | NOT MEASURED；环境未安装工具，本轮未安装新依赖 |
| Configuration clarity | PASS；13 frozen fields、稳定序列化、唯一默认值、非法/unknown/non-frozen 拒绝、无 tuning |

这些指标不合成总分，也不构成 candidate ranking。

## Actual commands and statistics

正式执行使用 `set -o pipefail`，原始 log、JUnit、metrics、环境和 pre/post-check 均保存在唯一
qualification output directory。主要命令为：

```bash
PYTHONPATH=src/windarmor_flight_control python3 -m pytest -p no:cacheprovider \
  src/windarmor_flight_control/test/test_alg006_candidate_a.py -q \
  --junitxml="$QUAL_DIR/alg006-targeted.xml"

PYTHONPATH=src/windarmor_flight_control python3 -m pytest -p no:cacheprovider \
  src/windarmor_flight_control/test/test_alg001_candidate_a.py \
  src/windarmor_flight_control/test/test_alg002_candidate_a.py \
  src/windarmor_flight_control/test/test_alg003_candidate_a.py \
  src/windarmor_flight_control/test/test_alg004_candidate_a.py \
  src/windarmor_flight_control/test/test_alg005_candidate_a.py -q \
  --junitxml="$QUAL_DIR/alg001-005-historical-regression.xml"

PYTHONPATH=src/windarmor_flight_control \
  python3 "$QUAL_DIR/capture_alg006_metrics.py" "$QUAL_DIR"

WINDARMOR_CI_OUTPUT_ROOT="$QUAL_DIR/ci-output" ./scripts/ci_software.sh
```

| 执行 | 实际统计 | 结果 |
| --- | --- | --- |
| Formal ALG-006 targeted | 289 passed；0 errors/failures/skipped；exit 0 | PASS |
| Historical ALG-001～005 regression | 1375 passed；0 errors/failures/skipped；exit 0 | PASS |
| ALG-006 allocation capture | 45 atomic variants ×3；D06/D07/D11/D12；exit 0 | PASS |
| ALG-005 Level E through ALG-006 | 11 scenarios ×3 complete runs；exit 0 | PASS |
| CI tooling | 26 passed | PASS |
| CI motor | 431 passed | PASS |
| CI fan | 159 passed | PASS |
| CI Flight/interfaces | 2022 passed | PASS |
| CI Python compile / five-package build | 完成 | PASS |
| CI full workspace colcon test | five packages finished | PASS |
| CI colcon test-result | 2643 tests、0 errors、0 failures、0 skipped | PASS |

临时 metrics capture 第一次仅因 reporting serializer 不支持只读 `mappingproxy` 而退出；它没有
修改 Candidate、fixture、threshold 或 repository。只修正 `/tmp` reporting script 的通用 Mapping
序列化后从头重跑，最终 capture exit 0；首次失败日志也保留在 evidence directory。不同层级的
重复执行数量没有相加为虚构 unique-test count。

## Documentation / evidence validation

| 检查 | 本轮结果 |
| --- | --- |
| `python3 scripts/check_ci_safety.py` | PASS |
| `git diff --check` / cached diff check | PASS |
| `python3 scripts/check_git_whitespace.py` | PASS |
| Repository-standard Markdown link scan | NOT EXECUTED — no repository-standard scanner found |
| Local supplementary Markdown link check | PASS；4 changed docs，76 local targets，0 failures |
| Evidence SHA-256 manifest | CREATED；1540 files，`sha256sum --check` PASS |

JUnit summary、Software CI statistics、environment、pre/post fixed-tree checks、raw allocation/Level E
JSON、两次 reporting logs、temporary reporting/checking scripts 与 provenance 均保存在
qualification output directory，未加入 Git。Candidate Result 只保存稳定工程结论。

## Hard Qualification checklist

| Hard Gate | 结果 |
| --- | --- |
| Metadata / fixed SHA / config / Profile / fixture / environment / commands | PASS |
| Structured ALG-005 outcome / timeout sentinel | PASS |
| Normalization / bounds / out-of-envelope fail-close | PASS |
| Authority validity / bounds / synthetic-only source semantics | PASS |
| Controller nominal `(1,1,1)` semantics | PASS |
| Common-q / output bounds / status / signed residual | PASS |
| Left/right symmetry / D04 / no differential over-allocation | PASS |
| D00～D12 and all variants | PASS |
| Five status classes / reversal / zero crossing | PASS |
| Reset / external fail-close / timeout latch / fresh-start equivalence | PASS |
| Finite / mirror / at least three repeats | PASS |
| Factory / configuration / Level B validation / current hold / fan-zero / exact safe-stop | PASS |
| ALG-001 inheritance | PASS |
| ALG-002 inheritance | PASS |
| ALG-003 inheritance | PASS |
| ALG-004 inheritance | PASS |
| ALG-005 A/B/D/E inheritance | PASS |
| No ALG-007 leakage | PASS |
| No API/Runtime/authority/hardware mapping/safety change | PASS |
| Hardware access NO | PASS |

## Future-task boundary / known evidence gaps

- normalized motor allocation → absolute rad projection：**NOT DEFINED / NOT IMPLEMENTED**；
- runtime actuator availability → normalized authority contract：**NOT DEFINED / NOT VERIFIED**；
- real motor torque effectiveness 与 motor recovery direction：**NOT VERIFIED**；
- fan RPM/thrust/direction/moment arm 与 left/right physical symmetry：**NOT VERIFIED**；
- motor/fan relative physical authority：**NOT VERIFIED**；
- actuator latency/rate/deadband/cross-coupling：**NOT VERIFIED**；
- safe actuator recovery envelope、maximum recoverable disturbance：**NOT VERIFIED**；
- sim-to-real equivalence、real actuator safety、dynamic closed-loop recovery on hardware 与 real
  Balance Recovery：**NOT VERIFIED**。

## Tests not executed

- Level C optional preview：NOT EXECUTED；不是 Profile v1 Hard Gate。
- Level F：NOT AUTHORIZED / NOT EXECUTED。
- 真实 CAN、IMU 串口、GPIO/PWM、电机、风扇、ESC、hardware node/launch：NOT EXECUTED。
- ALG-006 actuator dynamic plant：NOT ADDED / NOT EXECUTED；Profile v1 明确禁止无依据模型。

## Overall

**Formal Qualification: PASS**

**Overall: ALG-006 QUALIFIED**

该结论只适用于 fixed implementation SHA、Algorithm Benchmark v1 / ALG-006 Profile v1、
`ALG006-NORMALIZED-ALLOCATION-v1` 与 ALG-005 inheritance 的纯软件证据。Candidate 尚未通过
PR/merge 进入 `develop`，因此状态为 **QUALIFIED / NOT INTEGRATED**；v0.5.0 仍为
**NOT RELEASED**。real actuator safety 与 real Balance Recovery 均为 **NOT VERIFIED**。
