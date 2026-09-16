# ALG-004 Candidate A Result

本文记录 ALG-004 Candidate A 在固定 implementation commit
`5e78f7986ae6450596abd511b3d8c6d10b8881e8` 上，针对
[Algorithm Benchmark v1 / ALG-004 Profile v1](../ALGORITHM_BENCHMARK.md#11-alg-004-profile-v1)
和 `ALG004-FIXTURE-v1` 执行的正式纯软件资格验证。Level D 是 deterministic software
replay，不是 dynamic simulation、hardware replay、real actuator safety 或真实 Balance
Recovery evidence。

## Metadata 与固定起点

| 字段 | 实际值 |
| --- | --- |
| Candidate | Candidate A |
| Task | ALG-004 / [Task Spec v1](../algorithm_tasks/ALG-004.md) |
| Benchmark | Algorithm Benchmark v1 / ALG-004 Profile v1 |
| Fixture | ALG004-FIXTURE-v1 |
| Lineage | ALG-003 Candidate A inherited feedback semantics + ALG-004 Candidate A output shaping |
| Qualification branch | `feature/algo-004-candidate-a` |
| Implementation task baseline | `1cfab2f22d82d1468ac3ad5fd37ad7b6380c9065` |
| Production algorithm initial review checkpoint | `5e78f7986ae6450596abd511b3d8c6d10b8881e8` |
| Implementation commit / formal qualification tree | `5e78f7986ae6450596abd511b3d8c6d10b8881e8` |
| Configuration | `{"kd_intent_per_rad_s": 0.1, "kp_intent_per_rad": 1.0, "max_abs_intent": 0.1, "max_slew_rate": 2.0, "window_size": 2}` |
| Benchmark date | 2026-09-15 |
| Hardware access | NO |
| Hardware authorization | NONE |
| Hardware validation | NOT EXECUTED / NOT AUTHORIZED |

正式 qualification 前通过 `git fetch origin`、`git status --short --branch`、
`git rev-parse HEAD`、远端 tracking ref 与 `git ls-remote` 核对本地和远端固定 SHA。工作区
干净；targeted、历史回归、指标、完整 Flight 回归和 fixed-tree CI 完成后，HEAD 仍精确等于
上述 implementation SHA，随后才创建本文。

## 实际环境与安全边界

| 项目 | 实际值 |
| --- | --- |
| OS | Ubuntu 24.04.4 LTS (Noble Numbat) |
| Kernel / platform | Linux 6.8.0-1064-raspi aarch64 GNU/Linux |
| Architecture | arm64 |
| ROS distro | jazzy |
| Python | 3.12.3 |
| pytest / pluggy | 7.4.4 / 1.4.0 |
| pytest-cov | 4.1.0 |
| colcon-core / colcon-ros | 0.20.1 / 0.5.0 |
| colcon-cmake / colcon-python-setup-py | 0.2.29 / 0.2.9 |
| Qualification output | `/tmp/windarmor-alg004-formal.xrmO9b` |
| Flight build overlay | `/tmp/windarmor-alg004-formal.xrmO9b/preflight-build/install` |

环境值由本轮 `/etc/os-release`、`uname -srmo`、`dpkg --print-architecture`、
`python3 --version`、Python `importlib.metadata` 和 ROS setup 后的 `ROS_DISTRO` 实际采集；本次
未新增依赖。测试前只读复核 production、fixture、tests、CI 入口与 safety checker。所有测试
只使用纯函数、in-memory `FlightState`、fake/mock/依赖注入和软件 build，不打开串口，不连接
CAN，不访问 GPIO/PWM，不启动 ROS hardware node/launch、电机或风扇。

## 配置、算法语义与层级

Candidate A 复用 ALG-003 Candidate A 的 `Kp=1.0 intent/rad`、
`Kd=0.1 intent/(rad/s)`、`window_size=2` 两样本输入移动平均语义。它先把 inherited abstract
intent clamp 到 `[-0.10,+0.10] intent unit`，再以当前真实 `dt` 和
`2.0 intent unit/s` 做对称、time-normalized slew limiting。cold start、reset 或
controller-layer fail-close 后，previous shaped intent 精确回到 `0.0`，且 ALG-003 输入历史也
被原子清除。

配置键、值、单位与语义明确；稳定 JSON 序列化通过。测试拒绝 bool、string、`None`、NaN、
Inf、unknown key、非 frozen 值和非 mapping，不允许运行期、场景或 dt-specific tuning。
Configuration clarity：PASS。没有 actuator mapping；普通 Level B 命令只保持当前完整 motor
feedback position，左右 fan 均为 `0.0`。

| Level | 本次状态 | 结论边界 |
| --- | --- | --- |
| A | EXECUTED / PASS | composite core、输出 contract、history、继承反馈语义 |
| B | EXECUTED / PASS | factory、FlightState/FlightCommand、当前完整帧、safe-stop |
| C | NOT EXECUTED | 不属于 ALG-004 Profile v1 Hard Gate |
| D | EXECUTED / PASS | `ALG004-FIXTURE-v1` deterministic software replay |
| E | NOT REQUIRED | 当前 Profile 不要求可信 dynamic/closed-loop model |
| F | NOT AUTHORIZED / NOT EXECUTED | 无硬件授权且未访问设备 |

三个合法 dt variant 均实际执行：D00A 为每帧 `0.020 s`；D00B 为每帧 `0.037 s`；D00C 从
第一帧开始连续 `0.020/0.037 s` 交替。S01/S02/S03 的 segment 边界不重启 D00C phase，runner
schedule spy 对完整序列逐帧验证通过。

## Scenario evidence

下表全部数值来自本轮固定树 reporting script 对冻结 helper 的只读调用。显示值适度舍入，gate
比较使用未舍入值与 Profile 容差。steady attenuation 为 `abs(mean_tail)/abs(target)`；
`50%/80%` 格式为 `frame / synthetic elapsed s`。steady gate 要求正确符号、ratio 在
`[0.80,1.00]`（含容差）且 50% 响应不超过 3 帧；P04/N04 另要求饱和在 `0.10`，N00 要求为零。

### Neutral、steady 与 saturation

| Scenario | Variant | Target | Tail mean | Ratio | Max output | 50% ; 80% | Result |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| ALG004-N00 | D00A | +0.000 | +0.000 | — | 0.000 | — | PASS |
| ALG004-N00 | D00B | +0.000 | +0.000 | — | 0.000 | — | PASS |
| ALG004-N00 | D00C | +0.000 | +0.000 | — | 0.000 | — | PASS |
| ALG004-P01 | D00A | +0.030 | +0.030 | 1.000 | 0.030 | 1 / 0.020; 1 / 0.020 | PASS |
| ALG004-P01 | D00B | +0.030 | +0.030 | 1.000 | 0.030 | 1 / 0.037; 1 / 0.037 | PASS |
| ALG004-P01 | D00C | +0.030 | +0.030 | 1.000 | 0.030 | 1 / 0.020; 1 / 0.020 | PASS |
| ALG004-N01 | D00A | -0.030 | -0.030 | 1.000 | 0.030 | 1 / 0.020; 1 / 0.020 | PASS |
| ALG004-N01 | D00B | -0.030 | -0.030 | 1.000 | 0.030 | 1 / 0.037; 1 / 0.037 | PASS |
| ALG004-N01 | D00C | -0.030 | -0.030 | 1.000 | 0.030 | 1 / 0.020; 1 / 0.020 | PASS |
| ALG004-P02 | D00A | +0.070 | +0.070 | 1.000 | 0.070 | 1 / 0.020; 2 / 0.040 | PASS |
| ALG004-P02 | D00B | +0.070 | +0.070 | 1.000 | 0.070 | 1 / 0.037; 1 / 0.037 | PASS |
| ALG004-P02 | D00C | +0.070 | +0.070 | 1.000 | 0.070 | 1 / 0.020; 2 / 0.057 | PASS |
| ALG004-N02 | D00A | -0.070 | -0.070 | 1.000 | 0.070 | 1 / 0.020; 2 / 0.040 | PASS |
| ALG004-N02 | D00B | -0.070 | -0.070 | 1.000 | 0.070 | 1 / 0.037; 1 / 0.037 | PASS |
| ALG004-N02 | D00C | -0.070 | -0.070 | 1.000 | 0.070 | 1 / 0.020; 2 / 0.057 | PASS |
| ALG004-P03 | D00A | +0.100 | +0.100 | 1.000 | 0.100 | 2 / 0.040; 2 / 0.040 | PASS |
| ALG004-P03 | D00B | +0.100 | +0.100 | 1.000 | 0.100 | 1 / 0.037; 2 / 0.074 | PASS |
| ALG004-P03 | D00C | +0.100 | +0.100 | 1.000 | 0.100 | 2 / 0.057; 2 / 0.057 | PASS |
| ALG004-N03 | D00A | -0.100 | -0.100 | 1.000 | 0.100 | 2 / 0.040; 2 / 0.040 | PASS |
| ALG004-N03 | D00B | -0.100 | -0.100 | 1.000 | 0.100 | 1 / 0.037; 2 / 0.074 | PASS |
| ALG004-N03 | D00C | -0.100 | -0.100 | 1.000 | 0.100 | 2 / 0.057; 2 / 0.057 | PASS |
| ALG004-P04 | D00A | +0.100 | +0.100 | 1.000 | 0.100 | 2 / 0.040; 2 / 0.040 | PASS |
| ALG004-P04 | D00B | +0.100 | +0.100 | 1.000 | 0.100 | 1 / 0.037; 2 / 0.074 | PASS |
| ALG004-P04 | D00C | +0.100 | +0.100 | 1.000 | 0.100 | 2 / 0.057; 2 / 0.057 | PASS |
| ALG004-N04 | D00A | -0.100 | -0.100 | 1.000 | 0.100 | 2 / 0.040; 2 / 0.040 | PASS |
| ALG004-N04 | D00B | -0.100 | -0.100 | 1.000 | 0.100 | 1 / 0.037; 2 / 0.074 | PASS |
| ALG004-N04 | D00C | -0.100 | -0.100 | 1.000 | 0.100 | 2 / 0.057; 2 / 0.057 | PASS |

### Delayed step

| Scenario | Variant | 50% frame | 50% time | 80% frame | 80% time | Tail | Ratio | Result |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| ALG004-S01P | D00A | 1 | 0.020 | 2 | 0.040 | +0.070 | 1.000 | PASS |
| ALG004-S01P | D00B | 1 | 0.037 | 1 | 0.037 | +0.070 | 1.000 | PASS |
| ALG004-S01P | D00C | 1 | 0.037 | 1 | 0.037 | +0.070 | 1.000 | PASS |
| ALG004-S01N | D00A | 1 | 0.020 | 2 | 0.040 | -0.070 | 1.000 | PASS |
| ALG004-S01N | D00B | 1 | 0.037 | 1 | 0.037 | -0.070 | 1.000 | PASS |
| ALG004-S01N | D00C | 1 | 0.037 | 1 | 0.037 | -0.070 | 1.000 | PASS |
| ALG004-S02P | D00A | 2 | 0.040 | 2 | 0.040 | +0.100 | 1.000 | PASS |
| ALG004-S02P | D00B | 1 | 0.037 | 2 | 0.074 | +0.100 | 1.000 | PASS |
| ALG004-S02P | D00C | 1 | 0.037 | 2 | 0.057 | +0.100 | 1.000 | PASS |
| ALG004-S02N | D00A | 2 | 0.040 | 2 | 0.040 | -0.100 | 1.000 | PASS |
| ALG004-S02N | D00B | 1 | 0.037 | 2 | 0.074 | -0.100 | 1.000 | PASS |
| ALG004-S02N | D00C | 1 | 0.037 | 2 | 0.057 | -0.100 | 1.000 | PASS |

### Full reversal

有效符号使用 `eps_sign=0.002 intent unit`；opposite 50% 必须在 6 帧内。时间从 reversal segment
第一帧起累计。

| Scenario | Variant | First opposite frame / s | Opposite 50% frame / s | 80% frame / s | Final tail | Ratio | Result |
| --- | --- | --- | --- | --- | ---: | ---: | --- |
| ALG004-S03P | D00A | 3 / 0.060 | 4 / 0.080 | 5 / 0.100 | -0.100 | 1.000 | PASS |
| ALG004-S03P | D00B | 2 / 0.074 | 3 / 0.111 | 3 / 0.111 | -0.100 | 1.000 | PASS |
| ALG004-S03P | D00C | 2 / 0.057 | 3 / 0.077 | 4 / 0.114 | -0.100 | 1.000 | PASS |
| ALG004-S03N | D00A | 3 / 0.060 | 4 / 0.080 | 5 / 0.100 | +0.100 | 1.000 | PASS |
| ALG004-S03N | D00B | 2 / 0.074 | 3 / 0.111 | 3 / 0.111 | +0.100 | 1.000 | PASS |
| ALG004-S03N | D00C | 2 / 0.057 | 3 / 0.077 | 4 / 0.114 | +0.100 | 1.000 | PASS |

### High-frequency reversal

冻结门槛为 `TV(candidate) <= 1.32`、`effective reversal count <= 4`；target TV 为 2.20。
reduction ratio 是比较指标，不用于抵消 Hard Gate。

| Scenario | Variant | TV(candidate) | TV(target) | Reduction | Reversals | Result |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| ALG004-S04P | D00A | 0.440 | 2.20 | 80.000% | 0 | PASS |
| ALG004-S04P | D00B | 0.814 | 2.20 | 63.000% | 0 | PASS |
| ALG004-S04P | D00C | 0.540 | 2.20 | 75.455% | 3 | PASS |
| ALG004-S04N | D00A | 0.440 | 2.20 | 80.000% | 0 | PASS |
| ALG004-S04N | D00B | 0.814 | 2.20 | 63.000% | 0 | PASS |
| ALG004-S04N | D00C | 0.540 | 2.20 | 75.455% | 3 | PASS |

## Output contract、镜像与重复性

| 指标 | 实际值 | 冻结限制 / 预期 | 结果 |
| --- | ---: | ---: | --- |
| Evaluated normal frames | 450 | 17 scenarios × 3 variants | PASS |
| Non-finite output count | 0 | 0 | PASS |
| Maximum absolute output | 0.1 intent unit | ≤ 0.10 | PASS |
| Envelope violation count | 0 | 0 | PASS |
| Maximum observed slew rate | 2.0000000000000004 intent unit/s | ≤ 2.0（按 Profile tolerance） | PASS |
| Slew violation count | 0 | 0 | PASS |
| Directed transition / overshoot violations | 0 | 0 | PASS |
| Maximum framewise mirror error | 0.0 intent unit | Profile tolerance 内 | PASS |
| Maximum three-run pairwise delta | 0.0 intent unit | Profile tolerance 内 | PASS |

镜像覆盖全部 8 对场景 × D00A/B/C；三次重复覆盖全部 17 个场景 × D00A/B/C。production module
执行 `wc -l` 得到 `377` physical LOC，包含空行、注释和 docstring。Cyclomatic complexity：
NOT MEASURED；未为此安装新依赖。

## Inheritance、失效与 Level B evidence

ALG-001、ALG-002、ALG-003 inheritance 均在当前 ALG-004 post-shaped intent 上重新执行，不以
历史 Result 的资格代替。ALG-001 覆盖 neutral、direction、比例/幅值关系、symmetry、finite、
repeatability、fail-close、reset、factory 和 Level B；ALG-002 覆盖 zero-rate、diverging /
recovering、zero-pitch moving、signed damping separation、trend、symmetry、finite、
repeatability、dt、fail-close、reset、factory 和 Level B；ALG-003 覆盖 Q01–Q04 noise gate、
S01/S02 meaningful response、diverging/recovering trend、D00A/B/C、invalid dt、fail-close、
reset、factory、Level B、mirror 和 repeatability。三项 inheritance 均 PASS；历史
ALG-001/002/003 Result 文件保持不变。

| Fault / reset | Layer 与实际证据 | 结果 |
| --- | --- | --- |
| F01 missing pitch/rate | state-validation 前置拒绝；harness reset 后 fresh-cold-start 等价 | PASS |
| F02 NaN/±Inf pitch/rate | state-validation 前置拒绝；harness reset 后 fresh-cold-start 等价 | PASS |
| F03–F06 | controller-layer；先建立双层非零 history，精确 valid unloaded safe-stop，双 history 清除，下一合法输入 fresh-cold-start 等价 | PASS |
| D01 `dt=0` | controller-layer safe-stop、双 history 清除、cold-start 等价 × D00A/B/C | PASS |
| D02 `dt=-0.01` | 同上 | PASS |
| D03 `dt=NaN` | 同上 | PASS |
| D04 `dt=+Inf/-Inf` | 同上 | PASS |
| R01 | P04 history 后 reset；N02 与 fresh run 等价 × D00A/B/C | PASS |
| R02 | P02/N02 交换顺序不改变序列并保持逐帧镜像 × D00A/B/C | PASS |

F01/F02 的 state-validation rejection 未记作 controller-layer safe-stop。controller fault 与非法 dt
路径均通过 `validate_flight_command()`，不发旧普通命令，不复用旧 command/cache/latch；reset
不修改 Runtime、authority、IMU zero 或 E-STOP。

| Level B 项目 | 正式结果 |
| --- | --- |
| Factory / frozen configuration / invalid and unknown rejection | PASS |
| FlightCommand validation | PASS |
| Normal motor payload | current complete feedback position hold；不复用上一帧 baseline |
| Fan payload | left=0.0；right=0.0 |
| Safe-stop | valid unloaded `FlightCommand.safe_stop()` |
| Actuator allocation | NOT IMPLEMENTED |
| Default controller | UNCHANGED |
| Flight API | UNCHANGED |
| Runtime | UNCHANGED |

## Future-task boundary review

固定 production source 的只读 review 与 targeted tests 确认：ALG-005 recovery process、ALG-006
actuator allocation、ALG-007 multi-axis、ALG-008 full disturbance recovery 均 NOT IMPLEMENTED；
new input filtering=NO，Kp/Kd retuning=NO，integral/anti-windup=NO，hardware-specific tuning=NO，
future-task leakage=NO。源码中 recovery intent 和 actuator allocation 字样分别是既有抽象接口
语义与明确的未实现边界，不构成相应能力实现。

## 实际命令与测试统计

正式 targeted、历史回归、metrics 与 LOC 使用以下精确命令；每个 pytest 都保留 `pipefail` 后的
pytest exit code，日志与 JUnit 写入 qualification output：

```bash
QUAL_DIR=/tmp/windarmor-alg004-formal.xrmO9b
set -o pipefail
PYTHONPATH=src/windarmor_flight_control python3 -m pytest -p no:cacheprovider \
  src/windarmor_flight_control/test/test_alg004_candidate_a.py -q \
  --junitxml="$QUAL_DIR/alg004-targeted.xml" 2>&1 | tee "$QUAL_DIR/alg004-targeted.log"
PYTHONPATH=src/windarmor_flight_control python3 -m pytest -p no:cacheprovider \
  src/windarmor_flight_control/test/test_alg001_candidate_a.py -q \
  --junitxml="$QUAL_DIR/alg001-regression.xml" 2>&1 | tee "$QUAL_DIR/alg001-regression.log"
PYTHONPATH=src/windarmor_flight_control python3 -m pytest -p no:cacheprovider \
  src/windarmor_flight_control/test/test_alg002_candidate_a.py -q \
  --junitxml="$QUAL_DIR/alg002-regression.xml" 2>&1 | tee "$QUAL_DIR/alg002-regression.log"
PYTHONPATH=src/windarmor_flight_control python3 -m pytest -p no:cacheprovider \
  src/windarmor_flight_control/test/test_alg003_candidate_a.py -q \
  --junitxml="$QUAL_DIR/alg003-regression.xml" 2>&1 | tee "$QUAL_DIR/alg003-regression.log"
PYTHONPATH=src/windarmor_flight_control python3 "$QUAL_DIR/collect_metrics.py" \
  | tee "$QUAL_DIR/alg004-formal-metrics.json"
wc -l src/windarmor_flight_control/windarmor_flight_control/algorithms/alg004_candidate_a.py
```

完整 Flight 测试需要仓库生成的 ROS interfaces overlay。实际先执行：

```bash
source /opt/ros/jazzy/setup.bash
WINDARMOR_CI_OUTPUT_ROOT="$QUAL_DIR/preflight-build" ./scripts/ci_software.sh build
source "$QUAL_DIR/preflight-build/install/setup.bash"
PYTHONPATH="src/windarmor_flight_control:${PYTHONPATH}" \
python3 -m pytest -p no:cacheprovider src/windarmor_flight_control/test -q \
  --junitxml="$QUAL_DIR/flight-package-built-overlay.xml"

WINDARMOR_CI_OUTPUT_ROOT="$QUAL_DIR/ci-output" ./scripts/ci_software.sh
```

此前两个未正确加载可用 overlay 的尝试在 collection 阶段各报 5 个 `rclpy` import errors、未执行
测试；未改代码或阈值。正确隔离 overlay 上的正式运行全部 PASS。

| 测试 | Passed | Failed | Errors | Skipped | pytest/JUnit time |
| --- | ---: | ---: | ---: | ---: | ---: |
| ALG-004 formal targeted | 433 | 0 | 0 | 0 | 2.976 s |
| ALG-001 historical regression | 47 | 0 | 0 | 0 | 0.413 s |
| ALG-002 historical regression | 84 | 0 | 0 | 0 | 0.719 s |
| ALG-003 historical regression | 172 | 0 | 0 | 0 | 1.739 s |
| Full `windarmor_flight_control`（有效 overlay） | 1086 | 0 | 0 | 0 | 19.164 s |

Fixed-tree Software CI：PASS。CI safety、whitespace、compile、5-package build 均 PASS；tooling
pure-software tests 26 passed，motor 431 passed，fan 159 passed，flight/interfaces 1094 passed；
最终 `colcon test-result` 为 1715 tests、0 errors、0 failures、0 skipped，CI exit code 0。这些
结果均是 software/fake/mock/in-memory evidence，不是硬件验证。

## Hard Qualification

| Hard Gate | 结果 |
| --- | --- |
| Metadata / fixed implementation / config / fixture | PASS |
| Finite output | PASS |
| Output Envelope | PASS |
| Slew Rate | PASS |
| Directed Transition | PASS |
| Neutral | PASS |
| Steady Signal Preservation | PASS |
| Step Response | PASS |
| Saturation | PASS |
| Full Reversal | PASS |
| High-frequency Reversal | PASS |
| D00A / D00B / D00C | PASS / PASS / PASS |
| D01–D04 | PASS |
| F01–F06 | PASS |
| Dual-history invalidation | PASS |
| R01/R02 | PASS |
| Mirror symmetry | PASS |
| Three-run repeatability | PASS |
| ALG-001 inheritance | PASS |
| ALG-002 inheritance | PASS |
| ALG-003 inheritance | PASS |
| Factory/configuration | PASS |
| Level B FlightCommand | PASS |
| Future-task boundary | PASS |
| Hardware access NO | PASS |

Hard Qualification：**PASS**。

Overall：**ALG-004 QUALIFIED**。

该结论只证明固定 implementation SHA、Algorithm Benchmark v1、ALG-004 Profile v1 和
`ALG004-FIXTURE-v1` 中的 abstract intent 软件输出约束通过。它不能证明 REAL ACTUATOR SAFE、
CyberGear safe、fan/PWM safe、actuator direction 或 allocation 正确、dynamic closed-loop
recovery、机器人能够恢复平衡或 real Balance Recovery verified。
