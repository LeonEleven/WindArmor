# WindArmor 当前开发交接

> **INTERNAL DEVELOPMENT HANDOFF — MUTABLE。** 本文件只记录当前任务状态和下一步，
> 不是普通用户操作文档、长期接口契约或 release evidence source of truth。历史发布事实
> 必须引用对应的版本化 release/verification 文档。

## 当前任务

- 任务：`v0.4.0 FINAL RELEASE PREPARATION`
- 日期：2026-08-26
- task-start branch：`master`
- task-start HEAD：`1c17898a5f86533673437769e57a738962b04c2d`
- 当前 stable release：v0.3.2
- 当前开发目标：v0.4.0（未发布）
- Gate B / C / D：**COMPLETE / COMPLETE / COMPLETE**
- hardware / functional verification：**COMPLETE**
- DOC-1：**COMPLETE / REVIEW PASS**
- DOC-2：**COMPLETE / REVIEW PASS**
- DOC-3：**COMPLETE / REVIEW PASS**
- DOC-3.1：**COMPLETE / REVIEW PASS**
- 五包版本元数据：**PREPARED AS 0.4.0**
- 根许可证：**Apache License 2.0 PRESENT**
- v0.4.0 release notes：**PREPARED**
- release readiness：**READY FOR FINAL RELEASE COMMIT**
- v0.4.0 release status：**NOT YET RELEASED**

## v0.4.0 final release preparation

本轮完成发布前仓库整理，不改变生产控制行为、公开 ROS 接口、配置、launch 或硬件映射。

- 五个 ROS 2 包的 `package.xml` 版本均已准备为 `0.4.0`；四个 Python 包的
  `setup.py` 版本与对应 `package.xml` 一致；
- 仓库根目录已补齐标准 Apache License 2.0 全文；
- 已新增 `RELEASE_NOTES_v0.4.0.md`，汇总功能变化、兼容性、验证状态、已知限制和发布状态；
- README 与 v0.4 verification record 已更新为 release readiness `READY`，同时明确
  v0.4.0 尚未打 tag、尚未发布，当前 stable release 仍为 v0.3.2；
- 发布契约测试已覆盖全部五包版本和许可证，并继续校验四个 Python 包的 setup metadata；
- Gate B / C / D、hardware / functional verification、DOC-1 / DOC-2 / DOC-3 / DOC-3.1
  均保持 `COMPLETE`；历史 session、测量值、PASS/FAIL/NOT VERIFIED 和证据判断未改变。

## 前序 DOC-3.1 final language hotfix

本轮只修复五份长期新人文档中残留的普通英文说明，未扩大到历史文档、源码或运行时文本。

- Architecture 图示中的普通英文边界/硬件说明和 `required_inputs_fresh` 说明图已改为自然中文，
  正式类型名 `MotorState` 保持不变；
- README、Algorithm Developer Guide、Flight Control API、Architecture 和 Hardware Reference
  仅处理明显且不必要的普通英文，正式标识符、状态、单位和命令文本保持原样；
- 本轮只修改 Markdown prose；Python comment/docstring、运行时日志、异常文本、CLI 输出、
  production behavior、config、launch 和 interface 均未修改；
- 相对 Markdown 链接检查为 67 checked、missing 0，`git diff --check` 为 PASS；
- 按任务要求，纯文字微修未重复运行 full CI，也未执行任何硬件测试。

## 前序 DOC-3.1 结果

本轮将面向中文维护者和算法开发者的说明改为以中文为主，同时严格保留正式标识符、接口、
状态值、硬件缩写、单位、命令参数和历史证据。生产控制行为没有改变。

1. 深度本地化 `FLIGHT_CONTROL_API.md` 的表头、字段说明、单位、有效性、新鲜度、校验规则和
   示例说明；`FlightState`、`FlightCommand`、字段名、类型名及状态值保持原样；
2. 在不改变章节结构和阅读顺序的前提下，本地化 Algorithm Developer Guide 的数据流、最小
   控制器、状态输入、测试层级、控制权说明和检查表；
3. 本地化 Flight Architecture 的组件边界、观测链路、两阶段 handoff、原子截止点、lease、
   回滚、重启/关闭、E-STOP 和最终否决权说明；
4. 本地化 Hardware Reference 的平台、电机物理映射、transport 边界、冷启动、IMU 坐标、
   风扇接线与测量限制，硬件 ID、GPIO、CAN、限位和符号保持不变；
5. 对根 README 和 `src/imu_cybergear_ros2/README.md` 做轻量本地化；另外三个包内历史运行
   指南经扫描后保持不变，避免重写历史事实；
