# 最新反馈：Gate C 证据方案收敛

> 本文件只保留当前最新任务反馈。
>
> 日期：2026-08-19

## Result

本次完成 Gate C fail-closed verification 的 evidence/design review：

```text
Gate B: COMPLETE
Gate C: NOT EXECUTED / NOT AUTHORIZED
```

本次只修改文档，没有执行真实硬件，没有启动硬件 node/launch，没有配置 CAN、访问
串口/IMU、操作 GPIO/PWM/CyberGear/ESC/fan、publish `/e_stop`、调用 authority prepare
或执行 lifecycle transition。pure software/static validation 不能表述为 Gate C 实机验证。

## Evidence workflow 收敛

- `record_gate_evidence.py` continuous recorder 继续作为长期通用 verification
  infrastructure，优先保存 transient ROS history。
- operator physical observation 始终独立存在；场景结束后默认人工离线审查 trigger、
  continuous ROS、物理观察和 no-automatic-recovery 四类证据。
- 只有人工判定容易出错、条件复杂且重复执行价值明显时，才考虑 gate-specific analyzer；
  analyzer 不能替代 physical observation，也不能单独宣布 hardware PASS。
- 本次没有新增 Gate C analyzer、recorder、config 或其他 verification framework。
- `analyze_b2_evidence.py` 和对应测试属于 v0.4.0 verification-cycle scoped tooling，暂时
  保留到 Gate C、Gate D 和 v0.4.0 release cycle 收口；形成正式 tag/release 后，再通过
  独立 cleanup task 判断是否从未来 master 删除。Git tag/history 承担历史可追溯性。

## Gate C evidence responsibilities

- C1：lifecycle CLI/transition 和 IMU sample cessation 共同证明 stale-input trigger；默认
  recorder 不足，未来使用不提交仓库的本地完整 topic config，在默认八项之外加入
  `/imu/data_raw` 和 `/imu_driver_node/transition_event`。`--config` 与 `--topic` 都会替换
  默认 topic 集，不能只列额外项。
- C2：带 PID 的 stopped-process transcript 与 command cessation 证明 Runtime pause；两路
  lease timeout 和 ownership transition 的 required historical evidence 由 continuous
  recorder 提供。人工 `ros2 topic echo` 仅为 optional live observation，其缺失或未追上
  瞬态不能推翻有效 continuous history。
- C3：旧/新 PID 和 terminal transcript 证明 graceful stop 与新 process/session；recorder
  跨 restart 保存 revoke、halt/stop、新 epoch、DRY_RUN/NONE 和 stale authority 隔离证据。
- C4a：lifecycle CLI 证明 owner-loss trigger；recorder 保存 motor node inactive、owner
  release、Runtime inhibit、motor halt 和 fan stop/revoke。
- C4b：预热 watchdog 的 stdout/stderr 与真实 exit status 是正式 timing evidence；必须
  保存 ready、ACTIVE detected、E-STOP published、ACTIVE-to-publish、Flight observed
  E-STOP/inhibit 和 publish-to-inhibit 字段。exit code 0 本身不是 PASS；字段缺失为
  `NOT VERIFIED`/FAIL。continuous recorder 仍负责 ROS topic history。
- 每个子场景都要求人工观察 actuator 是否及时停止、未批准 motor movement、错侧/继续
  旋转的 fan，以及异常声音、振动、气味和温升。
- 每个子场景都要求证明 fault 清除、Runtime restart、lifecycle 恢复或 transport reconnect
  不会自动恢复 ACTIVE、旧 epoch/generation/token/target、legacy owner 或 actuator 动作。

Gate C 的 motor logical axis、offset、LEFT/RIGHT fan command、powered actuator combination
和最大 ACTIVE 持续时间对 C1/C2/C3/C4a/C4b 均保持：

```text
TO BE SET BEFORE EXECUTION
```

B1/B2 历史值只能作为未来讨论参考，不能成为 Gate C 授权值。

## 修改文件

本次修改：

```text
docs/V0.4.0_HARDWARE_VERIFICATION_PLAN.md
docs/LATEST_FEEDBACK.md
```

任务开始时已有的 `docs/NEXT_COMMAND.md` 修改属于用户工作区内容，本次按其执行但不覆盖
或回退。

## Validation

本次只运行 pure software/static validation：

```bash
git diff --check
./scripts/ci_software.sh
```

结果：PASS。

```text
git diff --check: PASS
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

这些检查均不构成硬件验证。

## Hardware impact and remaining work

- Gate B 保持 `COMPLETE`。
- Gate C 保持 `NOT EXECUTED / NOT AUTHORIZED`；没有执行任何 Gate C trigger。
- Gate C actuator values 和最大持续时间尚未决定，全部等待未来明确授权。
- 下一步是在本次 review 完成后，由用户决定是否开始第一个 Gate C 硬件子场景；本任务
  不执行 Gate C，也不自动申请或推定硬件授权。

## Git limits

本次不创建或切换 branch，不 commit、push、tag，也不创建 GitHub Release。
