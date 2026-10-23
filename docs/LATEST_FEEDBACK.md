# WindArmor 当前开发交接

> **INTERNAL DEVELOPMENT HANDOFF — MUTABLE。** 当前 branch、push、PR、CI 与 merge 等实时
> 生命周期状态以 Git / GitHub 为准；本文件仅保留下一工作单元需要的稳定工程状态。

## 当前工作单元

- 日期：2026-10-23；Task：`IMU_REAL_EVIDENCE_020A6`，仅归档既有证据，无生产代码变更。
- task-start / 实测生产源码 baseline：
  `develop@d5245a901229c2880a471f8e19c55309bf0a74e1`。
- operator 在宿主机完成的 A、B、C v2、诊断 runner D：**PASS，限单设备正常场景**。
  本次从原始字节及连续 JSONL 复核统计、窗口、新 pair 与清理事件；
  完整结果、文件大小/哈希及证据边界见
  [020A.6 IMU 读回实测记录](verification/IMU_020A6_READBACK_EVIDENCE.md)。
- A：53,024 字节、4,820 条合法普通帧、602 对；B：单次 `0x02`，
  `[639, 6, 2, 5]`，host write-return 到响应 read-return 为 204.715079 ms；
  C v2：单次 `0x20`，`[3, 3, 0, 0]`，204.576116 ms、603 对。
  初次 Stage C 因没有安全发送机会为 **NOT EXECUTED**，不是硬件通信失败。
- D：生产源码指纹匹配；一次 activation、一次连接、两次各 5 字节写入；
  `host-associated-checked`、`required_values_passed=true`，随后新 `post_check_pair`
  的 GYRO/ANGLE 同属 generation 3，均在检查完成后接受；约 4.10 秒，程序清理证据完整。
  无 guard violation。`observation_complete=false`，仍缺少 11 项 provenance。
  终端退出码及外部无占用由 operator 报告，提供的 JSON 文件不含独立终端记录。
- 原始证据 12/12 文件已非破坏性保存到 `~/windarmor_evidence/020A6/`，
  源文件与副本的大小及 SHA-256 一致；原 `/tmp` 目录保留，日志和临时 helper 不进入 Git。
- B=1.0 秒仍是有限主机实验假设，不是厂家最大寿命保证；匿名应答关联仍为条件性结果。
  RSW 实测 `0x027F` 不等于历史预期 default `0x001E`；额外输出位不自动失败，也不写回默认值。
- Level-2 软件配对有本次正常实机证据；Level-3/4 周期/物理同采样仍 **NOT PROVEN**。
  有限 component/pair 年龄、完整数值误差预算、near-singularity 规则、`theta_max`/`K_max`
  及非零 `FlightCommand` projection / actuator authority 仍未冻结或未验证。
- `relative_roll_rate_rad_s`：**PLANNED / NOT IMPLEMENTED**；020B 与 ALG-007 Candidate：
  **BLOCKED / NOT IMPLEMENTED**；Candidate Result **NOT CREATED**，Formal Qualification
  **NOT EXECUTED**。原生 launch、真实异常/重连、电机、风扇及整机恢复不由此次正常样本验证。
- 本轮归档 hardware access：**NO**，没有重新运行 A/B/C/D；任何新实机场景仍需另行授权。
  Stable release 仍为 `v0.4.0`，v0.5.0 **NOT RELEASED**。

## 020A.5 历史交接

> 以下保留 2026-10-19 的软件实现交接。其“当前／本轮／未执行／未验证”均指 020A.5
> 当时，不否定上方 020A.6 后续 operator 实测；当时未执行硬件测试的历史结论不作改写。

### 当时工作单元

- 日期：2026-10-19；Task：`IMU_CONFIG_RUNTIME_020A5`。
- task-start baseline：`develop@1240afa8be2b97324f63103167678919928ef3b7`。
- 当前交付为默认关闭的 startup/reconnect READADDR 及验证后新 pair gate；成功仅称
  `host-associated-checked`，依赖显式有限应答寿命、独占请求来源和配置稳定假设。
  匿名应答的厂家地址关联仍 **NOT PROVEN**，真实启用与寿命假设适用性 **NOT VERIFIED**。
- Stable release：`v0.4.0`；v0.5.0：**NOT RELEASED**。
- ALG-001～006：**QUALIFIED / INTEGRATED**。ALG-006 fixed implementation SHA：
  `9a7a624713010eff48cf7112b0501266eb24521e`；Formal Qualification/Result evidence SHA：
  `6729443d5e190986c75b8521a4ec7ebd0554d34e`。
