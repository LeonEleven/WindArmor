# 最新反馈：Gate C / C3 graceful restart 设计与执行准备

> 日期：2026-08-20
> 任务起点：`master` / `57df48d41d8132276dc98a8155f29bd850c30dee`
> 本轮性质：production contract/source review、C3 verification contract 校准、local-only
> operator bundle、pure/static validation 与文档更新
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

C1/C2 的硬件 PASS、安全结论与证据已归档在当前 `README.md`、
`docs/V0.4.0_HARDWARE_VERIFICATION_PLAN.md` 和 Git history `57df48d`，本轮没有覆盖或
降低这些结论，也不把历史授权延伸到 C3。本轮没有启动 ROS 2、WindArmor launch、Flight
Runtime 或 hardware node，没有调用 prepare/E-STOP，没有向真实 Runtime 发送 SIGINT/
SIGTERM/SIGKILL/SIGCONT，没有访问 CAN、GPIO、PWM、串口、IMU、motor 或 ESC/fan，也没有
执行 C3/C4。production source/config/launch/message/service/test 均未修改；没有 commit、
push、tag 或 release。

## Actual Runtime graceful-shutdown contract

console entry point 为 installed
`lib/windarmor_flight_control/flight_control_runtime_node`，对应
`windarmor_flight_control.runtime.node:main`。`main()` 执行 `rclpy.spin(node)`，显式捕获
`KeyboardInterrupt`，并在所有退出路径的 `finally` 调用 `node.destroy_node()`；context 仍为
ok 时再调用 `rclpy.shutdown()`。当前 source 没有显式捕获
`rclpy.executors.ExternalShutdownException`。因此 future C3 candidate 期望 exact-PID SIGINT
产生正常 exit 0，但 old/new Runtime transcript、traceback 和 `PIPESTATUS[0]` 才是 authoritative
exit evidence；observer 只证明 old process identity 消失，不能替代 exit code。

ARMING/READY/ACTIVE 的 `destroy_node()` 调用 `_rollback_handoff("runtime_shutdown")`。本地
fail-close 顺序为：

1. `_command_dispatch_enabled=false`，立即关闭 executable command gate；
2. handoff/reserved/committed/source-epoch tracking 清除；
3. last command tracking 清除；
4. `_inhibit()` 使 `CommandEnvelopeSequencer.invalidate()`，并使 authority attempt/token 在
   内存中失效、authority state 进入 `INHIBITED/NONE`；
5. motor/fan 各发起一次 asynchronous nonblocking best-effort revoke；
6. `super().destroy_node()` 销毁 node；shutdown 不等待 revoke response。

production shutdown 不显式发布 `request_safe_stop=true` envelope，也不显式调用
`_publish_authority_status()` 发布 final INHIBITED status。因此 continuous recorder 可以留下 OLD
Runtime 的最后一条 TRANSIENT_LOCAL ACTIVE authority sample；future C3 不把缺少 final safe-stop/
INHIBITED frame判为异常。若 revoke service unavailable、调用/响应失败或 request 未在 node
销毁前完成，motor/fan lower-level `0.25 s` ACTIVE command lease 仍是独立 backstop；C2 已在
硬件上验证这条 fail-close 路径。C3 分开审查“explicit revoke 是否观察到”和“lease 是否作为
backstop”，不创造新的毫秒级 shutdown SLA。

## Actual authority/session identity 与 restart semantics

真实 Runtime session 字段为 `FlightAuthorityStatus.authority_epoch`：node 构造时由
`time.monotonic_ns()` 生成一次正 `uint64`，reset 不改变，NEW Runtime 必须与 OLD 不同。正式
owner token 是现有字段的组合，不存在额外 opaque token：

```text
FlightAuthorityStatus: (authority_epoch, authority_generation)
FlightCommandEnvelope: (authority_epoch, generation)
OwnershipState:        (authority_epoch, generation) when authority_present=true
```

