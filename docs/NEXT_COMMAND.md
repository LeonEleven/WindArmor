# WindArmor — Gate B Closure + Hardware Verification Evidence Tooling

## 0. Task intent

本任务有两个目标：

1. 根据已经由用户真实硬件执行并提供的 B2 evidence，正式关闭 B2 / Gate B。
2. 把本次 B2 中已经验证有效的 continuous recorder + evidence analyzer 固化为仓库工具，避免 Gate C 继续依赖人工追高速 topic、临时 awk、多段易出错 shell pipeline。

本任务属于：

```text
Gate B closure
+
hardware-verification tooling cleanup
```

不是：

```text
Flight architecture redesign
新的 Task 6.2.x
Gate C hardware execution
```

不要创建 Task 6.2.8。

---

# 1. Git / branch absolute rules

开始前按照 `AGENTS.md` 做 baseline 检查。

必须首先记录：

```bash
git status --short --branch
git branch --show-current
git rev-parse HEAD
git log -5 --oneline --decorate
```

## 1.1 禁止擅自创建或切换分支

本任务明确禁止：

```text
git switch
git switch -c
git checkout
git checkout -b
git branch <new>
```

以及任何：

```text
feature/*
fix/*
docs/*
dev
develop
```

分支的创建或切换。

必须：

```text
stay on the branch that exists when the task begins
```

如果开始时 branch / working tree 状态存在风险或与预期不符：

```text
STOP
报告
```

不要自行切分支解决。

同样禁止：

```text
git merge
git rebase
git stash
git reset
git restore
git clean
```

未经明确授权不要改变 Git history。

不要：

```text
tag
GitHub Release
修改 stable tags
创建 v0.4.0 tag
```

## 1.2 commit / push

遵循当前 `AGENTS.md` 对 commit / push 的正式规则。

但无论如何：

```text
禁止为了本任务创建新分支。
```

如果 `AGENTS.md` 没有明确允许自动 push：

```text
不要自行扩大权限；
完成修改、测试和 LATEST_FEEDBACK 后报告状态。
```

---

# 2. Mandatory latest-feedback rule

这是今后的固定项目规则：

```text
每一个 Codex task 在最终回复用户之前，
必须更新：

docs/LATEST_FEEDBACK.md
```

`docs/LATEST_FEEDBACK.md`：

```text
只保留当前最新一次任务反馈
```

不要把旧任务报告持续追加进去。

本任务结束前必须真实记录：

```text
Task / Scope
Result
B2 evidence
Gate state
Files changed
Tests
Hardware execution
Git branch
HEAD / commit（如有）
working tree
remaining blockers
next step
```

如果本任务没有执行硬件：

必须明确写：

```text
No hardware executed by Codex in this task.
```

不要把用户此前执行的 hardware evidence 描述成 Codex 自己执行的测试。

---

# 3. B2 operator-provided hardware evidence

以下证据来自用户在 Raspberry Pi 5 + WindArmor 真实硬件上完成的一次独立授权 B2 session。

Codex 本任务只负责如实记录和整理，不重新执行。

## 3.1 B2 configuration

最终 hardware mapping：

```text
LEFT fan:
BCM GPIO12
physical pin 32

RIGHT fan:
BCM GPIO26
physical pin 37
```

B2：

```text
tested physical fan = LEFT

fan_left_test_command = 0.05
fan_right_test_command = 0.0

expected LEFT target = 1210 us
expected RIGHT target = 800 us

motor_test_offset_configured = true
motor_test_offset_rad = 0.0

test_motor_name = left_lift

intentional motor movement = NONE

all four motors = captured baseline hold
```

RIGHT ESC 在本次最终 B2 session 中：

```text
independently POWER OFF
```

这是已有 B2 plan 允许的最小风险配置。

因此不要错误声称：

```text
RIGHT ESC received powered physical Flight verification
```

正确表述为：

```text
RIGHT command remained 0.0
RIGHT software PWM remained 800 us
RIGHT ESC was independently unpowered during the bounded LEFT test
```

---

# 4. B2 software evidence

用户最终 analyzer 输出为：

