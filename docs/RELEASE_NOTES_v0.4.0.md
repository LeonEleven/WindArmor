# WindArmor v0.4.0

> **发布状态：RELEASED / v0.4.0。** 本文是 v0.4.0 正式发布快照的版本化说明。

## 版本定位

v0.4.0 引入正式的 Flight control API、Runtime 和控制权（authority）体系，使纯算法、
ROS 状态聚合、控制权交接与底层执行器安全边界形成可验证的分层契约。同时，v0.3.2 的
MANUAL、HOME 和 LEGACY AUTO 正常操作路径继续保留。

## 相比 v0.3.2 的主要变化

### 1. Flight algorithm API

- 新增纯 Python `FlightController` 契约，通过 `reset()` 和 `update(state, dt)` 隔离算法逻辑；
- 新增不可变 `FlightState`、`FlightCommand` 及其嵌套状态，明确单位、存在性、有效性、
  新鲜度和完整电机键集合；
- 安全停止使用不含执行器载荷的 `FlightCommand.safe_stop()`，算法不直接访问 ROS、CAN、
  串口、GPIO 或 PWM；
- controller factory 使用 `module.path:function` 契约加载算法，失败时显式闭锁，不静默回退；
- 新人入口见[算法开发者指南](ALGORITHM_DEVELOPER_GUIDE.md)，完整字段契约见
  [Flight Control API](FLIGHT_CONTROL_API.md)。

### 2. Flight Runtime 与 authority

- 控制权接管需要显式 prepare，默认 `flight_takeover_enabled=false`；
- `(authority_epoch, generation)` 隔离 Runtime 进程会话和每次接管尝试，旧 epoch、旧
  generation 和旧命令不能在重启后恢复；
- 电机和风扇使用两阶段 reserve/commit ownership 协议，并在两侧权威回读匹配后执行单独的
  原子提交；
- `FlightCommandEnvelope` 携带当前 token、严格递增的命令序号、原子截止点后的状态序号和
  完整载荷；
- 任一必要输入、安全回读、ownership、租约、算法或通信条件失败时先在 Runtime 本地关闭
  可执行命令路径，再尽力撤销；不会自动恢复控制权、旧 owner 或旧目标。

### 3. 结构化 ROS 接口

- 新增 `windarmor_interfaces` 包，集中定义 Flight Runtime、执行器 ownership、安全回读和
  结构化反馈契约；
- Flight 状态与命令接口包括 `FlightAuthorityStatus`、`FlightRuntimeStatus`、
  `FlightCommandPreview` 和 `FlightCommandEnvelope`；
- 执行器状态接口包括 `OwnershipState`、`MotorFeedback`、`MotorFeedbackArray`、
  `MotorSafetyState` 和 `FanSafetyState`；
- 两阶段交接服务包括 `PrepareFlightOwnership`、`CommitFlightOwnership` 和
  `RevokeFlightOwnership`；
- ROS 消息不能表达 Python `None` 的字段均使用显式存在性标志，避免用零值冒充未知状态。

### 4. 电机与风扇集成

- 电机和风扇管理器新增 Flight ownership 路径，但继续各自校验 token、命令序号、载荷和
  本地安全状态；
- handoff lease 与 ACTIVE command lease 独立计时，重复帧、错误 token、safe-stop 或非法载荷
  不刷新命令租约；
- 电机软限位、运动步长/速率、反馈故障、transport 故障、风扇 PWM 范围和斜率限制继续由
  底层管理器执行最终否决；
- 既有电机 MANUAL、HOME、LEGACY AUTO 和风扇 MANUAL/LEGACY AUTO 路径继续保留，失权后
  不会自动重新取得旧控制归属。

### 5. Runtime lifecycle

- Runtime 对 `SIGINT`/`SIGTERM` 使用受控关闭路径，在 rollback 和节点销毁期间保持 ROS
  context 有效，并区分正常信号退出与普通执行错误；
- Runtime 重启必须建立新的进程 epoch 和完整的新交接，不能继承旧 token、命令序号或目标；
- lifecycle 自动激活只绑定启动阶段的预期转换，避免运行期 deactivate 后被 launch 自动
  重新激活；
- transport 重连只恢复传输和读取器，不初始化电机，也不恢复控制状态或旧命令。

### 6. E-STOP 与安全闭环

- 全局 `/e_stop` 同时进入电机和风扇的失效后安全闭锁路径，并高于普通控制状态更新；
- Runtime、执行器 manager、watchdog 和 command lease 构成分层的 fail-close 边界；
- E-STOP、ERROR、输入过期、ownership 丢失或 Runtime 停止后，旧命令不能重新取得控制权；
- 恢复仍要求显式的安全检查和重新授权，不存在输入恢复后的自动运动恢复。

