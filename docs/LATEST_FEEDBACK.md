# WindArmor 当前开发交接

> **INTERNAL DEVELOPMENT HANDOFF — MUTABLE。** 当前 branch、push、PR、CI 与 merge 等实时
> 生命周期状态以 Git / GitHub 为准；本文件仅保留下一工作单元需要的稳定工程状态。

## 当前工作单元

- 日期：2026-09-22
- Task：`v0.5.0-018 — ALG-007 Task Spec + Multi-axis Recovery Benchmark Design`
- task branch：`docs/alg-007-design`
- task-start baseline / actual `origin/develop`：`607eefb85c31e8da35b884a6059dc00d62deba18`
- 本地 `develop` 与 `origin/develop` 在任务开始时相同；工作区无已有未提交修改；ALG-006
  remote feature branch 在 fetch/prune 与 `ls-remote` 检查后不存在。
- Stable release：`v0.4.0`；v0.5.0：**NOT RELEASED**。
- ALG-001～006：**QUALIFIED / INTEGRATED**。ALG-006 fixed implementation SHA：
  `9a7a624713010eff48cf7112b0501266eb24521e`；Formal Qualification/Result evidence SHA：
  `6729443d5e190986c75b8521a4ec7ebd0554d34e`；integration SHA：
  `607eefb85c31e8da35b884a6059dc00d62deba18`。
- [ALG-007 Task Spec v1 design](algorithm_tasks/ALG-007.md)：**COMPLETE / REMOTE REVIEW REQUESTED**。
- [ALG-007 planned benchmark design](ALGORITHM_BENCHMARK.md#14-alg-007-planned-profile-design-v1)：
  **COMPLETE / PLANNED / NOT YET FROZEN**。
- ALG-007 Candidate：**NOT STARTED**；Candidate Result：**NOT CREATED**；Formal Qualification：
  **NOT EXECUTED**。PR：**NOT CREATED**；merge：**NOT PERFORMED**。

## 审计依据与设计结论

按权威顺序审阅 `AGENTS.md`、`DEVELOPMENT_WORKFLOW.md`、旧交接、路线图、Benchmark、
ALG-001～006 Task/Result、Flight API/Architecture、Hardware Reference；只读检查六个 Candidate、
factory、models/validation、IMU adapter、benchmark helpers/tests、电机/风扇适配器及配置。

`FlightState` 已表达相对 pitch/roll 角度，但只有统一的 pitch rate；Controller API 只约定
`update(state,dt)`，当前 Candidate 仍是单轴。`FlightCommand` 只有完整 absolute motor rad 帧
与左右 fan `[0,1]`，没有双轴 intent；ALG-006 的 common-`q` 是单轴 normalized synthetic
allocation，Level B 仍为当前 motor hold/fan-zero。现有 status/availability 不提供 numerical
authority；hardware mapping 也不是 pitch/roll 物理恢复矩阵。

ALG-007 design 冻结联合软件请求/服务/residual 的安全结构、combined synthetic budget 的
边界、确定性 arbitration 必需条件、simultaneous disturbance 和 fail-close，以及在最终路径
fresh 重跑 ALG-001～006 的 inheritance。`ALG007-SYNTHETIC-VECTOR-v1` 和拟议 coupling fixture
均只是纯软件压力模型；roll rate/source、竞争规则、coupling 数值模型和多轴 Level E 阈值
须在 Candidate 前 review 冻结。现阶段不能声称多轴动态资格 PASS。

## Hardware / evidence boundary

- Hardware access：**NO**；authorization：**NONE**；hardware validation / Level F：
  **NOT AUTHORIZED / NOT EXECUTED**。
- Real actuator safety、dynamic closed-loop recovery on hardware 与 real Balance Recovery：
  **NOT VERIFIED**。
- 真实 motor torque/recovery direction、fan thrust/moment arm、motor/fan relative authority、
  pitch/roll physical allocation、normalized request → executable rad/PWM projection、runtime
  availability → numerical authority、真实 cross-coupling 和 maximum recoverable disturbance：
  **UNKNOWN / NOT VERIFIED**。
- ALG-006 既有 qualification 与单轴 synthetic Level E 证据见
  [ALG-006 Candidate Result](algorithm_results/ALG-006_CANDIDATE_A.md)；不得扩展为 ALG-007
  qualification 或硬件能力。

## 本工作单元产物与下一步

修改 `algorithm_tasks/ALG-007.md`、`ALGORITHM_BENCHMARK.md`、`ALGORITHM_ROADMAP.md` 和
本交接文件；未修改 production、qualification implementation 或历史 Result。此 design
Remote Review checkpoint 请求 ChatGPT/user 审查 ALG-007 轴/速率来源、arbitration、synthetic
coupling 与双轴动态阈值。**不要自行进入 Candidate implementation**；Candidate、Result、
Formal Qualification、PR、merge、release 与硬件验证仍需各自后续任务和授权。