- 020A～020A.3 冻结的设计与厂家 provenance 见
  [ALG-007 §7.8–7.9](algorithm_tasks/ALG-007.md#78-imu-data-path-provenance-and-sample-coherence-prerequisite--v050-020a2-frozen)
  与 [Benchmark §14](ALGORITHM_BENCHMARK.md#14-alg-007-planned-profile-design-v1)。
- `relative_roll_rate_rad_s`：**PLANNED / NOT IMPLEMENTED**；020B 与 ALG-007 Candidate：
  **BLOCKED / NOT IMPLEMENTED**；Candidate Result：**NOT CREATED**；Formal Qualification：
  **NOT EXECUTED**。本轮普通回归测试不是新一轮资格验证。

### Level-2 实现与接口

parser 在原有合法 ACC/GYRO/ANGLE decode 路径记录不可变组件与配对快照：

- 合法新 GYRO 建立 pending；一个 ANGLE 前多个合法 GYRO 使用 latest pending。
- 同代次随后合法 ANGLE 至多形成一个 pair，成功后清除 pending；ANGLE 单独/重复到达不增加
  pair count，也不复用已消费 GYRO。
- 坏校验/残帧不建立合法组件；坏 ANGLE 和坏 GYRO 不消耗已有的未消费合法 pending。
  前一 pair 的已消费 GYRO 不会因随后 bad GYRO + valid ANGLE 被重新使用。
- 每个组件独立保存完整合法帧在主机接受时的 `received_monotonic`，不是厂家采样时间、ROS
  发布时间或一次 serial read 的共同时间。GYRO 为 module-reported rad/s，ANGLE 为度。
- `reset()` 清除 byte buffer、legacy ACC/GYRO/ANGLE cache、组件时间、pending、历史 pair 与
  count，递增 generation。driver 在 activation、连接尝试、断线、停用、清理/关闭时接入；
  reconfigure 保持代次隔离，reset 后迟到的旧 read 字节不能进入新代次。
- 重连/空闲等待可被 stop event 打断；尚未退出的旧 reader 阻止重新激活。

parser 与 driver 的 `coherence_state()` 为只读观察接口；driver 未配置时返回 `None`。
`latest_pair` 是本代次最近一次形成的**历史结果**，以 `(generation, pair_count)` 识别更新，
非空不表示新的更新、有限时间有效性或 ALG-007 availability。接口详见
[IMU 包 README](../src/imu_cybergear_ros2/README.md#imu-软件一致组件对)。

- Level 1 — same composite ROS `Imu`：**AVAILABLE / LEGACY BEHAVIOR PRESERVED**；
- Level 2 — ordered/new/no-reuse coherent GYRO+ANGLE：**IMPLEMENTED / SOFTWARE TESTED**；
- Level 3 — same vendor output/update cycle：**NOT PROVEN**；
- Level 4 — same physical sampling instant：**NOT PROVEN**。

legacy ANGLE 触发 ROS 发布仍允许 latest cached GYRO，并不代表严格 pair；本轮没有将 ROS
发布收缩为每次 fresh ACC+GYRO+ANGLE。新 pair 只在底层形成可观察的软件候选，没有被 Flight
消费，ALG-001～006 base validity、默认控制行为与既有 ROS 接口保持兼容；新增读回参数默认
关闭，不激活请求路径。

### 厂家与配置依据

020A.5 离线子集工作单元曾直接复核 git-ignored `reference/document/IMU/` 的《10轴IMU模块通讯协议》与
《用户手册》，未将 PDF 加入 Git。厂家 `0x52` signed-int16 / 32768 * 2000 deg/s 与 `0x53`
signed-int16 / 32768 * 180 deg 支持现有 wire decode；不证明厂家规范帧顺序、cycle identity
或物理同采样。当前 orientation source 仍为 `0x53` Euler，ROS quaternion 为软件转换；
`0x50 TIME` 与 `0x59` quaternion 均未新增解析/使用。

owner 历史仅支持设备合理预期仍为 documented vendor defaults，**NOT RUNTIME VERIFIED**。
`0x52` 包含厂家 offset、auto-calibration、filtering、static detection/low-rate zeroing 影响，
不能称为无条件 raw MEMS rate。wire gyro 满量程不是 robot operating envelope；厂家 typical
accuracy/noise 不是 guaranteed hard maximum，100 Hz noise specification 的 applicability
仍未证明；配置分类/defaults 与 specification applicability 完整保留在 Task Spec §7.8–7.9。

选定配置 design 仍为 **STARTUP / RECONNECT READBACK + VALIDATE**，required failure 只 gate
未来 ALG-007 derived capability，不因 config/coherence-only failure 自动使 base IMU invalid。
`READADDR` 离线编码、`0x5F` unsigned little-endian 四 word 解码与匿名接收历史已实现。
parser 复用现有 serial reader；合法匿名帧不携带请求地址，不能据此更新已关联配置结果，
坏校验/残帧不能产生新合法结果。匿名历史与 coherence 共用 reset/generation 隔离。
startup/reconnect transaction 现复用 reader；先观察 B，再按 `0x02`、`0x20` 顺序单在途
读回，每窗口完整观察 B，最多 4B 等待，在读空且完整帧边界才发送/提交。意外/重复帧、
坏校验、截断、超时、短写/写失败或代次失效均闭锁，不在同一 transport 重试；成功后额外
`0x5F` 前缀也撤销结果。两类成功窗口的首 word 形状不相交，排除它们的跨窗口互用。
仅此不能证明匿名响应的来源；厂家 continuous-stream / KEY / request association / timeout
仍 **NOT FULLY SPECIFIED**。B 之外旧连接响应或外部同形响应可能无法识别，不能声称检出
所有假设违背；没有关联前提时必须保持关闭或 `incomplete`。

纯函数 `check_imu_configuration()` 只检查已独立确认地址的离线数据：RSW GYRO/ANGLE 位、
GYRORANGE 2000 deg/s 与 actual host/module BAUD 一致性。§7.9.6 的全部 provenance 寄存器
保留 raw word 或缺失项；未冻结值偏离 default 和合法非零 offset 不失败。runtime 只有在
显式有界主机策略完成两窗口后才条件性解释地址并复用规则检查，不能仅凭 pending request
补地址。required values PASS 与 observation complete 分开表示，二者均不代表厂家关联
证明或 ALG-007 READY；两个最小窗口以外的 provenance 保持 incomplete。

默认 **DO NOT AUTO-WRITE / DO NOT SAVE / DO NOT RESTORE FACTORY DEFAULTS**；校准状态受保护，
非零 offset 不自动视为 failure 或清零。module BAUD 必须等于 effective configured host baud，
不是永久固定 9600；没有 baud scan/auto-detection/rewrite。参数
`config_readback_enabled=false` 与 `config_readback_response_bound_sec=0.0` 默认不发任何请求；
开启但不给正有限 B 也不写串口。B 是明确的主机假设，仓库无硬件验证过的推荐值，fake 的
1 秒不是设备依据。configure 读取参数；无新增话题/服务/线程。详见
[IMU 包读回策略](../src/imu_cybergear_ros2/README.md#可选启动重连读回主机条件性关联)。

`configuration_state()` 为不可变诊断；`host-associated-checked` 才表示条件性配置前置条件
通过。随后重新接受新 GYRO→ANGLE 才记录 `post_check_pair`，验证前 pending GYRO 不进入该
结果；legacy coherence/ROS 发布继续。reset/断线/重连/停用/再激活/清理/关闭清除旧结果、
pending 与 pair，旧 read 字节通过 generation 拒绝。快照是历史，消费者必须核对当前
generation/status。没有接入 Flight，也不保证 finite component/pair age。

### 软件验证与剩余前置条件

- 020A.4 定向 parser + fake serial/lifecycle 测试：**PASS，86 项**；覆盖 normal pair、ANGLE alone/
  duplicate、latest pending、坏校验、跨 read/多帧、独立组件时间、旧缓存/残帧/迟到 read 的
  reset/reconnect 隔离、deactivate/reactivate、cleanup/reconfigure、shutdown 与 legacy 发布。
- 020A.4 完整 `./scripts/ci_software.sh`：**PASS**；五包构建、分包测试（IMU/电机 471、fan 159、
  Flight/interfaces 2022）与五包完整测试通过，`colcon test-result` 汇总 **2683 tests，
  0 errors / 0 failures / 0 skipped**。ALG-001～006 回归通过，未执行新的正式资格验证。
- 020A.4 `git diff --check`、CI safety checker：**PASS**；三份更新 Markdown 文档的本地链接与
  锚点扫描：**PASS，58 项**。软件测试/构建不构成真实串口或执行器验证。
- 历史 020A.5 离线子集定向协议/coherence/匿名应答与配置测试：**PASS，140 项**；其中新增 54 项，
  覆盖 READADDR 编码、四 word 解码、坏校验/残帧/拆包、普通帧交错、匿名重复/无请求帧、
  reset/旧 read/reconnect/deactivate 隔离、默认零新增串口写入、三项冻结检查、配置缺失与
  非默认 provenance/非零 offset。纯函数成功数据的地址由 fixture 独立指定，不能当作多
  窗口自动读回事务成功。完整 startup/reconnect validation、单在途/超时/迟到关联事务和
  验证后的新 pair gate 测试**未执行**，原因：对应事务未实现，缺少关联依据。
- 历史 020A.5 离线子集完整 `./scripts/ci_software.sh`：**PASS**；五包构建、分包测试（IMU/电机 525、
  fan 159、Flight/interfaces 2022）和五包完整测试通过；`colcon test-result` 汇总
  **2737 tests，0 errors / 0 failures / 0 skipped**。ALG-001～006 普通回归通过，未执行
  新的正式资格验证或真实配置读回。
- 020A.5 `git diff --check`、CI safety checker：**PASS**；三份更新 Markdown 的本地
  链接与锚点扫描：**PASS，59 项**。
- 本轮 runtime 定向协议/parser + fake serial/lifecycle 测试：**PASS，199 项**，其中本轮
  新增 59 项。覆盖默认零写入/缺少有限 B 的闭锁、初始隔离、两窗口完整观察、逐字节拆包、
  legacy 发布交错、跨窗口迟到/重复/意外帧、坏校验/截断/超时、并发单在途与代次错配、
  reset 时旧 read 返回、disconnect/reconnect、ROS 参数启用、deactivate/reactivate、
  cleanup/reconfigure/shutdown、验证后新 pair gate，以及 mismatch 不切断 base。
- 本轮完整 `./scripts/ci_software.sh`：**PASS**；五包构建、工具测试 26 项、分包测试
  （IMU/电机 584、fan 159、Flight/interfaces 2022）及五包完整测试通过；
  `colcon test-result` 汇总 **2796 tests，0 errors / 0 failures / 0 skipped**。
  ALG-001～006 普通回归通过，未执行新的正式资格验证。
- 本轮 `git diff --check`、CI safety checker：**PASS**；三份更新 Markdown 的本地链接与
  锚点扫描：**PASS，60 项**。真实串口、READADDR、B 适用性及执行器验证均**未执行**，
  原因：本任务只授权软件实现与 fake 测试，硬件启用须另行授权。
- 本轮定向命令（先 `source /opt/ros/jazzy/setup.bash`）：

  ```bash
  PYTHONPATH=src/imu_cybergear_ros2${PYTHONPATH:+:$PYTHONPATH} python3 -m pytest \
    src/imu_cybergear_ros2/test/test_imu_protocol.py \
    src/imu_cybergear_ros2/test/test_imu_driver_coherence.py \
    src/imu_cybergear_ros2/test/test_imu_register_readback.py \
    src/imu_cybergear_ros2/test/test_imu_config_runtime.py -q
  ```

- **Configuration prerequisite**：默认关闭的条件性读回、validation/generation 和验证后
  新 pair gate 已实现；严格厂家关联及实际硬件适用性仍 **NOT PROVEN / NOT VERIFIED**。
- **Timing prerequisite**：必需的 finite component/pair temporal-age rule 尚未冻结；base freshness
  `0.2 s` 不能自动作为 pair-age threshold，Level-2 不保证 bounded temporal freshness。
- **Numerical blocker**：deterministic combined uncertainty/error budget、relevant rate magnitude、
  exact near-singularity rule、`theta_max`、`K_max` 仍 **NOT FROZEN**；现有
  `EULER_GIMBAL_LOCK_COS_TOLERANCE=1e-9` 只是 mathematical/implementation guard。
- 非零 executable `FlightCommand` projection、物理 motor/fan authority 与 allocation 仍为独立
  **NOT DEFINED / NOT VERIFIED** 前置条件；本轮未实现 020B、ALG-007 Candidate 或 roll-rate API。

### Hardware / evidence boundary

- Hardware access：**NO**；authorization：**NONE**；hardware validation / Level F：
  **NOT AUTHORIZED / NOT EXECUTED**。
- Real actuator safety、hardware dynamic closed-loop recovery 与 real Balance Recovery：
  **NOT VERIFIED**。
- 本轮所有帧/transport/lifecycle 验证只使用软件字节、fake serial 与进程内 ROS；未读写真实 IMU，
  未访问 CAN/GPIO/PWM、电机或风扇，未修改配置、硬件映射、Flight takeover 或硬件 launch。
