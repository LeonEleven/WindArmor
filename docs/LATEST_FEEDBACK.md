# INTERNAL DEVELOPMENT HANDOFF — DOC-1 Complete

> 日期：2026-08-24
> task-start branch / HEAD：`master` / `a6fda76aba5b2a771f6abe53e976564cf667fc0c`
> task：DOC-1 truth correction + newcomer algorithm onboarding + software-only teaching path
> existing production behavior changed：`NO`
> default config / launch / interface changed：`NO`
> hardware executed：`NO`

## 正式状态（本轮未改变）

```text
Gate B: COMPLETE
Gate C: COMPLETE
Gate D: COMPLETE
v0.4.0 hardware / functional verification: COMPLETE
Documentation audit: COMPLETE
DOC-1: COMPLETE
Release readiness review: PENDING
Current stable release: v0.3.2
```

Gate B/C/D 的 final PASS、invalidated/NOT VERIFIED attempt、session ID、operator physical
observation、continuous recorder evidence、powered boundary 和 limitation 继续保存在
`docs/V0.4.0_HARDWARE_VERIFICATION_PLAN.md`。本轮没有删除或重写这些历史，也没有执行新的
硬件 session。

## DOC-1 A — Truth / documentation layer

### 五个 P0 disposition

1. **API stale verification claim — RESOLVED。** `FLIGHT_CONTROL_API.md` 现在简洁记录
   v0.4.0 release-specific hardware/functional verification 已完成，并链接 verification plan；
   不复制 session history，也不把结果扩展到任意新算法或新场景。
2. **Architecture stale verification claim — RESOLVED。** 删除 Task build-diary/future-state
   叙事，改为 current architecture，Gate B/C/D 状态只保留简洁链接。
3. **`required_inputs_fresh` semantics — RESOLVED。** API、Architecture 和 `SystemState`
   docstring 均明确：它只聚合 paired IMU freshness 和所有 configured motor feedback
   freshness；不包含 fan、安全 readback、E-STOP clearance、ownership 或 authority readiness，
   不能当作 whole-system ready。`actuation_allowed` 是独立 Runtime dispatch decision。
4. **Motor cold-start documentation — RESOLVED。** package README 已从旧 `0.0 rad` startup
   target 改为本次 fresh/valid measured-position hold；明确 startup hold 不等于机械零点，
   `/motors/set_zero` 由 operator 在正确 reference posture 下显式执行，单位 rad。
5. **Historical GPIO12/13 instruction — RESOLVED。** v0.3.2 checklist 保留历史原文，但增加
   prominent HISTORICAL banner 和 item-level 禁止当前执行警告；当前 mapping 明确为
   LEFT GPIO12/pin32、RIGHT GPIO26/pin37，GPIO13 保留给 CAN HAT INT_1，并链接 Hardware
   Reference。

### Algorithm Developer Guide

新增 `docs/ALGORITHM_DEVELOPER_GUIDE.md`，以第一天加入项目的基础 Python 开发者为 audience，
按 step-by-step 顺序覆盖：

- pure algorithm/hardware boundary 和数据流；
- 当前真实文件路径；
- 完整、可复制的最小 pitch controller；
- `reset()`、`update()` 和非固定 `dt`；
- `FlightState`、IMU、motor、fan、safe-stop；
- 完整 unit-test 示例和 exact command；
- LEVEL 1 pure unit → LEVEL 2 software-only synthetic DRY_RUN；
- authority plain-language boundary；
- LEVEL 3 maintainer/operator-owned bounded hardware review；
- common mistakes、debug checklist 和 review checklist。

文档明确算法开发者不需要修改 Runtime/authority/manager/driver，不能自行 enable takeover、
prepare、set zero、reset E-STOP/ERROR、启动 hardware launch 或给 actuator 通电。

### API restructuring

`FLIGHT_CONTROL_API.md` 现在只承担 algorithm-facing reference：

- `FlightController.reset/update` 和 factory contract；
- `FlightState`/IMU/motor/fan/system field type、unit、frame/sign、`None`、valid/fresh/healthy；
- `FlightCommand` complete frame、normalized fan、safe-stop；
- validation rules、minimal fake/test/demo examples；
- Guide/Architecture/Hardware/verification advanced links。

authority state machine、epoch/generation、two-phase ownership、atomic cutoff、lease、rollback、
shutdown 和 adapter details 不再在 API 重复展开。

### Architecture restructuring

`FLIGHT_CONTROL_ARCHITECTURE.md` 现在面向 Runtime/safety/integration maintainer，集中记录：

- package/dependency boundary 和 observation aggregation；
- authoritative safety readback 与 unknown semantics；
- authority/preflight/actuation readiness；
- two-phase owner handoff、atomic cutoff 和 command envelope；
- handoff/command leases；
- safe-stop/E-STOP 区分；
- actuator adapter final veto；
- rollback、shutdown、restart isolation 和 non-negotiable safety invariants。

旧 Task 1–4 chronology/future language 已移除；算法教程和逐字段 reference 分别链接 Guide/API。

### README navigation

本轮没有执行 README 大清理。只把“飞控算法开发”入口调整为：

1. Algorithm Developer Guide；
2. Flight Control API；
3. Architecture（需要深入时）；
4. Hardware Reference（需要硬件背景时）。

同时加入 newcomer targeted test 和 synthetic DRY_RUN exact command。README 的 Gate/history
consolidation 保留给 DOC-2。

