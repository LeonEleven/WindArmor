# ALG-001 Candidate A Result

本文记录 Candidate A 针对固定 implementation commit 的正式纯软件 qualification 结果。
能力和结论边界分别以 [ALG-001 Task Spec v1](../algorithm_tasks/ALG-001.md) 和
[Algorithm Benchmark v1 / ALG-001 Profile v1](../ALGORITHM_BENCHMARK.md) 为准。本文不是
动态仿真、真实执行器验证或硬件运行授权。

## Metadata

| 字段 | 值 |
| --- | --- |
| Candidate | `Candidate A` |
| Task | `ALG-001 / Task Spec v1` |
| Benchmark | `Algorithm Benchmark v1 / ALG-001 Profile v1` |
| Fixture | `ALG001-FIXTURE-v1` |
| Implementation lineage | `Independent Candidate A` |
| Implementation task baseline | `7971ffa14d7f60d93a6100d128e875ee79908c2f` |
| Implementation commit | `fe575c9589013138d238e567e93dac2925384ab7` |
| Configuration | `{"kp_intent_per_rad": 1.0}` |
| Benchmark date | `2026-09-08` |
| Hardware access | `NO` |
| Hardware validation | `NOT EXECUTED / NOT AUTHORIZED` |

正式运行开始时，当前分支为 `feature/algo-001-candidate-a`，工作区干净，`HEAD` 精确等于
上述 implementation commit。所有 benchmark、回归和 CI 都先在该干净提交上完成；取得结果
后才创建本文。

## Environment

| 项目 | 实际值 |
| --- | --- |
| OS | `Ubuntu 24.04.4 LTS` |
| Kernel / platform | `Linux 6.8.0-1064-raspi aarch64 GNU/Linux` |
| ROS distro | `jazzy` |
| Python | `3.12.3` |
| pytest | `7.4.4` |
| pytest pluggy | `1.4.0` |
| pytest plugins shown by targeted run | `colcon-core 0.20.1`, `cov 4.1.0` |

没有为本次 benchmark 新增依赖。需要 `rclpy` 和本工作空间生成接口的完整 Flight 测试使用
本次在 `/tmp` 创建的隔离 build/install overlay；Targeted Level A/B 测试直接使用源树纯
Python 路径。

## Configuration verification

固定正式配置为：

```text
kp_intent_per_rad = 1.0
```

实际读取 implementation commit 中的默认值为 `1.0`，检查结果为正且有限。正式 benchmark
期间没有修改或调节该值。`Kp=1.0` 只是软件 qualification 配置，不是机器人真实最优增益。

## Commands

### Level A observation and comparative metrics

实际执行命令：

```bash
PYTHONPATH=src/windarmor_flight_control python3 -c "import json; from windarmor_flight_control.algorithms.alg001_candidate_a import Alg001CandidateAController, CandidateAConfiguration; from test.alg001_benchmark import NORMAL_SCENARIOS, collect_level_a_results; names=('left_lift','left_pitch','right_pitch','right_lift'); controller=Alg001CandidateAController(names, CandidateAConfiguration(1.0)); results=collect_level_a_results(controller); scenarios={item.scenario_id:item for item in NORMAL_SCENARIOS}; first={key:values[0] for key,values in results.items()}; gains=[first[key]/scenarios[key].pitch_error_rad for key in first if scenarios[key].pitch_error_rad != 0.0]; metrics={'proportional_consistency_error':max(abs(value-1.0) for value in gains),'symmetry_error':max(abs(first['ALG001-P01']+first['ALG001-N01']),abs(first['ALG001-P02']+first['ALG001-N02'])),'repeatability_delta':max(abs(left-right) for values in results.values() for left in values for right in values)}; print(json.dumps({'results':results,'metrics':metrics}, sort_keys=True))"
```

### Targeted qualification

实际执行命令：

```bash
PYTHONPATH=src/windarmor_flight_control python3 -m pytest -p no:cacheprovider src/windarmor_flight_control/test/test_alg001_candidate_a.py -v
```

结果：`47 collected, 47 passed, 0 failed, 0 skipped`。

### Isolated build overlay

实际执行命令：

```bash
source /opt/ros/jazzy/setup.bash && WINDARMOR_CI_OUTPUT_ROOT=/tmp/windarmor-alg001-result.iClWLo ./scripts/ci_software.sh build
```

结果：五个包 build PASS。

### Complete windarmor_flight_control regression

实际执行命令：

```bash
source /opt/ros/jazzy/setup.bash && source /tmp/windarmor-alg001-result.iClWLo/install/setup.bash && python3 -m pytest -p no:cacheprovider src/windarmor_flight_control/test -q
```

