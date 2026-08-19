# 最新反馈：B2 收口、Gate B 完成与连续证据工具

> 本文件只保留当前最新任务反馈。
>
> 日期：2026-08-18

## Result

依据任务开始前操作员提供的、来自紧邻前一次已授权实机阶段的物理观察和运行时证据，
本次完成 B2 的正式收口，并将 Gate B 标记为完成：

```text
B2 bounded fan hardware verification:
HARDWARE PASS

Gate B:
COMPLETE

Gate C:
NOT EXECUTED
NEXT
```

No hardware executed by Codex in this task.

本次没有重跑 B2，也没有执行 Gate C。Gate C 必须先讨论测试边界，再取得新的明确硬件
授权；当前任务的确认不构成 Gate C 或任何其他带电测试授权。

## B2 最终证据与判定

### 最终硬件配置

```text
LEFT fan:  BCM GPIO12 / physical pin 32，通电并参与 B2
RIGHT fan: BCM GPIO26 / physical pin 37，RIGHT ESC 独立断电
LEFT command:  0.05，预期 1210 us
RIGHT command: 0.0，预期 800 us
left_lift test offset: 0.0
motor intent: 四电机保持 baseline，无有意电机运动
```

当前正式映射仍为 LEFT GPIO12、RIGHT GPIO26；GPIO13 保留给 Waveshare 2-CH CAN
HAT+ 的 CAN_1 INT_1，不用于风扇 PWM。

### 操作员物理观察

```text
LEFT physical bounded response: PASS
Unexpected motor movement: NONE
Abnormal vibration/noise/smell: NONE
LEFT stopped after E-STOP: PASS

RIGHT ESC independently OFF during final B2 physical test.
RIGHT software command remained 0.0 / 800 us.
```

### 连续运行时证据

- ACTIVE 证据完整：状态为 ACTIVE / FLIGHT_CONTROL，motor 与 fan authority 均已提交，
  token、cutoff、last command 和 actuation 条件一致。
- 完整 command frame 包含 fan `0.05 / 0.0` 和四个电机名称；四电机位置均为 baseline
  hold 指令。
- `/fans/status_pwm` 连续证据首尾均为 `800 / 800`；LEFT 最大值为 `1210`，RIGHT
  全程唯一值为 `[800]`。
- 至少存在一个完整、健康的四电机 feedback snapshot，无 fault、stale 或 unhealthy。
- E-STOP 后 authority 为 INHIBITED / NONE，motor 与 fan owner 均为 NONE，相关安全
  latch 已置位，actuation 关闭。

```text
ACTIVE evidence: PASS
command 0.05 / 0.0: PASS
4-motor frame: PASS
motor healthy evidence: PASS

PWM:
first (800,800)
left_max 1210
right_unique [800]
last (800,800)

post-E-STOP authority / owners / latches:
PASS
```

Evidence collection note：

```text
post_fan_pwm.txt:
EMPTY

classification:
supplemental one-shot capture failure

does not invalidate continuous final PWM evidence.
```

这个空文件不是运行时失败或硬件失败，也不推翻连续证据已经确认的最终 `800 / 800`。
因此 B2 判定为 HARDWARE PASS，Gate B 判定为 COMPLETE。

Codex executed no hardware in this task.
B2 hardware evidence was operator-provided from the immediately preceding authorized physical session.

## 新增连续证据工具

- `scripts/hardware_verification/record_gate_evidence.py`：只读订阅 Gate 证据话题，分别
  保存原始 YAML stream；建立时间戳会话目录和 JSON manifest；记录开始/结束时间、
  topic、文件、sample 状态、子进程退出码和清理分类；SIGINT/SIGTERM 时有界关闭全部
  子进程。默认不 publish、不调用 service、不启动硬件节点，也不执行 E-STOP。
- `scripts/hardware_verification/analyze_b2_evidence.py`：只离线读取 manifest 和证据文件，
  检查 ACTIVE、完整 command、PWM 边界、健康四电机 frame、E-STOP 后 authority / owner /
  latch；接受 `0.05`、`5e-2` 等等价数值；忽略并报告尾部不完整 YAML。补充快照为空或
  缺失时，只要连续证据完整且无矛盾，仍可通过软件证据判定；若补充快照有效但与最终
  `800 / 800` 矛盾，则阻止通过。
- 分析器报告明确把 `SOFTWARE EVIDENCE` 与 `OPERATOR PHYSICAL EVIDENCE`、最终硬件 Gate
  分开，不会凭离线文件自行宣称物理观察或最终硬件 PASS。
- `.gitignore` 忽略默认本地 `hardware_evidence/` 采集目录，避免意外提交运行时证据。

该工作流已写入 README、硬件参考和 v0.4.0 验证计划。Gate C 的后续实机阶段应先启动
连续 recorder，再触发受控场景，最后停止 recorder 并离线分析；`ros2 topic echo --once`
只等待未来一条消息，不用于证明瞬态历史。

## 修改文件

本次实现修改或新增：

