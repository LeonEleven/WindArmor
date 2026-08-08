# 最新反馈：v0.3.2 最终发布文档收口

> 本文件只保留最近一次反馈。
>
> 日期：2026-08-08

## 1. 执行结论

- `v0.3.2` RC 固定提交为
  `5bc8ecc75708067d34102dfb33996970ed0e14a4`（“发布：冻结 v0.3.2
  候选版本”）。
- 该 RC 的 GitHub Hosted `WindArmor Software CI` run `31162441004` 为
  `completed/success`，日志 artifact
  `windarmor-software-ci-logs-31162441004` 正常生成。
- 用户最终整机正常功能回归：**PASS**。
- 用户未报告新的异常或明显功能回归。
- 本任务只收口发布文档，不修改产品代码、控制参数、package 版本、测试逻辑
  或 CI workflow。
- 用户明确决定不创建 GitHub Release。
- 本任务不创建、移动、删除或推送任何 tag；`v0.3.2` annotated tag 仍需用户
  下一阶段单独明确授权。

## 2. 用户最终 RC 整机回归

用户报告：

```text
测试结果正常
```

按用户最终 RC 正常功能回归范围，可记录为：

- 系统正常启动；
- IMU 零点；
- 机械零点；
- MANUAL；
- HOME；
- 小幅 AUTO；
- 风扇 MANUAL；
- 风扇 AUTO；
- 普通急停；
- 正常急停恢复；
- 正常退出。

用户没有提供逐项测量值，因此本文不补写角度、速度、力矩、PWM、时长或其他
具体数据。准确结论是：

```text
用户报告最终 RC 整机正常功能回归通过，未报告新的异常或明显功能回归。
```

该结果是正常功能回归，不是真实危险故障注入认证。

## 3. 仍未完成的真实硬件故障注入

以下项目没有完成真实硬件故障注入或认证：

- USB-CAN 拔线；
- CAN 断线；
- 真实欠压；
- 真实过流；
- 真实 90 °C 过温；
- 编码器故障；
- feedback timeout；
- `stop_motor` 故障；
- 机械卡死。

现有 pure logic、fake driver、fake feedback、fake clock 和 fake transport 覆盖是
纯软件故障注入，不是真实硬件认证。上述项目不因本次正常功能回归 PASS 而被
视为已完成。

## 4. RC 软件验证基线

### 本地纯软件验证

RC 阶段已完成并通过：

- release contract 专项：`5 passed`；
- CI infrastructure：`16 passed`；
- 电机 package pytest：`359 passed`；
- 风扇关键回归：`98 passed`；
- 三 package 隔离 build：`3 packages finished`；
- 三 package 完整 colcon：
  `480 tests, 0 errors, 0 failures, 0 skipped`；
- CI safety checker、Python compile 与 whitespace 检查：通过。

这些结果是纯软件验证，不表述为实机验证。

### RC Hosted CI

- Workflow：`WindArmor Software CI`；
- run ID：`31162441004`；
- head SHA：`5bc8ecc75708067d34102dfb33996970ed0e14a4`；
- 状态：`completed/success`；
- artifact：`windarmor-software-ci-logs-31162441004`；
- artifact ID：`8987708589`；
- artifact 大小：`97318` bytes；
- 复核时状态：未过期。

最终软件验证仍以本发布文档收口提交 push 后触发的新 Hosted CI run 为准。只有
该 run `completed/success` 且日志 artifact 正常生成，本阶段才算完成；最终
commit SHA、run ID 与 artifact 状态在任务完成报告中记录。

## 5. Package 版本

三个 package 的 `package.xml` 与 `setup.py` 均保持：

| Package | package.xml | setup.py |
|---|---:|---:|
| `imu_cybergear_ros2` | `0.3.2` | `0.3.2` |
| `windarmor_fan_controller` | `0.3.2` | `0.3.2` |
| `windarmor_bringup` | `0.3.2` | `0.3.2` |

本任务只读确认版本元数据，没有修改版本号。

## 6. 本任务文档范围

发布状态收口文件：

- `README.md`；
- `docs/RELEASE_NOTES_v0.3.2.md`；
- `docs/LATEST_FEEDBACK.md`；
- `docs/V0.3.2_RC_HARDWARE_CHECKLIST.md`；
- `src/imu_cybergear_ros2/README.md`；
- `src/imu_cybergear_ros2/docs/项目总览与功能清单.md`。

后三处附加修改只用于清除即将失真的“等待用户执行”或“发布候选”当前状态，
不改变产品行为、接口或参数。

本任务没有修改：

- `src/**` 产品运行时代码；
- 电机或风扇控制参数；
- package 版本；
- CI workflow 或统一 CI 入口；
- 测试逻辑；
- `/e_stop`、看门狗、软限位、停用或安全退出机制。

## 7. Git 与发布边界

- 任务开始分支：`master`；
- 任务开始 HEAD/upstream：
  `5bc8ecc75708067d34102dfb33996970ed0e14a4`；
- 任务开始 ahead/behind：`0/0`；
- `v0.3.0` 指向的 commit 保持
  `c3b3c3989674c2c1c902e940953da87fd5812db5`；
- `v0.3.1` 指向的 commit 保持
  `5d7bd0fbf0acac3be4f2354a616d109928d5091d`；
- 本任务开始时本地和远端均不存在 `v0.3.2` tag。

`docs/NEXT_COMMAND.md` 是用户已有工作区修改。本任务不得修改、暂存、覆盖、
还原或提交该文件；任务开始时其 SHA-256 为：

```text
b1d5e5c85928728c43b67da34b8d950ccdc0c972bec448368ed23e3735f6acc9
```

用户明确决定不创建 GitHub Release，因此本任务和后续 tag 阶段都不应创建
draft release、正式 release、release asset 或自动生成的 GitHub Release。

## 8. 硬件安全声明

Codex 本任务不执行：

- `ros2 run`、`ros2 launch`、`ros2 topic` 或 `ros2 service`；
- `sudo` 或 `scripts/setup_can.sh`；
- IMU、`/dev/imu_usb`、真实串口、CAN、`can10` 或真实 SDO 访问；
- CyberGear 初始化、使能、停止或运动命令；
- GPIO12/GPIO13、PWM、电调或风扇操作；
- 带电测试或任何真实硬件测试。

用户已经提供最终 RC 正常功能回归结果，Codex 不重复运行硬件验证。

## 9. 下一阶段

本发布文档收口提交 push 后，必须等待对应的新 GitHub Hosted CI
`completed/success` 并确认日志 artifact 正常。完成后，软件验证与用户最终 RC
正常功能回归的前置条件即满足。

下一步只剩用户单独明确授权创建 annotated `v0.3.2` tag，并将该 tag 精确指向
最终 release commit。没有这项单独授权，不得创建或推送 tag。