## DOC-1 B — Teaching software layer

### Non-default educational controller

新增：

```text
src/windarmor_flight_control/windarmor_flight_control/
  algorithms/example_algorithm_controller.py
```

`ExampleAlgorithmController`：

- structurally satisfies `FlightController`；
- factory contract 可被现有 loader 显式加载；
- 捕获一次完整 valid/fresh/healthy motor position baseline；
- relative pitch × `0.25` 生成 `left_pitch` 示例 offset，clamp 到 `±0.05 rad`；
- positive/negative pitch 分别生成 LEFT/RIGHT normalized fan preview，clamp 到 `0.10`；
- 输出完整四 motor frame 和左右 fan payload；
- invalid/stale/unknown input、E-STOP 或非法 `dt` 返回 payload-free safe-stop，并清除 baseline；
- reset 清除 algorithm-local baseline；
- no ROS node/publisher/client/service，no CAN/serial/GPIO/PWM/driver/manager import。

它是 **NON-DEFAULT / EDUCATIONAL / SOFTWARE-FIRST** controller。默认 factory、default config、
Runtime safety、authority、hardware launch 和 existing production controller 均未改变。

### Unit tests

新增：

```text
src/windarmor_flight_control/test/test_example_algorithm_controller.py
src/windarmor_flight_control/test/test_synthetic_dry_run.py
```

覆盖 reset/recapture、neutral、positive/negative pitch、motor/fan clamp、stale/invalid input
safe-stop、complete output shape、finite values、factory loading、required logical name、human-readable
demo 和 AST no-ROS/no-hardware imports。

### Software-only synthetic DRY_RUN

新增：

```text
src/windarmor_flight_control/windarmor_flight_control/synthetic_dry_run.py
```

exact command：

```bash
PYTHONPATH=src/windarmor_flight_control \
python3 -m windarmor_flight_control.synthetic_dry_run
```

自定义 pitch：

```bash
PYTHONPATH=src/windarmor_flight_control \
python3 -m windarmor_flight_control.synthetic_dry_run \
  --pitches -0.20 -0.10 0.0 0.10 0.20
```

demo 使用 current factory loader、fake immutable state、state/command validation 和 teaching
controller，打印 pitch、`left_pitch` target、fan left/right、safe-stop 以及
`authority=NONE / actuation_allowed=false`。最后主动展示 stale input → safe-stop。

该路径不 import `rclpy`，不创建 ROS graph，不读取 `/dev`，不访问 CAN、serial、GPIO、PWM、
ESC、电机或风扇，不创建 authority/actuator publisher/client，也不调用 prepare/E-STOP。

## Validation results

### Targeted

```text
72 passed in 0.58s
```

覆盖 teaching controller/demo、default example、factory loader、models、state aggregator、
validation 和 import boundary。首次 targeted run 的唯一 failure 是 source-string safety test 把
输出文案中的 `serial` 误判为 import；检查改为 AST import analysis 后 final run 全绿，不涉及
controller behavior 修复。

教程 synthetic command 已人工运行，输出按顺序显示 negative/neutral/positive/clamped pitch、
左右 fan preview、无 authority/no actuation 和 stale safe-stop。

### Full software CI

执行：

```bash
./scripts/ci_software.sh
```

结果：

```text
CI safety check: PASS
Git whitespace check: PASS
Python compile: PASS
hardware verification tooling: 26 passed
colcon build: 5 packages finished
motor package: 431 passed
fan package: 159 passed
Flight/interfaces: 318 passed
full colcon: 939 tests, 0 errors, 0 failures, 0 skipped
```

这些是 pure/fake/mock/software evidence，不是新的真实硬件验证。

## Stale-content regression

- API/Architecture 不再包含 Flight takeover “仅 software、尚未 hardware verified” 或旧 Task 4
  future-state claim；
- current docs 中的 `required_inputs_fresh` 均使用 IMU + configured motors 精确语义；
- package README 中 `0.0 rad` 只用于说明“不是 cold-start fallback”以及 set-zero 后 target；
- GPIO13 出现处均为 current reservation/diagnosis 或已加 HISTORICAL banner 的 v0.3.2 evidence；
- verification plan 中 `NOT VERIFIED`、旧 GPIO/offset 和 attempt history 保持历史分类，不作为
  current instructions；
- `尚未` 的剩余 current occurrences 表达 unknown observation 或明确未完成的 performance
  calibration，不与 Gate B/C/D 状态冲突。

`git diff --check` 在 LATEST 更新前已 PASS；final handoff 后仍需再次执行。

## Recommended next task

下一任务：**DOC-2 — README/docs consolidation + verification archive**。

建议范围：

1. 将 README 836+ 行收敛为项目、stable/development 状态、安装/build、正常使用、算法入口和
   documentation index；
2. 把 Gate B/C/D chronology、timing、recorder/watchdog 细节移到 versioned verification record；
3. 建立 `docs/verification/v0.4.0/HARDWARE_VERIFICATION_RECORD.md`，完整保留 final、invalidated、
   NOT VERIFIED、session IDs、operator evidence、powered boundaries 和 limitation；
4. consolidation package hardware guides，避免多份 executable instructions 分裂 authority；
5. 修复 immutable v0.3.2 release evidence 指向 mutable handoff 的链接；
6. 运行 link/path/evidence inventory、`git diff --check`；仅文档移动时不需要硬件。

本轮不 commit、push、tag 或 release，等待用户审核。
