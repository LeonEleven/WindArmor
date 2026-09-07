# WindArmor 算法研发路线

本文定义 WindArmor v0.5.0 “Balance Recovery”及后续平衡恢复能力的长期递进路线、任务边界
和验证升级原则。它用于规划和比较算法能力，不是某个候选实现的设计说明、硬件操作手册或
真实执行器授权。

算法实现必须遵守根目录 [`AGENTS.md`](../AGENTS.md) 的安全规则和
[开发协作流程](DEVELOPMENT_WORKFLOW.md)。输入、输出与失效行为以
[Flight Control API](FLIGHT_CONTROL_API.md) 为准；Runtime、控制权和底层最终否决权以
[飞控架构](FLIGHT_CONTROL_ARCHITECTURE.md) 为准；物理轴、接线和机械约束以
[硬件参考](HARDWARE_REFERENCE.md) 为准。第一次参与实现时先阅读
[算法开发者指南](ALGORITHM_DEVELOPER_GUIDE.md)。

## 1. 最终问题与场景边界

v0.5.0 的目标场景是：机器人初始站立在地面，双手自然垂下、手掌朝向地面；算法持续感知
状态，在推动、碰撞或其他外部扰动造成失衡后，结合姿态、运动趋势和必要的执行器状态，
协调微电机与涵道风扇产生受约束的恢复作用。

完整 Balance Recovery 至少需要形成以下闭环过程：

```text
稳定站立
  -> 外部扰动
  -> 检测失衡与倾倒趋势
  -> 产生方向正确且受约束的恢复作用
  -> 抑制继续倾倒
  -> 向平衡位置恢复
  -> 减小 overshoot 与持续振荡
  -> 重新稳定
```

因此，单一的 `pitch -> 0` 静态映射不等价于 Balance Recovery。目标是动态闭环扰动恢复，
而不是仅在若干离散姿态输入上得到方向合理的输出。

本路线不把初始姿态转换为硬编码电机位置，也不预先规定未经实验支持的控制器结构、增益、
滤波器、状态机或执行器分配公式。每一阶段只在自己的资格验证范围内作出结论。

## 2. 能力递进总览

| Task | 新增的主要能力 | 所属 Milestone |
| --- | --- | --- |
| ALG-001 | Basic Attitude Feedback / 基础姿态反馈 | M1 |
| ALG-002 | Motion Trend / Damping / 运动趋势与阻尼 | M1 |
| ALG-003 | Noise Robustness / 噪声鲁棒性 | M1 |
| ALG-004 | Actuator-safe Output / 执行器友好输出 | M1 |
| ALG-005 | Recovery Process / 恢复过程控制 | M2 |
| ALG-006 | Actuator Coordination / Control Allocation / 执行器协调与控制分配 | M2 |
| ALG-007 | Multi-axis Recovery / 多轴恢复 | M3 |
| ALG-008 | Full Disturbance Recovery / 完整扰动恢复 | M3 |

ALG 编号表示新增控制能力，不表示开发人员、工具或实现来源。后一个任务可以复用已通过的
前序能力，但不得用更高编号的实现结果替代较低编号任务自身的 qualification。

## 3. M1 — Basic Feedback

M1 包含 ALG-001 至 ALG-004。目标是基于姿态与运动趋势，产生方向正确、能抑制小噪声、
连续且受限的恢复控制输出。

M1 主要通过纯函数单元测试、边界测试和 synthetic DRY_RUN 验证。完成 M1 表示控制意图
具备基础软件质量，不表示机器人已经能从扰动中恢复，也不表示输出已在真实执行器上验证。

### ALG-001 — Basic Attitude Feedback

主要能力：根据单轴姿态误差（第一候选通常为 `relative_pitch_rad`）产生基础恢复控制意图。
独立规范见 [ALG-001 Task Spec v1](algorithm_tasks/ALG-001.md)，统一资格与历史比较规则见
[Algorithm Benchmark v1](ALGORITHM_BENCHMARK.md)。

资格验证重点：

