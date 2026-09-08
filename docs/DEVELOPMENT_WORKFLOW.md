# WindArmor 开发协作流程

本文面向 WindArmor 的人类开发成员和维护者，定义 v0.4.0 发布后的分支、Pull Request、
CI、硬件授权与发布协作方式。仓库级强制规则仍以根目录 [`AGENTS.md`](../AGENTS.md) 为准；
本文不能放宽其中的硬件安全门槛或 Git 操作限制。

当前正式稳定版本为 v0.4.0。`develop` 已建立并作为下一版本的实际集成主线；分支已经存在
不代表任何 agent 获得创建、切换、合并、推送或删除分支的隐式授权。

## 分支模型

```text
master
  |
  `-- develop
        |-- feature/*
        |-- fix/*
        |-- docs/*
        `-- experiment/*

hotfix/*  <- master
release/* <- develop（按需）
```

- `master` 保存稳定、已验证、可发布的主线。
- `develop` 集成下一版本的正常开发。
- 普通工作使用可 review、可测试、可合并的短期任务分支。
- `hotfix/*` 从 `master` 处理已发布版本的紧急修复。
- `release/*` 只在版本冻结与并行开发确有需要时建立。
- 长期个人分支不属于正式集成模型；分支按工作单元而不是按人员归属。

## master

`master` 对应稳定发布基线和正式 tag，不作为日常开发入口。推荐只通过 Pull Request 合入，
并要求软件 CI、维护者 review 和相应发布门槛通过。

从 `develop` 或 `release/*` 提升到 `master` 前，至少确认：

- required software CI PASS；
- integration review PASS；
- 用户文档、API 文档和发布文档已更新；
- release-specific blocker 已关闭；
- 涉及真实 actuator behavior 的变更已完成该版本所需的硬件验证；
- release readiness review PASS。

合入 `master` 后才允许创建正式 tag。普通 feature、实验或未完成最终验证的内容不得直接
把 `master` 当作集成分支。

## develop

`develop` 是下一版本的集成主线。正常 feature、fix 和 docs 原则上先通过 PR 合入
`develop`，再在发布周期中整体提升到 `master`。

`develop` 可以包含尚未完成最终硬件验证的新功能，但必须保持：

- 工作空间可构建；
- WindArmor Software CI 为 green；
- 无已知严重破坏；
- 安全机制没有被删除、绕过或弱化；
- 未验证的硬件行为和 release blocker 被清楚记录。

代码进入 `develop` 只代表软件集成状态，不代表允许访问 CAN、串口、GPIO、PWM、ESC、
电机或风扇。

## 功能、修复、文档与实验分支

短期任务分支通常从最新 `develop` 创建，一个分支只承载一个独立工作单元：

| 类型 | 命名 | 用途 |
| --- | --- | --- |
| 功能 | `feature/<short-name>` | 新功能或可独立 review 的能力 |
| 修复 | `fix/<short-name>` | 下一版本普通缺陷修复 |
| 文档 | `docs/<short-name>` | 独立文档任务 |
| 实验 | `experiment/<short-name>` | 不承诺进入发布线的探索 |

名称使用小写英文和连字符，例如 `feature/algo-pitch-control`、`fix/runtime-restart`、
`docs/algorithm-tuning-guide` 或 `experiment/algo-lqr`。不要把用户名作为主分类。

任务分支完成实现和本地验证后，先形成下述 Remote Review Checkpoint；remote review PASS 后，
再由用户明确授权创建 PR 到 `develop`。CI 与 review 通过并由用户明确授权 merge 后才合并；
分支清理也需要用户针对当前任务授权。不要在一个分支中混入无关重构、多个独立功能或顺手
修复。

## Remote Review Checkpoint

Review Checkpoint 是当前短期任务分支上供远端 review 的可追溯快照。它解决 reviewer 无法从
远端读取未 push 改动的问题，同时不把 task branch push 混同为集成。完整阶段为：

```text
Task Start
  -> short-lived task branch
  -> implement
  -> local verification
  -> Review Checkpoint: normal commit + push current task branch
  -> Remote Review
       |-- changes requested
       |     -> modify -> verify -> new checkpoint commit + normal push
       `-- PASS
             -> user authorizes PR
             -> PR to develop
             -> required Software CI
             -> user authorizes merge
             -> merge
             -> post-merge CI
             -> user authorizes branch cleanup
```

Review Checkpoint 供 reviewer 精确读取 diff、commit、files 和 tests/evidence。它不表示任务已
通过 review，不是 PR approval、merge authorization 或 release evidence，不改变 `develop` /
`master`，也不表示功能已正式进入集成主线。checkpoint push 与 PR 是两个不同阶段。

### 默认授权与边界

用户已经明确启动一个 `feature/*`、`fix/*`、`docs/*` 或 `experiment/*` 短期任务，且
`NEXT_COMMAND` / Task Spec 已明确 scope 时，在修改严格处于 scope 且完成规定本地验证的前提
下，agent 默认可以：

1. 只 `git add` 任务范围内文件；
2. 使用有长期工程意义的正常 message 创建 review commit；
3. 正常 push 当前短期任务分支到 `origin`；
4. 汇报远端 checkpoint 并停止等待 review。

message 应使用仓库正常风格，例如“飞控：实现 ALG-002 Candidate A”或“修复：处理控制器 stale
input”，不使用 `checkpoint`、`temporary`、`AI generated` 或工具/模型身份作为说明。Squash
merge 允许短期分支保留多轮 review commits；changes requested 后应修改、重新验证、创建新
commit 并正常 push，不 amend 已 review commit，也不 force push。同一已授权 scope 和同一
分支内的普通多轮 checkpoint 不需要逐轮重新申请 commit/push 权限。

默认授权严格不包含：

- push 到 `develop` 或 `master`、force push、amend 已 review commit 或其它 history rewrite；
- rebase、reset、clean、merge、创建 PR、删除本地或远端分支；
- release branch、version bump、tag、GitHub Release 或 master release merge；
- 任何真实硬件访问或硬件授权。

remote review PASS 后，仍必须由用户明确授权 create PR -> `develop`；即使 PR checks PASS、
mergeability CLEAN 且 branch protection satisfied，也必须由用户明确授权 merge。PR merge 后的
本地和远端分支删除仍分别需要用户授权。release/tag 使用独立 release task，不从 checkpoint
权限推导。

以下情况禁止自动 checkpoint，agent 必须停止并询问用户：scope 越界；需要修改禁止文件；
出现 API / architecture conflict 或 hardware / safety 问题；测试 FAIL 且不能在当前 scope 内
安全解释；工作区存在来源不明修改；需要 reset、clean、rebase、force push、删除分支、改变
`develop` / `master`、硬件授权或 tag/release。Review Checkpoint 不能绕过 branch protection
或任何其它授权制度。

### Checkpoint 验证与汇报

checkpoint 前至少运行 `git diff --check`，并完成任务规定的 targeted tests、Software CI、
Markdown link scan、safety checker、build/test 等适用验证。不能执行的规定验证必须明确写为
“未执行”并说明原因，不能静默省略。

checkpoint 后的当前任务汇报至少列出：task branch、task-start baseline、checkpoint commit
SHA、changed files、diff summary、验证命令与结果、未执行测试、hardware access、剩余风险、
`remote branch pushed: YES`、`PR created: NO` 和 `merge: NO`。这些实时字段属于任务汇报，
不要求全部写入 mutable handoff。

### Git / GitHub 与 mutable handoff 的职责

以下实时生命周期状态以 Git / GitHub 当前状态为 source of truth：branch 是否存在、当前 branch
HEAD、commit 是否已 push、PR 是否创建及其 number/state、required check 的 PENDING/PASS/FAIL、
Actions run ID、mergeability/conflict、merge 和 branch deletion。不要要求
`docs/LATEST_FEEDBACK.md` 持续复制这些会在文档 commit 后立即变化的状态，也原则上不因单纯
发生 commit、push、PR create、CI PASS、merge 或 branch delete 而创建 handoff 修正 commit。

`LATEST_FEEDBACK.md` 继续是 **INTERNAL DEVELOPMENT HANDOFF — MUTABLE**，只记录对下一工作
单元有价值的稳定工程状态，例如当前 Task ID、task-start baseline、短期任务分支、当前阶段的
工程含义、Task Spec / Benchmark version、作为正式证据对象的 implementation commit、Candidate
Result 与 qualification、已知限制、hardware authorization/validation 和下一推荐工作单元。
可以记录 task-start baseline、frozen implementation commit、Candidate Result 对应 commit、
release commit 或 verified evidence commit 等稳定 SHA；不要把随下一 commit 失效的 current
`HEAD` 当作长期 handoff 状态。tag/release 的“未创建”等稳定结论可按任务需要保留。

算法 Candidate 的两阶段证据链不变：先形成固定 implementation commit，再针对该精确 SHA
运行正式 benchmark 并形成 Candidate Result。默认 checkpoint 权限不能把 implementation 与
formal Result 混为无法追溯的单一提交。

未来 `NEXT_COMMAND` 建议显式分为四层授权：Task-start authorization（fetch、创建短期分支、
task-scoped 修改和安全验证）、Review Checkpoint authorization（默认允许 task-scoped commit、
正常 push 当前分支和 remote review report）、PR authorization（默认不包含）以及 Merge /
cleanup / release authorization（均不包含，分别按现有制度授权）。

## 算法开发流程

算法成员的标准路径为：

```text
develop
  -> feature/algo-<short-name>
  -> unit test
  -> synthetic DRY_RUN
  -> Review Checkpoint commit / push
  -> remote review
  -> user-authorized PR
  -> software CI
  -> maintainer review
  -> user-authorized merge to develop
```

算法任务通常只修改算法、算法测试和必要算法文档。authority、ownership、Runtime safety、
hardware manager 和 hardware driver 不属于普通算法任务范围；确需修改时必须明确提出 API
或安全边界变化并接受维护者 review。

v0.5.0 Balance Recovery 的能力递进、Milestone、异步研发轨、Task Spec 与 benchmark 原则见
[算法研发路线](ALGORITHM_ROADMAP.md)。详细的控制器契约、测试命令和硬件边界见
[算法开发者指南](ALGORITHM_DEVELOPER_GUIDE.md)。

## Pull Request 与 CI

推荐的 PR 目标为：

| 来源 | 目标 |
| --- | --- |
| `feature/*`、`fix/*`、`docs/*` | `develop` |
| `release/*` | `master` |
| `hotfix/*` | `master` |

每个 PR 至少应包含：

- 清晰的工作范围和兼容性说明；
- 与风险相称的软件测试结果；
- WindArmor Software CI PASS；
- 文档和测试与行为同步；
- maintainer review；
- 未执行硬件验证时明确写明“未执行”或“等待实机验证”。

团队规模较小时不需要制造额外流程层级，但 `master` 仍不应成为直接日常开发入口。

## Hardware authorization boundary

软件流程与真实硬件授权相互独立。算法或控制改动即使已经通过单元测试、synthetic DRY_RUN、
PR、CI 和 `develop` 集成，也不能据此启动 actuator。

需要真实硬件时，流程仍是：

```text
maintainer review
  -> 确定 bounded values
  -> 明确 hardware scope
  -> 用户/operator 独立授权
  -> bounded hardware smoke test
  -> evidence review
```

任何带电场景继续执行 [`AGENTS.md`](../AGENTS.md) 的十项授权门槛。历史 PASS、软件 CI、
fake/mock、代码合并或分支状态都不能替代本次硬件授权。

## Release branch

`release/*` 是按需使用的冻结分支，不要求每个版本长期保留。当下一版本进入 RC，而
`develop` 还需要继续其它开发时，可以从 `develop` 建立例如 `release/v0.5.0`。

冻结后的 release branch 只接收：

- bug fix；
- documentation；
- version metadata；
- release notes；
- verification-driven fix。

不得再加入新 feature。release branch 完成验证后通过 PR 合入 `master`，确认 CI 与发布
门槛后创建 tag；其中必要修复必须同步回 `develop`。

## Hotfix

正式版本出现紧急缺陷时，从 `master` 创建 `hotfix/<issue>` 或版本化分支，例如
`hotfix/v0.4.1`：

```text
master
  -> hotfix/v0.4.1
  -> test / review
  -> PR to master
  -> release tag
  -> 同步修复到 develop
```

不要只在 `develop` 修复已发布版本的问题。发布完成后必须把同一修复 merge 或 cherry-pick
回 `develop`，防止下一版本重新引入缺陷。

## Flight API 变更规则

从 v0.4.0 起，以下内容是共享开发者 API：

- `FlightController`；
- `FlightState`；
- `FlightCommand`；
- controller factory contract。

这些 contract 不能作为普通内部重构静默改变。变更必须：

- 明确标记 API change；
- 更新 [Flight Control API](FLIGHT_CONTROL_API.md)；
- 更新 [算法开发者指南](ALGORITHM_DEVELOPER_GUIDE.md)；
- 更新相关测试；
- 提前通知并协调算法开发成员；
- 尽量保持 backward compatibility，无法保持时提供 migration path。

应避免共享 API 在集成期间无通知漂移，使短期算法分支直到合并时才发现不兼容。

## GitHub branch protection

维护者已确认仓库的 branch protection 已建立。具体规则可能继续调整，精确生效配置以
GitHub 当前设置为准；以下条目是本仓库应保持的保护目标，不用于虚构或替代远端配置。

`master` 推荐：

- Require pull request before merging；
- Require status checks；
- 将 `WindArmor Software CI` 设为 required；
- Block force push；
- Block deletion；
- 可根据团队安排要求至少 1 位 reviewer approval。

`develop` 推荐：

- Require status checks；
- 推荐通过 PR 合入；
- Block force push；
- 可根据团队安排要求至少 1 位 reviewer approval。

是否启用 reviewer 数量要求由维护者结合团队规模决定；不要把推荐状态写成已经生效的事实。

## Agent / Codex 分支限制

分支模型本身不会赋予 AI agent 隐式 Git 权限。创建或切换分支、merge、rebase、删除分支或
执行其它 Git 状态变更前，必须有用户针对当前任务的明确授权；普通 task-scoped commit/push
仅按上述 Remote Review Checkpoint 规则获得默认授权。

用户授权某个任务分支后，agent 只能在该分支和约定 scope 内工作，不得擅自切换
`master`、扩大合并范围、force push 或删除分支。仓库存在 `develop`、checkpoint tests PASS
或 remote review PASS 都不会改变这一规则。

## 常见场景示例

### 新算法功能

从 `develop` 建立 `feature/algo-<short-name>`，完成算法、单元测试和 synthetic DRY_RUN，
通过 PR、CI 和维护者 review 合入 `develop`。需要 actuator 冒烟测试时另行准备受限场景并
取得用户授权。

### 普通运行时缺陷

面向下一版本的普通修复使用 `fix/<short-name>` 并合入 `develop`。如果缺陷影响当前已发布
版本且需要立即发布补丁，则改用从 `master` 建立的 `hotfix/*`。

### 文档更新

独立文档工作使用 `docs/<short-name>` 并通过 PR 合入 `develop`。发布冻结期间与当前版本
直接相关的发布文档修复可以进入相应 `release/*`。

### 下一版本发布

若不需要并行冻结，维护者可以直接将经过发布审查的 `develop` 通过 PR 提升到 `master`；
若需要继续其它开发，则先创建 `release/vX.Y.Z`。两种路径都必须完成 CI、集成审查、文档、
必要硬件验证和 release readiness review，之后才能在 `master` 创建 tag。
