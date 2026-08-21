# 最新反馈：Gate C / C3 `/proc` state sampling race 修复

> 日期：2026-08-21
> 任务起点：`master` / `7f9831819e64245dbbf89d2c2f12f5fb46f96090`
> 本轮性质：local-only observer `/proc` sampling race 修复、pure self-test 与反馈归档
> C3 结论：`DESIGN/PREPARATION COMPLETE, NOT AUTHORIZED / NOT EXECUTED`
> Gate C：`IN PROGRESS / NOT COMPLETE`

## 正式状态与本轮边界

```text
Gate B: COMPLETE
Gate C / C1: HARDWARE PASS
Gate C / C2: HARDWARE PASS
Gate C / C3: DESIGN/PREPARATION COMPLETE, NOT AUTHORIZED / NOT EXECUTED
Gate C / C4: NOT AUTHORIZED / NOT EXECUTED
Gate C: IN PROGRESS / NOT COMPLETE
```

C1/C2 的硬件 PASS、安全结论与证据继续由当前 `README.md`、
`docs/V0.4.0_HARDWARE_VERIFICATION_PLAN.md` 和 Git history 保存；本轮没有覆盖、降低或扩展
这些结论，也不把历史授权延伸到 C3。本次修复执行没有启动 ROS 2、WindArmor launch、Flight
Runtime 或 hardware node，没有调用 prepare/E-STOP，没有向任何真实进程发送 SIGINT/SIGTERM/
SIGKILL/SIGCONT，没有访问 CAN、GPIO、PWM、串口、IMU、motor 或 ESC/fan，也没有执行 C3/C4。

production source、config、launch、message、service 和 tests 均未修改。仓库内只更新当前反馈，
本地 bundle 继续位于 `~/windarmor_test_sessions/c3/`，不纳入 Git。

## C3 pre-flight abort 分类

session `gate-evidence-20260821T014852.009218Z-1200735` 分类为：

```text
C3 PRE-FLIGHT ABORTED / HARDWARE ATTEMPT NOT STARTED
```

helper 依次读取 `/proc/<pid>/status` 与 `/proc/<pid>/stat`，此前要求两次非原子采样得到的 process
state 完全相等。进程在两次读取之间发生正常调度状态变化时会产生 false-positive identity
failure；这是 helper preflight defect，不是 Runtime identity change 或 C3 hardware FAIL。

该 session 中 prepare 未执行、ACTIVE 未进入、SIGINT 未发送，C3 hardware scenario 未开始；
因此不构成 C3 attempt、PASS 或 FAIL，也不改变正式状态：C3 仍为
`DESIGN/PREPARATION COMPLETE, NOT AUTHORIZED / NOT EXECUTED`。

## Strict Runtime argv identity

`c3_graceful_stop_observer.py` 不再把 `/proc/<pid>/cmdline` 拼成字符串做子串匹配。现在按 NUL
分隔原始 bytes、丢弃空字段并以 replacement mode 解码，保存为完整 `tuple[str, ...]`。候选
Runtime 至少必须满足：

```text
any(Path(argument).name == "flight_control_runtime_node" for argument in argv)
```

因此 `--note=flight_control_runtime_node` 之类的参数子串不能冒充 Runtime，而任意安装前缀下
basename 精确匹配的 executable/script argument 仍可接受。初始验证继续要求 current UID、
exact executable basename、非 stopped/zombie/dead state，并保存 PID、UID、`/proc` start time
和完整 argv tuple。

SIGINT 前的最终 revalidation 要求 PID 对应的 UID、start time 与完整 argv tuple 全部不变，
再次确认 exact Runtime basename 和 running state。相同 PID/start time 下只要 argv 改变也会
FAIL；start time 改变仍按 PID reuse FAIL。失败时不会调用 signal sender。

本次修复移除了 `status.State == stat.state` 检查。UID 继续只取自
`/proc/<pid>/status`；process state 与 `start_time_ticks` 统一只取自同一次
`/proc/<pid>/stat` 采样。PID、UID、start time、完整 argv、exact basename 防护全部保持，
`T/t/Z/X/x` stopped/zombie/dead rejection 也继续基于 authoritative `stat` state 执行。

