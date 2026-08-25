# WindArmor Flight Control Architecture

## Audience and status

本文是 Runtime、safety、authority 和 integration maintainer 的长期架构依据。算法新人应先读
[Algorithm Developer Guide](ALGORITHM_DEVELOPER_GUIDE.md)，字段 reference 见
[Flight Control API](FLIGHT_CONTROL_API.md)。

v0.4.0 Flight control stack 已完成该 release 对应的 hardware/functional verification，Gate
B/C/D 均 COMPLETE。最终判定、release-specific evidence 和限制保存在
[v0.4.0 Hardware Verification Record](verification/v0.4.0/HARDWARE_VERIFICATION_RECORD.md)，
完整执行过程保存在 [historical plan](V0.4.0_HARDWARE_VERIFICATION_PLAN.md)。本文不
复制 session/timestamp，也不把该结果扩展为任意新算法、性能标定或新硬件场景已获验证。
`flight_takeover_enabled=false` 继续是 production default。

## Architectural goals

- algorithm 不依赖 ROS transport、message、topic、service 或 lifecycle；
- algorithm 不理解 CyberGear、CAN、serial、GPIO、PWM 或 ESC；
- existing motor/fan manager 和 safety layer 始终保留最终裁决权；
- unknown、valid、fresh、healthy 与 authority readiness 显式区分；
- handoff、command stream、shutdown、timeout 和 restart 全部 fail closed；
- transport recovery 不自动恢复 control state、owner 或旧 target。

## Component and dependency boundaries

```text
ROS / hardware observation sources
                 |
                 v
       Runtime adapters + aggregator
                 |
                 v
             FlightState
                 |
        pure algorithm boundary
                 |
                 v
       FlightController.update()
                 |
                 v
            FlightCommand
                 |
        pure algorithm boundary
                 |
                 v
 Runtime validation / authority / envelope
                 |
                 v
 MotorManager / FanCommandManager / safety
                 |
                 v
              hardware
```

Package ownership：

- `imu_cybergear_ros2`：IMU/CyberGear I/O、motor lifecycle/state machine、soft limit、
  watchdog、fault/transport recovery；
- `windarmor_fan_controller`：GPIO/PWM I/O、fan command arbitration、slew、watchdog、stop；
- `windarmor_interfaces`：ROS package 间结构化 transport contract；
- `windarmor_flight_control/core`：pure model、validation、authority、preflight、envelope；
- `windarmor_flight_control/algorithms`：pure controller implementations；
- `windarmor_flight_control/runtime`：ROS adapters、aggregation、controller loader、authority
  orchestration 和 actuator envelope transport；
- `windarmor_bringup`：选择是否启动 Runtime；不把选择逻辑放入 algorithm。

`core/` 与 `algorithms/` 禁止依赖 `rclpy`、ROS message、CAN/serial library、GPIO/PWM backend、
CyberGear driver 或其他 hardware package。ROS ↔ pure model conversion 只属于 Runtime adapter。

## Runtime observation pipeline

sensor callback 只校验、转换并更新 observation cache；固定 control timer 每 tick 使用同一个
local monotonic time 构造一次 immutable `FlightState`，先 validate state，再调用 controller，
最后 validate command。

### IMU correlation and time

raw IMU 与 relative roll/pitch 只按相同 source stamp 配对。snapshot timestamp、`dt` 和
freshness 都使用 Runtime-local monotonic time；不使用 wall time 推断 freshness。zero generation
变化会丢弃旧 pair，避免跨 reference 复用。

### Motor observation

`/motors/feedback` 是 configured logical motors 的 complete snapshot。publisher 只复制当前
feedback cache 和 local receive age；normal controller 的 lifecycle/owner-gated acquisition
timer 可重发同值 authoritative `loc_ref` 获取 type-2 feedback，但 observer publisher 本身不做
driver I/O。unknown physical values 使用 presence flags/`None`，不能用 ROS 数值默认零冒充。

### Fan observation

fan applied output 从 observed PWM 归一化，仅表达实际应用 output 的已知/未知状态，不是 RPM
或 thrust。enabled/control state 过期后回到 `None`。algorithm normalized command 与 observed
applied output 是不同方向的数据。

### `required_inputs_fresh`

StateAggregator 当前定义为：

```text
paired IMU is fresh
AND
every configured MotorState is fresh
```

它不包含 fan output/state、motor/fan authoritative safety readback、E-STOP clearance、owner
readback 或 authority readiness。preflight 和 `actuation_allowed` 会分别检查这些条件，因此
不得把 `required_inputs_fresh=True` 当作 whole-system ready。

## Unknown and authoritative safety readback

startup 尚未收到外部 observation 时必须使用 `None`，不能用 false、空字符串或零伪造安全
状态。`/e_stop` 是 trigger channel，不是 authoritative clear readback；`/e_stop=False` 不能
单独证明急停已解除。

motor/fan safety readback 使用 reliable transient-local QoS，并携带：