```text
========== B2 SOFTWARE EVIDENCE ==========
ACTIVE complete evidence: PASS
Flight command 0.05/0.0 + 4 motor names: PASS
Fan PWM bounded/right-stop/final-stop: PASS
At least one 4-motor healthy/fault-free snapshot: PASS
Post E-STOP authority: PASS
Post E-STOP motor owner NONE: PASS
Post E-STOP fan owner NONE: PASS
Post E-STOP motor latch: PASS
Post E-STOP fan latch: PASS
Post E-STOP fan PWM [800,800]: FAIL

PWM summary:
first=(800, 800)
last=(800, 800)
left_max=1210
right_unique=[800]

SOFTWARE EVIDENCE: FAIL
```

最后这一项 FAIL 不是 runtime / hardware FAIL。

随后检查发现：

```text
post_fan_pwm.txt
```

文件存在但：

```text
EMPTY
```

原因分类应记录为：

```text
supplemental one-shot evidence capture failure
```

而不是：

```text
post E-STOP fan failed to return to STOP
```

原因是同一次 continuous recorder 已经明确得到：

```text
first = (800,800)
last  = (800,800)

LEFT max = 1210
RIGHT unique = [800]
```

因此：

```text
continuous fan PWM evidence:
PASS
```

空的 `post_fan_pwm.txt` 只是额外 `ros2 topic echo --once` 没有收到未来新消息，不能覆盖 continuous recorder 的实际结果。

---

# 5. B2 physical evidence

用户直接观察：

```text
LEFT fan bounded response:
YES

Unexpected motor movement:
NO

Abnormal vibration/noise/smell:
NO

LEFT stopped after E-STOP:
YES
```

软件侧同时证明：

```text
ACTIVE complete evidence:
PASS

command_authority:
FLIGHT_CONTROL

motor_committed:
true

fan_committed:
true

owner_tokens_match:
true

atomic_cutoff_present:
true

last_command_present:
true

actuation_allowed:
true
```

Flight command：

```text
fan_left = 0.05
fan_right = 0.0

4 logical motor names present
```

Fan PWM：

```text
initial:
(800,800)

bounded LEFT:
max 1210

RIGHT:
always 800

final:
(800,800)
```

motor feedback：

```text
at least one complete 4-motor snapshot:
healthy
fresh
valid
fault_flags = 0
```

E-STOP 后：

```text
Flight authority:
PASS

command authority revoked:
PASS

motor owner NONE:
PASS

fan owner NONE:
PASS

motor E-STOP latch:
PASS

fan E-STOP latch:
PASS
```

---

# 6. Formal B2 classification

根据上述真实硬件 + continuous software evidence，正式记录：

```text
B2 bounded fan hardware verification:
HARDWARE PASS
```

同时：

```text
Gate B:
COMPLETE
```

必须明确记录一个 evidence note：

```text
post_fan_pwm.txt:
EMPTY

classification:
supplemental one-shot capture failure

impact on B2:
NONE

reason:
continuous fan_pwm.log captured final (800,800),
physical LEFT fan stopped after E-STOP,
and authority / ownership / E-STOP latch evidence all passed.
```

不要把最初 analyzer 输出里的：

```text
SOFTWARE EVIDENCE: FAIL
```

直接照搬成最终 Gate failure。

更准确的最终分类：

```text
runtime/hardware failure:
NO

evidence collection defect:
YES

B2 result:
PASS
```

---

# 7. Update hardware verification documentation

Audit 当前：

```text
docs/V0.4.0_HARDWARE_VERIFICATION_PLAN.md
```

以及相关 current hardware docs。

更新当前正式状态为：

```text
B0 PASS

B1 FUNCTIONAL HARDWARE PASS

B2 HARDWARE PASS

Gate B COMPLETE

Gate C NEXT
```

不要重新展开或修改已经冻结的 Flight architecture。

如果 current docs 中仍有 active/current wiring instruction：

```text
RIGHT = GPIO13 / pin33
```

必须根据当前正式 mapping 修正为：

```text
RIGHT = GPIO26 / pin37
```

但历史 root-cause 记录中：

```text
Waveshare CAN HAT INT_1 uses GPIO13
```

应保留作为历史问题原因。

不要机械全文替换所有 GPIO13。

---

# 8. Hardware evidence tooling design

本次 B2 最大的问题不是 product runtime，而是人工测试工具过于碎片化：

```text
continuous topic echo
+
--once snapshots
+
awk
+
grep
+
临时 Python
+
人工高速观察
```

导致：

```text
awk syntax incompatibility
empty --once capture
operator workflow confusion
```

目标是新增一个小型、可维护、纯软件辅助工具集。

推荐目录：

```text
scripts/hardware_verification/
```

