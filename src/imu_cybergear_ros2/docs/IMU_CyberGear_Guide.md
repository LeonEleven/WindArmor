# IMU 与 CyberGear 早期使用指南（历史）

> **LEGACY / HISTORICAL。** 本文件保留早期文档文件名和引用兼容性，不再是当前
> 安装、启动、硬件操作或安全说明。历史命令不构成新的实机授权。

该指南最初汇总 Hiwonder IMU、CyberGear 后端、键盘控制和 ROS 接口。随着统一
bringup、安全状态、结构化反馈、Flight ownership 和版本化验证记录建立，其中的
运行说明已并入下列当前来源：

- 整机安装、正常启动、MANUAL/AUTO、风扇和 E-stop：
  [仓库 README](../../../README.md)
- 本包节点、接口、状态、反馈和配置契约：
  [imu_cybergear_ros2 README](../README.md)
- CAN ID、方向、限位、GPIO 和接线：
  [硬件参考](../../../docs/HARDWARE_REFERENCE.md)
- Flight 消息、服务和 ownership：
  [Flight Control API](../../../docs/FLIGHT_CONTROL_API.md)

如历史分支或外部笔记仍链接本文件，应把上述当前来源作为实际依据，不要从旧版本
复制启动命令或硬件参数。