- 正、负和零附近输入对应的输出方向符合该 Task Spec；
- proportional feedback 的输入—输出关系和幅值边界可解释、可重复；
- 平衡附近不存在非预期偏置；
- 无效、未知、非有限或过期输入，以及非法 `dt`，均按 API 契约安全处理；
- 输出能通过 `FlightCommand` 校验且不绕过 Runtime 或底层安全机制。

本任务只证明基础姿态反馈能力。filtering、damping、恢复状态机、control allocation 和
multi-axis recovery 属于后续任务，不应顺手加入。

### ALG-002 — Motion Trend / Damping

主要能力：在姿态误差之外使用角速度等运动趋势，使控制器能够区分“已经倾斜且仍快速继续
倾倒”和“已经倾斜但正在恢复”。

资格验证重点：

- 在相同姿态、不同运动趋势下产生有意义且方向一致的差异；
- 阻尼作用不会把正在恢复的状态错误放大；
- `dt` 变化、角速度边界以及趋势信息无效/过期时行为明确；
- 不破坏 ALG-001 的方向、完整输出和 fail-close 契约。

可评估 PD 或其他带阻尼思想的候选方案，但本路线不预先指定具体控制律。

### ALG-003 — Noise Robustness

主要能力：降低真实 IMU 小幅波动、量化噪声或微小扰动造成的持续无效动作。

资格验证重点：

- 对定义过的小幅噪声序列不产生不合理的持续输出或频繁反向；
- 对确有意义的姿态变化仍保持足够响应，不因抑噪完全失去控制作用；
- 重置后不复用旧滤波历史；
- 缺样、异常值、时间间隔变化和边界输入行为确定。

deadband、filtering 或其他小扰动抑制方法都是候选，不在 roadmap 阶段锁定。

### ALG-004 — Actuator-safe Output

主要能力：让算法输出在自身层面连续、有限且更适合后续执行器集成，同时保留底层全部安全
限制和最终否决权。

资格验证重点：

- saturation、slew-rate limiting、output shaping 等候选约束满足 Task Spec 的数值边界；
- 阶跃输入不会产生不合理的瞬时变化或高频反向；
- 限制器在可变 `dt`、重置和符号切换处行为明确；
- 算法约束不被描述为电机软限位、PWM 斜率限制、看门狗或 E-STOP 的替代品。

本任务不提前解决恢复阶段管理或微电机/风扇之间的控制分配。

## 4. M2 — Recovery Controller

M2 包含 ALG-005 和 ALG-006。目标是从逐帧基础纠偏扩展为可描述完整恢复过程的控制器，
并开始把抽象恢复需求协调分配给不同类型的执行器。

M2 需要比静态输入—输出测试更强的时序场景、replay 或 dynamic benchmark。进入真实执行器
验证仍须另行评审和授权。

### ALG-005 — Recovery Process

主要能力：表达和处理从稳定、受扰、恢复到重新稳定的完整过程，例如：

```text
STABLE -> DISTURBED -> RECOVERING -> SETTLING -> STABLE
```

这是一组能力和可观察阶段，不要求第一版必须采用有限状态机。资格验证应覆盖扰动进入、
恢复进展、settling、重新稳定、超时/无法恢复、reset 和输入失效等过程，并评估 overshoot、
持续振荡与误判。ALG-005 不负责锁定多执行器分配方法或扩展到完整多轴控制。

### ALG-006 — Actuator Coordination / Control Allocation

主要能力：把抽象恢复作用需求逐步转换为微电机与左右风扇之间一致、受限、可解释的协同
命令。

资格验证应覆盖执行器可用性组合、分配饱和、冲突需求、方向切换、control effort 以及任何
必要状态未知/失效时的安全行为。分配不得绕过完整四电机帧、归一化风扇命令、控制权、
底层软限位或安全停止契约。

具体分配矩阵、优先级、优化目标和增益必须来自独立 Task Spec、模型或实验依据；在没有
依据时不得写死。本任务不以单轴分配结果宣称已经具备多轴扰动恢复。

## 5. M3 — Full Balance Recovery

M3 包含 ALG-007 和 ALG-008。目标是形成至少 pitch/roll 的多轴恢复能力，并在软件证据充分、
风险评审完成后进入受限真实机器人验证。