### 7. 算法开发体验

- [算法开发者指南](ALGORITHM_DEVELOPER_GUIDE.md) 提供从最小控制器、fake 状态、单元测试到
  受限验证边界的分级路径；
- `example_algorithm_controller` 提供非默认、无硬件访问的教学控制器；
- `synthetic_dry_run` 提供不连接 ROS graph、不创建控制权且不访问硬件的确定性预览；
- 软件优先路径明确区分纯算法测试、观测模式 Runtime 和需要逐场景授权的真实硬件验证。

### 8. 文档体系

- [Flight Control API](FLIGHT_CONTROL_API.md) 作为算法字段、单位和校验契约；
- [Flight Control Architecture](FLIGHT_CONTROL_ARCHITECTURE.md) 作为 Runtime、authority、
  ownership、lease、回滚与安全不变量依据；
- [Hardware Reference](HARDWARE_REFERENCE.md) 固化硬件映射、坐标、接线和测量边界；
- [v0.4.0 硬件与功能验证记录](verification/v0.4.0/HARDWARE_VERIFICATION_RECORD.md) 固化
  Gate B/C/D 的最终判定和证据限制；
- README、算法指南、API、架构和硬件参考已整理为中文优先的长期新人文档。

## 兼容性与升级注意事项

- workspace 的五个 ROS 包版本统一为 `0.4.0`：`imu_cybergear_ros2`、
  `windarmor_fan_controller`、`windarmor_bringup`、`windarmor_interfaces` 和
  `windarmor_flight_control`；
- v0.3.2 的电机 MANUAL、HOME、LEGACY AUTO 和风扇 MANUAL/LEGACY AUTO 操作路径继续保留；
- Flight takeover 默认仍为关闭状态；启用前必须满足 Runtime 预检、两阶段 ownership 和
  底层安全条件；
- 新算法必须使用 `FlightController`、`FlightState`、`FlightCommand` 和 controller factory
  契约，不得直接导入硬件驱动或绕过 Runtime；
- 版本升级不会授权真实硬件执行。任何 CAN、GPIO、PWM、串口、电机或风扇场景仍须遵守
  `AGENTS.md` 的逐场景明确授权要求；
- v0.3.2 的历史内容和接口边界见
  [v0.3.2 发布说明](RELEASE_NOTES_v0.3.2.md)。

## 验证

版本化硬件与功能结论见
[v0.4.0 硬件与功能验证记录](verification/v0.4.0/HARDWARE_VERIFICATION_RECORD.md)：

- Gate B：**COMPLETE**；
- Gate C：**COMPLETE**；
- Gate D：**FUNCTIONAL REGRESSION PASS / COMPLETE**。

发布准备基线的最新完整纯软件 CI 结果为：

```text
939 tests, 0 errors, 0 failures, 0 skipped
```

release-prep commit `d08b1f7` 对应的 GitHub Hosted WindArmor Software CI 已成功；本说明
不写死 GitHub Actions run number。软件 CI、fake、mock 和 DRY_RUN 不构成真实 CAN、串口、
GPIO、电调或机械验证。

## 已知限制

- CyberGear 0x02 反馈没有独立验证的数值 `current_a`，不得从力矩推导电流；
- 当前硬件验证是受限控制和失效后安全闭锁验证，不是完整飞行动力学、性能、RPM、推力或
  全包线标定；
- RIGHT ESC 在 B2 和 C1–C4 Flight 场景中保持断电，RIGHT 侧只有命令/PWM 停止证据，
  没有带电物理旋转验证；
- C4b 在 E-stop 前没有观察到明显风扇旋转；该场景的正面证据是控制路径、记录器 PWM 和
  停止结果；
- Gate D 的部分条目依赖历史操作者验证/用户确认与当前安全路径交叉验证，不是新的连续
  记录器实机会话；
- `flight_takeover_enabled=false` 仍是生产默认值；
- 本版本不授权新的硬件场景，任何真实硬件操作仍必须单独取得明确授权。

上述限制以[硬件参考](HARDWARE_REFERENCE.md)和
[v0.4.0 验证记录](verification/v0.4.0/HARDWARE_VERIFICATION_RECORD.md)为准。

## 发布状态

- **RELEASED / v0.4.0**；
- 当前正式稳定版本为 v0.4.0；
- v0.3.2 保留为上一稳定版本的历史记录。
