# WindArmor 当前开发交接

> **INTERNAL DEVELOPMENT HANDOFF — MUTABLE。** 本文件只记录当前任务状态和下一步，
> 不是普通用户操作文档、长期接口契约或 release evidence source of truth。历史发布事实
> 必须引用对应的版本化 release/verification 文档。

## 当前任务

- 任务：`DOC-3 — comments/docstrings cleanup + final documentation consistency`
- 日期：2026-08-25
- task-start branch：`master`
- task-start HEAD：`4aca75ce54b37a8e668546f260d1f481104b0053`
- 当前 stable release：v0.3.2
- 当前开发目标：v0.4.0（未发布）
- Gate B / C / D：**COMPLETE / COMPLETE / COMPLETE**
- hardware / functional verification：**COMPLETE**
- DOC-1：**COMPLETE / REVIEW PASS**
- DOC-2：**COMPLETE / REVIEW PASS**
- DOC-3：**COMPLETE / REVIEW PASS**
- release readiness：**PENDING FINAL REVIEW**

## DOC-3 结果

本轮只收紧源码说明、包维护者元数据和最终文档一致性，没有改变生产控制行为：

1. 补齐 Flight public contract、authority/envelope/preflight、controller loader、state
   aggregation 和 actuator adapter 的短 docstring；
2. 将注释聚焦于不变量、fail-close 原因、时间/单位和 authority ordering，移除装饰性分隔
   与历史优先级标签；
3. 保留 Runtime 本地先 fail-close 再外部清理、publisher 创建顺序、E-stop trigger
   semantics、禁用 verification/takeover 默认值和 bounded verification baseline 等仍有价值
   的安全说明；
4. 统一五个包的维护者元数据，保持既有版本、license、description 和发布边界不变；
5. 复核 README、Algorithm Developer Guide、API、Architecture、Hardware Reference、实际
   源码/配置和版本化验证记录之间的一致性。

## Public contract 与注释收口

- `FlightController.update()` 现在明确 `dt` 是正的 monotonic seconds、调用周期可变、正常
  命令必须覆盖完整配置电机集合，输入不可用时返回 payload-free safe-stop；算法本身不访问
  ROS 或硬件。
- `FanSystemState` 区分 observed applied PWM 与 requested `FanCommand`；`SystemState` 明确
  `None` 表示 unknown，不得解释为 false、clear、stopped 或 healthy。
- `required_inputs_fresh` 的范围保持为 paired IMU fresh 且每个配置电机 feedback fresh；
  fan、safety readback、E-stop clearance 和 authority readiness 仍由独立条件裁决。
- authority identity 继续使用 `(authority_epoch, generation)`；epoch 隔离 Runtime process
  session，generation 标识该进程内 takeover attempt，旧 session 不会因 restart 恢复。
- command envelope 继续要求 current token、post-cutoff state 和递增 sequence；safe-stop
  不携带 actuator payload，也不充当 heartbeat。
- preflight 仍是 handoff attempt 的 point-in-time readiness check；ACTIVE 后的连续安全监督
  不会被 preflight 替代。
- controller factory 仍使用 `module.path:function`，可接收配置，加载失败显式报错且不回退；
  loader/algorithm 不建立 authority，也不得以 import side effect 访问 ROS/hardware。
- motor adapter 继续要求完整、无重复的反馈 frame；fan adapter 只把 applied PWM readback
  归一化为 `[0, 1]` observation，不宣称 RPM、推力或已执行命令。
- ownership reserve/commit/revoke、safety epoch/sequence 和最终 safety veto 的现有顺序没有
  改变。

`imu_motor_controller_node.py` 删除了文件顶部装饰性标题和“构造”分隔，将 `P0 安全参数`
替换为说明 stale command/feedback、thermal/fault、position error 和 transport 阈值用途及单位
来源的注释。参数数值、声明顺序和行为未改。

过程词扫描中，production source 没有遗留 DOC-1/DOC-2/DOC-3、Task 1–4、P0/P1/P2 或
“下一步”等任务措辞。仓库工具中保留两个有意命名：`GateCEstopWatchdogCore` 是版本化硬件
验证 helper 的领域名称；`record_gate_evidence.py` 的局部变量 `temporary` 用于原子写入
manifest，不是临时任务说明。

## Algorithm 说明