至少实现：

```text
record_gate_evidence.py
analyze_b2_evidence.py
```

可以根据仓库结构适当调整名称，但不要过度设计。

---

# 9. record_gate_evidence.py requirements

目标：

```text
一个 terminal
一个命令
持续记录多个 ROS evidence topics
Ctrl+C 后统一安全退出并写 session metadata
```

它是：

```text
evidence recorder
```

不是：

```text
authority controller
hardware controller
E-STOP controller
prepare controller
```

## 9.1 Recorder must NOT

禁止它：

```text
publish ROS commands
call prepare
call reset
call ownership services
publish /e_stop
configure CAN
touch GPIO
touch PWM
control motors
control fans
power hardware
```

它只能：

```text
subscribe / record
```

## 9.2 Recommended implementation

优先使用 Python 管理：

```text
ros2 topic echo
```

subprocess。

原因：

```text
现有 CLI YAML output
已经是当前 evidence parser 的数据格式
不需要重新实现 ROS serialization layer
```

工具应：

```text
create unique timestamped session directory

write session manifest

record start time

record command line

record topic -> file mapping

launch all recorder subprocesses

keep running in foreground

handle Ctrl+C / SIGTERM

send SIGINT to child ros2 processes

wait bounded time

terminate only if child does not exit

record child exit codes

record stop time
```

推荐默认支持这些 topic：

```text
/flight_control/authority/status
/flight_control/command
/motors/feedback
/motors/safety_state
/motors/ownership_state
/fans/status_pwm
/fans/safety_state
/fans/ownership_state
```

但不要硬编码成只能用于 B2。

应允许：

```text
generic topic/type configuration
```

例如 config / CLI 参数。

工具运行时应清楚显示：

```text
SESSION DIR
topics being recorded
READY
Ctrl+C to stop
```

不要把 topic 内容刷到 operator terminal。

---

# 10. Recorder robustness

必须考虑本次实际遇到的问题。

## 10.1 Empty files

empty topic file 应被记录成：

```text
NO SAMPLE CAPTURED
```

但 recorder 本身不要擅自判断 Gate FAIL。

## 10.2 Process exit

主动 Ctrl+C / SIGINT 导致 child 退出时：

不要把正常 shutdown：

```text
SIGINT / SIGTERM due recorder cleanup
```

错误描述为 product failure。

## 10.3 Buffering

保证持续日志尽可能实时 flush。

可以使用：

```text
PYTHONUNBUFFERED
stdbuf
```

或更稳健的等价机制。

## 10.4 No shell quoting dependency

不要要求 operator 写复杂：

```text
awk '
...
'
```

pipeline。

尤其不要依赖：

```text
multiline awk assignment
```

---

# 11. analyze_b2_evidence.py requirements

这个 analyzer 只分析：

```text
B2 SOFTWARE evidence
```

它不能单独宣布：

```text
B2 HARDWARE PASS
```

因为 physical fan movement / vibration / smell / motor observation 必须来自 operator。

最终输出应明确区分：

```text
SOFTWARE EVIDENCE
OPERATOR PHYSICAL EVIDENCE
FINAL HARDWARE GATE
```

其中 script 只负责第一项。

---

# 12. B2 required software evidence

Analyzer 至少验证：

## ACTIVE

同一个完整 `FlightAuthorityStatus` message 中：

```text
authority_state: ACTIVE
command_authority: FLIGHT_CONTROL

motor_committed: true
fan_committed: true

owner_tokens_match: true
atomic_cutoff_present: true
last_command_present: true

actuation_allowed: true
```

## Flight command

同一个完整 command 中：

```text
request_safe_stop: false
fan_commands_present: true

fan_left ~= 0.05
fan_right ~= 0.0

motor logical names include:
left_lift
left_pitch
right_pitch
right_lift
```

float comparison 不要依赖纯字符串：

```text
fan_left: 0.05
```

应容忍合理 YAML float formatting，例如：

```text
0.05
5e-2
```

## Fan PWM

从 continuous recorder 验证：

```text
first = (800,800)

LEFT > 800 at least once

LEFT maximum <= expected B2 target

RIGHT == 800 for all parseable samples

last = (800,800)
```

本次 B2 expected LEFT target：

```text
1210 us
```

当前实际 evidence：

```text
left_max = 1210
right_unique = [800]
```

不要把：

```text
1400
```

作为本次 B2 expected target。

