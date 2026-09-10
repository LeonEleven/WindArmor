# ALG-002 Candidate A Result

本文记录 Candidate A 针对固定 implementation commit 的正式纯软件 qualification 结果。
能力和结论边界分别以 [ALG-002 Task Spec v1](../algorithm_tasks/ALG-002.md) 和
[Algorithm Benchmark v1 / ALG-002 Profile v1](../ALGORITHM_BENCHMARK.md) 为准。本文不是
动态仿真、真实执行器验证或硬件运行授权。

## Metadata

| 字段 | 值 |
| --- | --- |
| Candidate | `Candidate A` |
| Task | `ALG-002 / Task Spec v1` |
| Benchmark | `Algorithm Benchmark v1 / ALG-002 Profile v1` |
| Fixture | `ALG002-FIXTURE-v1` |
| Implementation lineage | `Independent Candidate A` |
| Implementation task baseline | `e58e66144e1e9640adb330dc0f2eed1927e95624` |
| Implementation commit | `77e7b4f98e60602d3b224618225e11e9fecc8fe8` |
| Configuration | `{"kp_intent_per_rad": 1.0, "kd_intent_per_rad_s": 0.1}` |
| Benchmark date | `2026-09-10` |
| Hardware access | `NO` |
| Hardware authorization | `NONE` |
| Hardware validation | `NOT EXECUTED / NOT AUTHORIZED` |

正式运行开始时，当前分支为 `feature/algo-002-candidate-a`，工作区干净，`HEAD` 精确等于
上述 implementation commit。所有 benchmark、回归和 CI 都先在该干净提交上完成；取得结果
后才创建本文。

## Environment

| 项目 | 实际值 |
| --- | --- |
| OS | `Ubuntu 24.04.4 LTS` |
| Kernel / platform | `Linux 6.8.0-1064-raspi aarch64 GNU/Linux` |
| Architecture | `arm64` |
| ROS distro | `jazzy` |
| Python | `3.12.3` |
| pytest | `7.4.4` |
| pytest pluggy | `1.4.0` |
| pytest plugins shown by targeted run | `colcon-core 0.20.1`, `cov 4.1.0` |

没有为本次 benchmark 新增依赖。需要 `rclpy` 和本工作空间生成接口的完整 Flight 测试使用
本次在 `/tmp/windarmor-alg002-result.VSrTNw` 创建的隔离 build/install overlay；Targeted
Level A/B 测试直接使用源树纯 Python 路径。

实现阶段曾有两次非正式环境尝试没有形成测试结果：一次因仓库根目录不存在
`install/setup.bash` 而在 pytest 启动前退出；一次因手工 `PYTHONPATH` 覆盖 ROS overlay，导致
五个依赖 `rclpy` 的测试模块收集失败。两者均为 environment/setup failure，不是 candidate
test failure。本次正式 full Flight 回归明确加载上述隔离 overlay，收集和执行均正常。

## Configuration verification

固定正式配置为：

```text
kp_intent_per_rad = 1.0
kd_intent_per_rad_s = 0.1
```

实际读取固定 implementation commit 的默认配置精确为上述数值。`Kp` 单位为 intent/rad，
`Kd` 单位为 intent/(rad/s)；两者均为正有限值并在控制器实例内冻结。构造与 factory 测试会
拒绝零、负数、NaN、Inf、bool、string 和 unknown key。正式 benchmark 期间没有修改或调节
任一增益；它们只是 software qualification configuration，不是机器人真实最优增益或动力学
参数。

Candidate A 的瞬时无状态控制律为：

```text
target_pitch_rad = 0.0
pitch_error_rad = target_pitch_rad - relative_pitch_rad
pitch_feedback_intent = Kp * pitch_error_rad - Kd * relative_pitch_rate_rad_s
```

控制律只消费统一后的 `relative_pitch_rad` 和 `relative_pitch_rate_rad_s`，不直接读取或重新
解释 raw `angular_velocity_rad_s`，也不通过历史 pitch 和 `dt` 求导。

## Commands

### Environment and fixed configuration

实际执行：