同一 Runtime 的 prepare generation 从 1 开始递增，cancel/inhibit 后当前 attempt 永久失效；
NEW Runtime 从自己的 generation counter 重新开始合法。NEW 未 prepare 时必须为
`authority_generation=0`、`attempt_present=false`、占位 `attempt_generation=0`、
`DRY_RUN/NONE`。每个新 token 的 `FlightCommandEnvelope.command_sequence` 可从 0 合法开始并
严格递增；C3 NEW Runtime 不 prepare，因此必须完全没有新 executable envelope。
`FlightAuthorityStatus.state_sequence` 也是 Runtime-local，可在新 process 重新开始。
`OwnershipState.source_epoch` 属于 persistent lower-level owner process，不是 Runtime epoch，
normal system 未重启时可保持不变。

lower-level reserve 永久记录最高 `(authority_epoch, generation)`，拒绝 older epoch 或同 epoch
不更大的 generation；active command 还必须匹配 current token且 command sequence 严格增加。
wrong token、duplicate/stale sequence、invalid payload 与 safe-stop 都不刷新 normal command
lease。新 Runtime 没有 prepare 时既不 reserve/commit owner，也不生成 executable command，
因此绝对不能自动复活 OLD authority/target。

## Existing stale/replay pure-test evidence

现有 pure/fake tests 已提供以下软件证据：

- `test_command_envelope.py`：zero/wrong epoch、zero/wrong generation、non-increasing/negative
  command sequence、pre-cutoff state、invalid payload拒绝；sequencer invalidation 后不能复用
  pre-cutoff target；
- `test_authority_state_machine.py`：prepare generation 不复用，旧/duplicate/out-of-state ack 与
  old-generation commit拒绝，inhibit/reset 后必须新 prepare；
- motor ownership tests：wrong epoch/generation/duplicate command拒绝且不改 target，old epoch
  reserve拒绝，timeout/revoke 后旧 generation 不恢复 output，feedback probe 不 replay revoked
  Flight generation；
- fan ownership tests：wrong epoch/generation/duplicate sequence拒绝且不刷新 lease，timeout/
  safe-stop/E-STOP 后旧 command不恢复 output，legacy owner只能显式 reclaim；
- Runtime handoff/readback tests：OLD epoch readback不能激活 NEW session；NEW Runtime fresh epoch
  必须完成完整新 handoff；owner process source-epoch/observation-sequence replay与 ACTIVE owner
  restart均 fail-close；shutdown 在两个 revoke service 都 unavailable 时仍完成本地 fail-close。

窄 software gap：fan tests 没有对 prepare path 的 `older_authority_epoch` 与 `old_generation`
reason code各写一条 focused assertion；fan source contract 与 combined Runtime/command behavior
已有覆盖。本轮按任务要求只报告该 test-granularity gap，不修改 production/tests，也不把它
扩大成 powered replay fault。C3 hardware 不主动重新 publish 捕获的 OLD actuator envelope；
协议级 stale rejection归 software evidence，restart 后没有自动复活 OLD authority/target归
runtime/hardware evidence。

## Calibrated C3 candidate（NOT AUTHORIZED）

候选 powered boundary 继续复用已由 C1/C2 证明的低幅 operating point，仅用于未来十项授权
审查：

```text
IMU: normal auto activation
motor bus: ON
LEFT ESC: ON
RIGHT ESC: physically OFF
OLD selected motor: left_pitch = captured ACTIVE-session baseline +0.05 rad
other 3 motors: captured baseline hold
LEFT/RIGHT fan command: 0.05 / 0.0
legal ACTIVE to exact-PID SIGINT: candidate 3.0 s
maximum OLD ACTIVE exposure: candidate 10 s
```

这些值全部是 `CANDIDATE / NOT AUTHORIZED`。C1/C2 历史值和授权不自动授权供电、prepare、
signal 或 C3 execution。