结果：`357 passed, 0 failed, 0 skipped`。该命令加载了上述 build/install overlay。

### WindArmor Software CI

实际执行命令：

```bash
source /opt/ros/jazzy/setup.bash && WINDARMOR_CI_OUTPUT_ROOT=/tmp/windarmor-alg001-result.iClWLo ./scripts/ci_software.sh
```

结果：PASS。

- CI safety check：PASS（2 files）；
- Git whitespace check：PASS；
- Python compile：PASS；
- hardware verification tooling tests：26 passed；
- five-package build：PASS；
- motor package tests：431 passed；
- fan safety regression：159 passed；
- flight/interface software tests：365 passed；
- final colcon result：`986 tests, 0 errors, 0 failures, 0 skipped`。

这些结果都是 software/fake/mock/in-memory evidence，不是硬件验证。

## Level A results

每个正常场景都在独立运行前调用 `reset()`，并实际重复三次：

| Scenario | `relative_pitch_rad` | `pitch_error_rad` | 实际 `pitch_feedback_intent`（3 次） | 结果 |
| --- | ---: | ---: | --- | --- |
| `ALG001-N00` | `0.00` | `0.00` | `0.0, 0.0, 0.0` | PASS |
| `ALG001-P01` | `+0.05` | `-0.05` | `-0.05, -0.05, -0.05` | PASS |
| `ALG001-P02` | `+0.10` | `-0.10` | `-0.1, -0.1, -0.1` | PASS |
| `ALG001-N01` | `-0.05` | `+0.05` | `+0.05, +0.05, +0.05` | PASS |
| `ALG001-N02` | `-0.10` | `+0.10` | `+0.1, +0.1, +0.1` | PASS |

Neutral bias、direction、strict monotonic magnitude、proportional consistency、symmetry、
finite output 和 repeatability 全部 PASS。`dt=0.02 s` 与另一个正有限值 `0.037 s` 不改变
基础 intent 或当前状态 hold frame。

## Level B results

Candidate A 通过现有 factory/loader 成功加载。五个正常场景全部返回通过
`validate_flight_command()` 的普通完整帧：

- motor keys 精确为 `left_lift/left_pitch/right_pitch/right_lift`；
- motor payload 逐帧复制当前合法 feedback position，不依赖上一帧；
- fan payload 为合法的 `left=0.0, right=0.0`；
- default controller 和 example controller 保持独立且未改变；
- 非法 Candidate A 配置按现有 loader 风格明确拒绝。

该 hold/fan-zero payload 不编码 `pitch_feedback_intent`，不表示任何真实电机/风扇方向或
control allocation，也不能被解释为真实恢复命令。

## Fail-close and reset results

| Scenario | Variant / layer | 实际结果 |
| --- | --- | --- |
| `ALG001-F01` | invalid、unfresh IMU / controller | 合法无载荷 safe-stop；PASS |
| `ALG001-F02` | stale IMU / controller | 合法无载荷 safe-stop；PASS |
| `ALG001-F03` | `required_inputs_fresh=false` / controller | 合法无载荷 safe-stop；PASS |
| `ALG001-F04` | valid IMU 缺 pitch / state validation | 前置拒绝，未调用 controller；PASS |
| `ALG001-F04` | 合法 unobserved IMU / controller | 合法无载荷 safe-stop；PASS |
| `ALG001-F05` | pitch NaN / state validation | 前置拒绝，未调用 controller；PASS |
| `ALG001-F06` | pitch `+Inf` / state validation | 前置拒绝，未调用 controller；PASS |
| `ALG001-F06` | pitch `-Inf` / state validation | 前置拒绝，未调用 controller；PASS |
| `ALG001-F07` | 缺 motor key / state validation | 前置拒绝，未调用 controller；PASS |
| `ALG001-F07` | 完整 key、motor unobserved / controller | 合法无载荷 safe-stop；PASS |
| `ALG001-F08` | motor stale / controller | 合法无载荷 safe-stop；PASS |
| `ALG001-F08` | motor invalid / controller | 合法无载荷 safe-stop；PASS |
| `ALG001-F08` | motor unhealthy / controller | 合法无载荷 safe-stop；PASS |
| `ALG001-D01` | `dt=0` / controller | 合法无载荷 safe-stop；PASS |
| `ALG001-D02` | `dt=-0.01` / controller | 合法无载荷 safe-stop；PASS |
| `ALG001-D03` | `dt=NaN` / controller | 合法无载荷 safe-stop；PASS |
| `ALG001-D04` | `dt=+Inf` / controller | 合法无载荷 safe-stop；PASS |
| `ALG001-D04` | `dt=-Inf` / controller | 合法无载荷 safe-stop；PASS |
| `ALG001-R01` | reset + 不同当前 motor frames | intent 不受历史影响且不复用旧 payload；PASS |