```bash
python3 --version
python3 -c "import pytest; print(pytest.__version__)"
sed -n 's/^PRETTY_NAME=//p' /etc/os-release
uname -srmo
dpkg --print-architecture
source /opt/ros/jazzy/setup.bash && printf '%s\n' "$ROS_DISTRO"
PYTHONPATH=src/windarmor_flight_control python3 -c "from windarmor_flight_control.algorithms.alg002_candidate_a import CandidateAConfiguration, DEFAULT_KP_INTENT_PER_RAD, DEFAULT_KD_INTENT_PER_RAD_S; c=CandidateAConfiguration(); print(DEFAULT_KP_INTENT_PER_RAD, DEFAULT_KD_INTENT_PER_RAD_S, c)"
```

### Level A observations and comparative metrics

实际执行命令：

```bash
PYTHONPATH=src/windarmor_flight_control python3 -c "import json; from windarmor_flight_control.algorithms.alg002_candidate_a import Alg002CandidateAController, CandidateAConfiguration, compute_pitch_feedback_intent; from test.alg002_benchmark import collect_level_a_results, relationship_tolerance; names=('left_lift','left_pitch','right_pitch','right_lift'); controller=Alg002CandidateAController(names, CandidateAConfiguration(1.0, 0.1)); results=collect_level_a_results(controller); first={key:values[0] for key,values in results.items()}; separations={'P_div':first['ALG002-P00']-first['ALG002-P01'],'P_rec':first['ALG002-P02']-first['ALG002-P00'],'N_div':first['ALG002-N01']-first['ALG002-N00'],'N_rec':first['ALG002-N00']-first['ALG002-N02']}; pairs={'P_div':(first['ALG002-P00'],first['ALG002-P01']),'P_rec':(first['ALG002-P02'],first['ALG002-P00']),'N_div':(first['ALG002-N01'],first['ALG002-N00']),'N_rec':(first['ALG002-N00'],first['ALG002-N02'])}; tolerances={key:relationship_tolerance(*pairs[key]) for key in pairs}; metrics={'damping_separation_mirror_error':max(abs(separations['P_div']-separations['N_div']),abs(separations['P_rec']-separations['N_rec'])),'normal_mirror_symmetry_error':max(abs(first['ALG002-P00']+first['ALG002-N00']),abs(first['ALG002-P01']+first['ALG002-N01']),abs(first['ALG002-P02']+first['ALG002-N02'])),'zero_pitch_damping_symmetry':abs(first['ALG002-Z01']+first['ALG002-Z02']),'repeatability_delta':max(abs(value-values[0]) for values in results.values() for value in values)}; recovering={'positive_pitch_negative_rate':compute_pitch_feedback_intent(0.05,-1.0,kp_intent_per_rad=1.0,kd_intent_per_rad_s=0.1),'negative_pitch_positive_rate':compute_pitch_feedback_intent(-0.05,1.0,kp_intent_per_rad=1.0,kd_intent_per_rad_s=0.1)}; print(json.dumps({'configuration':{'kp_intent_per_rad':controller.configuration.kp_intent_per_rad,'kd_intent_per_rad_s':controller.configuration.kd_intent_per_rad_s},'results':results,'separations':separations,'tolerances':tolerances,'separation_pass':{key:separations[key]>tolerances[key] for key in separations},'metrics':metrics,'recovering_regression':recovering},sort_keys=True))"
```

### Targeted qualification

实际执行命令：

```bash
PYTHONPATH=src/windarmor_flight_control python3 -m pytest -p no:cacheprovider src/windarmor_flight_control/test/test_alg002_candidate_a.py -v
```

结果：`84 collected, 84 passed, 0 failed, 0 skipped`。

### ALG-001 Candidate A regression

实际执行命令：

```bash
PYTHONPATH=src/windarmor_flight_control python3 -m pytest -p no:cacheprovider src/windarmor_flight_control/test/test_alg001_candidate_a.py -v
```

结果：`47 collected, 47 passed, 0 failed, 0 skipped`。该回归没有修改或重新生成 ALG-001
Candidate A implementation/Result。

### Isolated build overlay

实际执行命令：

```bash
source /opt/ros/jazzy/setup.bash && WINDARMOR_CI_OUTPUT_ROOT=/tmp/windarmor-alg002-result.VSrTNw ./scripts/ci_software.sh build
```

结果：五个包 build PASS。

### Complete windarmor_flight_control regression

实际执行命令：

```bash
source /opt/ros/jazzy/setup.bash && source /tmp/windarmor-alg002-result.VSrTNw/install/setup.bash && python3 -m pytest -p no:cacheprovider src/windarmor_flight_control/test -q
```

