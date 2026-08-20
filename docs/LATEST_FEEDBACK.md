# 最新反馈：长期硬件验证规则与 C1 retry 准备

> 本文件只保留当前最新任务反馈。
>
> 日期：2026-08-19

## Result

```text
task-start branch: master
task-start HEAD: 7b8f621fcbdb73131b102611539cbac518b26c97
task-end branch: master
task-end HEAD: 7b8f621fcbdb73131b102611539cbac518b26c97
Gate B: COMPLETE
Gate C / C1: NOT VERIFIED — retry prepared, not executed
Gate C / C2: NOT AUTHORIZED / NOT EXECUTED
```

本任务只完成 pure software、documentation 和 local operator tooling preparation；没有执行
C1 retry，也没有访问真实 hardware。

## Task-start workspace and archival

任务开始时工作区为：

```text
## master...origin/master
 M docs/LATEST_FEEDBACK.md
 M docs/NEXT_COMMAND.md
```

两项均为用户已有修改，已保留并按任务内容处理。覆盖上一份
`docs/LATEST_FEEDBACK.md` 前，已把 2026-08-19 C1 attempt 的简洁历史永久归档到
`docs/V0.4.0_HARDWARE_VERIFICATION_PLAN.md`，包括：

- 最终分类 `NOT VERIFIED`；
- ACTIVE exposure 约 `16.385 s`，超过批准的 `10 s`；
- IMU deactivate 后 normal launch 自动恢复；
- LEFT ESC powered sequence 偏差；
- `+0.05 rad` 不适合作为肉眼精确测量；
- stale 后 command cutoff、无 old target replay、Runtime inhibit、两 owner 回收和
  operator stop observation 等局部正向证据。

归档明确声明这些局部证据不是 C1 HARDWARE PASS，不得据此进入 C2。

## NEXT_COMMAND local-only

`.gitignore` 已加入：

```gitignore
/docs/NEXT_COMMAND.md
```

已按任务明确授权执行普通 `git rm --cached docs/NEXT_COMMAND.md`，没有使用 `-f`，也没有
stage 其他文件。最终验证：

```text
local docs/NEXT_COMMAND.md: EXISTS
git check-ignore: .gitignore:10:/docs/NEXT_COMMAND.md
git ls-files -- docs/NEXT_COMMAND.md: no output
index: tracked-file deletion only
```

该文件现在是用户与 agent 的本地 scratchpad，不是 repository artifact。旧内容继续保留在
本地和 Git history，不做 history rewrite。

## Long-term hardware verification rules

`AGENTS.md` 已将 NEXT_COMMAND authority 描述改为 optional/local/ignored，并新增
`agent-prepared / operator-executed` 长期规则：

- agent 准备确定性 runbook、准确命令、临时 helper/config、纯软件验证和离线证据审查；
- operator 负责真实供电、真实硬件命令、physical kill 和现场观察；
- timing-sensitive trigger 必须在 prepare/ACTIVE 前 pre-arm/prewarm；
- 瞬态历史优先 continuous recorder；
- 软件反馈不得冒充 operator physical observation；
- 单场景工具默认保存在 `/tmp`、`~/windarmor_test_sessions` 或
  `~/windarmor_evidence`；
- operator 自行执行仍不降低十项授权门槛；
- 覆盖 LATEST_FEEDBACK 前先归档尚未进入权威文档的重要硬件结论。

## `imu_auto_activate`

确认原低层 launch 的实际路径为：

```text
OnProcessStart -> automatic CONFIGURE
OnStateTransition(goal_state="inactive") -> automatic ACTIVATE
```

同一 inactive handler 会在手工 deactivate 后再次运行，正是上一轮 C1 auto-reactivation
的原因。

最小修复：

- `imu_cybergear_system.launch.py` 声明 `imu_auto_activate`，默认 `"true"`；
- 参数只作为 IMU automatic activate handler 的 `IfCondition`；
- automatic configure 不受影响；
- motor controller lifecycle 不变；
- unified `windarmor.launch.py` 声明同名默认参数并透传；
- README 已最小说明公开参数与硬件授权边界。

因此默认 production behavior 完全保持：

```text
imu_auto_activate:=true
process start -> configure -> inactive -> automatic activate
```

C1 retry 使用：

```text
imu_auto_activate:=false
process start -> configure -> inactive and stay inactive
operator explicit activate
fault deactivate -> inactive and stay inactive
```

本任务没有运行上述 launch 或 lifecycle 命令。

## C1 retry contract

验证计划已校准：