## Continuous legal ACTIVE latch

首次建立 coherent legal ACTIVE 仍要求 authority 为 ACTIVE/FLIGHT_CONTROL、actuation allowed、
motor/fan committed、owner tokens match，两 ownership 均为同 token 的 FLIGHT_CONTROL，且至少
收到一帧同 token executable command。此时锁定 OLD `(authority_epoch,
authority_generation)` 并进入约 `3.0 s` 的连续 pre-SIGINT phase。

该 phase 不在每个任意 callback 上重新组合可能不同步的缓存。只有新收到的 authoritative
sample 本身明确非法时才锁存相应 `PRE_SIGINT_FAILURE=...`：

- authority 不再 ACTIVE、command authority 不再为 FLIGHT_CONTROL；
- actuation disallowed、motor/fan commit 丢失或 owner token-match flag 丢失；
- authority epoch/generation 改变；
- motor/fan ownership 不再为 FLIGHT_CONTROL 或 owner token 改变；
- normal executable command 使用不同 token。

锁存后后续合法样本不能恢复、不能清除 failure、不能重启 timer，也不能发送 SIGINT。
同 token normal executable command 只更新 `last_old_command_at`；safe-stop envelope 不作为
heartbeat。helper 不引入 command-frequency SLA。连续合法时间达到 delay 后，先完成最终
process identity revalidation，再通过唯一 signal path 恰好发送一次 SIGINT；仍没有 SIGTERM、
SIGKILL、SIGCONT、automatic retry、restart、prepare、E-STOP 或 actuator control 路径。

## Local-only bundle

```text
~/windarmor_test_sessions/c3/
  RUNBOOK.md
  run_c3_runtime.sh
  c3_graceful_stop_observer.py
```

`RUNBOOK.md` 已最小同步：明确 trigger 需要约 3 秒连续 legal ACTIVE；任一 authority/owner/token/
legal-condition loss 都锁存 FAIL，后续 recovery 不重启计时且不发送 SIGINT；继续要求
`python3 -u`、显式 flush、`pipefail` 与 `PIPESTATUS[0]`。wrapper 没有结构或内容改动。

## Pure/static validation

按本轮任务只执行不访问 ROS graph、Runtime 或硬件的验证：

```text
bash -n ~/windarmor_test_sessions/c3/run_c3_runtime.sh                 PASS
python3 -m py_compile .../c3_graceful_stop_observer.py                 PASS
python3 .../c3_graceful_stop_observer.py --self-test                  13/13 PASS
git diff --check                                                       PASS
```

13 项 self-test 只使用 temporary fake `/proc`、fake messages、fake clock 与 mock signal sender。
覆盖 valid Python argv + Runtime path + args、参数子串 false positive、exact basename path、
full argv mutation、PID reuse、`status=S/stat=R` accepted、`stat=T/t/Z/X/x` rejected、
starts-ACTIVE 拒绝、连续合法路径 exactly one mock SIGINT、authority
loss、actuation false、motor/fan owner NONE、motor/fan token change、authority generation change、
illegal 后 recovery 仍 FAIL/no signal、wrong-token executable command、exit timeout、缺失 owner/PWM
transition、forbidden signal absence 与 flushed marker。所有 signal assertion 都停留在内存列表；
没有向真实 PID 发信号，也没有读取真实 `/proc`。

完整 `scripts/ci_software.sh` 与此前的 75 项 selected package tests 本轮未执行：本轮没有修改
production code/config/launch/test，新增行为全部位于 local-only helper，已由其 focused pure
self-test 覆盖。此前测试结果仍是历史证据，不冒充本轮重跑结果。

production code changed = `NO`；real signal sent = `NO`；ROS graph accessed = `NO`；real hardware
executed = `NO`。README 无需修改，因为正式 hardware 状态和公开 production behavior 未变。

## 下一步

下一步只允许用户 review 加固后的 bundle、production contract 和完整十项 powered boundary，
再决定是否单独授权 C3。当前不得执行 wrapper/helper、不得启动 Runtime、不得 prepare、不得
发送真实 signal、不得供电，也不得进入 C4。
