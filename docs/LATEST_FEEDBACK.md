# INTERNAL DEVELOPMENT HANDOFF — v0.4.0 Documentation Audit Complete

> 日期：2026-08-24
> task-start branch / HEAD：`master` / `02d102351c664cc75c36ea90d19154a0058ca16b`
> 本轮性质：documentation + code comment inventory audit only
> production changed：`NO`
> tests/scripts/config/launch/interfaces changed：`NO`
> hardware executed：`NO`
> audit report：`docs/V0.4.0_DOCUMENTATION_AUDIT.md`

## 正式状态（未因本轮审计改变）

```text
Gate B: COMPLETE
Gate C / C1: HARDWARE PASS
Gate C / C2: HARDWARE PASS
Gate C / C3: HARDWARE PASS
Gate C / C4a: HARDWARE PASS
Gate C / C4b: HARDWARE PASS
Gate C / C4: HARDWARE PASS
Gate C: COMPLETE
Gate D: FUNCTIONAL REGRESSION PASS
Gate D: COMPLETE
v0.4.0 hardware / functional verification: COMPLETE
Release readiness review: PENDING
Current stable release: v0.3.2
```

此前 C1/C2/C3/C4a/C4b 的最终 PASS、invalidated/NOT VERIFIED attempt、session ID、
operator physical evidence、continuous recorder evidence、RIGHT ESC 供电边界、Gate D
evidence matrix 和 release limitation 均已保存在
`docs/V0.4.0_HARDWARE_VERIFICATION_PLAN.md`。本轮可以压缩 handoff，但没有删除或改写这些
权威历史。

## 审计范围

- 读取全部 13 个 tracked Markdown 文档；另读取 untracked task scratchpad
  `docs/NEXT_COMMAND.md`，但不把它计入 repository documentation inventory。
- 扫描 `src/` 下全部 123 个 tracked Python 文件的 comments/docstrings。
- 直接核对 Flight public models/validation、example controller、
  `bounded_verification_controller`、factory/loader、fake state/tests、Runtime state aggregation/
  control tick/envelope，以及 motor/fan `/flight_control/command` consumer 路径。
- 未运行 ROS node、launch、Runtime、CAN、GPIO、PWM 或串口；未执行真实硬件操作。

## 主要结论

### P0 — 5

1. `FLIGHT_CONTROL_API.md` 仍 blanket 声称 Flight takeover 未实机验证，与 Gate B/C/D
   已完成冲突。
2. `FLIGHT_CONTROL_ARCHITECTURE.md` 仍保留同类 stale blanket claim。
3. API 把 `required_inputs_fresh` 写成全部 required inputs；当前 source 实际只聚合 paired IMU
   与全部 configured motor freshness，不证明 fan/safety/authority readiness。
4. `src/imu_cybergear_ros2/README.md` 仍称初始化写 `0.0 rad`，与已实现/实机验证的
   measured-position cold-start hold 冲突，属于直接硬件安全文档错误。
5. 历史 `V0.3.2_RC_HARDWARE_CHECKLIST.md` 仍写 GPIO12/13，且没有足够醒目的 historical-only
   隔离；当前 mapping 是 GPIO12/26，GPIO13 保留给 CAN HAT INT_1。

### P1 — 9

- 缺少真正 step-by-step 的 newcomer algorithm guide；
- 缺少能展示姿态输入到输出的 non-default 教学 controller/test；
- 当前 DRY_RUN launch 只启动 Runtime，仓库没有 bundled synthetic state path；
- API 混入大量 authority/ownership/lease/rollback internals；
- 高风险 public fields 缺 frame/sign/reference/default/example 说明；
- README 836 行，Gate/process history 在 install/normal-use 之前占据大量篇幅；
- package 内多个硬件操作手册重复且存在 authority fragmentation；
- v0.4.0 plan/final record/attempt diary 与 `LATEST_FEEDBACK` 职责混合；
- 多处 Task/future/closed-pending 叙事及 immutable release → mutable handoff 引用需整理。

### P2 — 5

- public-looking core/adapter types 的 docstring 补充；
- 删除只复述代码或 decorative 的低价值注释；
- 三个 `setup.py` 的 `todo.todo` maintainer metadata；
- early v0.2 overview/archive navigation；
- 中英文术语和 heading style 小范围统一。

