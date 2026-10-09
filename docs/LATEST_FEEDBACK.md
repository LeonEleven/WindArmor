# WindArmor 当前开发交接

> **INTERNAL DEVELOPMENT HANDOFF — MUTABLE。** 当前 branch、push、PR、CI 与 merge 等实时
> 生命周期状态以 Git / GitHub 为准；本文件仅保留下一工作单元需要的稳定工程状态。

## 当前工作单元

- 日期：2026-10-09；Task：`v0.5.0-020A.5 — IMU Configuration Readback + Validation`。
- task-start baseline：`develop@35da9ec100d64624b03ce6b1d0da585dffcad871`。
- 当前交付为离线解析/规则检查的受限实现；完整 startup/reconnect transaction **BLOCKED**。
  `0x5F` 无地址/ID，单在途不能排除旧请求延迟重复应答；后续自动读回仍需补齐关联依据。
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

## Level-2 实现与接口

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
消费，ALG-001～006 base validity、默认控制行为、公开 ROS 话题/服务/参数保持不变。

## 厂家与配置依据

本工作单元直接复核 git-ignored `reference/document/IMU/` 的《10轴IMU模块通讯协议》与
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
完整 transaction、configuration validation generation 与验证后的新 pair gate
**NOT IMPLEMENTED**；continuous-stream interleave、KEY、request association、timeout 等细节
仍 **NOT FULLY SPECIFIED / NOT FROZEN**。尤其连续多窗口读取不能以单在途冒充关联保证，
上一连接 validation 不能跨代次继承。

纯函数 `check_imu_configuration()` 只检查已独立确认地址的离线数据：RSW GYRO/ANGLE 位、
GYRORANGE 2000 deg/s 与 actual host/module BAUD 一致性。§7.9.6 的全部 provenance 寄存器
保留 raw word 或缺失项；未冻结值偏离 default 和合法非零 offset 不失败。required values
PASS 与 observation complete 分开表示，二者均不代表 runtime configuration verified 或
ALG-007 READY。不能将匿名应答按当前 pending request 补地址后直接传入该函数。

默认 **DO NOT AUTO-WRITE / DO NOT SAVE / DO NOT RESTORE FACTORY DEFAULTS**；校准状态受保护，
非零 offset 不自动视为 failure 或清零。module BAUD 必须等于 effective configured host baud，
不是永久固定 9600；本轮没有 baud scan/auto-detection/rewrite，没有发送任何串口请求或
配置写入，也没有新增 opt-in 参数；driver 自动读回路径尚未接入。

## 软件验证与剩余前置条件

- 020A.4 定向 parser + fake serial/lifecycle 测试：**PASS，86 项**；覆盖 normal pair、ANGLE alone/
  duplicate、latest pending、坏校验、跨 read/多帧、独立组件时间、旧缓存/残帧/迟到 read 的
  reset/reconnect 隔离、deactivate/reactivate、cleanup/reconfigure、shutdown 与 legacy 发布。
- 020A.4 完整 `./scripts/ci_software.sh`：**PASS**；五包构建、分包测试（IMU/电机 471、fan 159、
  Flight/interfaces 2022）与五包完整测试通过，`colcon test-result` 汇总 **2683 tests，
  0 errors / 0 failures / 0 skipped**。ALG-001～006 回归通过，未执行新的正式资格验证。
- 020A.4 `git diff --check`、CI safety checker：**PASS**；三份更新 Markdown 文档的本地链接与
  锚点扫描：**PASS，58 项**。软件测试/构建不构成真实串口或执行器验证。
- 020A.5 定向协议/coherence/匿名应答与离线配置测试：**PASS，140 项**；其中新增 54 项，
  覆盖 READADDR 编码、四 word 解码、坏校验/残帧/拆包、普通帧交错、匿名重复/无请求帧、
  reset/旧 read/reconnect/deactivate 隔离、默认零新增串口写入、三项冻结检查、配置缺失与
  非默认 provenance/非零 offset。纯函数成功数据的地址由 fixture 独立指定，不能当作多
  窗口自动读回事务成功。完整 startup/reconnect validation、单在途/超时/迟到关联事务和
  验证后的新 pair gate 测试**未执行**，原因：对应事务未实现，缺少关联依据。
- 020A.5 完整 `./scripts/ci_software.sh`：**PASS**；五包构建、分包测试（IMU/电机 525、
  fan 159、Flight/interfaces 2022）和五包完整测试通过；`colcon test-result` 汇总
  **2737 tests，0 errors / 0 failures / 0 skipped**。ALG-001～006 普通回归通过，未执行
  新的正式资格验证或真实配置读回。
- 020A.5 `git diff --check`、CI safety checker：**PASS**；三份更新 Markdown 的本地
  链接与锚点扫描：**PASS，59 项**。
- 本轮定向命令（先 `source /opt/ros/jazzy/setup.bash`）：

  ```bash
  PYTHONPATH=src/imu_cybergear_ros2${PYTHONPATH:+:$PYTHONPATH} python3 -m pytest \
    src/imu_cybergear_ros2/test/test_imu_protocol.py \
    src/imu_cybergear_ros2/test/test_imu_driver_coherence.py \
    src/imu_cybergear_ros2/test/test_imu_register_readback.py -q
  ```

- **Configuration prerequisite**：离线规则检查已有，readback transaction、runtime
  validation/generation 尚未实现；整项 020A.5 尚未完成。
- **Timing prerequisite**：必需的 finite component/pair temporal-age rule 尚未冻结；base freshness
  `0.2 s` 不能自动作为 pair-age threshold，Level-2 不保证 bounded temporal freshness。
- **Numerical blocker**：deterministic combined uncertainty/error budget、relevant rate magnitude、
  exact near-singularity rule、`theta_max`、`K_max` 仍 **NOT FROZEN**；现有
  `EULER_GIMBAL_LOCK_COS_TOLERANCE=1e-9` 只是 mathematical/implementation guard。
- 非零 executable `FlightCommand` projection、物理 motor/fan authority 与 allocation 仍为独立
  **NOT DEFINED / NOT VERIFIED** 前置条件；本轮未实现 020B、ALG-007 Candidate 或 roll-rate API。

## Hardware / evidence boundary

- Hardware access：**NO**；authorization：**NONE**；hardware validation / Level F：
  **NOT AUTHORIZED / NOT EXECUTED**。
- Real actuator safety、hardware dynamic closed-loop recovery 与 real Balance Recovery：
  **NOT VERIFIED**。
- 本轮所有帧/transport/lifecycle 验证只使用软件字节、fake serial 与进程内 ROS；未读写真实 IMU，
  未访问 CAN/GPIO/PWM、电机或风扇，未修改配置、硬件映射、Flight takeover 或硬件 launch。
