# WindArmor — 修复 RIGHT fan GPIO13 / Waveshare 2-CH CAN HAT+ 引脚冲突

## 1. 任务性质

这是一个已经通过真实硬件诊断确认的：

```text
targeted hardware pin-assignment fix
```

不是 Flight architecture redesign。

不要创建：

```text
Task 6.2.8
```

不要修改：

```text
Flight authority architecture
FlightController API
motor authority
fan authority
E-STOP architecture
CAN protocol
CyberGear driver
Flight algorithm
```

本任务只解决：

```text
RIGHT fan 当前 BCM GPIO13
与 Waveshare 2-CH CAN HAT+ CAN_1 INT_1 默认 GPIO13
之间的硬件引脚冲突
```

目标映射改为：

```text
LEFT fan:
BCM GPIO12
physical pin 32

RIGHT fan:
BCM GPIO26
physical pin 37
```

---

# 2. 当前代码基线

当前已知开发基线：

```text
master

a3978c4101cef8a21071b2867fd820faa42b3127
```

开始前先按照 `AGENTS.md` 执行 repository baseline 检查。

当前工作流允许：

```text
docs/NEXT_COMMAND.md
docs/LATEST_FEEDBACK.md
```

存在预期修改。

除这些 workflow 文档外，如发现任何未预期源码/config 修改：

```text
STOP
报告
```

不要使用：

```text
git reset
git restore
git clean
git stash
```

去隐藏现场状态。

---

# 3. 已确认的硬件背景

平台：

```text
Raspberry Pi 5
Ubuntu 24.04
ROS 2 Jazzy

Waveshare 2-CH CAN HAT+
```

WindArmor 当前 fan mapping：

```text
LEFT:
GPIO12 / physical pin 32

RIGHT:
GPIO13 / physical pin 33
```

Waveshare 官方 2-CH CAN HAT+ 文档说明：

```text
CAN_0 INT_0 default:
BCM GPIO22

CAN_1 INT_1 default:
BCM GPIO13
```

官方说明中：

```text
INT_1 默认焊接 PIN13
```

Ubuntu / Raspberry Pi 5 推荐设备树配置也包含：

```text
dtoverlay=mcp2515,spi1-2,oscillator=16000000,interrupt=13
```

官方还说明：

如果要把 HAT 的 INT_1 从 GPIO13 改到例如 GPIO24，需要：

```text
修改 PCBA 对应 0Ω 电阻焊接位置
+
修改 /boot/firmware/config.txt interrupt pin
```

本项目本次明确选择：

```text
不修改 Waveshare HAT 硬件
不修改 CAN interrupt routing

改 RIGHT fan GPIO
```

官方参考：

```text
https://www.waveshare.net/wiki/2-CH_CAN_HAT%2B
```

---

# 4. 已完成的真实硬件诊断证据

以下是本次问题出现后的真实人工硬件证据。

## 4.1 原始故障

重新连接 RIGHT fan 后：

```text
ros2 launch windarmor_bringup windarmor.launch.py
```

表现：

```text
LEFT ESC:
正常识别控制信号，不持续滴滴

RIGHT ESC:
持续滴滴，无法正常控制
```

使用：

```text
ros2 run windarmor_fan_controller fan_keyboard
```

结果：

```text
LEFT fan:
可以正常提高 PWM 并转动

RIGHT fan:
无法正常响应
```

---

# 5. ESC / fan 交叉测试

将两个 ESC/fan 与 GPIO 输出互换：

```text
原 RIGHT ESC/fan → GPIO12:
正常工作

原 LEFT ESC/fan → GPIO13:
仍无法工作
```

因此：

```text
故障不跟随 ESC/fan

故障跟随 GPIO13 path
```

更换 GND 接点没有解决问题。

---

# 6. WindArmor 软件 routing 验证

在：

```text
ESC power OFF
CyberGear power OFF
```

状态下使用：

```text
fan_keyboard
+
/fans/status_pwm
```

验证：

```text
LEFT manual command:
第一路 PWM 正常变化
第二路保持 800

RIGHT manual command:
第一路保持 800
第二路 PWM 正常变化
```

