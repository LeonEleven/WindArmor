# IMU 020A.6 单设备读回验证证据

## 1. 范围、来源与结果

- 归档日期：2026-10-23；日志主机墙钟显示 A/B/C v2/D 均执行于 2026-10-22。
  墙钟未作独立校准，延迟计算使用日志中的主机单调时钟。
- 生产代码及归档 task-start baseline：`develop@d5245a901229c2880a471f8e19c55309bf0a74e1`。
- A/B/C v2/D 由 operator 在树莓派宿主机执行；本次归档只读取已保存字节、JSON 和 JSONL，
  没有重新运行任何阶段，没有启动硬件节点或访问串口、CAN、GPIO、PWM、电机、风扇。
- 四阶段结论为 **PASS，限下述单设备、指定场景及主机假设**；ALG-007 仍 **BLOCKED**。
  本记录不构成新硬件执行授权，不是 Candidate Result、Formal Qualification 或 release evidence。
- 设计与未关闭前置条件见 [ALG-007 Task Spec](../algorithm_tasks/ALG-007.md)；
  生产接口与条件性读回规则见 [IMU 包 README](../../src/imu_cybergear_ros2/README.md)。

原始目录及持久副本的 12 个文件全部存在。复核独立重扫原始字节，核对每条 frame 事件的
偏移、完整内容与校验结果，重新计算 GYRO→ANGLE latest-pending/no-reuse 配对，并对照
JSONL 中的接收、发送、状态转换及清理事件；结论不是只转录 `summary.json`。

## 2. A/B/C v2 原始流复核

三阶段均以 `/dev/imu_usb`、9600 baud 采集，名义观察时长 60 秒。下表区分普通帧与 `0x5F`，
完整帧数不包含采集边缘的跳过字节或尾部残帧。

| 阶段 | 目的与结果 | RX 字节 / read 记录 | 合法普通帧 / `0x5F` | 合法 pair | 校验失败 / 孤立 ANGLE / pending 替换 |
| --- | --- | --- | --- | --- | --- |
| A — PASS | 被动连续流基线，日志无 TX 事件 | 53,024 / 1,808 | 4,820 / 0 | 602 | 0 / 0 / 0 |
| B — PASS | 单次 `READADDR 0x02`；一条 TX、一条 5-byte 写入返回、一条合法应答，无重试事件 | 53,019 / 1,808 | 4,818 / 1 | 602 | 0 / 0 / 0 |
| C v2 — PASS | 单次 `READADDR 0x20`；一条 TX、一条 5-byte 写入返回、一条合法应答，无重试事件 | 53,049 / 1,809 | 4,820 / 1 | 603 | 0 / 0 / 0 |

普通流中实际出现 `0x50/51/52/53/54/55/56/59`。记录到 TIME、QUATERNION 等额外帧，
不改变当前生产姿态来源为 `0x53` Euler、ROS quaternion 为软件转换的事实。

| 阶段 | 跳过字节 | 尾部残帧字节 | 打开至关闭时长（秒） | 主机 parse GYRO→ANGLE 间隔 min / median / max（毫秒） |
| --- | --- | --- | --- | --- |
| A | 4 | 0 | 59.988022187 | 0.023611 / 0.0345355 / 0.186806 |
| B | 0 | 10 | 60.002030919 | 0.024482 / 0.0387495 / 1.312768 |
| C v2 | 9 | 9 | 60.002014740 | 0.025148 / 0.039018 / 33.111143 |

跳过字节和尾部残帧均完整保存在 `raw.bin`，未被计作合法帧或校验失败。
名义 60 秒不表示打开与关闭两个事件间必须精确为 60 秒。
主机 parse 间隔包括解析和日志开销；A/B 的 pair 均在同一次 read 返回中完成，
其 read-return 时间差为零；C v2 的最大 read-return 差为 33.178049 ms。
这些是有限主机观察，不能据此证明物理同采样或冻结组件年龄门槛。

### 实际请求、响应与延迟

| 阶段 | 唯一请求 | 完整合法应答 | unsigned little-endian words | 主机延迟（毫秒） |
| --- | --- | --- | --- | --- |
| B | `FF AA 27 02 00` | `55 5F 7F 02 06 00 02 00 05 00 42` | `[639, 6, 2, 5]` | 204.715079 |
| C v2 | `FF AA 27 20 00` | `55 5F 03 00 03 00 00 00 00 00 BA` | `[3, 3, 0, 0]` | 204.576116 |

延迟按 `完整合法 0x5F 所在 read 的 read_end_ns − tx_write_return.mono_ns` 重算。
这是 host write-return 到 host read-return 的间隔，不是 UART 发完到设备响应的纯链路时延，
也不是 parser 完整接受时间，更不能由两次观测推出最大应答寿命 B。

**最初 Stage C：NOT EXECUTED。** operator 历史说明为未获得安全发送机会，不属于硬件通信失败；
本次复核的是上述 C v2 成功目录。初次 Stage C 的独立原始目录/终端记录未提供，未补造统计。

## 3. Stage D：生产驱动条件性读回与新 pair gate

### 代码与诊断 runner 的角色