### ALG-007 — Multi-axis Recovery

主要能力：从主要单轴问题扩展到至少 pitch 和 roll，并处理轴间耦合、同时扰动、组合饱和
以及不同方向上的恢复优先级。

资格验证应使用覆盖单轴和组合扰动的统一场景集，防止一个轴改善时另一个轴明显恶化；同时
保留 M1/M2 的输入有效性、噪声、输出约束、过程控制和失效后安全闭锁能力。本阶段不能仅凭
坐标分量分别通过静态测试就宣称完成多轴动态恢复。

### ALG-008 — Full Disturbance Recovery

主要能力：面向最终目标，把检测、趋势判断、抑制倾倒、恢复、消振和重新稳定串成可量化的
闭环能力。

软件 qualification 应覆盖不同扰动方向、幅度、初始趋势和允许的执行器边界，并以 peak
tilt、peak angular velocity、recovery time、overshoot、oscillation、steady-state error、
actuator saturation 和 control effort 等指标评估。无法恢复、状态失效或超出设计包线时，
必须有明确的安全处置和结论边界。

ALG-008 的软件 PASS 仍不自动等价于真实机器人在受到推动后能够重新站稳。真实 Balance
Recovery 结论必须来自该版本单独授权、受限且证据充分的实机验证。

## 6. 异步研发轨与候选实现

不同研发轨不要求保持相同速度。推荐使用中性名称，例如：

```text
Fast Progression Track:
  ALG-001 PASS
  ALG-002 PASS
  ALG-003 PASS
  ALG-004 IN PROGRESS

Independent Learning / Validation Track:
  ALG-001 IN PROGRESS
```

共同规则如下：

1. 每条轨道保留自己的 implementation lineage、baseline 和 qualification 证据；
2. 前一递进任务通过该轨道自己的 qualification 后，快速推进轨即可进入下一任务，不必等待
   其他轨道；
3. 独立学习与验证轨的第一阶段至少独立完成 ALG-001，用来验证开发人员对 Flight API、
   控制器结构、测试、synthetic DRY_RUN、Git/PR 工作流和安全边界的理解；
4. 独立轨通过 ALG-001 并证明基础能力后，不要求机械重做快速轨已完成的所有历史任务；可以
   阅读当前成果并参与当前最有价值的问题；
5. 多个候选可以并存，但合并或替换生产候选需要明确的 review、兼容性说明和证据；
6. 公平历史比较只比较相同任务和 benchmark 版本，例如 `ALG-001 Candidate A` 与
   `ALG-001 Candidate B`，不得用 `ALG-001` 与 `ALG-005` 作同级优劣结论。

### Historical Comparison / 历史同级比较

历史同级比较的比较单元是“相同 Task Spec 版本 + 相同 benchmark 版本 + 各自可追溯的
implementation lineage”。报告应同时保留 baseline、实现提交、结果、失败项和已知限制；
不能只挑选单个最好指标，也不能把不同能力阶段的结果包装成公平的候选对比。

## 7. 独立 ALG Task Spec 模板

每个 ALG task 原则上只增加一个主要能力，并在实现前建立独立、可 review 的 Task Spec。
至少包含：

1. `Task ID`：稳定标识，例如 `ALG-001`；
2. `Objective`：本任务新增且可验证的单一主要能力；
3. `Baseline`：分支、baseline commit、已继承能力和已知限制；
4. `Inputs`：字段、单位、坐标/符号、有效性、新鲜度、采样与 `dt` 假设；
5. `Expected behavior`：中性、正负、动态、边界和故障场景的预期关系；
6. `Safety constraints`：输出包络、safe-stop、reset、禁止访问的层和保留的底层机制；
7. `Verification`：测试层级、场景、fixture、benchmark 与可复现命令；
8. `Pass / Fail criteria`：客观阈值、容差、失败分类和不得扩大的结论；
9. `Out of scope`：本任务明确不解决的相邻问题；
10. `Future-task boundary`：哪些能力必须留给后续 ALG task。

为支持复现与历史同级比较，还应保存：

```text
Task ID
Task Spec version
Baseline commit
Implementation commit
Benchmark version
Benchmark result
```

