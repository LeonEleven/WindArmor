# 最新反馈：GitHub Actions 无硬件 CI 与纯软件回归基线

> 本文件只保留最近一次反馈。
>
> 日期：2026-08-07

## 1. 执行结论

- 已新增 GitHub Actions 无硬件软件 CI、统一的本地/Hosted CI 脚本、提交范围
  whitespace 检查和 CI 自身硬件安全检查。
- workflow 使用 GitHub 托管 `ubuntu-24.04` 和 ROS 2 Jazzy，支持 `master`
  push、面向 `master` 的 pull request 以及 `workflow_dispatch`。
- workflow 只有 `contents: read` 权限，不使用 secret、自托管 runner、设备映射、
  privileged container 或写权限。
- 本地等价 CI 最终完成 3 包构建；电机包 `306 passed`；风扇关键回归
  `98 passed`；三包完整 `422 tests, 0 errors, 0 failures, 0 skipped`。
- 新增 16 项 CI infrastructure 测试，覆盖安全 checker、统一脚本和 workflow
  contract。
- 未修改任何产品控制算法、硬件参数、安全阈值、ROS 公共接口或硬件映射。
- Codex 未启动或 spin 任何硬件节点，未访问 IMU、串口、CAN、CyberGear、GPIO
  或 PWM。
- GitHub Hosted CI 尚未触发，不能声称远端 CI green。

## 2. 开始前 Git 基线

- 分支：`master`。
- HEAD：`fae3a08fc1010b0c5b72314470e5359b087a4752`。
- upstream：`origin/master`，同为
  `fae3a08fc1010b0c5b72314470e5359b087a4752`。
- 本地领先/落后：`0/0`。
- 最近提交：`fae3a08 加固：完善电机反馈安全并修正状态帧端序`。
- `v0.3.0` commit：`c3b3c3989674c2c1c902e940953da87fd5812db5`。
- `v0.3.1` commit：`5d7bd0fbf0acac3be4f2354a616d109928d5091d`。
- HEAD 位于 `v0.3.1` 后 4 个提交；开始时 describe 为
  `v0.3.1-4-gfae3a08-dirty`。
- 任务开始前唯一工作区修改为 `M docs/NEXT_COMMAND.md`，无未跟踪文件；该文件
  是用户任务说明，本任务未修改、暂存、覆盖或还原。
- 任务开始时不存在 `.github/workflows`。

## 3. 修改文件

### 3.1 任务前已有修改

- `docs/NEXT_COMMAND.md`：用户任务说明，原样保留。

### 3.2 本任务新增或更新

- `.github/workflows/ci.yml`：新增 GitHub Actions 软件 CI。
- `scripts/ci_software.sh`：新增可分阶段运行的统一纯软件 CI 入口。
- `scripts/check_ci_safety.py`：新增 workflow/CI 脚本硬件能力拒绝检查。
- `scripts/check_git_whitespace.py`：新增 GitHub event commit range 和本地工作区
  whitespace 检查。
- `src/windarmor_bringup/test/test_ci_infrastructure.py`：新增 16 项 CI 基础设施
  契约测试。
- `src/imu_cybergear_ros2/package.xml`：补充既有测试实际需要的
  `python3-pytest` test dependency。
- `README.md`：修正反馈健康功能仍为工作区修改的过时描述，新增纯软件 CI 说明。
- `AGENTS.md`：最小增加 GitHub Actions 硬件安全边界，未削弱既有规则。
- `docs/LATEST_FEEDBACK.md`：按本次结果完整覆盖。

## 4. CI 架构

- 单 job workflow 在 GitHub 托管 `ubuntu-24.04` 上运行，明确超时 45 分钟。
- `ros-tooling/setup-ros` 安装 ROS 2 Jazzy、colcon 和 rosdep 基础环境。
- `rosdep install --from-paths src --ignore-src --rosdistro jazzy -r -y` 根据三包
  manifest 安装声明依赖；未使用全局 pip workaround。
- workflow 和本地开发者均调用 `scripts/ci_software.sh`。workflow 按阶段调用以
  形成可诊断 step，本地无参数调用依次完成全部阶段。
- build/install/log/ROS log 使用隔离输出根目录；本地默认使用 `mktemp`，不读取、
  覆盖或依赖仓库已有 `build/`、`install/`、`log/`。
- 测试日志无论成功或失败均上传，范围只包括 colcon log、ROS log 和各包
  `Testing` 目录，保留 10 天，不上传整个 build/install。

## 5. GitHub Actions 触发规则

- `push`：仅 `master`。
- `pull_request`：目标分支仅 `master`，未使用 `pull_request_target`。
- `workflow_dispatch`：允许人工触发。
- 未增加 `schedule` 或 `repository_dispatch`。
- concurrency 使用 workflow 与 PR number/ref 组合；同一 PR 或分支的新运行取消
  旧运行，PR 与 master 不会共用同一 key。

## 6. 权限与供应链