- positive `source_epoch`：lower-level process instance identity；
- positive, strictly increasing `observation_sequence` within one epoch；
- lifecycle/manager state、E-STOP/ERROR latch 和 owner-related safety facts。

Runtime 判序规则：同 epoch 只接受更大 sequence；更大 epoch 建立新 baseline；更小 epoch
永久拒绝；epoch/sequence 为零非法。Runtime 自身 restart 时重建 observation baseline。

Global E-STOP aggregate：

1. 任一路 authoritative latch true → `True`；
2. 两路都已观测、新鲜且 false → `False`；
3. 其他情况 → `None`；
4. trigger true 后，必须看到两路在 trigger 之后的新鲜 false 才能解除其风险证据。

## Authority state machine

普通 command ownership 独立建模为：

```text
NONE
MANUAL
LEGACY_AUTO
FLIGHT_CONTROL
```

同一时刻只允许一个 ordinary command owner。Flight authority state：

```text
DISABLED -> DRY_RUN -> ARMING -> READY_TO_TAKEOVER
                                      |
                                      v
                                   ACTIVE
                         |              |
                         +-----> INHIBITED <----+
```

`reset_inhibit` 只回到 DRY_RUN；之后必须重新 prepare。input/transport 恢复不能自动从
INHIBITED 回到 ACTIVE，也不能自动恢复 MANUAL、LEGACY_AUTO 或旧 target。E-STOP/ERROR 的
裁决永远高于 authority。

### Identity and restart isolation

正式 identity 是 `(authority_epoch, generation)`：

- `authority_epoch` 是 Runtime process-session 的正 uint64，restart 产生新值；
- generation 在该 epoch 的 prepare attempt 中分配正值；
- `0` 保留给 no authority；
- cancel/inhibit 立即使 attempt token 永久失效；
- owner 拒绝 old epoch/generation，new epoch 也不能抢占仍 active 的旧 Flight owner；
- command sequence 在同 token 内严格递增，用于拒绝 duplicate/out-of-order frame。

## Preflight and readiness

prepare 进入 ARMING。preflight 至少要求：

- IMU valid/fresh；
- every required motor valid/fresh/healthy；
- global E-STOP 明确 false；
- motor safety 已观测、新鲜、active、无 ERROR/feedback latch，并处于允许的 passive mode；
- fan safety 已观测、新鲜、enabled、无 E-STOP、无 legacy active owner，并处于允许的 passive
  safe-stop state；
- owner readback、process epoch/sequence 和 cross-field state 一致。

ARMING 初期可以等待尚未出现的 observation。明确危险、已观测 safety readback stale，或
已经满足过的 required input 再次失效会锁存 INHIBITED。READY 丢失任一 preflight 条件也会
INHIBITED，不自动恢复。

`actuation_allowed=True` 比 `required_inputs_fresh=True` 更严格：必须 ACTIVE、current authority
token committed、两 owner readback 匹配、E-STOP 明确 false、fan enabled、motor/fan mode 已
观测，并满足所有 Runtime safety gate。默认 takeover 关闭时永远 false。

## Two-phase owner handoff

motor owner states 包含 `MANUAL/LEGACY_AUTO/NONE/FLIGHT_RESERVED/FLIGHT_CONTROL`；fan 包含
`LEGACY_MANUAL/LEGACY_AUTO/NONE/FLIGHT_RESERVED/FLIGHT_CONTROL`。

Handoff sequence：

1. Runtime 在 READY 后向 motor/fan 请求 reserve；
2. lower level 校验 current token 与本地 safety，清除旧 target/command 并阻止 legacy input；
3. 两边 reserve 成功后分别 commit；
4. commit response 只作为 owner acknowledgement；
5. Runtime 还必须观察两路 ownership readback 为同一 token 的 `FLIGHT_CONTROL`；
6. 满足全部条件后执行单独 atomic authority commit。

两路 ack 顺序不重要；duplicate、old token、cancel/inhibit 后、READY 前或 malformed response
都拒绝。任何一边失败都先本地 invalidate Runtime token/dispatch，再 best-effort revoke；绝不
fallback 到 legacy owner。

## Atomic cutoff and command envelope

atomic commit 使用提交瞬间的最新 `FlightState.sequence` 形成 immutable
`arming_cutoff_state_sequence`，且不能早于 READY barrier。成功后：

- controller 只 reset 一次；
- pre-commit preview 全部丢弃；
- 第一条 executable command 必须来自 `state_sequence > cutoff` 的新 snapshot；
- handoff 前 command 不缓存、不复用；
- envelope 携带 current epoch/generation、strictly increasing command sequence、state sequence、
  finite produced monotonic time 和完整 validated `FlightCommand`。

唯一 Runtime → actuator transport 是 `/flight_control/command`。motor/fan consumer 各自重新
校验 token、sequence 和本域 payload；任一域拒绝不被另一域覆盖。

## Leases and heartbeat