```text
.github/workflows/ci.yml
.gitignore
README.md
docs/HARDWARE_REFERENCE.md
docs/V0.4.0_HARDWARE_VERIFICATION_PLAN.md
scripts/ci_software.sh
scripts/hardware_verification/__init__.py
scripts/hardware_verification/record_gate_evidence.py
scripts/hardware_verification/analyze_b2_evidence.py
scripts/hardware_verification/test/test_record_gate_evidence.py
scripts/hardware_verification/test/test_analyze_b2_evidence.py
src/windarmor_bringup/test/test_ci_infrastructure.py
docs/LATEST_FEEDBACK.md
```

任务开始时已有的 `docs/NEXT_COMMAND.md` 修改属于用户工作区内容，本次按其执行但未覆盖
或回退该修改。

## 纯软件验证

所有成功测试均为 pure/fake/mock、离线分析或静态检查；没有访问 CAN、GPIO、PWM、
串口、IMU、ESC、风扇或 CyberGear。

1. 新工具语法与专项测试：

   ```bash
   python3 -m py_compile \
     scripts/hardware_verification/record_gate_evidence.py \
     scripts/hardware_verification/analyze_b2_evidence.py
   python3 -m pytest scripts/hardware_verification/test -q
   ```

   结果：`26 passed`。

2. 新 CI stage 与安全检查：

   ```bash
   ./scripts/ci_software.sh tooling-tests
   python3 scripts/check_ci_safety.py
   ```

   结果：tooling tests `26 passed`；CI safety 对 2 个受控文件检查 PASS。

3. Flight、interface 与新工具目标回归：首次执行时，`rclpy` 尝试在只读的
   `/home/h-goal/.ros/log` 建立日志目录，产生 1 个 setup error；这不是测试断言失败，
   也没有硬件访问。将 ROS 日志定向到 `/tmp` 后重跑：

   ```bash
   source /opt/ros/jazzy/setup.bash
   source install/setup.bash
   ROS_LOG_DIR=/tmp/windarmor-target-ros-logs \
     python3 -m pytest \
       scripts/hardware_verification/test \
       src/windarmor_flight_control/test \
       src/windarmor_interfaces/test -q
   ```

   结果：`326 passed`。

4. 仓库完整纯软件 CI：

   ```bash
   source /opt/ros/jazzy/setup.bash
   ./scripts/ci_software.sh
   ```

   结果：PASS。

   ```text
   CI safety check: PASS
   Git whitespace check: PASS
   Python compile: PASS
   hardware verification tooling tests: 26 passed
   colcon build: 5 packages PASS
   motor package pytest: 431 passed
   fan safety regression: 159 passed
   Flight and interface software tests: 300 passed
   full workspace colcon test: 918 tests, 0 errors, 0 failures, 0 skipped
   ```

5. `git diff --check`：PASS。

新增 26 个工具测试覆盖：ACTIVE 完整/缺失、`0.05` 与 `5e-2`、PWM 合格及左右/最终值
失败、空或缺失补充快照不造成假失败、矛盾补充快照阻止通过、健康/故障/stale 电机
frame、owner 转换、不完整尾部 YAML、CLI 报告与退出码、recorder SIGINT 清理、异常子
进程、只读且 `shell=False` 的命令构造、通用 topic 配置及禁止控制/硬件动作的静态约束。

## Git 状态

```text
task-start branch: master
task-end branch: master
task-start HEAD: 9ecff154c2a740ace699efc7907d9726ca8fe903
task-end HEAD:   9ecff154c2a740ace699efc7907d9726ca8fe903
task-start working tree: M docs/NEXT_COMMAND.md
task-end working tree:
  M .github/workflows/ci.yml
  M .gitignore
  M README.md
  M docs/HARDWARE_REFERENCE.md
  M docs/LATEST_FEEDBACK.md
  M docs/NEXT_COMMAND.md
  M docs/V0.4.0_HARDWARE_VERIFICATION_PLAN.md
  M scripts/ci_software.sh
  M src/windarmor_bringup/test/test_ci_infrastructure.py
  ?? scripts/hardware_verification/
commit created: NO
push performed: NO
tag / release created: NO
branch created or switched: NO
```

以上 Git 状态记录的是实现任务完成、反馈写入时的归档前状态。用户随后于
2026-08-19 明确授权创建中文提交并推送到 GitHub；归档提交哈希和推送结果以 Git
历史及该后续操作的最终回复为准。

No branch was created or switched by Codex.

## 硬件影响、未执行项与剩余风险

- 本次没有启动任何硬件节点或 launch，没有 publish 控制话题，没有调用控制 service，
  没有配置 CAN，没有访问真实串口，没有操作 GPIO12、GPIO26 或 GPIO13，没有输出 PWM，
  也没有改变树莓派运行时硬件或系统配置。
- B2 实机证据来自操作员先前紧邻的已授权物理阶段；本次没有重复带电验证。
- 新 recorder 的子进程生命周期和 analyzer 的判定通过 fake/offline 测试验证；尚未在真实
  ROS 图或实机阶段使用，不能把这些测试表述为采集工具的实机验证。
- Gate C 尚未执行；B1 中 `<= 3 s` 的运行时断线边界仍应由 Gate C 的新授权场景验证，
  不能由软件测试替代。

## Next

Next:
discuss and prepare Gate C fail-closed hardware verification.

Gate C requires a new explicit hardware authorization.
