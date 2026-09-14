# ALG-003 Candidate A Result

本文记录 Candidate A 在固定 implementation commit 上针对 synthetic fixture 的正式纯软件资格验证。判定依据为 [ALG-003 Task Spec v1](../algorithm_tasks/ALG-003.md) 和 [Algorithm Benchmark v1 / ALG-003 Profile v1](../ALGORITHM_BENCHMARK.md#10-alg-003-profile-v1)。Level D 是确定性软件序列回放，不是动态仿真；本文不是硬件授权或真实 Balance Recovery 证据。

## Metadata 与固定起点

| 字段 | 实际值 |
| --- | --- |
| Candidate | Candidate A |
| Task | ALG-003 / Task Spec v1 |
| Benchmark | Algorithm Benchmark v1 / ALG-003 Profile v1 |
| Fixture | ALG003-FIXTURE-v1 |
| Lineage | Independent Candidate A |
| Implementation task baseline | f71404e1fa302f2e097442d707a6688aac6e65a2 |
| Production algorithm initial review checkpoint | ed679a9eea0e92e37bbb11f3e5784c43a5927177 |
| Implementation commit / formal qualification tree | 240cda9f1c2b73dad7ae70bf0c2c9205a76f0364 |
| Configuration | {"kp_intent_per_rad": 1.0, "kd_intent_per_rad_s": 0.1, "window_size": 2} |
| Benchmark date | 2026-09-14 |
| Hardware access | NO |
| Hardware authorization | NONE |
| Hardware validation | NOT EXECUTED / NOT AUTHORIZED |

正式 benchmark 开始前执行 git status --short --branch、git rev-parse HEAD、git log -5 --oneline，并核对本地 tracking ref 与 git ls-remote。分支为 feature/algo-003-candidate-a，工作区干净，本地与远端分支同步，HEAD 精确等于 240cda9f1c2b73dad7ae70bf0c2c9205a76f0364。下述资格、回归、指标计算和 CI 都先在这个纯固定 tree 上完成，随后才创建本文。

240cda9 只修正了先前 pre-formal checkpoint 的 benchmark/test harness 可变 dt 执行忠实度；从 ed679a9 到该 SHA，production Candidate source 未改变。本文中的固定 implementation commit 包含经评审的生产实现与正确的正式测试树。

## 实际环境与安全边界

| 项目 | 实际值 |
| --- | --- |
| OS | Ubuntu 24.04.4 LTS |
| Kernel / platform | Linux 6.8.0-1064-raspi aarch64 GNU/Linux |
| Architecture | arm64 |
| ROS distro | jazzy |
| Python | 3.12.3 |
| pytest / pluggy | 7.4.4 / 1.4.0 |
| pytest-cov | 4.1.0 |
| colcon-core / colcon-ros | 0.20.1 / 0.5.0 |
| colcon-cmake / colcon-python-setup-py | 0.2.29 / 0.2.9 |

上述值实际由 /etc/os-release、uname -srmo、dpkg --print-architecture、python3 --version、Python importlib.metadata 和 ROS setup 后的 ROS_DISTRO 取得。没有为本次 qualification 新增依赖。完整 Flight 回归使用本轮隔离 build/install overlay：/tmp/windarmor-alg003-formal.FzR4Xo。

运行前只读检查固定 ALG-003 production、runner、targeted tests 的导入和调用路径，以及 scripts/ci_software.sh。它们使用纯 Python core、fake FlightState、依赖注入和隔离的测试，不打开真实 IMU 串口，不创建真实 CyberGear driver，不访问 CAN/GPIO/PWM，不启动电机、风扇或 hardware launch。CI 中的 hardware verification tooling tests 仅测试证据工具逻辑，不是硬件验证。

## 配置与算法语义

固定源码默认值与 CandidateAConfiguration() 实例均为 Kp=1.0 intent/rad、Kd=0.1 intent/(rad/s)、window_size=2；工厂配置稳定序列化为上表三个键。正有限增益以实例冻结，窗口只允许整数 2；测试拒绝零、负数、NaN、Inf、bool/string、错误窗口和 unknown key。正式运行期间没有按 Q、S 或 dt variant 调整参数。

Level A core 保留上一条合法原始 pitch/rate；cold start 直接使用当前输入，随后对当前与上一输入做固定两样本 boxcar 平均，再计算 −Kp × filtered pitch − Kd × filtered rate。dt 必须为正有限秒数；它决定合法性和时序报告，不改变固定帧权重。因此 D00A/B/C 下 intent 相同，但合成 elapsed time 不同。非法输入、非法 dt、controller-layer fail-close 与 reset 均清除本地 history。控制输入只用统一 relative_pitch_rad、relative_pitch_rate_rad_s 与 dt；raw gyro 未用作控制输入。

Level B 的普通 FlightCommand 仅复制当前合法完整 motor feedback position，左右 fan command 均为 0.0；该 hold/fan-zero payload 不编码 abstract intent，也不是执行器分配或真实恢复命令。失效时精确返回无 motor/fan 载荷的 FlightCommand.safe_stop()。

## 实际执行命令与测试结果

固定配置读取：

    PYTHONPATH=src/windarmor_flight_control python3 -c 'from windarmor_flight_control.algorithms.alg003_candidate_a import CandidateAConfiguration,DEFAULT_KP_INTENT_PER_RAD,DEFAULT_KD_INTENT_PER_RAD_S,DEFAULT_WINDOW_SIZE; c=CandidateAConfiguration(); print(DEFAULT_KP_INTENT_PER_RAD,DEFAULT_KD_INTENT_PER_RAD_S,DEFAULT_WINDOW_SIZE,c)'

Targeted ALG-003 正式资格：

    PYTHONPATH=src/windarmor_flight_control python3 -m pytest -p no:cacheprovider src/windarmor_flight_control/test/test_alg003_candidate_a.py -q

结果：172 collected、172 passed、0 failed、0 skipped。覆盖 Level A/B/D，Q01–Q04 与 S01–S04 的三个 dt variants、dt schedule spy 回归、两个独立总 gate、继承、F01–F06、D01–D04、R01/R02、镜像、三次重复、factory/config 和 FlightCommand validation。

历史 Candidate A 回归（分别实际重跑，不改历史 implementation/Result）：

    PYTHONPATH=src/windarmor_flight_control python3 -m pytest -p no:cacheprovider src/windarmor_flight_control/test/test_alg001_candidate_a.py -q
    PYTHONPATH=src/windarmor_flight_control python3 -m pytest -p no:cacheprovider src/windarmor_flight_control/test/test_alg002_candidate_a.py -q

结果：ALG-001 为 47 passed、0 failed、0 skipped；ALG-002 为 84 passed、0 failed、0 skipped。

完整 Software CI 实际执行：

    source /opt/ros/jazzy/setup.bash
    WINDARMOR_CI_OUTPUT_ROOT=/tmp/windarmor-alg003-formal.FzR4Xo ./scripts/ci_software.sh

结果：PASS。CI safety check PASS（2 files）；Git whitespace PASS；Python compile PASS；hardware verification tooling pure-software tests 26 passed；五包 build PASS；motor package 431 passed；fan safety regression 159 passed；flight/interface 661 passed；最终 colcon test-result：1282 tests、0 errors、0 failures、0 skipped。

在该隔离 overlay 上单独执行完整 windarmor_flight_control 回归：

    source /opt/ros/jazzy/setup.bash
    source /tmp/windarmor-alg003-formal.FzR4Xo/install/setup.bash
    python3 -m pytest -p no:cacheprovider src/windarmor_flight_control/test -q

结果：653 passed、0 failed、0 skipped。以上均为 software/fake/mock/in-memory 证据，不是实机验证。

指标抽取实际使用 PYTHONPATH=src/windarmor_flight_control 的 Python 进程，分别遍历 DT_VARIANTS，调用固定 test.alg003_benchmark 中的 raw_sequence、metrics、run_noise_scenario、run_signal_scenario、response_metrics、steady_mean、trend_means、max_mirror_error、collect_repeated_runs 和 max_repeatability_delta，并以固定 CandidateAConfiguration(1.0, 0.1, 2) 每次新建 core。每个 variant 的 Q/S 都实际执行，不复用另一 variant 的结果。以下表格数值按冻结公式计算；展示值适度舍入，门槛比较使用未舍入值。

指标抽取完整命令：

    PYTHONPATH=src/windarmor_flight_control python3 - <<'PY'
    from test.alg003_benchmark import (
        DT_VARIANTS, NOISE_SCENARIOS, NOISE_BY_ID, SIGNAL_SCENARIOS, SIGNAL_BY_ID,
        collect_repeated_runs, max_mirror_error, max_repeatability_delta, metrics,
        raw_sequence, response_metrics, run_noise_scenario, run_signal_scenario,
        steady_mean, trend_means,
    )
    from windarmor_flight_control.algorithms.alg003_candidate_a import Alg003CandidateACore, CandidateAConfiguration
    def core():
        return Alg003CandidateACore(CandidateAConfiguration(1.0, 0.1, 2))
    for variant in DT_VARIANTS:
        for q in NOISE_SCENARIOS:
            raw = metrics(raw_sequence(q.samples))
            candidate = metrics(run_noise_scenario(core(), q, variant))
            print(variant, q.scenario_id, raw, candidate, 1-candidate["tv"]/raw["tv"])
        for s in SIGNAL_SCENARIOS:
            values = run_signal_scenario(core(), s, variant)
            if s.scenario_id in ("ALG003-S01", "ALG003-S02"):
                print(variant, s.scenario_id, response_metrics(s, values, variant), steady_mean(values))
            else:
                print(variant, s.scenario_id, trend_means(s, values))
        for positive, negative in (
            ("ALG003-Q02", "ALG003-Q03"), ("ALG003-S01", "ALG003-S02"),
            ("ALG003-S03P", "ALG003-S03N"), ("ALG003-S04P", "ALG003-S04N"),
        ):
            noise = positive.startswith("ALG003-Q")
            cases = NOISE_BY_ID if noise else SIGNAL_BY_ID
            runner = run_noise_scenario if noise else run_signal_scenario
            print(variant, positive, negative, "mirror",
                  max_mirror_error(runner(core(), cases[positive], variant),
                                   runner(core(), cases[negative], variant)))
        print(variant, "repeatability",
              max(max_repeatability_delta(collect_repeated_runs(core, s, variant))
                  for s in NOISE_SCENARIOS + SIGNAL_SCENARIOS))
    PY

## dt schedule fidelity 与执行层级

| Variant | 实际 schedule |
| --- | --- |
| D00A | 每帧 0.020 s |
| D00B | 每帧 0.037 s |
| D00C | 整个独立 run 从首帧起连续 0.020 / 0.037 s 交替 |

Noise run 的未计分 priming 是执行的第一帧：D00C 下 priming=0.020、首计分帧=0.037、第二计分帧=0.020 s，后续连续交替；计分仍只取 12 帧 sequence。Signal 无单独 priming：D00C 下首帧=0.020、第二帧=0.037 s，后续连续交替。Level B Q/S 验证也按相同实际索引输入 dt。六个 runner spy 用例直接记录实际收到的 dt，D00A/B/C 全部 PASS。

| Level | 本次状态 | 结论边界 |
| --- | --- | --- |
| A | EXECUTED / PASS | 纯软件 core、固定配置、history 与 intent |
| B | EXECUTED / PASS | factory、FlightState/FlightCommand、完整当前帧、safe-stop |
| C | NOT EXECUTED | 非 ALG-003 v1 Hard Gate；当前 synthetic DRY_RUN 选择教学控制器 |
| D | EXECUTED / PASS | ALG003-FIXTURE-v1 确定性软件 sequence replay；不是动态仿真 |
| E | NOT EXECUTED | 无可信动态/闭环模型，不属于本 Profile |
| F | NOT EXECUTED / NOT AUTHORIZED | 无硬件授权，不访问设备 |

## Noise Suppression Gate

下表为每个 Q 场景的正式实际结果。D00A、D00B、D00C 分别运行后的 intent/metrics 一致；raw → Candidate 表示同一计分序列的比较，不是多次复制执行。

| 场景 | TV raw → Candidate | TV 降幅 | 有效反向 raw → Candidate | PEAK raw → Candidate | MAA raw → Candidate | P2P raw → Candidate |
| --- | --- | ---: | --- | --- | --- | --- |
| Q01 | 0.134 → 0.017 | 87.3134% | 11 → 0，减少 11 | 0.008 → 0.003 | 0.006 → 0.0008333333 | 0.016 → 0.005 |
| Q02 | 0.134 → 0.017 | 87.3134% | 0 → 0，减少 0 | 0.058 → 0.053 | 0.050 → 0.0501666667 | 0.016 → 0.005 |
| Q03 | 0.134 → 0.017 | 87.3134% | 0 → 0，减少 0 | 0.058 → 0.053 | 0.050 → 0.0501666667 | 0.016 → 0.005 |
| Q04 | 0.066 → 0.008 | 87.8788% | 7 → 0，减少 7 | 0.004 → 0.002 | 0.003 → 0.0004166667 | 0.008 → 0.0025 |

Q01 的 TV/reversal/PEAK/MAA，Q02/Q03 的 TV/reversal/P2P，以及 Q04 的 TV/reversal/PEAK/MAA 均满足冻结阈值。Q02/Q03 逐帧镜像误差为 0.0 intent unit。Q02/Q03 的额外 PEAK/MAA 与 Q01/Q04 的额外 P2P 仅为比较指标，不是新增 Hard Gate。

| 场景 | D00A | D00B | D00C |
| --- | --- | --- | --- |
| Q01 | PASS | PASS | PASS |
| Q02 | PASS | PASS | PASS |
| Q03 | PASS | PASS | PASS |
| Q04 | PASS | PASS | PASS |
| Variant 总判定 | PASS | PASS | PASS |

Noise Suppression Gate：PASS。

## Signal Preservation Gate

Meaningful threshold 为与 raw tail 同方向且 abs(intent) ≥ 0.035；首个满足阈值的帧号必须 ≤3。下表 synthetic elapsed time 是从 transition 到首个有效响应帧结束的累计 dt，不是机器人实机响应时间。

| 场景 | Variant | Frames to response | Synthetic elapsed | 末三帧 signed mean | Raw / Candidate steady magnitude | Attenuation / preservation | 判定 |
| --- | --- | ---: | ---: | ---: | --- | ---: | --- |
| S01 | D00A | 2 | 0.040 s | −0.070 | 0.070 / 0.070 | 1.0 | PASS |
| S01 | D00B | 2 | 0.074 s | −0.070 | 0.070 / 0.070 | 1.0 | PASS |
| S01 | D00C | 2 | 0.057 s | −0.070 | 0.070 / 0.070 | 1.0 | PASS |
| S02 | D00A | 2 | 0.040 s | +0.070 | 0.070 / 0.070 | 1.0 | PASS |
| S02 | D00B | 2 | 0.074 s | +0.070 | 0.070 / 0.070 | 1.0 | PASS |
| S02 | D00C | 2 | 0.057 s | +0.070 | 0.070 / 0.070 | 1.0 | PASS |

S01 的 −0.070 位于冻结区间 [−0.084,−0.056]；S02 的 +0.070 位于 [+0.056,+0.084]。固定帧 moving average 没有固定物理时间常数；D00A/B/C 的合成耗时差异已如实保留。

| 场景 | Variant | Before mean | After mean | 有符号 separation | 与 raw 0.020 的误差 | 判定 |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| S03P | D00A | −0.050 | −0.070 | 0.020 | 3.47e−18 | PASS |
| S03P | D00B | −0.050 | −0.070 | 0.020 | 3.47e−18 | PASS |
| S03P | D00C | −0.050 | −0.070 | 0.020 | 3.47e−18 | PASS |
| S03N | D00A | +0.050 | +0.070 | 0.020 | 3.47e−18 | PASS |
| S03N | D00B | +0.050 | +0.070 | 0.020 | 3.47e−18 | PASS |
| S03N | D00C | +0.050 | +0.070 | 0.020 | 3.47e−18 | PASS |
| S04P | D00A | −0.050 | −0.030 | 0.020 | 1.04e−17 | PASS |
| S04P | D00B | −0.050 | −0.030 | 0.020 | 1.04e−17 | PASS |
| S04P | D00C | −0.050 | −0.030 | 0.020 | 1.04e−17 | PASS |
| S04N | D00A | +0.050 | +0.030 | 0.020 | 1.04e−17 | PASS |
| S04N | D00B | +0.050 | +0.030 | 0.020 | 1.04e−17 | PASS |
| S04N | D00C | +0.050 | +0.030 | 0.020 | 1.04e−17 | PASS |

S03P 使用 before−after、S03N 使用 after−before、S04P 使用 after−before、S04N 使用 before−after；四者均超过 0.010 阈值。S01/S02、S03P/N、S04P/N 在三个 dt variants 下逐帧镜像一致。

| 独立子门槛 | 正式结果 |
| --- | --- |
| Meaningful positive disturbance (S01) | PASS |
| Meaningful negative disturbance (S02) | PASS |
| Response delay ≤3 frames | PASS |
| Steady nonzero preservation | PASS |
| Diverging trend (S03P/N) | PASS |
| Recovering trend (S04P/N) | PASS |
| Framewise symmetry | PASS |

Signal Preservation Gate：PASS。Noise Gate 的指标未用于抵消或放宽本 Gate。

## 继承、失效与命令契约

当前 ALG-003 Candidate 对未修改的 ALG001-FIXTURE-v1 和 ALG002-FIXTURE-v1 重新运行六帧保持后的末三帧均值及首帧检查；没有引用历史 Candidate 的 PASS 代替当前继承 gate。

| ALG-001 场景 | N00 | P01 | P02 | N01 | N02 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 六帧末三帧均值 | 0.0 | −0.05 | −0.10 | +0.05 | +0.10 |

ALG-001 inheritance：PASS。Neutral、首帧 finite/direction、strict magnitude、proportional-style Kp=1.0、正负镜像、三次重复、state-validation/controller fail-close、reset、factory 与 Level B 完整帧/command validation 均按当前 Candidate 重验。继承正常场景最大重复差异为 0.0。

| ALG-002 场景 | P00 | P01 | P02 | N00 | N01 | N02 | Z01 | Z02 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 六帧末三帧均值 | −0.05 | −0.07 | −0.03 | +0.05 | +0.07 | +0.03 | −0.02 | +0.02 |

ALG-002 inheritance：PASS。Zero-rate、diverging、recovering、zero-pitch moving、四个 signed damping separation（各约 0.020）、正负 mirror、首帧 finite、fail-close、合法/非法 dt、reset、三次重复、factory 与 Level B validation 均按当前 Candidate 重验。继承正常场景最大重复差异为 0.0。

| ALG-003 场景 | Layer / variant | 正式结果 |
| --- | --- | --- |
| F01 | valid IMU 缺 pitch 或 rate；state validation | 两个 variant 均前置拒绝；harness reset 后 cold-start 等价；PASS |
| F02 | pitch/rate 为 NaN、+Inf 或 −Inf；state validation | 所有 variant 均前置拒绝；harness reset 后 cold-start 等价；PASS |
| F03 | 合法 unobserved/invalid IMU；controller | 无载荷 safe-stop、history cleared、下一合法输入 cold-start 等价；PASS |
| F04 | IMU stale；controller | 同上；PASS |
| F05 | required_inputs_fresh=false；controller | 同上；PASS |
| F06 | motor unobserved/stale/invalid/unhealthy 或 E-STOP unknown/active；controller | 每个合法 variant 均无载荷 safe-stop、history cleared、cold-start 等价；PASS |

F01/F02 的前置拒绝没有被误记为 controller-layer PASS。Controller-layer 检查实际按“先建立非零 history → 故障 → 精确 FlightCommand.safe_stop() → history 清除 → 下一合法输入等价于 fresh reset cold start”执行；safe-stop 均通过 validate_flight_command()，不复用旧 command。

| 非法 dt | 正式结果 |
| --- | --- |
| D01 = 0 | 合法无载荷 safe-stop、history cleared、下一合法输入 cold-start 等价；PASS |
| D02 = −0.01 | 同上；PASS |
| D03 = NaN | 同上；PASS |
| D04 = +Inf | 同上；PASS |
| D04 = −Inf | 同上；PASS |

R01：PASS；Q02 history 后 reset，Q01 的完整计分序列与全新 core 的 Q01 cold run 等价。R02：PASS；Q02/Q03 交换执行顺序后各自序列不变，且逐帧保持镜像。Level B 的每帧 motor payload 来自当前完整 feedback，不复用上一普通 command。Reset 不修改 Runtime、authority、IMU zero 或 E-STOP，也不产生外部硬件副作用。

Factory/固定配置验证：PASS；default/teaching controller 仍与 Candidate 分离。FlightCommand validation：PASS；Q/S 的 Level B D00A/B/C 所有合法帧、继承正常帧和 fail-close 均验证，普通命令电机键完整、数值有限、fan payload 为 [0,1] 内的左右 0.0；safe-stop 不含载荷。

## 镜像、重复性与比较指标

| 指标 | 覆盖范围 | 实际最大值 |
| --- | --- | ---: |
| Framewise mirror symmetry error | Q02/Q03、S01/S02、S03P/N、S04P/N × D00A/B/C，以及 ALG-001/002 继承镜像场景 | 0.0 intent unit |
| Three-run repeatability delta | Q/S × D00A/B/C 与 ALG-001/002 继承正常场景 | 0.0 intent unit |

继承镜像按 ALG-001 P01/N01、P02/N02 和 ALG-002 P00/N00、P01/N01、P02/N02、Z01/Z02 的三次实际结果逐对计算，误差也均为 0.0 intent unit。

上述值均在冻结 tol(a,b)=1e−9+1e−6×max(abs(a),abs(b)) 内。所有 intent、raw baseline 与 Level B payload finite。Q 场景 TV、反向次数、equilibrium PEAK/MAA、非零姿态 P2P、response frames、synthetic elapsed、steady ratio 和四个 trend separation 已分别列示，不合成为无依据的总分。

Production module physical LOC 实测命令：

    wc -l src/windarmor_flight_control/windarmor_flight_control/algorithms/alg003_candidate_a.py

结果：277 physical LOC，包含空行、注释和 docstring。Cyclomatic complexity：NOT MEASURED；没有仅为该数值引入依赖。

Test coverage quality：ALG-003 Profile v1 的 Q/S、合法/非法 dt、F/R、继承、factory/command 与 Level A/B/D 必需场景和 variant 已覆盖；targeted 172 passed，ALG-001/002 历史 Candidate 回归 47/84 passed，flight-control 全量 653 passed，完整 CI 最终 1282 tests 且无失败。Code coverage percentage：NOT MEASURED；未运行 coverage.py，场景覆盖和测试数量不冒充行/分支覆盖率。

Configuration clarity：PASS；仅三个稳定参数，数值、单位、合法范围及非法值拒绝明确。Kp/Kd 是正有限值，window_size 仅整数 2，默认值与正式序列化值相同，运行期间未调参；固定帧窗口不等于以秒定义的时间常数。

## Future-task review、Hard Qualification 与 Overall

只读审查固定 production source：没有 ALG-004 最终 intent slew-rate、output shaping 或 dynamic saturation；没有 ALG-005 recovery state/timeout；没有 ALG-006 motor/fan allocation 或 actuator direction；没有 ALG-007 roll/multi-axis；没有 ALG-008 full dynamic recovery。也没有 integral、raw gyro axis/sign logic 或真实硬件调参。future-task leakage：NO。Flight API、Runtime、default controller、硬件映射与既有安全机制在此固定 Candidate Result 阶段未修改。

| ALG-003 Profile v1 Hard Gate | 判定 |
| --- | --- |
| Metadata、固定 configuration、fixture、raw baseline、执行命令与固定 implementation commit | PASS |
| ALG-001 inheritance | PASS |
| ALG-002 inheritance | PASS |
| Deterministic fixture 与 dt schedule fidelity | PASS |
| Noise Suppression Gate，包括 Q01/Q04 equilibrium 与 Q02/Q03 nonzero-pose | PASS |
| Signal Preservation Gate，包括双向 response、steady、trend 与镜像 | PASS |
| D00A/B/C 合法 dt 与 D01–D04 非法 dt | PASS |
| F01–F06 layer 分类、fail-close 与 history invalidation | PASS |
| R01/R02 reset 与 sequence isolation | PASS |
| Finite、framewise symmetry 与三次 repeatability | PASS |
| Factory/config 与全部 Level B FlightCommand validation | PASS |
| Future-task boundary（ALG-004+ leakage NO） | PASS |
| Hardware access NO | PASS |

Noise Suppression Gate：PASS。Signal Preservation Gate：PASS。Level A/B/D：EXECUTED / PASS。Global 与 Task-specific Hard Gate 均 PASS；比较指标没有抵消失败。

Hard Qualification：PASS。

Overall：ALG-003 QUALIFIED。

该结论只针对固定 implementation commit、Algorithm Benchmark v1 / ALG-003 Profile v1 和 ALG003-FIXTURE-v1 的纯软件资格，不是系统集成、动态闭环或实机资格。

## Known limitations 与未执行测试

- ALG003-FIXTURE-v1 是显式 synthetic noise，不是实测 Hiwonder IMU noise statistics、量化误差或机器人振动谱；真实 IMU 噪声和振动谱未测试。
- 两样本 moving average 和 window_size=2 没有真实硬件统计或最优性依据；固定帧窗口不是固定物理时间常数。
- Kp=1.0 / Kd=0.1 是软件资格配置，不是实机最优增益；没有真实硬件调参。
- D00A/B/C 的 synthetic elapsed time 不是实机响应时间。
- 真实电机抖动、执行器响应、风扇推力、实际恢复方向均未测试；software intent sign 不代表真实 actuator direction。
- ALG-004 output shaping、recovery state machine 和 actuator allocation 尚未实现；普通 hold/fan-zero payload 不编码 intent。
- 没有动态闭环模型、recovery time、overshoot 实测数据或最大可恢复扰动；没有真实 Balance Recovery 证据。
- 硬件验证未执行且未授权。真实 IMU/串口/CAN/CyberGear/GPIO/PWM/ESC/电机/风扇均未访问。
- 真实闭环验证前，Flight Runtime 与 relative attitude 发布者之间的 pitch_axis_sign 配置一致性必须保证不会漂移；本次纯软件资格不验证运行时配置一致性。

Level C synthetic DRY_RUN：未执行，不属于 ALG-003 Profile v1 必需门槛且当前入口选择教学控制器。Level E trusted dynamic benchmark：未执行，无可信模型。Level F bounded hardware verification：未执行且未授权。Code coverage percentage 与 cyclomatic complexity：未测量。真实硬件与真实 Balance Recovery：未执行 / NOT VERIFIED。
