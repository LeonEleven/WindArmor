# 最新反馈：RIGHT fan GPIO26 引脚冲突修复

> 本文件只保留当前最新任务反馈。
>
> 日期：2026-08-18

## 结果

已确认并记录 RIGHT fan 旧映射 BCM GPIO13 与 Waveshare 2-CH CAN HAT+ 的
CAN_1 INT_1 默认 GPIO13 之间的硬件引脚分配冲突。WindArmor 的正式软件映射已改为：

```text
LEFT fan:  BCM GPIO12 / physical pin 32
RIGHT fan: BCM GPIO26 / physical pin 37
```

节点默认参数与权威 YAML 一致，新增纯软件回归测试锁定该映射。PWM 范围、normalized
mapping、E-STOP、ownership、Flight API、motor authority 和 fan authority 均未改变。

```text
WindArmor software mapping fix: PASS
GPIO26 replacement fan channel direct hardware verification: PASS
B2: PAUSED / PENDING
Gate B: NOT COMPLETE
Gate C: NOT STARTED
```

GPIO26 direct hardware PASS 来自本任务开始前用户已经完成并提供的人工实机证据；本次
Codex 任务没有运行或重复任何硬件测试。

## 问题证据与工程分类

### 症状与交叉测试

- RIGHT ESC 接在 GPIO13 时持续鸣叫，不接受油门；LEFT channel 正常。
- 两套 ESC/fan 交叉后，任一 ESC/fan 接 GPIO12 均能正常工作，接 GPIO13 均失败。
- 更换 GND 没有解决问题，故障跟随 GPIO13 path，而不跟随 ESC/fan。

### 软件与 GPIO 证据

- RIGHT manual command 会正确改变 `/fans/status_pwm` 第二路，第一路保持 800 us，说明
  `fan_keyboard -> fan_command_manager -> fan_node` 的左右 routing 正常。
- GPIO12 和 GPIO13 均被 lgpio 成功 claim，LEFT/RIGHT 共用同一套 `_set_output()` /
  `_apply_pair()` 实现；不是 RIGHT 软件通道遗漏或未初始化。

### Direct hardware evidence

```text
direct lgpio GPIO12, 800 us @ 50 Hz: ARMED NORMAL
direct lgpio GPIO13, 800 us @ 50 Hz: STILL BEEPING
direct lgpio GPIO26, 800 us @ 50 Hz: ARMED NORMAL
direct lgpio GPIO26, 1210 us @ 50 Hz, ~1 s: BOUNDED RESPONSE
GPIO26 return to 800 us: STOPPED
```