- 下一次 C1 candidate 使用 manual IMU lifecycle mode；
- motor bus 与 LEFT ESC 可以在 prepare 前均已通电，RIGHT ESC 保持 OFF，但仍需新的十项
  场景授权；
- prepare 前必须确认 fan `SAFE_STOP`、PWM `[800,800]`、LEFT 无非批准旋转、四 motor
  healthy/hold 和 physical kill ready；
- 软件 evidence 证明 selected target/feedback、其他 motor hold 和 fan command/PWM；
- operator 不再负责肉眼精确测量 `+0.05 rad`，但仍须确认无错误轴、异常大幅运动、机械
  干涉、错侧 fan、异常振动/声音/气味/温升，以及 stale 后 motor/fan stop；
- 最大 ACTIVE duration 保持 `10 s`；pre-armed helper 在合法 ACTIVE 后约 `1 s` 请求
  deactivate；
- fault 后不恢复 IMU，不自动 retry，不进入 C2。

没有新增 C1 analyzer。

## Local operator bundle

仓库外 bundle：

```text
/home/h-goal/windarmor_test_sessions/c1_retry/
├── RUNBOOK.md
├── c1_recorder_topics.json
└── c1_trigger_on_active.py
```

三个主文件均不属于 repository artifact，未进入 Git。

`c1_recorder_topics.json` 使用现有 recorder schema，完整包含默认八个 topic 加
`/imu/data_raw` 和 `/imu_driver_node/transition_event`，共 10 个唯一 topic；schema 纯函数
校验通过。config SHA256：

```text
ea79de849340b6c96eae8ef567fe5fc3bf157c83d0517da5dedbf20f3e5d4c41
```

`c1_trigger_on_active.py` 在 prepare 前创建 authority subscription 和
`/imu_driver_node/change_state` client；先观察非 ACTIVE、确认 service ready 后打印
`C1_TRIGGER_READY / C1_TRIGGER_ARMED`。它只在下一次同时满足以下条件时计时：

```text
authority_state == ACTIVE
command_authority == FLIGHT_CONTROL
actuation_allowed == true
motor_committed == true
fan_committed == true
owner_tokens_match == true
```

约 `1.0 s` 后使用已创建 client 请求 DEACTIVATE，并输出稳定 monotonic timing、service
success 和 PASS/FAIL 字段。启动时已经 ACTIVE、service/authority 未 ready、ACTIVE timeout、
service reject/exception/result timeout 都会非零退出。helper 不 call prepare、不 publish
Flight command 或 E-STOP、不控制 motor/fan，也不自动 reactivate IMU。

RUNBOOK 按 Terminal A/B/C/D 与 operator 划分，顶部明确
`PREPARED ONLY — NOT HARDWARE AUTHORIZATION`，包含 preflight、manual activation、条件式
set-zero、recorder/helper READY、prepare、immediate stop、expected evidence 和 safe exit。

## Validation

只运行 pure/static/fake/mock validation：

```bash
python3 -m pytest src/windarmor_bringup/test/test_launch_syntax.py -q
python3 -m py_compile \
  ~/windarmor_test_sessions/c1_retry/c1_trigger_on_active.py
git diff --check
git diff --cached --check
source /opt/ros/jazzy/setup.bash
./scripts/ci_software.sh
```

结果：

```text
targeted launch/source tests: 6 passed
local helper py_compile: PASS
local recorder config: 10 unique topics accepted
git diff --check: PASS
git diff --cached --check: PASS
CI safety check: PASS
Git whitespace check: PASS
Python compile: PASS
hardware verification tooling tests: 26 passed
colcon build: 5 packages PASS
motor package pytest: 431 passed
fan safety regression: 159 passed
Flight and interface software tests: 301 passed
full workspace colcon test: 921 tests, 0 errors, 0 failures, 0 skipped
```

这些结果不构成真实硬件验证。

## Hardware and Git limits

本任务没有启动任何 ROS hardware node/launch，没有打开 `/dev/imu_usb`，没有配置或访问
CAN，没有初始化 CyberGear，没有调用 set-zero，没有操作 GPIO/PWM/ESC/fan，没有 Flight
prepare，没有 lifecycle 操作真实 IMU，也没有发布 `/e_stop`。C1 retry 未执行。

没有创建或切换 branch，没有 commit、push、tag 或 release。除
`git rm --cached docs/NEXT_COMMAND.md` 产生的 tracked-file deletion 外，没有 stage 其他
文件。

下一步只能由用户审查本次改动，并为 C1 retry 重新逐项完成十项硬件授权；本任务不建议
自动执行硬件。
