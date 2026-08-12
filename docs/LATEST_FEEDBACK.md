# 最新反馈：v0.4.0 Task 5 Repository Cleanup & Algorithm Handoff

> 本文件只保留当前最新任务反馈。
>
> 日期：2026-08-12

## Scope

Task 5 已完成文档迁移、仓库审计、算法交接入口和完整无硬件软件验证。

新增：

- `docs/HARDWARE_REFERENCE.md`。

删除：

- `docs/FIRST_COMMAND.md`；
- `docs/MANUAL_VERIFICATION.md`。

修改：

- `AGENTS.md`：稳定基线、权威来源、工作流文档语义、五包 CI 和工程措辞规则；
- `README.md`：精简 Flight 内部实现叙述，增加硬件参考与算法交接入口，移除已删除
  人工验证文档的链接；
- `docs/FLIGHT_CONTROL_API.md`：增加 Quick Start / Handoff；
- `.github/workflows/ci.yml`、`scripts/ci_software.sh`：修正五包和 flight/interface
  测试阶段显示文字，未放宽 CI safety checker；
- `src/imu_cybergear_ros2/README.md` 及其三个 package docs：修正旧工作区路径、旧
  快捷目标/速度说明、失效引用，并明确硬件授权门槛；
- `src/windarmor_flight_control/package.xml`、`setup.py`：同步当前 authority runtime
  和 actuator adapter 的 description；
- `src/windarmor_flight_control/config/flight_control.yaml`：仅把一次性 Task 编号注释
  改为当前工程状态措辞；配置值未改变；
- 本反馈。

未修改 motor/fan/IMU/Flight Runtime 控制逻辑、ROS message/service、launch 行为、
测试代码或受保护硬件配置。package metadata 只修改了 Flight package description；
五包版本、依赖、maintainer、entry point 均未改变。

任务开始前用户已有的 `docs/NEXT_COMMAND.md` 修改未编辑。任务开始与本反馈生成前
SHA-256 均为
`3505ade3ec29a6afdb7e46fb9270a4c69758036df7531138746e0fc538ad5292`。

最终根 `docs/` inventory：

```text
docs/
├── FLIGHT_CONTROL_API.md
├── FLIGHT_CONTROL_ARCHITECTURE.md
├── HARDWARE_REFERENCE.md
├── LATEST_FEEDBACK.md
├── NEXT_COMMAND.md
├── RELEASE_NOTES_v0.3.2.md
└── V0.3.2_RC_HARDWARE_CHECKLIST.md
```

## Documentation Classification

### KEEP

- `docs/FLIGHT_CONTROL_ARCHITECTURE.md`：Flight 长期架构依据；其中 Task 编号用于
  区分架构演进阶段，不是 stale current-state claim；
- `docs/NEXT_COMMAND.md`：当前最新任务，保持用户原文；
- `docs/RELEASE_NOTES_v0.3.2.md`：v0.3.2 历史发布证据；
- `docs/V0.3.2_RC_HARDWARE_CHECKLIST.md`：v0.3.2 历史实机回归证据；
- `docs/HARDWARE_REFERENCE.md`：完成迁移后的长期硬件依据。

### MIGRATE

- `docs/FIRST_COMMAND.md` 中唯一长期有效的 platform、motor mechanical mapping、
  IMU mounting/frame、GPIO12 已验证连接背景已迁入 `HARDWARE_REFERENCE.md`；
- `docs/MANUAL_VERIFICATION.md` 中仍适用的带电授权、设备/限制/急停/停止条件记录、
  pure/mock 不等于实机验证等规则已由 `AGENTS.md` 的现有最高安全规则覆盖；没有把
  一次性 v0.3.0 后速度验证流程迁入长期文档。

### DELETE

- `docs/FIRST_COMMAND.md`：历史启动任务背景，迁移后不再作为产品文档；
- `docs/MANUAL_VERIFICATION.md`：已经不是最新人工验证，不创建替代的 v0.4.0
  hardware checklist。

### REWRITE

- `AGENTS.md`、根 `README.md`、`docs/FLIGHT_CONTROL_API.md`、本反馈；
- `src/imu_cybergear_ros2/README.md`；
- `src/imu_cybergear_ros2/docs/IMU_CyberGear_Guide.md`；
- `src/imu_cybergear_ros2/docs/环境搭建到调试运行手册.md`；
- `src/imu_cybergear_ros2/docs/项目总览与功能清单.md`。