future 因果链校准为：pre-armed helper全部 ready -> operator仅调用一次 prepare -> legal ACTIVE/
stable bounded actuation -> helper 对 exact OLD PID 发送一次 SIGINT -> old executable stream cease
-> explicit revoke若观察到则记录，否则 0.25 s lower-level lease backstop -> owners NONE、fan PWM
`[800,800]`、motor/fan physical stop -> OLD process正常退出 -> operator确认 old safe state -> 手工
启动 NEW Runtime -> fresh PID/start identity与 fresh `authority_epoch` -> NEW 只保持 DRY_RUN/NONE，
不 prepare、不 ACTIVE、无 executable command/owner/old target/movement。

OLD graceful process-exit observation timeout candidate 为 `5.0 s`。依据是 production cleanup
无阻塞 wait，现有 in-process test 在两个 revoke service unavailable 时也同步返回；但仓库没有
真实进程 SIGINT timing test，所以 5 s 只是保守 helper/operator timeout，不是 actuator SLA。
timeout -> FAIL；helper绝不在 powered 状态自动 SIGKILL，operator独立使用 E-STOP + physical
kill。actuator fail-close仍按 explicit revoke实际证据或独立 lower-level lease evidence审查。

NEW stable observation candidate 为 `3.0 s`，不是 production SLA。当前 Runtime authority status
随 50 Hz control tick发布，fan periodic safety/ownership status为 5 Hz；3 s 理论上覆盖约 150 个
fresh authority tick与约 15 个 fan status周期，足以取得多个 NEW identity/status sample。证据
不足可延长只读观察，不能调用 prepare制造 evidence。

## Local-only operator bundle

```text
~/windarmor_test_sessions/c3/
  RUNBOOK.md
  run_c3_runtime.sh
  c3_graceful_stop_observer.py
```

`RUNBOOK.md` 顶部为 `PREPARED ONLY — NOT HARDWARE AUTHORIZATION`，包含十项 candidate powered
boundary、Terminal A-E、independent emergency terminal、preflight、old/new transcript、physical
observation、restart acceptance与 safe exit。它明确 all pre-fault terminals在 prepare 前 ready，
ACTIVE 后不再人工切换 terminal Ctrl+C，helper不 restart，NEW 只由 operator在 OLD evidence/
physical stop确认后手工启动且绝不 prepare，不 automatic retry，不进入 C4。

`run_c3_runtime.sh` 由 operator传 `old_runtime.pid` 或 `new_runtime.pid`。它通过
`ros2 pkg prefix windarmor_flight_control` 定位并验证真实 installed executable/config，拒绝覆盖
仍指向 live process 的 pidfile，使用同目录 temporary file + rename原子写自身 PID，随后
`exec` actual Runtime使 PID保持；foreground/no daemon。它输出：

```text
C3_RUNTIME_PID=...
C3_RUNTIME_PID_FILE=...
C3_RUNTIME_EXECUTABLE=...
C3_PREPARED_ONLY_NOT_HARDWARE_AUTHORIZATION
```

wrapper保留同一 bounded candidate config，但不 prepare、不 signal、不 actuator control。old/new
分别使用 `old_runtime.log` / `new_runtime.log`，`pipefail` + `PIPESTATUS[0]` 保存真实 exit status。

`c3_graceful_stop_observer.py` 只负责 OLD half。启动时检查 pidfile/PID/current UID/cmdline/
`/proc` start time/running state，拒绝 missing、mismatch、stopped/zombie/dead与 PID reuse；subscribe
authority、Flight command、motor/fan ownership、fan PWM和 supplemental motor/fan safety；必须先
看到 non-ACTIVE，全部初始观察 ready后以 flush 输出 `C3_STOP_READY` / `C3_STOP_ARMED`。它只在
完整 legal ACTIVE、两 owner FLIGHT_CONTROL且 token match、至少一帧同 token executable command
后计时，约 3.0 s 再次验证 exact process identity并仅发送一次 SIGINT。它不发送 SIGTERM/
SIGKILL/SIGCONT，不 prepare、E-STOP、actuator control、restart或retry。PASS只证明 OLD trigger/
software stop transitions/process disappearance，不等于整个 C3 PASS。