6. 对硬件验证记录做轻量本地化，保留 PASS/FAIL/NOT VERIFIED、COMPLETE、session、时间戳、
   数值、证据等级和 Gate disposition；历史验证计划仅调整当前标题、入口与发布准备说明；
7. 本地化 IMU/电机、风扇和 Flight 三个包中 42 个 Python 文件的 public docstring 与解释性
   注释；运行时日志、异常文本、函数签名、返回值和执行路径均未修改；
8. 更新本交接文档，记录 DOC-3.1 验证结果和下一步。

本轮共修改 8 份内容文档，另更新本交接文档；Python 变更只包含 docstring 和注释。源代码
去除 docstring 后与 task-start HEAD 比较的 42 文件 AST 完全一致。

## 术语与标识符边界

- 普通工程叙述以中文为主；`epoch`、`generation`、atomic handoff、lease、safe-stop、
  fail-close、Runtime、owner 等在首次上下文中用中文解释，并在需要对应源码时保留英文术语。
- API/class/function/field 名、ROS topic/service/parameter 名、枚举与状态值、GPIO/CAN/PWM/IMU、
  单位、CLI flag、环境变量、文件/模块名和代码片段保持英文或原始拼写。
- `required_inputs_fresh` 仍只表示 paired IMU fresh 且每个配置电机 feedback fresh；风扇状态、
  权威安全回读、E-STOP clearance 和 authority readiness 仍由独立条件裁决。
- `(authority_epoch, generation)`、post-cutoff state、递增 sequence、两阶段 reserve/commit、
  Runtime 本地先关闭下发再 best-effort revoke、底层最终否决权和不自动恢复旧 owner/目标等
  架构不变量保持不变。
- 运行时日志和 machine-readable marker 均未修改。

## 新人可读性与架构复核

按 `README → Algorithm Developer Guide → Flight Control API` 的顺序完成中文新人视角抽查：

- README 能直接定位算法开发入口、API、架构和硬件参考；
- Guide 保持从最小控制器、`reset()`/`update()`、状态输入到三级验证的原顺序；
- API 的字段表、单位、`None`、`valid/fresh/healthy` 与 safe-stop 说明均可直接用于实现；
- 相对链接均能解析，未因本地化改变链接目标；
- 未把 pure/fake/mock 结果表述成真实硬件验证。

Architecture 复核确认仍明确：epoch/generation 身份隔离、两阶段原子 handoff、独立 lease、
命令包络截止点、回滚顺序、Runtime 重启/关闭隔离、E-STOP/ERROR 优先级、底层最终否决权，
以及故障后绝不自动恢复 MANUAL/AUTO/HOME、owner、authority 或旧目标。

## 本轮最终发布准备验证

已执行且通过的发布准备纯软件验证：

- 发布契约定向 pytest：`6 passed`；
- 五包 `package.xml` 均为 `0.4.0`，四个 `setup.py` 与对应包元数据一致；
- 根 `LICENSE` 与系统标准 Apache-2.0 文本逐字节一致；
- 相对 Markdown link check：17 files scanned、81 links checked、missing 0；
- `git diff --check`：PASS；
- `source /opt/ros/jazzy/setup.bash && ./scripts/ci_software.sh`：PASS，五包 build 完成，
  最终 `939 tests, 0 errors, 0 failures, 0 skipped`。

以上均为构建、pure/fake/mock 或静态验证，不是真实 CAN、串口、GPIO、电调、风扇或机械
实机验证。本轮未启动 ROS 节点/launch，未访问硬件 I/O，未改变树莓派运行时状态，也未给
actuator 通电。

## 本轮最终发布准备的变更边界

- production behavior changed：**NO**
- package metadata changed：**YES — VERSION ONLY**
- root license added：**YES**
- release documentation/status changed：**YES**
- comments/docstrings changed：**NO**
- runtime logs changed：**NO**
- machine-readable markers changed：**NO**
- tests changed：**YES — RELEASE METADATA CONTRACT ONLY**
- scripts changed：**NO**
- configs changed：**NO**
- launch changed：**NO**
- public ROS interfaces changed：**NO**
- hardware executed or affected：**NO**
- historical verification facts/status/evidence changed：**NO**
- branch created/switched：**NO**
- commit/push/tag/release：**NO**

## 下一任务

先 review 本轮 release-preparation commit，再单独创建 final release status commit；确认该提交
对应的 GitHub Actions CI 成功后，才创建 annotated `v0.4.0` tag，最后创建 GitHub Release。
v0.4.0 当前仍为 **NOT YET RELEASED**；本交接不自动授权 commit、push、tag、release 或任何
新的真实硬件操作。