若 Task Spec、fixture、模型或指标发生实质变化，必须更新版本并说明兼容性；不能把新基准的
结果无说明地覆盖旧结果。

## 8. Future-task boundary

任务评审必须检查“主要新增能力是否只有一个”。例如 ALG-001 不应顺手实现 filtering、
恢复状态机、control allocation 或 multi-axis recovery。必要的安全输入检查、输出合法性和
测试不是越界；提前实现会改变控制行为的未来能力则属于越界。

若实现中发现共享 API、Runtime、authority、hardware manager 或 driver 必须改变，应停止将
其当作普通算法任务处理，拆出独立的 API/架构/安全评审；不得借 ALG task 静默扩大范围。

## 9. Benchmark 演进

本路线不要求当前立即建立完整 benchmark infrastructure，但验证能力应随 ALG 阶段升级：

| 层级 | 适用阶段 | 主要用途 | 不能声称 |
| --- | --- | --- | --- |
| 纯函数/单元场景 | ALG-001 起 | 方向、范围、输入—输出关系、invalid/stale、reset、`dt` 边界 | 动态闭环恢复 |
| synthetic DRY_RUN | ALG-001 起 | 工厂加载、状态/命令契约、可读预览、safe-stop | 真实机器人动态或执行器效果 |
| 序列/replay benchmark | ALG-002 起 | 趋势、噪声、时序、状态演进与回归比较 | 模型外真实动力学表现 |
| dynamic benchmark / 可信仿真 | ALG-005 起 | 闭环扰动、恢复时间、overshoot、振荡、饱和与 effort | 未经验证的 sim-to-real 等价性 |
| 受限硬件验证 | 软件证据和评审充分后 | 当前设备、当前边界内的真实 actuator behavior | 未测试包线或通用性能保证 |

当前 synthetic DRY_RUN 若只是静态的
`FlightState -> controller -> FlightCommand`，只能证明软件映射与契约，不能描述为机器人动态
闭环仿真。v0.5.0 后续应以独立任务建立版本化的 dynamic benchmark、replay 或可信仿真能力。

指标按阶段逐步引入：

- 早期：输出方向、数值范围、输入—输出关系、safe behavior、invalid/stale input、reset、
  `dt` 边界；
- 中后期：peak tilt、peak angular velocity、recovery time、overshoot、oscillation count、
  steady-state error、actuator saturation、control effort，以及是否最终恢复稳定。

所有指标都必须在 Task Spec 中定义采样、时间窗、阈值、容差和失败条件；不同 benchmark
版本的数字不可直接当作同级结果。

## 10. 完成边界与发布结论

### 软件研发完成

按阶段可能包括 unit test、synthetic DRY_RUN、版本化 replay/dynamic benchmark、可信仿真、
软件 CI 和 integration review。其结论应准确限定为软件实现、模型和测试场景内通过。

### 真实 Balance Recovery 已验证

只有真实机器人在规定初始姿态、扰动、执行器边界和停止条件下产生可审查证据，才能对相应
范围声称真实 Balance Recovery 已验证。任何真实电机或风扇场景都必须在执行前单独满足
`AGENTS.md` 的十项授权门槛，并执行 bounded hardware validation 和 evidence review。

未经这些步骤，不得声称机器人受推动后能够重新站稳，不得把软件 CI、fake/mock、静态
DRY_RUN、replay 或仿真等价为实机结果。若 v0.5.0 正式发布时宣称实现真实 Balance Recovery，
release 前必须完成该版本所需的真实硬件验证；否则发布说明必须清楚保留未验证边界。

## 11. 下一推荐任务

ALG-001 的 Task Spec 与 Benchmark v1 contract 已建立。下一独立工作单元是：

```text
ALG-001 implementation candidate
```

实现必须从同一冻结的 [ALG-001 Task Spec v1](algorithm_tasks/ALG-001.md) 和
[Algorithm Benchmark v1 / ALG-001 Profile v1](ALGORITHM_BENCHMARK.md) 出发，保留独立 lineage；
不得实现 ALG-002 及后续能力，也不自动进入任何真实硬件测试。