因此：

```text
fan_keyboard
→ fan_command_manager
→ /fans/command_pwm
→ fan_node
```

LEFT / RIGHT 软件 routing 均正常。

不要将此问题归因于：

```text
Flight command routing
Flight authority
fan command manager channel ordering
```

---

# 7. GPIO driver 静态及运行时证据

当前 fan implementation 使用：

```text
gpiozero.Servo
+
gpiozero.pins.lgpio.LGPIOFactory
```

LEFT 和 RIGHT 走同一套 `_set_output()` / `_apply_pair()` 路径。

当前 Raspberry Pi 5 GPIO controller：

```text
gpiochip4:
pinctrl-rp1
```

实际 line：

```text
GPIO12 = gpio-581
GPIO13 = gpio-582
GPIO26 = gpio-595
```

fan node 运行时：

```text
gpio-581 (GPIO12 |lg) out ...
gpio-582 (GPIO13 |lg) out ...
```

说明：

```text
GPIO12 被 lgpio 成功 claim
GPIO13 也被 lgpio 成功 claim
```

所以这不是简单的：

```text
GPIO13 没有被初始化
GPIO13 software channel missing
GPIO13 被 fan_node 忽略
```

---

# 8. direct lgpio GPIO12 / GPIO13 硬件对照

停止 ROS fan stack 后，直接使用：

```python
lgpio.gpio_claim_output(...)
lgpio.tx_servo(...)
```

并使用：

```text
800 us
50 Hz
```

测试同一个已知正常的 ESC/fan。

所有其他条件保持一致：

```text
same ESC
same fan
same signal wire
same GND
same ESC power
```

结果：

```text
GPIO12 / physical pin 32:

800 us @ 50 Hz
→ ESC ARMED NORMAL
```

而：

```text
GPIO13 / physical pin 33:

800 us @ 50 Hz
→ STILL BEEPING
```

因此即使绕过：

```text
ROS
fan_keyboard
fan_command_manager
fan_node
gpiozero.Servo
```

GPIO13 仍无法作为当前 ESC 的有效控制通道。

结合 Waveshare HAT+ 官方 GPIO13 INT_1 使用情况：

```text
GPIO13 不适合作为当前 WindArmor 硬件堆栈中的 RIGHT fan output
```

---

# 9. GPIO26 替代通道实机验证

随后在：

```text
BCM GPIO26
physical pin 37
gpiochip4 line 26 / gpio-595
```

执行 direct lgpio hardware verification。

GPIO26 当时没有其他 consumer。

使用同一个：

```text
ESC
fan
signal wire
GND
power
```

测试：

```text
800 us @ 50 Hz
→ ARMED NORMAL
```

随后：

```text
1210 us @ 50 Hz
持续约 1 秒
→ BOUNDED RESPONSE
```

最后：

```text
回到 800 us
→ STOPPED
```

正式硬件结果：

```text
GPIO26 replacement fan channel:
HARDWARE PASS
```

因此新的 physical mapping 已有真实硬件证据：

```text
LEFT:
GPIO12 / pin 32

RIGHT:
GPIO26 / pin 37
```

---

# 10. 本任务目标

实现最小 targeted fix：

```text
RIGHT fan:
BCM GPIO13
→
BCM GPIO26
```

并完整记录本次问题原因和验证过程。

要求：

```text
不改变 fan command semantics
不改变 PWM range
不改变 normalized mapping
不改变 E-STOP
不改变 ownership
不改变 Flight API
```

---

# 11. Repository audit

首先全仓库搜索：

```text
right_gpio

GPIO13
gpio13

physical pin 33
pin 33

BCM13

GPIO12
GPIO26
fan pin
fan mapping
```

判断每个引用属于：

```text
authoritative config

driver default

README

hardware documentation

test expectation

historical document

generated/build artifact
```

不要机械替换所有 `GPIO13`。

例如：

```text
Waveshare HAT 的 INT_1 = GPIO13
```

应该保留并记录为冲突原因，而不是改成 GPIO26。

---