Stage D 使用临时 runner，在进程内直接复用生产 `ImuDriverNode`、`WitImuFrameParser` 和
现有 READADDR 状态机；观察层记录内部状态，串口外层限制 activation、连接和写入次数。
它不是通过原生 `ros2 launch` 执行的全生命周期验证，也没有重新实现读回事务。

`environment.json` 的生产源码哈希已与该 baseline 的 Git blob 及归档时源码逐一核对：

| 文件 | SHA-256 |
| --- | --- |
| `imu_driver_node.py` | `bc58725ab393e4a9b385b740ad2170e6941f775de9f4618bd62a8ca8e431957c` |
| `imu_protocol.py` | `dbf296d6bec68084f542c6c716bc2998d216c41f5ff39698762e77c6e3ef2e68` |
| `__init__.py` | `46385002e9e76a3008af92f0475a6c4798f7c600e54676906e2077af6db14b30` |

环境记录的 runner SHA-256 为
`57a9fff36783ab910909c0fd8dafee14754033b643d538ba15cd3acef09361db`，
与归档时仍存在的本地 runner 内容一致。runner 与临时配置不提交到仓库。
环境为 ROS Jazzy、Python 3.12.3、pyserial 3.5；实际使用源码导入，未以安装目录代替源码核对。

本次参数为 `port=/dev/imu_usb`、`baud=9600`、`config_readback_enabled=true`、
`config_readback_response_bound_sec=1.0`。**B=1.0 秒仅是实验的有限主机假设**，并非厂家保证。

### 连续记录中的正常路径

`events.jsonl` 共 612 条记录，其中 611 条带连续 sequence；125 条 RX 记录可重建 3,622 字节，
包含 326 条合法普通帧、2 条合法 `0x5F`，5 个跳过字节及 9 字节尾部残帧。
重扫字节与 328 条 frame 事件逐条一致，未发现完整候选帧校验失败。

| 证据节点 | 主机单调时间（秒）或结果 |
| --- | --- |
| 隔离起点（由隔离 deadline 减 B 得到） | 2096761.150269310 |
| 首请求内部 `sent_at` | 2096762.160261992；此前观察 1.009992682 秒 |
| `0x02` 完整合法响应接受 | 2096762.365110952；words `[639, 6, 2, 5]` |
| 第二请求内部 `sent_at` | 2096763.160845837；首窗口完整观察 1.000583845 秒 |
| `0x20` 完整合法响应接受 | 2096763.360586850；words `[3, 3, 0, 0]` |
| `checked_monotonic` | 2096764.161473682；第二窗口完整观察 1.000627845 秒 |
| 首个 `post_check_pair` 的 GYRO 接受 | 2096764.223435080，generation 3 |
| 首个 `post_check_pair` 的 ANGLE 接受 | 2096764.223680728，generation 3，pair sequence 31 |

两条 TX 均与 B/C 的请求字节一致，各写入返回 5 字节。每个窗口完整接受唯一合法响应，
响应计数最终为 2；两次发送及最终窗口提交的 context 都记录 `input_drained=true`、
`frame_buffer_size_before=0`。内部 `sent_at`、实际 write 调用起止和响应接受时间分别保留，
不将不同时间定义混为一个指标。

最终状态为 `host-associated-checked`，`required_values_passed=true`；该状态首次出现时
`post_check_pair=null`，随后才建立上述新 GYRO→ANGLE pair。该 pair 的两个组件同属当前
generation，均在检查完成之后接受，ANGLE 完成距配置检查约 62.207046 ms。
普通 `/imu/data_raw` 发布不是上述配置结论的替代证据。

RSW 实测 `639 = 0x027F`，与历史 documented default `0x001E` 不同；必需 GYRO/ANGLE 位存在，
额外输出位没有导致 required-value failure，也没有写回默认配置。差异产生原因未验证。

`observation_complete=false`，缺少：`GXOFFSET`、`GYOFFSET`、`GZOFFSET`、`BANDWIDTH`、
`AXIS6`、`FILTK`、`ACCFILT`、`GYROCALITHR`、`GYROCALTIME`、`WZTIME`、`WZSTATIC`。
本次检查成功不能提升为所有配置及误差模型 provenance 完整。

### 限额、停止与资源清理

事件与摘要一致：一次 activation、一次连接，两次真实 backend 写入、合计返回 10 字节，
没有重连或额外写入事件，没有 guard violation。首次新 pair 后继续观察约 1.000622160 秒，
最终 reason 为 `success-observation-complete`，elapsed 为 4.099525459 秒。

日志记录 reader 退出、串口关闭且 `backend_is_open=false`；deactivate 返回 SUCCESS 并清除
旧配置及 pair，cleanup 返回 SUCCESS 且配置状态变为 `null`，之后 node destroyed、ROS context
shutdown。`summary.json` 为 `fake=false`、`success=true`，清理错误与 close errors 均为空，
reader/watchdog 均不存活，bindings restored，无 recording failure 或总预算超限。

operator 另报告终端退出码 0、结束后无串口占用。本次提供的三个 Stage D 文件没有独立的
终端退出码或 `fuser` 输出，因此这两项保留为 **operator-reported**；程序自身串口关闭与
清理链已由 JSONL 复核，不能扩展为独立验证系统中所有其他进程的占用状态。