Runtime transaction、lower-level handoff 和 ACTIVE command 使用独立 local monotonic deadline：

- Runtime handoff transaction default `1.0 s`；
- motor/fan handoff lease default `1.5 s`；
- motor/fan ACTIVE command lease default `0.25 s`；
- best-effort revoke diagnostic deadline default `0.25 s`。

reserve 启动 handoff lease，commit 不重置。只有第一条 token、sequence、post-cutoff 和 payload
都合法的 normal envelope 才结束 handoff lease并启动 ACTIVE heartbeat lease。之后只有合法
normal frame 刷新；duplicate、wrong token、invalid payload 和 safe-stop 都不刷新。

这些值是当前 production defaults。v0.4.0 bounded/fail-closed verification 已覆盖相关 release
scenarios，但本文不把单次 observation 扩展为通用 timing SLA、控制性能标定或任意 load 下的
保证。

## Command and safe-stop semantics

normal `FlightCommand` 包含 complete motor frame 和 left/right normalized fan payload。Runtime
strict validation 不 silent fill/clamp；motor soft limit、motion step/rate 和 fan PWM/slew 留在
lower-level manager。

`FlightCommand.safe_stop()` 是 payload-free intent：

- DRY_RUN 只发布 preview；
- ACTIVE Runtime 先关闭 executable dispatch、invalidate token/sequence 并进入 inhibit/rollback；
- 不复制上一帧，不将 `None` 替换为零；
- 不等于 hardware E-STOP，不清除 ERROR，不恢复 legacy owner。

## Actuator adapters and final veto

Motor adapter 复用 `MotorManager` 的 `MotionSource.FLIGHT` 和唯一 motion timer，不新增
`FLIGHT_RUNNING` controller state；它在 `AUTO_RUNNING + owner=FLIGHT_CONTROL` 下继续应用
soft limit、maximum step、mode/motor speed limit、feedback/transport fault 和 write-failure
ERROR path。

Fan adapter 不创建第二个 GPIO controller。`FanCommandManager` 继续是唯一 ordinary PWM
publisher；`0` 映射 stop，`(0,1]` 在 configured start/max 区间映射并应用既有 rise/fall slew。
normalized command 不是 thrust fraction。

Runtime、adapter 或 algorithm 都不能绕过 lower-level E-STOP、ERROR、watchdog、lease、
disabled/lifecycle state、soft limit 或 shutdown cleanup。

## Failure, rollback and shutdown

以下任一条件会关闭 executable command gate、invalidate token/sequence，并使 Runtime fail
closed：

- stale/invalid required state；
- authoritative safety unknown/stale/conflict；
- E-STOP/ERROR；
- owner readback loss/process epoch change；
- handoff/command lease timeout；
- safe-stop request；
- controller loader/reset/update 或 validation exception；
- Runtime shutdown/restart isolation failure；
- envelope/token/sequence/payload violation。

Rollback order：

1. local invalidate authority/token；
2. close executable dispatch；
3. clear pending handoff/ack/command tracking；
4. latch INHIBITED；
5. 对 motor/fan 各执行一次 non-blocking best-effort revoke。

cleanup diagnostic 区分 not attempted、success、service unavailable、timeout、exception、
rejected 和 malformed response。cleanup failure 不得递归触发 rollback，也不重新打开 dispatch；
lower-level lease 是 Runtime crash/unresponsive 的独立 fail-closed backstop。revoke 不自动恢复
legacy owner。

Runtime executable 禁用 rclpy default SIGINT/SIGTERM handler，由 Python signal handler 保持
ROS context 在 `destroy_node()`/rollback 期间有效，node destruction 后才 shutdown context。
普通 executor/Runtime error 不伪装成 clean signal exit。restart 必须获得 fresh process PID、
authority epoch 和完整新 handoff；不得恢复 old token/target/command sequence。

## Non-negotiable safety invariants

- ERROR 和 INHIBITED 不因 input/transport 恢复自动清除；
- 不自动恢复 MANUAL/AUTO/HOME、owner、authority 或旧 target；
- Runtime 不清除 ERROR/E-STOP，不 enable hardware，不 set zero；
- algorithm/Runtime 不直接访问 CAN/serial/GPIO/PWM/CyberGear backend；
- every executable normal command 使用 current token、post-cutoff state 和 strict sequence；
- safe-stop 永不携带 actuator payload；
- unknown 使用 `None`/presence，不用 false/zero/empty string 伪装；
- torque 不推导 current，不创建未经验证的 RPM/thrust；
- motor/fan manager、watchdog、lease、soft limit、E-STOP 和 physical operator boundary 保持最终
  裁决权；
- software CI/fake/mock/DRY_RUN 不表述为真实硬件验证。

新增 field 或 transport contract 必须有可验证来源、unit、frame/sign、presence/None、validity/
freshness 和 compatibility 说明。删除字段、改变单位/presence 或放宽 validation 属于 breaking
change，需要独立 migration review。