所有 controller-layer safe-stop 都精确等于 `FlightCommand.safe_stop()`，不携带 motor/fan
payload，并通过 `validate_flight_command()`。附加的未知/已激活 E-STOP 和普通命令后
fail-close 不复用 payload 检查也均 PASS。

## Comparative metrics

Hard Qualification 全部 PASS 后独立计算以下指标；这些指标不合成为总分。

### Proportional consistency error

对四个非零场景计算 `Ki = feedback_i / pitch_error_i`，再取：

```text
max_i abs(Ki - configured_Kp)
```

实际四个 `Ki` 均为 `1.0 intent/rad`；结果为 `0.0 intent/rad`。

### Symmetry error

计算：

```text
max(
  abs(feedback_P01 + feedback_N01),
  abs(feedback_P02 + feedback_N02)
)
```

结果为 `0.0 intent unit`。

### Repeatability delta

对每个正常场景的三次实际结果计算全部两两绝对差，再取所有场景中的最大值。结果为
`0.0 intent unit`。

### Implementation complexity

使用下面的命令统计 Candidate A production module 的 physical LOC；该口径包含空行、注释和
docstring：

```bash
wc -l src/windarmor_flight_control/windarmor_flight_control/algorithms/alg001_candidate_a.py
```

结果：`188 physical LOC`。

Cyclomatic complexity：`NOT MEASURED — no additional dependency introduced`。

### Test coverage quality

- ALG-001 Profile v1 required scenario coverage：全部场景和规定 variant 已覆盖；
- targeted qualification：47 tests，全部 PASS；
- complete `windarmor_flight_control` regression：357 tests，全部 PASS；
- full CI：986 tests，0 errors、0 failures、0 skipped。

Code coverage percentage：`NOT MEASURED`。场景覆盖与测试数量不冒充 line/branch coverage。

### Configuration clarity

Review：PASS。

- 正式配置只有一个键 `kp_intent_per_rad`；
- 默认值 `1.0` 明确且在实例内冻结；
- 构造时要求正有限数值并拒绝 bool/string；
- unknown keys 被明确拒绝；
- 正式 benchmark 前后配置一致，没有根据输出调参。

## Level C

`NOT EXECUTED`

Reason：current `synthetic_dry_run` selects the teaching controller and Candidate A implementation
does not modify that behavior。Level C 不是 ALG-001 Profile v1 的 A/B Hard Qualification 必需项；
本结果不声称完成 integration simulation。

## Future-task boundary review

Review：PASS。Candidate A 控制律只使用 `relative_pitch_rad` 和固定配置。安全检查/合法 frame
构造之外，没有使用或实现：

- `angular_velocity_rad_s`、`linear_acceleration_m_s2`、roll 或 yaw；
- previous pitch、time history、filter、deadband、derivative 或 damping；
- slew-rate 或其它 output shaping；
- recovery state machine；
- real motor/fan control allocation；
- multi-axis recovery 或 dynamic recovery logic。

`ALG-002`–`ALG-008` implementation leakage：`NO`。

## Qualification

Hard Qualification：`PASS`

Overall：`ALG-001 QUALIFIED`

该结论严格限定为固定 implementation commit 和 `ALG001-FIXTURE-v1` 上的 Level A/B 纯软件
qualification。

## Known limitations

- 只有 synthetic software fixture qualification；
- `Kp=1.0` 不代表真实最优增益；
- software feedback sign 不代表真实 actuator direction；
- Level B hold/fan-zero payload 不属于真实 control allocation；
- 没有 dynamic model、sequence/replay 或可信闭环仿真；
- 没有 recovery time、overshoot、oscillation 或真实 control effort 数据；
- 没有已验证最大安全倾角或可恢复倾角；
- 没有真实 Balance Recovery 证据；
- 没有硬件验证。

## Tests not executed

- Candidate A Level C synthetic DRY_RUN：未执行，原因见上文；
- Level D replay/sequence benchmark：未执行，不属于 ALG-001 Profile v1；
- Level E dynamic benchmark/trusted simulation：未执行，不属于 ALG-001 Profile v1；
- Level F bounded hardware verification：未执行且未授权；
- code coverage percentage：未测量；
- cyclomatic complexity：未测量；
- 真实 IMU、串口、CAN、CyberGear、GPIO/PWM、ESC、电机和风扇测试：未执行且未授权。
