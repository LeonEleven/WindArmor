# WindArmor 当前开发交接

> **INTERNAL DEVELOPMENT HANDOFF — MUTABLE。** 当前 branch、push、PR、CI 与 merge 等实时
> 生命周期状态以 Git / GitHub 为准；本文件仅保留下一工作单元需要的稳定工程状态。

## 当前工作单元

- 日期：2026-09-24；Task：`v0.5.0-020A.2 — ALG-007 IMU Data-path Provenance + Sample
  Coherence Prerequisite Freeze`；task branch：`docs/alg-007-imu-sample-coherence-prereq`。
- task-start baseline：`origin/develop@00d6f2fe105a837311bfe99a69755fd383766f2d`；
  v0.5.0-019、v0.5.0-020A 与 v0.5.0-020A.1 均已 **MERGED / INTEGRATED**。
- Stable release：`v0.4.0`；v0.5.0：**NOT RELEASED**。
- ALG-001～006：**QUALIFIED / INTEGRATED**。ALG-006 fixed implementation SHA：
  `9a7a624713010eff48cf7112b0501266eb24521e`；Formal Qualification/Result evidence SHA：
  `6729443d5e190986c75b8521a4ec7ebd0554d34e`。
- [ALG-007 Task Spec](algorithm_tasks/ALG-007.md) 与
  [Benchmark §14](ALGORITHM_BENCHMARK.md#14-alg-007-planned-profile-design-v1)：020A 已冻结
  roll-rate 公式、conditioning model、optional-derived compatibility、sign wiring 与逻辑
  same-sample/lifecycle design；020A.1 已冻结 numerical evidence gap；020A.2 已冻结 IMU
  data-path / module-configuration provenance 与 coherent composite-sample prerequisite。
- `relative_roll_rate_rad_s`：**PLANNED / NOT IMPLEMENTED**；exact near-singularity rule、
  `theta_max`、`K_max`：**NOT FROZEN**。
- ALG-007 Candidate：**BLOCKED / NOT IMPLEMENTED**；Candidate Result：**NOT CREATED**；
  Formal Qualification：**NOT EXECUTED**。

## IMU data-path provenance freeze

当前 production path 的厂家 orientation source 是 `0x53 ANGLE` Euler，不是 `0x59`
quaternion。parser 解析 `0x51 ACC`、`0x52 GYRO`、`0x53 ANGLE`，不解析/使用 `0x59`；driver
把 `0x53` Euler 转成软件生成的 ROS `(x,y,z,w)` quaternion，下游再从该表示重建 Z-Y-X Euler。
因此 vendor quaternion quantization 不适用于当前 active path。

`0x52` 应称为 **module-reported angular velocity**。厂家模块内部存在 offset、auto-calibration、
filtering、static detection 与 low-rate zeroing/threshold behavior；当前证据不能把它无条件称为
raw MEMS rate。WindArmor wire decode 使用厂家 `signed_int16 / 32768 * 2000 deg/s` 后转
`rad/s`，与 documented fixed range 一致，但该范围不是 robot operating envelope。

厂家资料来自人工已审查的 external evidence handoff，不是 repository-tracked normative
specification；本工作单元不声称独立读取或验证原 PDF/模型。owner 确认实际 IMU 只使用厂家
上位机做过功能测试且未主动修改配置，因此物理设备**合理预期**仍为 documented vendor
defaults；WindArmor Runtime 没有 write/readback verification，不能称为 `VERIFIED DEFAULT`。

## Sample coherence freeze

当前 parser 为 ACC/GYRO/ANGLE 分别保存 latest cache；合法 `0x53` 到达时，driver 使用 latest
ACC + latest GYRO + current ANGLE 合成一条新的 ROS `sensor_msgs/Imu` 并生成 ROS timestamp。
parser 没有 vendor sample/cycle ID、per-frame source timestamp 或完整 module-update generation，
也不使用 `0x50 TIME`。

- Same composite ROS `Imu`：**CURRENTLY AVAILABLE**；
- Same vendor module update/cycle：**NOT PROVEN**；
- lost/bad `GYRO_N+1` + arriving `ANGLE_N+1`：不能排除 `GYRO_N + ANGLE_N+1`；
- reconnect 后先到 new angle：当前没有证明 parser partial/component cache 清空，不能排除
  reconnect 前 gyro + reconnect 后 angle；
- 上述是当前静态实现允许/不能排除的 sequence，**不是硬件已观察故障**。

020A 的 logical same-sample contract 不变。未来 coherent composite implementation 必须保证：
previous gyro 不与 new angle 组合；reconnect/reset 清除或代次隔离 partial/component/pending state；
fresh ROS timestamp 不掩盖 stale component；只有新完成的 coherent composite sample 才建立
downstream freshness。具体 state machine、source-time、cycle tracking 或 bookkeeping 方案尚未选择。

## Configuration 与 specification applicability

厂家 defaults handoff 包括：RSW `0x001E`（ACC/GYRO/ANGLE/MAG，无 quaternion）、RRATE
`10 Hz`、BAUD `9600`、BANDWIDTH `20 Hz`、fixed GYRORANGE `2000 deg/s`、AXIS6 `0`
（9-axis）、FILTK `30`、GYROCALTIME `1000 ms`、WZTIME `500 ms`、WZSTATIC
`0.3 deg/s`。host serial baud `9600` 是 source-controlled；module side BAUD 与其它关键配置均
未由 WindArmor write/readback。完整 matrix 见 Task Spec §7.8.3。

- gyro range 与 `0.061035... deg/s/LSB` protocol quantization：**DIRECTLY APPLICABLE TO WIRE
  DECODE**，但不是 operating/error bound；
- Euler `0.005493... deg/LSB` protocol quantization：**DIRECTLY APPLICABLE**；
- gyro RMS noise `0.028~0.07 deg/s-rms @ 100 Hz bandwidth`：**NOT PROVEN DIRECTLY
  APPLICABLE**；module bandwidth 无 readback，owner-history expectation 为 default `20 Hz`；
- static zero drift 与 temperature drift：**CONDITIONALLY APPLICABLE**，不是 hard maximum；
- pitch/roll static `0.1 deg`、dynamic `0.5 deg` typical accuracy：**CONDITIONALLY APPLICABLE**，
  不是 guaranteed hard maximum；
- 与正式表冲突的产品特点 `0.05/0.1 deg`：不得用于 numerical guard；
- vendor `0x59` quaternion quantization：**NOT APPLICABLE TO CURRENT ACTIVE DATA PATH**。

## 独立 blockers 与下一步

- **Blocker A — numerical uncertainty/error budget**：仍缺 deterministic combined source
  uncertainty、relevant rate magnitude、accepted derived roll-rate error budget 与 exact guard；
  `EULER_GIMBAL_LOCK_COS_TOLERANCE=1e-9` 仍只是 mathematical/implementation guard。
- **Blocker B — sample coherence/data path**：必须关闭 old gyro + new angle、reconnect prior
  reuse、vendor-cycle identity 与 coherent freshness gap。
- **Module configuration contract**：未来需单独 review startup configure、startup
  readback/reject mismatch 或 explicit external provisioning contract；本任务未选择方案。

任一 blocker 关闭都不能推出另一个已关闭。两类 blocker、所需 lifecycle/reset semantics 与
可接受 module configuration contract 未完成前，020B 保持 **BLOCKED**；不得实现 shared
roll-rate API/runtime。Executable nonzero `FlightCommand` projection 仍是独立的
**NOT DEFINED / NOT VERIFIED** prerequisite，完成全部前置依赖及完整 Profile review 前不得进入
ALG-007 Candidate。

## Hardware / evidence boundary

- Hardware access：**NO**；authorization：**NONE**；hardware validation / Level F：
  **NOT AUTHORIZED / NOT EXECUTED**。
- Real actuator safety、hardware dynamic closed-loop recovery 与 real Balance Recovery：
  **NOT VERIFIED**。
- 020A.2 不修改 production source、tests、config、launch 或 CI，不实现 coherence mechanism、
  configuration write/readback、`relative_roll_rate_rad_s`、roll sign wiring、Candidate 或非零
  executable projection。