## Hardware Reference

- motor mechanical mapping：CAN ID 1 为右臂侧向肩部轴，2 为右臂前后肩部轴，
  3 为左臂前后肩部轴，4 为左臂侧向肩部轴；
- current config ordering：`motor_names=[left_lift,left_pitch,right_pitch,right_lift]`
  对应 `motor_ids=[4,3,2,1]`；software sign 和 soft limit 作为独立概念记录；
- 受保护的 `motor_ids`、`motor_signs`、`motor_limits_min/max` 原值保留；CAN ID
  不作为 Flight algorithm key；
- IMU 安装轴：X+ 向机器人正面、Y+ 向机器人左侧、Z+ 向上；没有新增 yaw reference；
- fan wiring：左 GPIO12/物理 32，右 GPIO13/物理 33，GND 为物理 34 或其他 GND；
- GPIO12 来自原单风扇已验证连接；GPIO13 仍只是第二路当前默认配置，首次带电前
  需要物理确认，没有改写成已经实机确认；
- 明确保留无 verified `current_a`、torque 不得推导 current、无真实 fan RPM、
  normalized fan command 不是 thrust fraction、takeover 尚未实机验证等边界。

没有新增未经验证的电流、RPM、推力、yaw reference 或 Flight 性能结论。

## Algorithm Handoff

Quick Start 位于 `docs/FLIGHT_CONTROL_API.md` 顶部。算法主要修改目录为：

```text
src/windarmor_flight_control/windarmor_flight_control/algorithms/
```

最小离线测试命令：

```bash
PYTHONPATH=src/windarmor_flight_control \
python3 -m pytest -p no:cacheprovider \
  src/windarmor_flight_control/test/test_example_controller.py -q
```

该入口说明算法只实现 `reset()` / `update(state, dt)`，只消费 `FlightState`、返回
`FlightCommand`，normal command 必须完整，无法继续时使用
`FlightCommand.safe_stop()`，且算法不 arm、不清除 ERROR/E-STOP、不 set-zero、
不 import ROS/hardware library。Flight API 与 public ROS contract 均未改变。

## Redundancy Audit

实际删除的过期/重复项只有 `FIRST_COMMAND.md` 和 `MANUAL_VERIFICATION.md`；没有
删除 source、config、launch、script、ROS entry point、message/service 或 test fixture。

审计结论：

- Python modules 均能由 import、console entry point、controller factory、package
  public API 或测试覆盖解释；
- `algorithms/base.py` 在仓库内部没有直接 import，但它明确是 stable controller
  protocol 的 compatibility import，外部算法可能依赖，列为 report-only，不删除；
- `flight_control_dry_run.launch.py` 由 setup glob 安装且属于公开 launch；低文本引用
  数量不能证明未使用，不删除；
- 三个 YAML、全部 launch、四个 scripts 均由 setup/launch/CI/docs 或公开操作入口引用；
- 所有 interface msg/srv 均在 `CMakeLists.txt` 注册，并由 runtime、owner 或 contract
  tests 使用；
- package 内三个详细手册由 `setup.py` 作为 package data 安装并由 package README
  导航，因此定向修正而非删除；
- deprecated motor scalar parameters、USB fallback、owner/safety/recovery path 属于
  public compatibility 或 safety contract，不删除；
- `runtime_helpers.py` 和 `fake_motor_driver.py` 分别被多项测试共享；没有可证明完全
  重复且值得合并的 helper。保持各 ROS package 测试边界，避免顶层 `test` package
  collection 冲突，也不减少 fault-injection scenario。

未发现满足安全删除六项条件的其他 dead code/config。高风险和动态/public compatibility
候选全部仅报告。

## Wording Audit

- stale current state：把 `AGENTS.md` 的 current stable 从 v0.3.1 修正为 v0.3.2；
  修正 workflow 三包标签、Flight package no-takeover description、config 的一次性
  Task 注释、package docs 的旧 workspace、快捷目标、速度和 broken reference；
- historical references：v0.3.0/v0.3.1 演进、v0.3.2 release/checklist、架构 Task
  阶段描述均有明确历史或分层语境，故保留；
- TODO/FIXME/XXX：没有发现真实未完成工作标记。`h-goal@todo.todo` 是既有
  maintainer placeholder，缺少可验证替代联系人，列为 report-only；`self._node.xxx`
  是属性示意而非 XXX 标记；
