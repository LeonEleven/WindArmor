# WindArmor 当前开发交接

> **INTERNAL DEVELOPMENT HANDOFF — MUTABLE。** 当前 branch、push、PR、CI 与 merge 等实时
> 生命周期状态以 Git / GitHub 为准；本文件仅保留下一工作单元需要的稳定工程状态。

## 当前工作单元

- 日期：2026-09-30；Task：`v0.5.0-020A.3 — ALG-007 IMU Coherent Component Pair +
  Configuration Verification Contract Freeze`；task branch：
  `docs/alg-007-imu-coherence-config-contract`。
- task-start baseline：`origin/develop@d512fe93f5be1b2ee730ca2a32b95f854516d65d`；
  v0.5.0-019、v0.5.0-020A、v0.5.0-020A.1 与 v0.5.0-020A.2 均已
  **MERGED / INTEGRATED**。
- Stable release：`v0.4.0`；v0.5.0：**NOT RELEASED**。
- ALG-001～006：**QUALIFIED / INTEGRATED**。ALG-006 fixed implementation SHA：
  `9a7a624713010eff48cf7112b0501266eb24521e`；Formal Qualification/Result evidence SHA：
  `6729443d5e190986c75b8521a4ec7ebd0554d34e`。
- [ALG-007 Task Spec](algorithm_tasks/ALG-007.md) 与
  [Benchmark §14](ALGORITHM_BENCHMARK.md#14-alg-007-planned-profile-design-v1)：020A 已冻结
  roll-rate 公式、conditioning model、optional-derived compatibility、sign wiring 与逻辑
  same-sample/lifecycle design；020A.1 已冻结 numerical evidence gap；020A.2 已冻结 IMU
  data-path / module-configuration provenance；020A.3 已冻结 Level-2 coherent component-pair 与
  startup/reconnect configuration readback+validate design，但尚未实现。
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

本工作单元直接复核了 git-ignored 的厂家《10轴IMU模块通讯协议》《用户手册》和两份应用教程；
它们是 local external manufacturer evidence，不是 repository-tracked normative specification。
owner 确认实际 IMU 只使用厂家上位机做过功能测试且未主动修改配置，因此物理设备**合理预期**
仍为 documented vendor defaults；WindArmor Runtime 没有 write/readback verification，不能称为
`VERIFIED DEFAULT`。

## Coherent component-pair freeze

当前 parser 为 ACC/GYRO/ANGLE 分别保存 latest cache；合法 `0x53` 到达时，driver 使用 latest
ACC + latest GYRO + current ANGLE 合成一条新的 ROS `sensor_msgs/Imu` 并生成 ROS timestamp。
parser 没有 vendor sample/cycle ID、per-frame source timestamp 或完整 module-update generation，
也不使用 `0x50 TIME`。

- Level 1 — same composite ROS `Imu`：**PROVEN / CURRENTLY AVAILABLE**；
- Level 2 — fresh ordered coherent GYRO+ANGLE pair：**DESIGN FROZEN / NOT IMPLEMENTED**；
- Level 3 — same vendor output/update cycle：**NOT PROVEN**；
- Level 4 — same physical sampling instant：**NOT PROVEN**；
- lost/bad `GYRO_N+1` + arriving `ANGLE_N+1`：不能排除 `GYRO_N + ANGLE_N+1`；
- reconnect 后先到 new angle：当前没有证明 parser partial/component cache 清空，不能排除
  reconnect 前 gyro + reconnect 后 angle；
- 上述是当前静态实现允许/不能排除的 sequence，**不是硬件已观察故障**。

logical same-sample 的精确软件含义已冻结：每个 Flight-usable pair 必须包含上一 emitted pair
后新接受的 valid GYRO，以及同一 parser/configuration generation 内随后接受的 valid ANGLE；
emission 后 GYRO consumed，不得由 duplicate/new ANGLE reuse。一个 ANGLE 前多个 valid GYRO
采用 latest pending；bad GYRO 不建立 generation，bad ANGLE 不 emission 也不 consume pending
GYRO。该 contract 不声称 same vendor cycle 或 same physical instant。

startup、disconnect/reconnect、parser reset、lifecycle reactivate 或 configuration-generation change
必须清除/代次隔离 partial parser bytes、component cache/pending state、consumed marker、receive
times、pair availability 与 config marker。required components 各自保留 host receive-time；fresh
composite timestamp 不得抹去 component age。exact maximum pair/component age **NOT FROZEN**，
现有 base freshness `0.2 s` 不自动成为 pair-age threshold。

legacy/base ALG-001～006 validity 与 ALG-007 derived prerequisite 分层：config/coherence-only failure
默认只令未来 `relative_roll_rate_rad_s=None` / unavailable，不自动使整个 base `ImuState` invalid。
ALG-001～006 validity semantics 未改变。

## Configuration verification 与 specification applicability

选定 design 是 **STARTUP / RECONNECT READBACK + VALIDATE**，required mismatch/readback failure
只让 ALG-007 derived capability fail closed；它不是 startup factory reset、blind configure-all 或
external provisioning only。每次 startup、reconnect、relevant reset/transport regeneration 建立新
configuration-validation generation；validation 完成前及其后第一对 new coherent GYRO+ANGLE
形成前，ALG-007 unavailable。上一连接 validation 不得继承。

厂家 `READADDR 0x27` 和固定返回四个连续 16-bit registers 的 `0x55 0x5F` 使 readback
protocol-feasible；continuous-stream interleave、KEY requirement、request association、timeout 与
暂停 streaming 的 exact transaction 仍 **NOT FULLY SPECIFIED / NOT FROZEN**。默认政策是
**DO NOT AUTO-WRITE / DO NOT SAVE / DO NOT RESTORE FACTORY DEFAULTS**。

厂家 defaults handoff 包括：RSW `0x001E`（ACC/GYRO/ANGLE/MAG，无 quaternion）、RRATE
`10 Hz`、BAUD `9600`、BANDWIDTH `20 Hz`、fixed GYRORANGE `2000 deg/s`、AXIS6 `0`
（9-axis）、FILTK `30`、GYROCALTIME `1000 ms`、WZTIME `500 ms`、WZSTATIC
`0.3 deg/s`。host serial baud `9600` 是 source-controlled；module side BAUD 与其它关键配置均
未由 WindArmor write/readback。完整分类 matrix 见 Task Spec §7.9.6：RSW 只冻结 GYRO+ANGLE
required bits，不冻结整个 `0x001E`；GYRORANGE 是 fixed wire-decode prerequisite，不是 operating
envelope；RRATE/BANDWIDTH/ORIENT/AXIS6/FILTK/ACCFILT 的 exact accepted values 尚未冻结。
GX/GY/GZ offsets 与其它 calibration/device state 只 read/observe，non-default 不自动 failure，
绝不在 startup 清零。GYROCALITHR/GYROCALTIME/WZTIME/WZSTATIC 要求 future runtime
observability 供 error-model provenance，但 exact accepted values 尚未冻结，也不得自动写入。

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

厂家 frame type/RSW bit mapping 不构成 ACC→GYRO→ANGLE normative order；wire order **NOT
SPECIFIED**。`0x50 TIME` 没有 sample sequence、per-component timestamp 或与 GYRO/ANGLE 的
normative binding，**NOT SUFFICIENT AS AUTHORITATIVE SAMPLE ID**。对 conservative Level-2
software contract 不需要新增厂家证据，但 Level-3 vendor-cycle claim 仍被阻止。

## 独立 blockers 与下一步

- **Blocker A — numerical uncertainty/error budget**：仍缺 deterministic combined source
  uncertainty、relevant rate magnitude、accepted derived roll-rate error budget 与 exact guard；
  `EULER_GIMBAL_LOCK_COS_TOLERANCE=1e-9` 仍只是 mathematical/implementation guard。
- **Implementation prerequisite — coherence/config**：design 已冻结，但 typed valid-frame handling、
  pair FSM/generation、receive-time tracking、reconnect reset、`0x5F` parsing、READADDR transaction
  和 configuration validation generation 均 **NOT IMPLEMENTED**。
- **Timing prerequisite**：component maximum-age threshold **NOT FROZEN**。

configuration/coherence design freeze 不关闭 numerical blocker。coherence/config implementation、
component-age review（如需要）与 exact numerical rule 未完成前，020B 保持 **BLOCKED**；不得
实现 shared roll-rate API/runtime。Executable nonzero `FlightCommand` projection 仍是独立的
**NOT DEFINED / NOT VERIFIED** prerequisite，完成全部前置依赖及完整 Profile review 前不得进入
ALG-007 Candidate。

## Hardware / evidence boundary

- Hardware access：**NO**；authorization：**NONE**；hardware validation / Level F：
  **NOT AUTHORIZED / NOT EXECUTED**。
- Real actuator safety、hardware dynamic closed-loop recovery 与 real Balance Recovery：
  **NOT VERIFIED**。
- 020A.3 不修改 production source、tests、config、launch 或 CI，不实现 coherence mechanism、
  configuration write/readback、numerical guard、`relative_roll_rate_rad_s`、020B、Candidate 或
  非零 executable projection。