结果：`481 passed, 0 failed, 0 skipped`。该命令明确加载本次隔离 build/install overlay。

### WindArmor Software CI

实际执行命令：

```bash
source /opt/ros/jazzy/setup.bash && WINDARMOR_CI_OUTPUT_ROOT=/tmp/windarmor-alg002-result.VSrTNw ./scripts/ci_software.sh
```

结果：PASS。

- CI safety check：PASS（2 files）；
- Git whitespace check：PASS；
- Python compile：PASS；
- hardware verification tooling tests：26 passed；
- five-package build：PASS；
- motor package tests：431 passed；
- fan safety regression：159 passed；
- flight/interface software tests：489 passed；
- final colcon result：`1110 tests, 0 errors, 0 failures, 0 skipped`。

这些结果都是 software/fake/mock/in-memory evidence，不是硬件验证。

## Level A results

每个正常场景都在独立运行前调用 `reset()`，并实际重复三次：

| Scenario | `relative_pitch_rad` | `relative_pitch_rate_rad_s` | 实际 `pitch_feedback_intent`（3 次） | 结果 |
| --- | ---: | ---: | --- | --- |
| `ALG002-P00` | `+0.05` | `0.00` | `-0.05, -0.05, -0.05` | PASS |
| `ALG002-P01` | `+0.05` | `+0.20` | `-0.07, -0.07, -0.07` | PASS |
| `ALG002-P02` | `+0.05` | `-0.20` | `-0.03, -0.03, -0.03` | PASS |
| `ALG002-N00` | `-0.05` | `0.00` | `+0.05, +0.05, +0.05` | PASS |
| `ALG002-N01` | `-0.05` | `-0.20` | `+0.07, +0.07, +0.07` | PASS |
| `ALG002-N02` | `-0.05` | `+0.20` | `+0.03, +0.03, +0.03` | PASS |
| `ALG002-Z01` | `0.00` | `+0.20` | `-0.020000000000000004`（3 次） | PASS |
| `ALG002-Z02` | `0.00` | `-0.20` | `+0.020000000000000004`（3 次） | PASS |

P00/N00 zero-rate、P01/N01 diverging、P02/N02 recovering、Z01/Z02 zero-pitch moving、
finite output、方向和有符号关系全部 PASS。P02/N02 没有被错误限制为始终与 pitch error
同号。

### Damping separation

关系容差使用冻结公式：

```text
tol(a,b) = 1e-9 + 1e-6 * max(abs(a), abs(b))
```

| 指标 | 实际 separation | 对应 tolerance | 判定 |
| --- | ---: | ---: | --- |
| `P_div = P00 - P01` | `0.020000000000000004` | `7.1e-08` | PASS |
| `P_rec = P02 - P00` | `0.020000000000000004` | `5.1e-08` | PASS |
| `N_div = N01 - N00` | `0.020000000000000004` | `7.1e-08` | PASS |
| `N_rec = N00 - N02` | `0.020000000000000004` | `5.1e-08` | PASS |

四个 separation 都严格大于各自容差，Damping effect present：PASS。

### Mirror and repeatability metrics

- Damping separation mirror error：
  `max(abs(P_div-N_div), abs(P_rec-N_rec)) = 0.0 intent unit`；
- Normal mirror symmetry error：
  `max(abs(P00+N00), abs(P01+N01), abs(P02+N02)) = 0.0 intent unit`；
- Zero-pitch damping symmetry：`abs(Z01+Z02) = 0.0 intent unit`；
- Repeatability delta：对每个正常场景三次结果计算
  `max(abs(value_i-value_0))`，所有场景最大值为 `0.0 intent unit`。

### ALG-001 inheritance gate

结果：PASS。

这不是沿用 ALG-001 Candidate A 的历史 PASS。Targeted qualification 把当前 ALG-002
Candidate A 的 rate 固定为 `0.0`，针对未修改的 `ALG001-FIXTURE-v1` 和 ALG-001 Profile v1
实际重新验证了 neutral、direction、strict monotonic magnitude、proportional-style
consistency、symmetry、finite output、三次 repeatability、完整普通 command、fail-close、
`dt`、reset 和 factory。当前 Candidate 的 zero-rate Level A 结果与 `Kp=1.0` 的基础反馈一致。

### Recovering early-braking regression