# 12. 必须修改的 runtime mapping

确认当前 authority 后，将实际 RIGHT fan mapping 从：

```text
right_gpio: 13
```

改为：

```text
right_gpio: 26
```

至少检查：

```text
src/windarmor_fan_controller/config/fan_params.yaml
```

以及：

```text
fan_node.py
```

中的默认 parameter。

如果 `fan_node.py` 当前仍为：

```python
self.declare_parameter("right_gpio", 13)
```

改成：

```python
self.declare_parameter("right_gpio", 26)
```

保持：

```text
left_gpio = 12
```

不变。

---

# 13. 不要改变 PWM 参数

以下配置保持不变：

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

不要因为此次 GPIO fix 修改：

```text
ESC calibration
fan curve
Flight normalized mapping
```

---

# 14. 更新必要的 tests

检查现有测试是否包含：

```text
GPIO13
right_gpio = 13
pin 33
```

对于表达当前正式 hardware contract 的测试：

```text
更新为 GPIO26 / physical pin 37
```

如果缺少针对 fan GPIO default mapping 的简单 regression test，并且现有测试结构允许以很小成本加入，则增加一个最小测试来保证：

```text
LEFT default = GPIO12
RIGHT default = GPIO26
```

不要为了这个 fix 建立新的大型 hardware abstraction。

---

# 15. 更新 README / hardware documentation

检查 README 和现有 hardware docs。

所有面向当前用户的正式 wiring instructions 必须更新为：

```text
LEFT fan signal:
BCM GPIO12
physical pin 32

RIGHT fan signal:
BCM GPIO26
physical pin 37
```

明确标注旧映射：

```text
GPIO13 / physical pin 33
```

不再用于 RIGHT fan。

同时增加简短说明：

```text
Waveshare 2-CH CAN HAT+ 的 CAN_1 INT_1
默认占用 BCM GPIO13。

因此 WindArmor 在当前 Raspberry Pi 5 +
Waveshare 2-CH CAN HAT+ 硬件组合下，
不得再把 GPIO13 用作 RIGHT ESC PWM。
```

记录官方 Waveshare 参考：

```text
https://www.waveshare.net/wiki/2-CH_CAN_HAT%2B
```

并说明：

```text
本项目选择将 RIGHT fan 改到 GPIO26，
而不是修改 HAT 上 INT_1 的 0Ω 电阻和设备树配置。
```

---

# 16. 记录问题来龙去脉

在合适的现有开发/hardware documentation 中记录：

## Symptom

```text
RIGHT ESC connected to GPIO13 kept beeping
and did not accept throttle.
```

## Cross-test

```text
Either ESC works on GPIO12.

Either ESC fails on GPIO13.
```

## Software evidence

```text
RIGHT /fans/status_pwm path changes correctly.
GPIO13 was successfully claimed by lgpio.
```

## Direct hardware evidence

```text
direct lgpio GPIO12 800 us:
ARMED NORMAL

direct lgpio GPIO13 800 us:
STILL BEEPING

direct lgpio GPIO26 800 us:
ARMED NORMAL

direct lgpio GPIO26 1210 us:
BOUNDED RESPONSE

GPIO26 return to 800 us:
STOPPED
```

## Root cause / engineering classification

不要声称：

```text
Raspberry Pi GPIO13 silicon is proven damaged
```

因为当前证据并没有证明芯片物理损坏。

更准确地记录为：

```text
hardware pin assignment conflict /
GPIO13 unsuitable in the current
Raspberry Pi 5 + Waveshare 2-CH CAN HAT+ stack
```

其中 Waveshare 官方资料证明：

```text
CAN_1 INT_1 defaults to GPIO13
```

所以该 GPIO 不应同时承担 RIGHT ESC PWM。

## Resolution

```text
RIGHT fan moved to BCM GPIO26 / physical pin 37.
```

---

# 17. 更新 hardware verification 状态

不要错误地把 B2 标为 PASS。

当前状态仍然：

```text
B2:
PAUSED / PENDING
```

因为 GPIO26 虽然已经完成 direct hardware verification，但：