没有新增 restart observer。默认 continuous recorder八项 topics 已覆盖 authority identity、command、
motor feedback/safety/ownership、fan PWM/safety/ownership；authority/command已经包含所需字段，故
不创建 C3 JSON config。recorder必须从 OLD prepare前连续运行到 NEW stable DRY_RUN观察完成后。
OLD cached sample与 NEW evidence必须通过 PID/start transcript、fresh `authority_epoch`、message
stamp和连续 fresh samples区分，不能仅看到一条 DRY_RUN就宣布 restart evidence。

## Restart acceptance 与 candidate safe exit

NEW required evidence：PID/start identity different；`authority_epoch` fresh；NEW-stamped
`DRY_RUN/NONE`；generation/attempt为 no-authority值；actuation disallowed；motor/fan committed
false；old committed token不延续；owners持续 NONE且 authority absent；PWM `[800,800]`；restart
后无 executable command、old target、automatic prepare/ACTIVE、legacy/manual takeover或 physical
movement。operator另记录错轴/错侧、异常声音/振动/气味/温升；精确 `+0.05 rad` 与 token/timing
由 software evidence负责。

candidate safe exit：NEW stable window后仍不 prepare，优先 Ctrl+C graceful stop NEW并保存
`NEW_RUNTIME_EXIT_STATUS`；确认 owners仍 NONE、PWM stop；停止 recorder；LEFT ESC physical OFF；
motor bus physical OFF；normal system exit；preserve logs。independent E-STOP + physical kill始终
ready，任一 anomaly立即使用。不存在 C2 frozen-SIGKILL cleanup复制到 C3。

## Pure/static validation 与下一步

已执行：

```text
bash -n ~/windarmor_test_sessions/c3/run_c3_runtime.sh                    PASS
python3 -m py_compile .../c3_graceful_stop_observer.py                    PASS
python3 .../c3_graceful_stop_observer.py --self-test                      5/5 PASS
Flight envelope/authority/owner-readback/Runtime-handoff selected tests   60 PASS
motor ownership selected tests                                             9 PASS
fan ownership selected tests                                               6 PASS
local bundle staged/installed byte comparison                             PASS
AST/static forbidden-behavior review                                      PASS
git diff --check                                                           PASS
```

第一次把三个 package tests 合并并手工覆盖 `PYTHONPATH` 的命令在 collection 阶段失败：覆盖值
移除了 `/opt/ros/jazzy` 的 `rclpy` 路径，多个 package 的 `test` namespace 也发生冲突；没有执行
test body，不是 source/test failure。改为 source ROS/install 环境并按 package 分开运行后，
60 + 9 + 6 共 75 项全部 PASS。

helper self-test只使用 temp fake `/proc`、fake messages、fake clock与mock signal sender，不初始化
rclpy、不连接 ROS graph、不发送真实 signal。它覆盖 pidfile/PID/UID/cmdline/state/PID-reuse拒绝、
starts ACTIVE/ACTIVE-before-armed、legal ACTIVE、3 s delay、mock SIGINT exactly once、无 SIGTERM/
SIGKILL/SIGCONT、graceful exit、exit timeout、逐项 missing motor owner/fan owner/PWM transition、
no automatic restart path及 flush marker不依赖进程退出。AST确认 production helper唯一 signal
sender调用为 `self.signal_sender(pid, signal.SIGINT)`，没有导入 `subprocess`，rclpy imports只在
非 self-test的 `run_ros()` 路径。

完整 900+ software CI 未执行：本轮只修改 Markdown 与 local-only files，没有修改 production
code/config/launch/test；selected pure tests已针对本轮契约覆盖。

production code changed = `NO`；real hardware executed = `NO`。README无需修改，因为 C3尚未执行，
正式 hardware状态不变。

下一步只允许用户 review bundle、production contract与完整十项 powered boundary，再决定是否
单独授权 C3。当前不得执行 wrapper/helper、不得 prepare、不得发送 signal、不得供电或进入 C4。