该 implementation regression 使用 Profile fixture 之外的更强 rate：

| 输入 | 实际 intent | 结果 |
| --- | ---: | --- |
| `pitch=+0.05 rad, rate=-1.0 rad/s` | `+0.05` | PASS |
| `pitch=-0.05 rad, rate=+1.0 rad/s` | `-0.05` | PASS |

这证明实现没有加入“total intent 必须始终与 pitch error 同号”的错误 clamp。它不是
`ALG002-FIXTURE-v1` 正常场景，也不是 overshoot 或真实动态效果证据。

## Level B results

Candidate A 通过现有 factory/loader 成功加载。全部正常场景返回通过
`validate_flight_command()` 的普通完整帧：

- motor keys 精确为 `left_lift/left_pitch/right_pitch/right_lift`；
- motor payload 逐帧复制当前合法 feedback position，不依赖上一帧；
- fan payload 为合法的 `left=0.0, right=0.0`；
- default controller 和 example controller 保持独立且未改变；
- raw gyro 值改变而统一 pitch/rate 不变时，ALG-002 结果不变；
- 非法 Candidate A 配置按现有 loader 风格明确拒绝。

该 hold/fan-zero payload 不编码 `pitch_feedback_intent`，不表示任何真实电机/风扇方向或
control allocation，也不能被解释为真实恢复命令。

## Fail-close, dt and reset results

| Scenario | Variant / layer | 实际结果 |
| --- | --- | --- |
| `ALG002-F01` | valid IMU 缺 rate / state validation | 前置拒绝，未调用 controller；PASS |
| `ALG002-F01` | 合法 unobserved IMU / controller | 合法无载荷 safe-stop；PASS |
| `ALG002-F02` | rate `NaN/+Inf/-Inf` / state validation | 三个 variant 均前置拒绝；PASS |
| `ALG002-F03` | IMU stale / controller | 合法无载荷 safe-stop；PASS |
| `ALG002-F04` | `required_inputs_fresh=false` / controller | 合法无载荷 safe-stop；PASS |
| Inherited safety | invalid/unobserved IMU、未知/激活 E-STOP | 合法场景 safe-stop；PASS |
| Inherited safety | pitch 缺失或 `NaN/+Inf/-Inf` | 按规定 layer 拒绝或 safe-stop；PASS |
| Inherited safety | motor key 缺失、unobserved/stale/invalid/unhealthy | 按规定 layer 拒绝或 safe-stop；PASS |
| `ALG002-D00A` | `dt=0.02` | 正常 finite intent 和合法完整 command；PASS |
| `ALG002-D00B` | `dt=0.037` | 与 D00A 的 intent/command 一致；PASS |
| `ALG002-D01` | `dt=0` | 合法无载荷 safe-stop；PASS |
| `ALG002-D02` | `dt=-0.01` | 合法无载荷 safe-stop；PASS |
| `ALG002-D03` | `dt=NaN` | 合法无载荷 safe-stop；PASS |
| `ALG002-D04` | `dt=+Inf/-Inf` | 两个 variant 均为合法无载荷 safe-stop；PASS |
| `ALG002-R01` | reset + 不同当前 motor frames | intent 无历史依赖且不复用旧 payload；PASS |

所有 controller-layer safe-stop 都精确等于 `FlightCommand.safe_stop()`，不携带 motor/fan
payload，并通过 `validate_flight_command()`。普通命令之后的 fail-close 也不复用上一帧
payload。

## Comparative metrics

Hard Qualification 全部 PASS 后独立记录以下指标；这些指标不合成为总分。

### Damping and symmetry

- `P_div/P_rec/N_div/N_rec`：均为 `0.020000000000000004 intent unit`；
- damping separation mirror error：`0.0 intent unit`；
- normal mirror symmetry error：`0.0 intent unit`；
- zero-pitch damping symmetry：`0.0 intent unit`；
- repeatability delta：`0.0 intent unit`。

### Implementation complexity

使用下面的命令统计 Candidate A production module 的 physical LOC；该口径包含空行、注释和
docstring：

```bash
wc -l src/windarmor_flight_control/windarmor_flight_control/algorithms/alg002_candidate_a.py
```

结果：`216 physical LOC`。

Cyclomatic complexity：`NOT MEASURED — no additional dependency introduced`。

### Test coverage quality