- 顶层权限只有 `contents: read`；没有 contents/packages/actions/PR/id-token 写权限。
- 未配置、读取或创建 repository/environment secret、PAT、deploy key 或 GitHub App
  credential；checkout 设置 `persist-credentials: false`。
- `actions/checkout` v6.1.0 固定为
  `d23441a48e516b6c34aea4fa41551a30e30af803`。
- `ros-tooling/setup-ros` 0.7.18 固定为
  `77bcad67a6cb15f6192d61464d99bbab658e4ca9`。
- `actions/upload-artifact` v7.0.1 固定为
  `043fb46d1a93c77aae656e7c1c64a875d1fc6a0a`。
- 三个 `uses:` 均来自 GitHub Actions 官方组织或 ROS Tooling Working Group，且
  使用完整不可变 commit SHA；未使用 `@main`、`@master` 或浮动 major tag。
- CI 不 commit、push、tag、release、修改 PR 或自动改代码。

## 7. CI 硬件安全边界

- 使用 GitHub hosted Ubuntu runner，不使用 Raspberry Pi、机器人或开发电脑作为
  runner。
- workflow 不使用 privileged、host network、device mount、`/dev` passthrough
  或 Docker device option。
- 统一脚本只运行 py_compile、colcon build、直接 pytest 和 colcon test；没有
  `ros2 run/launch/topic/service`，不会启动节点或 lifecycle spin。
- 测试只使用 pure logic、fake driver、fake feedback、fake clock、伪终端、
  monkeypatch 和未连接 backend 对象。
- 不访问 `/dev/imu_usb` 或任何真实串口，不创建 SocketCAN，不配置或访问
  `can10`，不连接/初始化 CyberGear，不写 SDO。
- 不导入或构造真实底层风扇控制器，不访问 GPIO12/GPIO13，不创建 Servo，不解锁
  电调，不输出 PWM。
- CI safety checker 会在构建和测试前拒绝上述高风险命令或 runner/container 配置。

## 8. 统一 CI 脚本

`scripts/ci_software.sh` 使用 `set -euo pipefail`，从自身路径解析仓库根目录，并
按以下顺序执行：

1. CI safety check；
2. commit/local whitespace check；
3. Python py_compile；
4. 三包隔离 colcon build；
5. 电机包全量 pytest；
6. 风扇四文件关键安全回归；
7. 三包完整 colcon test；
8. `colcon test-result --verbose`。

脚本支持 workflow 按上述 stage 名单独调用。任一命令失败由 `set -e` 传播为非零；
不存在 `|| true`。ROS 官方 setup 脚本 source 的短暂区间关闭 nounset，source 后
立即恢复 `set -u`，避免 `AMENT_TRACE_SETUP_FILES` 未定义导致环境加载失败。

## 9. Whitespace 检查策略

- pull request：检查 `base...head` 整个 PR range。
- push：正常分支更新检查 `before..head`；新分支零 before 时至少对当前 HEAD 使用
  `git diff-tree --check --root -r`。
- workflow_dispatch：对当前 HEAD 使用 `git diff-tree --check --root -r`。
- workflow 使用 `fetch-depth: 0`，确保需要的提交范围可用。
- 本地无 event 环境时检查当前 HEAD、暂存区和未暂存区；只在本地未暂存检查中
  排除禁止修改的 `docs/NEXT_COMMAND.md`。GitHub checkout 的 commit range 检查
  不使用该排除 workaround。
- 没有使用干净 checkout 中无意义的普通无参数 `git diff --check`。

## 10. CI safety checker

- 检查范围为 `.github/workflows/*.yml|yaml` 和 `scripts/ci_software.sh`。
- 对 YAML 只提取实际 `run:` scalar/block，并单独检查 runs-on、container options
  和 device mapping；对 shell 忽略完整注释行，避免文档式禁令文字误报。
- 拒绝 ROS node execution、CAN setup、`can10`、IMU device、CAN link configuration、
  modprobe、GPIO write、privileged/device passthrough 和 self-hosted runner。
- 自身测试覆盖合法 workflow、`ros2 launch`、setup_can、can10 配置、`/dev`
  device mount、self-hosted、privileged 以及注释不误报。

## 11. 本地等价 CI 测试结果

- `bash -n scripts/ci_software.sh`：通过。
- checker/helper `py_compile`：通过。
- `python3 scripts/check_ci_safety.py`：通过。
- CI infrastructure targeted tests：`16 passed`。
- 本地 whitespace（排除用户 `NEXT_COMMAND`）：通过。
- 最终全工作区 `git diff --check`：通过；当前用户版 `NEXT_COMMAND` 没有触发
  whitespace error，但本地 helper 仍按任务保护要求不把它纳入本任务检查范围。
- `./scripts/ci_software.sh`：最终通过。
- Python compile：通过，覆盖两个产品 Python 包、三个 launch 目录和两个 CI helper。
- 三包 build：`3 packages finished`。
- 电机包全量：`306 passed`。
- 风扇关键回归：`98 passed`。
- 三包完整：`422 tests, 0 errors, 0 failures, 0 skipped`。
- 相对原 406 项完整基线新增 16 项 CI infrastructure 测试；产品既有测试未删除、
  skip、xfail 或降低断言。