本次 D 是正常启动单场景 PASS，没有注入故障或测试真实重连；无 guard violation 不等于
所有异常拒绝路径均已经实机验证。

## 4. 持久化位置与文件指纹

原始 `/tmp` 目录均保留；持久副本位于 `~/windarmor_evidence/020A6/`，每个目录名与原目录
一致。复制对已有不同内容拒绝覆盖，复制后重新核对源文件和副本的字节数及 SHA-256。
预期 12 个文件全部存在，**缺失文件：无**。原始日志、个人设备信息及本地 helper 不进入 Git。

| 阶段 | 源目录（位于 `/tmp/`）及持久副本子目录 |
| --- | --- |
| A | `windarmor-020a6-A-fw4z8fq6/` |
| B | `windarmor-020a6-B-ftz7q4q5/` |
| C v2 | `windarmor-020a6-C-s8fgmskv/` |
| D | `windarmor-020a6-D-wx0ts4qv/` |

| 阶段 | 文件 | 字节数 | SHA-256 |
| --- | --- | --- | --- |
| A | `events.jsonl` | 1584838 | `d827c2ed343142c2ee5d77b04200516c76194da0b1697df4c0cc5e898852ceed` |
| A | `raw.bin` | 53024 | `f97ab1c7fd03ad6bbde2463e2b26a1171a06fcc84e8c43bae9cac17678a9320c` |
| A | `summary.json` | 1259 | `f14b8e5d719e469ccae501ccd219e399d22df39ae20047498cd600ef8b046795` |
| B | `events.jsonl` | 1465142 | `cfbfaabbd4d7982acbb6fdf41e6a907483486841dc13491a7d937feb9f0eba0d` |
| B | `raw.bin` | 53019 | `8985a8377dd5d9da16761e78fbad51055b18a636dfc5f18886df5e799f0280c4` |
| B | `summary.json` | 2496 | `18ff52d0f4f6d1e4031dfc62af3d3747b4c29a8144462d4fe031ebb28d21c3dc` |
| C v2 | `events.jsonl` | 1465886 | `99b043b5e7580938f10c33916c2003c840f98457cc03749cc1e90f26b73f8158` |
| C v2 | `raw.bin` | 53049 | `88f018121fbe8e0500cb59e76827a3fdfeed94c758ec3f3f2a112623a76800f3` |
| C v2 | `summary.json` | 2851 | `1e38d91e7f9e96112c251970324befae9b9548ff0c7c50feeef09eb342b31851` |
| D | `environment.json` | 1493 | `7940fdc3ef9c65ac5ecb62d4dc5441dfda8e1c985650031bb18db6daf7603cb7` |
| D | `events.jsonl` | 327728 | `d57a1fffbf32efb3a4a26c3f39db4d195680903f80fb9d38374569ce56eec8d5` |
| D | `summary.json` | 3086 | `c4c33fd18f465e17824bcec42d2c4eb814ff265a601fd2ca326312e57528c96c` |

持久目录根部 `MANIFEST.json` 保存相对路径、大小和哈希，其 SHA-256 为
`2a716d96f69dc693b262363b4a1b2cbdb74daf2d66808020a97142043e738023`。
这些指纹用于核验已保存文件内容，不证明设备身份、执行授权或采集程序完整性本身。

## 5. 历史语义与未关闭边界

020A.5 的软件实现交接确实记录当时未执行真实串口、READADDR 或执行器测试；该历史仍然成立。
020A.6 是后续 operator 实测证据，补充单设备正常路径，不将此前的 fake/software 测试改写为
硬件验证。020A.2/020A.3 的设计冻结段落中的实现状态同样对应其历史时点。

本轮 PASS 不关闭以下证据缺口：

- B=1 秒的普遍适用性或厂家最大应答寿命；更晚的重复/旧连接响应及外部同形响应仍可能不可区分。
- 匿名 `0x5F` 的厂家级地址/请求 ID 关联；当前仅为有限寿命、独占来源及配置稳定假设下的
  `host-associated-checked`。
- 全部配置寄存器、校准与误差模型 provenance；非零校准值不自动失败或清零。
- Level-3 厂家同更新周期、Level-4 物理同采样；当前 `post_check_pair` 仅证明 Level-2 软件配对。
- 有限组件/pair 年龄规则及 exact threshold；既有 base freshness `0.2 s` 不能直接替代。
- deterministic combined uncertainty/error budget、相关 rate magnitude、near-singularity 数值规则、
  `theta_max` 与 `K_max`；实现中的数学奇异点 guard 不是工程误差预算。
- 原生 ROS launch 全生命周期、真实异常/重连故障矩阵、执行器安全、非零 `FlightCommand`
  projection、motor/fan authority/allocation、整机平衡或闭环恢复。

`relative_roll_rate_rad_s` 仍 PLANNED / NOT IMPLEMENTED；020B、ALG-007 Candidate 仍 BLOCKED，
Candidate Result 未创建，Formal Qualification 未执行，v0.5.0 未发布。