- `example_algorithm_controller.py` 明确是 non-default educational software example；其中
  数字是软件示例值，不是 hardware tuning/default，也不授予 actuator authority。
- `bounded_verification_controller.py` 保留 verification-only、per-authority-session baseline、
  non-accumulating offset 和 invalid input fail-close 的设计理由；它不是 newcomer 默认算法。
- software-only `synthetic_dry_run` 与 `flight_control_dry_run.launch.py` observer Runtime 的
  区别保持清楚：前者不创建 ROS/hardware object 或 authority，后者需要外部 state publisher。

## Package metadata

五个 package manifest 的 maintainer 统一为仓库 Git 历史和本地仓库配置中已有的可信身份：

```text
LeonEleven <elevenlianm@foxmail.com>
```

Python 包的 `setup.py` 与对应 `package.xml` 已保持一致。`imu_cybergear_ros2`、
`windarmor_fan_controller`、`windarmor_bringup` 继续为 `0.3.2`；
`windarmor_interfaces`、`windarmor_flight_control` 继续为 `0.4.0`。未改 license、description，
也未把尚未发布的 v0.4.0 宣称为 stable release。

## 最终一致性复核

- 根 README 仍以 v0.3.2 为 stable、v0.4.0 为未发布开发目标；Gate B/C/D 与
  hardware/functional verification 为 COMPLETE，release readiness 为 PENDING。
- GPIO12（LEFT）、GPIO26（RIGHT）以及 GPIO13 保留给 CAN HAT INT_1 的映射一致。
- 电机配置保持 `motor_ids=[4,3,2,1]`、`motor_signs=[-1,1,-1,1]`、
  `motor_limits_min=[-1.57,-1.57,-1.57,0]`、
  `motor_limits_max=[0,1.57,1.57,1.57]`。
- README 中列出的 launch、服务、CI、pytest 和 synthetic demo 路径均能在当前仓库定位；
  硬件命令只做静态核对，未执行。
- 检查 README 与 `docs/**/*.md` 的 46 个相对 Markdown 文件链接，missing 0。
- `docs/verification/v0.4.0/HARDWARE_VERIFICATION_RECORD.md` 和
  `docs/V0.4.0_HARDWARE_VERIFICATION_PLAN.md` 未修改；历史 PASS/FAIL/NOT VERIFIED、证据
  等级和 operator observation 未重写。

## 验证

已执行且通过的纯软件验证：

- `python3 -m compileall -q`：Flight 与 IMU/motor Python source PASS；
- 定向 pytest：183 passed，覆盖 models/validation、loader、authority、envelope、preflight、
  adapters、aggregation、handoff/safety、示例/verification controller、synthetic demo 和
  release contracts；
- `PYTHONPATH=src/windarmor_flight_control python3 -m
  windarmor_flight_control.synthetic_dry_run`：PASS，只生成 preview，保持 `authority=NONE`、
  `actuation_allowed=false`；
- `source /opt/ros/jazzy/setup.bash && ./scripts/ci_software.sh`：PASS；五包 build 完成，
  hardware verification tooling 26 passed、motor package 431 passed、fan safety 159 passed、
  Flight/interface 318 passed；最终 `colcon test-result` 为
  `939 tests, 0 errors, 0 failures, 0 skipped`；
- `git diff --check`：PASS；
- 相对 Markdown link check：46 checked，missing 0。

以上均为构建、pure/fake/mock 或静态验证，不是真实 CAN、串口、GPIO、电调、风扇或机械
实机验证。本轮未启动 ROS 节点/launch，未访问硬件 I/O，未改变树莓派运行时状态，也未给
actuator 通电。

## 变更边界

- production behavior changed：**NO**
- comments/docstrings changed：**YES**
- package maintainer metadata changed：**YES**
- tests changed：**NO**
- scripts changed：**NO**
- configs/launch/public ROS interfaces changed：**NO**
- hardware executed or affected：**NO**
- historical verification evidence changed：**NO**
- branch created/switched：**NO**
- commit/push/tag/release：**NO**

## 下一任务

DOC-3 已完成，下一步是 v0.4.0 final release-readiness review：复核当前未提交 diff、版本和
release checklist，并由用户另行决定是否 commit/push/tag/release。该复核不自动授权任何
Git 发布动作或新的真实硬件操作。