首轮 checker 自测为 `12 passed, 4 failed`，暴露 YAML `- run:` 短写和 container
options 提取遗漏；修正 checker 后为 `16 passed`。统一脚本首轮在 build 前因 ROS
官方 setup 与 nounset 兼容问题退出，未开始构建或测试；限制 nounset 关闭范围后
最终整套通过。这两项均为新增 CI 基础设施问题，不是产品测试或硬件故障。

## 12. GitHub Hosted CI 状态

- 用户已在审查后明确授权创建中文 commit，但尚未授权 push，因此新 workflow
  尚未在 GitHub Hosted Actions 上触发。
- 当前只能确认 workflow 静态契约和本地等价 CI 通过，不能声称远端 CI green。

## 13. README 和 AGENTS 更新

- README 不再把已提交的反馈健康/端序修正描述为工作区修改，并概括 `v0.3.1`
  后四项已提交加固及用户正常功能实机复测边界。
- README 新增 runner、ROS 版本、触发条件、无硬件范围和本地统一入口，不把测试
  数量硬编码为永久保证。
- AGENTS 只新增 GitHub Actions 纯软件/hosted runner 安全边界；原硬件安全、
  带电授权门槛和 Git 权限限制均保留。

## 14. 保持不变的产品行为

- 未修改 MANUAL/AUTO/HOME 算法、推进速度、dt/step/tolerance、键盘算法或 AUTO
  映射/增益。
- 未修改 motor IDs、directions、软限位、初始化目标、默认速度或其他硬件配置。
- 未修改 feedback health、fault bit、温度 warning/critical、feedback timeout、
  电流能力边界或 0x02 大端序 parser。
- 未修改 IMU 协议、轴向、姿态换算或零点。
- 未修改风扇状态机、activity、响应曲线、PWM、GPIO12/GPIO13 或电调行为。
- 未修改 ROS 公共话题、服务、参数、消息类型或 launch 产品接口。
- 唯一 manifest 行为变化是准确声明已有 pytest 测试依赖。

## 15. 硬件安全声明

- 未执行 `ros2 run`、`ros2 launch`、`ros2 topic`、`ros2 service`、`sudo` 或
  `scripts/setup_can.sh`。
- 未启动或 spin IMU、电机、风扇节点或任何 hardware launch。
- 未打开 `/dev/imu_usb` 或任何真实串口。
- 未创建、连接或配置真实 SocketCAN，未访问 `can10`。
- 未构造用于真实连接的 CyberGear driver，未初始化/使能/控制电机，未写 SDO。
- 未访问 GPIO12/GPIO13，未创建 Servo，未初始化/解锁电调，未输出 PWM 或控制
  风扇。
- 未给电机或风扇通电，未进行任何带电测试。
- 本地 build/test/py_compile/whitespace/checker 都是纯软件验证，不表述为实机验证。

## 16. 用户授权提交时 Git 状态

- 分支仍为 `master`；HEAD/upstream 仍为
  `fae3a08fc1010b0c5b72314470e5359b087a4752`，领先/落后仍为 `0/0`。
- `docs/NEXT_COMMAND.md` 保留任务前用户修改，未修改或暂存。
- 用户已明确授权将本任务改动创建为中文 commit；本文件写入时 commit 尚未生成，
  最终提交 SHA 以会话终端汇报为准。
- `docs/NEXT_COMMAND.md` 明确排除在暂存和提交范围之外。
- 未获 push 或 tag 授权；未创建 release，也未修改任何既有 tag。
- 未 checkout、switch、reset、clean、restore、stash、rebase 或 merge。
- 最终详细 `git status` 与 diff 统计以本次会话终端汇报为准。

## 17. 未完成或限制

- GitHub Hosted CI 因尚未 push 而未实际运行；Hosted runner 上的依赖下载、构建
  耗时和 artifact 上传仍等待推送后验证。
- 本任务没有也不需要真实 IMU、CAN、电机、GPIO 或风扇验证；真实 fault、过温、
  反馈中断等硬件故障注入边界与上一基线相同。

## 18. 额外发现

- 电机包此前未在 `package.xml` 声明测试实际使用的 `python3-pytest`；本任务按
  manifest-first 原则补齐，避免 CI 依赖开发机手工环境。
- ROS Jazzy 的 setup 脚本与调用者启用 nounset 时需要受控兼容区间；统一脚本已把
  该区间限制在 source 操作内。
- 原仓库没有 GitHub Actions workflow。

## 19. 后续建议

- 本次中文 commit 创建后，如用户另行授权 push，再观察第一次 GitHub Hosted CI，
  确认 dependency setup、总耗时和 artifact 内容。
- Hosted CI 确认后再独立评估运行期断线与受控重连；本任务未顺带实现。