- ALG-002 Profile v1 required scenario/variant coverage：全部 Hard Qualification 项已覆盖；
- ALG-001 inheritance：当前 ALG-002 candidate 的 zero-rate、safety、`dt`、reset、factory 和
  FlightCommand 契约已实际重新验证；
- targeted qualification：84 tests，全部 PASS；
- existing ALG-001 Candidate A regression：47 tests，全部 PASS；
- complete `windarmor_flight_control` regression：481 tests，全部 PASS；
- full CI：1110 tests，0 errors、0 failures、0 skipped。

Code coverage percentage：`NOT MEASURED`。没有运行 coverage.py；场景覆盖和测试数量不冒充
line/branch coverage。

### Configuration clarity

Review：PASS。

- 正式配置只有 `kp_intent_per_rad` 和 `kd_intent_per_rad_s` 两个键；
- 稳定序列化值分别为 `1.0` 和 `0.1`，默认值明确且在实例内冻结；
- 单位分别为 intent/rad 和 intent/(rad/s)；
- 两者均要求正有限数值，并拒绝 bool/string；
- unknown keys 被明确拒绝；
- 正式 benchmark 前后配置一致，没有根据输出调参。

## Level C

`NOT EXECUTED`

Reason：current `synthetic_dry_run` selects the teaching controller and Candidate A implementation
does not modify that behavior。Level C 不是 ALG-002 Profile v1 的 Level A/B Hard Qualification
必需项；本结果不声称完成 integration simulation。

## Level D

`NOT EXECUTED`

Reason：ALG-002 Profile v1 将 `S01/S02/S03` 定义为推荐扩展，不属于 Hard Qualification；当前
固定 implementation 没有 sequence runner。本阶段没有修改固定 implementation/test semantics
来补充 runner，也不把独立静态场景冒充 sequence、replay 或动态仿真。

## Future-task boundary review

Review：PASS。Candidate A 只实现无状态瞬时 `Kp * error - Kd * rate`，安全检查和合法 frame
构造之外，没有使用或实现：

- filtering、low-pass、deadband、hysteresis 或 smoothing；
- slew-rate、output shaping 或 dynamic saturation；
- recovery state machine、timeout 或 recovery phase；
- motor/fan allocation、actuator priority 或 allocation matrix；
- roll/multi-axis control 或完整 dynamic recovery；
- integral、raw gyro axis/sign logic、finite-difference derivative 或硬件方向映射。

`ALG-003`–`ALG-008` implementation leakage：`NO`。

## Qualification

Hard Qualification：`PASS`

Overall：`ALG-002 QUALIFIED`

该结论严格限定为固定 implementation commit 和 `ALG002-FIXTURE-v1` 上的 Level A/B 纯软件
qualification。比较指标没有替代或抵消 Hard Qualification；全部 Hard Gate 均实际 PASS。

## Known limitations

- 只完成 synthetic software fixture 上的 ALG-002 qualification；
- `Kp=1.0`、`Kd=0.1` 不代表真实机器人最优增益或真实动力学调参结果；
- 没有 filtering、noise robustness、output shaping 或 slew-rate；
- 没有 recovery state machine 或 control allocation；
- abstract intent 尚未映射到真实电机/风扇，software feedback sign 不代表真实 actuator
  direction；
- Level B hold/fan-zero payload 不属于真实恢复命令；
- Level D sequence/replay 未执行，没有 dynamic model 或可信闭环仿真；
- 没有 recovery time、overshoot、oscillation、最大可恢复扰动或真实 control effort 数据；
- 没有真实 Balance Recovery 证据；
- 没有硬件验证；
- 真实闭环验证前，必须继续保证 Flight Runtime 和 relative attitude 发布者的
  `pitch_axis_sign` 配置一致，当前纯软件结果不验证运行时配置不会漂移。

## Tests not executed

- Candidate A Level C synthetic DRY_RUN：未执行，原因见上文；
- Level D `ALG002-S01/S02/S03` sequence/replay：未执行，原因见上文；
- Level E dynamic benchmark/trusted simulation：未执行，不属于 ALG-002 Profile v1；
- Level F bounded hardware verification：未执行且未授权；
- code coverage percentage：未测量；
- cyclomatic complexity：未测量；
- 真实 IMU、串口、CAN、CyberGear、GPIO/PWM、ESC、电机和风扇测试：未执行且未授权。