## 算法开发建议

新增 `docs/ALGORITHM_DEVELOPER_GUIDE.md`，以新人从零到 review 为主线：最小 controller、
常用 `FlightState`、IMU/motor/fan 单位与语义、`dt/reset/safe_stop`、fake state、unit test、
DRY_RUN、preview、plain-language authority、bounded hardware promotion、常见错误和 review
checklist。

新增独立、non-default 的 `example_algorithm_controller.py`（或等价清晰命名）及 unit test；
不要把 `bounded_verification_controller` 当新人模板。保留后者的 verification-only guards、
authority-session baseline 和 fail-closed 行为。

三阶段正式路径：

```text
LEVEL 1: fake FlightState -> update() -> validate/assert FlightCommand
LEVEL 2: Runtime -> state adapter -> algorithm -> status/preview; no actuator authority
LEVEL 3: reviewed controller -> explicit ten-item authorization -> bounded Runtime/authority/
         manager path -> real actuator + continuous evidence + safe shutdown
```

LEVEL 1 由算法开发者自行完成。LEVEL 2 使用纯 synthetic state 时可自行完成；当前仓库尚无该
provider，若接 live WindArmor state，相关 source node 可能访问硬件，必须按权限处理。LEVEL 3
必须由 maintainer/operator 负责 scenario、证据、授权、供电、执行和物理观察；算法开发者不得
自行启用 takeover、prepare authority、set zero、reset E-STOP/ERROR 或执行硬件 launch。

## API / README / archive / comment 建议

- `API.md`：只保留开发算法时查字段、单位、接口、factory、validation、safe-stop、invariant。
- `Architecture.md`：集中 Runtime、authority、epoch/generation、ownership、atomic commit、lease、
  rollback、transport envelope 和 fault containment。
- `README.md`：项目/版本、安全提示、安装/build、正常启动/使用/退出、算法入口、接口摘要、
  文档索引。
- archive：优先建立一个简单的
  `docs/verification/v0.4.0/HARDWARE_VERIFICATION_RECORD.md`，保留 current plan 中全部 final/
  invalidated evidence，不拆成逐 Gate 碎片；可复用流程另放
  `docs/ALGORITHM_HARDWARE_SMOKE_TEST.md`。
- `LATEST_FEEDBACK.md`：继续留在 docs 根目录作为 internal handoff，README 不链接；release 后按
  新任务重置，不承担永久 evidence source-of-truth。
- comments/docstrings：保留 WHY、安全不变量、单位、坐标/符号、lifecycle edge、兼容约束和
  failure rationale；优先补 `SystemState`/`FanSystemState`、factory loader、authority/envelope/
  preflight 和 adapter source/freshness contracts。

## 简单算法到真实 motor/fan 的事实结论

路径已经存在并有三层证据：

- pure unit：bounded controller、models/validation/loader/envelope tests；
- Runtime integration：factory、handoff/atomic cutoff、command envelope、motor/fan consumer tests；
- real hardware：Gate B1/B2 和 Gate C C1/C2/C3/C4a/C4b 使用同一 bounded controller，经 Runtime、
  `/flight_control/command`、motor/fan authority/manager 进入真实 actuator。

它证明架构路径，不等于任意新算法自动获准上硬件。建议新增 dedicated newcomer example；同时
新增 maintainer/operator-owned hardware smoke runbook，而不是复用 release verification controller
作为教学模板。

## 推荐后续任务

下一任务建议执行 **DOC-1 — P0 truth correction + algorithm onboarding/API**：

1. 修复上述五项 P0；
2. 创建 `ALGORITHM_DEVELOPER_GUIDE.md`；
3. 将 API 收敛为 reference，将 Runtime internals 移到 Architecture；
4. 增加 non-default 教学 controller/test 和 meaningful software-only DRY_RUN demo path；
5. 更新 README algorithm entry；
6. 因涉及 source/test，执行 targeted tests 与完整 `./scripts/ci_software.sh`，仍不访问硬件。

随后执行 DOC-2（README/package consolidation + verification archive），最后 DOC-3（comments/
docstrings + consistency/release-readiness）。不自动执行 hardware、commit、push、tag 或 release。