```text
新的 WindArmor runtime GPIO26 mapping
尚未完成双路 ROS sanity test
尚未完成正式 B2 Flight test
```

因此：

```text
Gate B:
NOT COMPLETE

Gate C:
DO NOT START
```

记录：

```text
GPIO26 replacement fan channel:
DIRECT HARDWARE PASS
```

但不要把它等同于：

```text
B2 HARDWARE PASS
```

---

# 18. Software validation

完成代码修改后，运行与本 fix 直接相关的 tests。

至少覆盖：

```text
windarmor_fan_controller
windarmor_bringup
```

优先按照 repository 现有标准测试入口和 `AGENTS.md` 执行。

如果仓库已有统一：

```text
scripts/ci_software.sh
```

且执行成本合理，则也运行。

至少验证：

```text
fan unit tests PASS

fan routing tests PASS

shutdown tests PASS

E-STOP tests PASS

bringup/release contract tests PASS

git diff --check PASS
```

不要执行真实硬件测试。

---

# 19. 本 Codex 任务没有新的硬件授权

虽然 GPIO26 已经由用户人工完成真实硬件验证，但：

```text
这次 Codex task 本身不授权任何新的硬件操作。
```

禁止：

```text
ros2 launch
ros2 run
ros2 topic pub
ros2 service call

CAN up/down

GPIO output

ESC output

CyberGear output

Flight prepare

E-STOP hardware test
```

允许：

```text
source inspection
code/config/doc changes
software unit/integration tests that do not access hardware
```

如果某个 test 会访问真实 GPIO/CAN：

```text
不要执行
报告原因
```

---

# 20. Git workflow

遵循 `AGENTS.md` 和当前项目分支策略。

这是明确的 fix，推荐分支：

```text
fix/right-fan-gpio26
```

如果当前 workflow / working-tree 状态允许安全创建，则从：

```text
master
a3978c4101cef8a21071b2867fd820faa42b3127
```

创建。

不要：

```text
push
tag
GitHub Release
修改 v0.3.x tags
创建 v0.4.0 tag
```

如果现有 `docs/NEXT_COMMAND.md` / `docs/LATEST_FEEDBACK.md` 修改使分支操作存在风险：

```text
不要擅自 stash/reset/restore
按照 AGENTS.md 采取安全方式并在反馈中说明
```

完成代码、文档和 software validation 后，可创建一个清晰的本地 commit。

建议 commit message：

```text
修复右侧风扇与 CAN HAT 的 GPIO13 冲突
```

不要自行 merge/push，除非 `AGENTS.md` 对当前 workflow 有明确不同要求。

---

# 21. 最终 docs/LATEST_FEEDBACK.md

更新：

```text
docs/LATEST_FEEDBACK.md
```

只保留当前最新反馈。

至少记录：

```text
问题症状

ESC/fan cross-test

RIGHT software PWM routing evidence

GPIO12 direct result

GPIO13 direct result

GPIO26 direct result

Waveshare GPIO13 INT_1 conflict

root-cause classification

modified files

new fan mapping

software tests

test results

Git branch

commit hash（如有）

working tree status
```

最后明确：

```text
RIGHT fan final proposed mapping:
GPIO26 / BCM26 / physical pin 37

GPIO26 direct hardware verification:
PASS

WindArmor software mapping fix:
PASS / FAIL

B2:
PENDING

Gate B:
NOT COMPLETE

Gate C:
NOT STARTED
```

---

# 22. 最终回复用户

最终报告不要重新展开整个 Flight architecture。

只简洁报告：

```text
1. 是否确认并记录 GPIO13 / CAN HAT 冲突

2. 修改了哪些代码/config/doc

3. RIGHT fan 是否已经改为 GPIO26

4. software regression 是否 PASS

5. branch / commit

6. 是否还需要人工双风扇 sanity test

7. B2 是否可以恢复
```

如果 software validation 全部 PASS：

```text
下一步应是：

LEFT GPIO12 + RIGHT GPIO26
双风扇 manual hardware sanity test

PASS 后恢复 B2。
```

不要自动执行该硬件测试。