- implementation provenance wording：未发现把生成工具、实现助手或模型身份当作
  实现来源的内容，cleaned 为 0；搜索命中的 `AGENTS.md` 文本是本任务要求新增的
  工程措辞规则，intentionally retained；
- package metadata：三个稳定 subsystem package 保持 0.3.2，interfaces/Flight
  development package 保持 0.4.0；名称、依赖、entry point 和版本未发现需修改项。

## Safety Boundary

- 无控制逻辑变化，无 public ROS breaking change；
- `FlightState`、`FlightCommand`、`FlightController`、`CommandAuthority`、
  authority epoch/generation、`FlightCommandEnvelope`、owner service/readback 未改变；
- `flight_takeover_enabled=false` 默认不变；
- `motor_feedback_timeout_sec=0.0` 默认不变；
- `motor_ids`、`motor_signs`、`motor_limits_min/max` 未修改；
- 未改变 ERROR 不自动恢复、transport-only reconnect、MANUAL/AUTO/HOME 不自动恢复、
  old target 不重发、E-STOP、watchdog、soft limit、command write consistency、
  feedback/temperature safety、ownership、epoch/generation 或 lease 语义；
- 未访问 `/dev/*`，未配置 SocketCAN，未启动 ROS node/launch，未访问 CAN、USB-CAN、
  CyberGear、IMU serial、GPIO12/13、PWM、ESC、电机或风扇；
- 本任务不是 hardware verification，也没有创建 Task 6 checklist。

## Tests

清理与审计命令包括：

```bash
git status --short --branch
git diff --check
git grep -n -E 'FIRST_COMMAND|MANUAL_VERIFICATION' -- \
  . ':(exclude)docs/NEXT_COMMAND.md'
rg -n -i --glob '!docs/NEXT_COMMAND.md' \
  'v0\.3\.1.*(current|当前|stable|稳定)|(current|当前|stable|稳定).*v0\.3\.1' .
rg -n -i --glob '!docs/NEXT_COMMAND.md' '\b(TODO|FIXME|XXX)\b' .
find docs -maxdepth 1 -type f -name '*.md' -printf '%f\n' | sort
git ls-files
```

另执行只读本地 Markdown link checker，检查 8 个相对链接，全部指向存在文件；删除
文档在 `NEXT_COMMAND.md` 之外引用为零。`git diff --check` 通过，旧 workspace、
broken package doc reference、stale 三包/current stable/no-takeover 表述均已清零。

最小算法验证：

```bash
PYTHONPATH=src/windarmor_flight_control \
python3 -m pytest -p no:cacheprovider \
  src/windarmor_flight_control/test/test_example_controller.py -q
```

结果：`4 passed in 0.11s`。

完整软件 CI：

```bash
source /opt/ros/jazzy/setup.bash
./scripts/ci_software.sh
```

结果：

- CI safety、Git whitespace、Python compile：通过；
- clean build：5 packages finished；
- motor pytest：385 passed；
- fan pytest：112 passed；
- flight + interfaces pytest：216 passed；
- full five-package colcon test：5 packages finished；
- `colcon test-result --verbose`：739 tests，0 errors，0 failures，0 skipped；
- 最终无 warnings、failures 或 skipped。

当前未发现进入 Task 6 hardware verification planning 前的软件或文档 blocker。真实
方向、机械动态、通信 timing、PWM/ESC 和联合 takeover 仍等待后续独立计划与授权，
不能由本次软件结果替代。

## Git 状态（反馈生成时）

- HEAD：`a1e4d2c9108653e4359c1adb95ff52fb4604e425`；
- branch：`master`，本地显示 `master...origin/master`，无 ahead/behind；
- working tree：dirty；包含本 Task 5 的 16 个新增/修改/删除路径，以及任务开始前
  用户已有且保持原 SHA-256 的 `docs/NEXT_COMMAND.md` 修改；
- implementation/verification 阶段：未 commit；
- push：未执行；tag：未创建、移动、删除或重建；
- remote：仅核验本地配置为
  `git@github-windarmor:LeonEleven/WindArmor.git`，未进行网络 fetch/ls-remote，
  因此不声称远端实时状态已核验；
- 本地 stable tag 保持：v0.3.0 tag object `f7d2a47`（commit `c3b3c39`）、
  v0.3.1 tag object `ff527a3`（commit `5d7bd0f`）、v0.3.2 tag object `29ae0bb`
  （commit `398ea9b`）；
- 未执行 checkout、reset 或 clean，未覆盖用户既有修改。