1400 是当前 Flight fan upper bound，不是 `fan_left=0.05` 的本次目标值。

## Motor feedback

至少找到一条完整四轴 frame，其中四个 motor 均：

```text
has_feedback = true
position_valid = true
fault_flags_valid = true
fault_flags = 0
valid = true
fresh = true
healthy = true
```

---

# 13. Post-E-STOP evidence policy

这是本任务最重要的工具修正之一。

不要再把：

```text
post_fan_pwm.txt --once snapshot
```

设成唯一 REQUIRED evidence。

原因：

```text
ros2 topic echo --once waits for a future message
```

如果 publisher 在 E-STOP 后不再继续发布：

```text
post_fan_pwm.txt
```

可能为空，即使 continuous recorder 已经捕获最终 stop。

B2 analyzer 应使用：

```text
continuous fan_pwm.log final sample == (800,800)
```

作为 REQUIRED software evidence。

如果额外存在：

```text
post_fan_pwm.txt
```

并有有效数据：

```text
将其作为 supplemental corroboration
```

如果：

```text
file missing
```

或者：

```text
file empty
```

应输出：

```text
SUPPLEMENTAL SNAPSHOT:
MISSING / EMPTY
```

但在 continuous final PWM PASS 的情况下：

```text
不能单独导致 SOFTWARE EVIDENCE FAIL
```

不要为了“让测试 PASS”降低真实安全条件。

必须正确区分：

```text
required evidence
vs
redundant supplemental capture
```

---

# 14. Analyzer output

最终输出应短、稳定、适合 operator 复制。

例如：

```text
========== B2 SOFTWARE EVIDENCE ==========

ACTIVE complete evidence: PASS
Flight command 0.05 / 0.0: PASS
Full 4-motor frame: PASS
4-motor healthy/fault-free snapshot: PASS

Fan PWM:
  first: (800,800)
  left_max: 1210
  right_unique: [800]
  last: (800,800)
  result: PASS

Post E-STOP authority: PASS
Post E-STOP motor owner NONE: PASS
Post E-STOP fan owner NONE: PASS
Post E-STOP motor latch: PASS
Post E-STOP fan latch: PASS

Supplemental post_fan_pwm snapshot:
EMPTY
non-blocking because continuous final PWM is valid

SOFTWARE EVIDENCE: PASS

==========================================
```

Exit code：

```text
0 = required software evidence PASS
non-zero = required software evidence FAIL
```

不要因为 optional / supplemental evidence 缺失返回 failure。

---

# 15. Tests for tooling

必须增加 pure software tests。

测试不得启动真实：

```text
ROS graph
CAN
GPIO
PWM
ESC
motor
fan
```

使用 fixtures / temporary files / mocked subprocess。

至少覆盖：

```text
1. valid ACTIVE message -> PASS

2. ACTIVE missing one required field -> FAIL

3. fan_left formatting:
   0.05
   5e-2
   both parse correctly

4. continuous PWM:
   (800,800)
   -> bounded LEFT
   -> (1210,800)
   -> (800,800)
   PASS

5. RIGHT != 800 at any sample -> FAIL

6. final continuous PWM != (800,800) -> FAIL

7. post_fan_pwm.txt empty
   + continuous final (800,800)
   -> SOFTWARE PASS
   + supplemental warning

8. post_fan_pwm.txt absent
   + continuous final valid
   -> SOFTWARE PASS
   + supplemental warning

9. four healthy motors -> PASS

10. one motor fault / stale / unhealthy -> FAIL

11. recorder graceful Ctrl+C cleanup

12. child recorder abnormal exit is reported
```

不要为此建立大型 framework。

---

# 16. Gate C relationship

本任务：

```text
DOES NOT EXECUTE GATE C
```

只允许为下一步 Gate C 整理 evidence workflow。

当前仓库已经存在：

```text
scripts/flight_estop_watchdog.py
```

不要复制它的职责。

它负责：

```text
pre-created / prewarmed /e_stop publisher

wait for ACTIVE / FLIGHT_CONTROL / actuation_allowed

monotonic delay

fail-closed timeout
```

新的 evidence recorder：

```text
只记录
```

不要把 watchdog 和 recorder 合并成一个“大一统硬件测试控制器”。

Gate C 的正式 hardware commands / authorization 必须留到用户和 ChatGPT 后续单独讨论并明确授权。

---

# 17. Documentation update for future operator workflow