Waveshare 官方资料说明 2-CH CAN HAT+ 的 CAN_1 INT_1 默认使用 BCM GPIO13。项目选择
把 RIGHT fan 改到 GPIO26，而不修改 HAT 上 INT_1 的 0Ω 电阻或设备树中断配置：
[Waveshare 2-CH CAN HAT+](https://www.waveshare.net/wiki/2-CH_CAN_HAT%2B)。

因此根因分类为：

```text
hardware pin assignment conflict /
GPIO13 unsuitable in the current Raspberry Pi 5 + Waveshare 2-CH CAN HAT+ stack
```

现有证据不证明 Raspberry Pi GPIO13 silicon 损坏，不作该结论。

## 修改内容

- `src/windarmor_fan_controller/config/fan_params.yaml`：`right_gpio` 从 13 改为 26，
  LEFT 保持 12，所有 PWM 参数保持不变。
- `src/windarmor_fan_controller/windarmor_fan_controller/fan_node.py`：默认
  `right_gpio` 从 13 改为 26。
- `src/windarmor_fan_controller/test/test_interface_routing.py`：增加静态 regression，
  同时验证节点默认值和 YAML 均为 LEFT 12 / RIGHT 26，不实例化 GPIO。
- `src/windarmor_bringup/test/test_launch_syntax.py`：确认 observation-only launch 不硬编码
  GPIO12、GPIO13 或 GPIO26。
- `README.md`、`docs/HARDWARE_REFERENCE.md`：更新当前接线并记录症状、交叉测试、
  direct lgpio 证据、Waveshare 冲突和解决方案。
- `docs/V0.4.0_HARDWARE_VERIFICATION_PLAN.md`：更新当前 GPIO12/26 契约；保留 B1
  发生时旧 GPIO12/13 断线边界的历史事实；明确 B2 仍 pending、Gate C 不得开始。
- `AGENTS.md`：把未授权 fan GPIO 操作禁令同步到 GPIO12/26，并保留 GPIO13 的 CAN HAT
  中断用途约束。
- `docs/NEXT_COMMAND.md`：保留任务开始前用户提供的当前任务文档。
- `docs/LATEST_FEEDBACK.md`：替换为本次最新反馈。

没有修改：

```text
min_pwm_us = 800
max_pwm_us = 2200
stop_pwm_us = 800
fan_stop_pwm_us = 800
fan_start_pwm_us = 1200
fan_auto_max_pwm_us = 1400
flight_fan_max_pwm_us = 1400
rise_step_pwm_us = 10
fall_step_pwm_us = 20
```

## 纯软件验证

所有实际执行的成功测试均为 pure/fake/mock 或静态检查，不访问真实 CAN、GPIO、串口、
ESC、CyberGear、IMU 或其他硬件 I/O。

1. 首次直接运行源码目录测试：

   ```bash
   source /opt/ros/jazzy/setup.bash
   python3 -m pytest \
     src/windarmor_fan_controller/test \
     src/windarmor_bringup/test -q
   ```

   结果：在 collection 阶段因尚未加载工作区 `install/setup.bash` 而终止，
   `ModuleNotFoundError: windarmor_fan_controller`；没有测试被执行，也没有硬件访问。

2. 仓库统一软件 CI：

   ```bash
   source /opt/ros/jazzy/setup.bash
   ./scripts/ci_software.sh
   ```

   结果：PASS。

   ```text
   CI safety check: PASS
   Git whitespace check: PASS
   Python compile: PASS
   colcon build: 5 packages PASS
   motor package pytest: 431 passed
   fan safety regression: 159 passed
   Flight and interface software tests: 300 passed
   full workspace colcon test: 918 tests, 0 errors, 0 failures, 0 skipped
   ```

3. 使用本次构建的 install 环境重跑目标包：

   ```bash
   source /opt/ros/jazzy/setup.bash
   source install/setup.bash
   python3 -m pytest \
     src/windarmor_fan_controller/test \
     src/windarmor_bringup/test -q
   ```

   结果：`186 passed`。

4. `git diff --check`：PASS。

风扇 unit、routing、shutdown、E-STOP 和 bringup/release contract 软件覆盖均包含在上述
通过结果中。

## Git 状态

```text
baseline: a3978c4101cef8a21071b2867fd820faa42b3127
branch: fix/right-fan-gpio26
implementation commit: f0cc341 (修复右侧风扇与 CAN HAT 的 GPIO13 冲突)
```

实现提交后仅本文件等待反馈归档提交；归档完成后的最终 `git status` 和 HEAD 由最终
回复报告。未创建 tag、GitHub Release，也未修改 v0.3.x tags。

## 硬件与剩余风险

本任务只修改仓库文件并执行纯软件验证；没有启动 `ros2 launch`、`ros2 run`、topic /
service 硬件命令，没有配置 CAN，没有操作 GPIO12、GPIO13 或 GPIO26，没有输出 PWM，
没有给 ESC/fan 或 CyberGear 通电。

新的 WindArmor runtime GPIO12/26 mapping 尚未完成双路 ROS sanity test，也没有完成正式
B2 Flight test。下一步仍需在新的独立十项带电授权下执行 LEFT GPIO12 + RIGHT GPIO26
双风扇 manual hardware sanity test；该测试 PASS 后才能恢复 B2。当前不得开始 Gate C。

最终目标映射：

```text
RIGHT fan final mapping: GPIO26 / BCM26 / physical pin 37
GPIO26 direct hardware verification: PASS
WindArmor software mapping fix: PASS
B2: PENDING
Gate B: NOT COMPLETE
Gate C: NOT STARTED
```