在 hardware verification docs 中，把推荐 evidence workflow 简化为：

```text
Terminal A:
normal bringup

Terminal B:
Flight Runtime

Terminal C:
record_gate_evidence.py

Terminal D:
Gate-specific trigger / watchdog

Operator:
physical observation

End:
Ctrl+C recorder
run analyzer
```

避免继续要求 operator：

```text
开很多 topic echo 窗口
肉眼追高速日志
运行复杂 awk
手工 grep 多个 transient state
```

稳态检查可以继续使用：

```text
ros2 topic echo ... --once
```

但文档必须说明：

```text
--once 只等待订阅后的下一条消息
不适合作为唯一瞬态历史证据
```

对于：

```text
ACTIVE
handoff
ownership transient
command transition
```

优先使用：

```text
continuous recorder
```

---

# 18. Current GPIO contract

Audit所有当前正式 hardware/operator docs。

正式 current mapping 必须保持：

```text
LEFT:
BCM12
physical pin 32

RIGHT:
BCM26
physical pin 37
```

不要重新引入：

```text
RIGHT fan = GPIO13
```

但 GPIO13 可以保留于：

```text
historical conflict explanation
Waveshare CAN HAT INT_1 context
```

不要修改 Flight algorithm API 或 authority architecture。

---

# 19. Software validation

运行与本任务相关的 pure software tests。

至少：

```text
new hardware verification tooling tests
existing flight_estop_watchdog tests
relevant Flight/interfaces tests
git diff --check
```

如果合理且不会访问真实 hardware：

```bash
./scripts/ci_software.sh
```

也应执行。

本任务禁止执行：

```text
sudo ./scripts/setup_can.sh

ros2 launch windarmor_bringup ...

ros2 run windarmor_flight_control ...

ros2 topic pub ...

ros2 service call ...

GPIO output
PWM output
CAN hardware access
ESC control
CyberGear control
```

如果测试套件中有会访问真实硬件的项目：

```text
不要运行该部分
报告原因
```

---

# 20. Hardware authorization

本 Codex task：

```text
NO HARDWARE AUTHORIZATION
```

用户此前执行 B2 的授权已经结束。

Codex 不得把此前授权视为：

```text
permission to rerun B2
permission to execute Gate C
```

本任务只做：

```text
source
docs
scripts
pure software tests
```

---

# 21. docs/LATEST_FEEDBACK.md mandatory final content

完成全部修改和软件测试后，在最终回复用户之前必须覆盖更新：

```text
docs/LATEST_FEEDBACK.md
```

只保留当前最新反馈。

至少包含：

## Result

```text
B2 bounded fan hardware verification:
HARDWARE PASS

Gate B:
COMPLETE

Gate C:
NOT EXECUTED
NEXT
```

## B2 evidence

记录：

```text
LEFT physical bounded response: PASS
Unexpected motor movement: NONE
Abnormal vibration/noise/smell: NONE
LEFT stopped after E-STOP: PASS

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

并明确：

```text
RIGHT ESC independently OFF during final B2 physical test.
RIGHT software command remained 0.0 / 800 us.
```

## Evidence collection note

```text
post_fan_pwm.txt:
EMPTY

classification:
supplemental one-shot capture failure

does not invalidate continuous final PWM evidence.
```

## Tooling

记录：

```text
files added / changed
tool responsibilities
tests
```

## Hardware

明确：

```text
Codex executed no hardware in this task.

B2 hardware evidence was operator-provided from the immediately preceding
authorized physical session.
```

## Git

记录：

```text
branch at task start
branch at task end

HEAD start
HEAD end

commit if any

working tree

push status
```

并明确：

```text
No branch was created or switched by Codex.
```

## Next

只写：

```text
Next:
discuss and prepare Gate C fail-closed hardware verification.

Gate C requires a new explicit hardware authorization.
```

不要自动执行 Gate C。

---

# 22. Final response to user

最终回复简洁报告：

```text
1. B2 是否正式记录为 PASS
2. Gate B 是否 COMPLETE
3. evidence tooling 新增了什么
4. 是否修复 empty --once 的 false-negative policy
5. software tests 是否 PASS
6. 当前 branch / commit / push 状态
7. 是否创建或切换了分支（必须 NO）
8. docs/LATEST_FEEDBACK.md 是否已更新
9. 下一步是否为 Gate C discussion
```

不要展开历史 Task 1～6。

不要执行任何真实硬件动作。