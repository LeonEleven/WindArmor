# WindArmor 开发协作流程

本文面向 WindArmor 的人类开发成员和维护者，定义 v0.4.0 发布后的分支、Pull Request、
CI、硬件授权与发布协作方式。仓库级强制规则仍以根目录 [`AGENTS.md`](../AGENTS.md) 为准；
本文不能放宽其中的硬件安全门槛或 Git 操作限制。

当前正式稳定版本为 v0.4.0。`develop` 是维护者核心研发主线，`dev` 是从 `master` 创建的
协作者开发集成线；两个分支长期并行存在，`dev` 不替代 `develop`。分支存在性与任务
实际基线以 Git / GitHub 当前状态为准；分支模型不构成任何 Git 操作的隐式授权。

## 分支模型

```text
master
  |
  |-- develop（维护者核心研发）
  |     |-- feature/*
  |     |-- fix/*
  |     |-- docs/*
  |     `-- experiment/*
  `-- dev（协作者开发集成）
        |-- feature/*（算法任务使用 feature/algo-*）
        |-- fix/*
        |-- docs/*
        `-- experiment/*

hotfix/*  <- master
release/* <- develop（按需）
```

- `master` 保存稳定、已验证、可发布的主线。
- `develop` 承载维护者核心研发及下一版本集成，原有核心研发流程保持不变。
- `dev` 承载协作者开发集成，默认任务分支从 `dev` 创建并通过 PR 返回 `dev`。
- 两条开发线平行存在、互不替代；分支图表示职责与起点，不授权自动同步代码。
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

`develop` 是维护者核心研发与下一版本的集成主线。维护者核心任务的 feature、fix 和 docs
仍从 `develop` 创建并通过 PR 返回 `develop`，再在发布周期中整体提升到 `master`。
协作者在 `dev` 上的开发不改变维护者的核心任务、基线或集成节奏。

`develop` 可以包含尚未完成最终硬件验证的新功能，但必须保持：

- 工作空间可构建；
- WindArmor Software CI 为 green；
- 无已知严重破坏；
- 安全机制没有被删除、绕过或弱化；
- 未验证的硬件行为和 release blocker 被清楚记录。

代码进入 `develop` 只代表软件集成状态，不代表允许访问 CAN、串口、GPIO、PWM、ESC、
电机或风扇。

## dev

`dev` 是从 `master` 创建的协作者开发集成线，与 `develop` 长期并行存在。
协作者先获取最新 `dev`，基于 `origin/dev` 创建独立任务分支，完成软件测试后推送任务
分支并向 `dev` 创建 PR，等待 CI 和维护者 review；通过后由维护者批准合入 `dev`。
`dev` 同样需要保持可构建、软件 CI green、安全机制完整，并清楚记录未验证的硬件行为。

协作者不得自行向 `develop` 或 `master` 合并。`dev` 上经过验证的成果是否进入 `develop`，
必须由维护者另行决定范围、兼容性、验证要求与集成方式，并取得相应 Git 操作授权。
不允许自动执行 `dev` 与 `develop` 之间的 merge、rebase 或 cherry-pick；也不得自动把
`develop` 的新代码或新算法任务文件带入 `dev`。`dev` 不直接改变 `master` 的发布管理
或安全门槛，代码进入 `dev` 不代表任何硬件执行授权。

## 功能、修复、文档与实验分支

协作者的短期任务分支默认从最新 `dev` 创建，维护者核心任务仍从最新 `develop` 创建。
一个分支只承载一个独立工作单元，并在任务开始时明确基线和 PR 目标：

| 类型 | 命名 | 用途 |
| --- | --- | --- |
| 功能 | `feature/<short-name>` | 新功能或可独立 review 的能力 |
| 修复 | `fix/<short-name>` | 下一版本普通缺陷修复 |
| 文档 | `docs/<short-name>` | 独立文档任务 |
| 实验 | `experiment/<short-name>` | 不承诺进入发布线的探索 |

名称使用小写英文和连字符，例如 `feature/algo-pitch-control`、`fix/runtime-restart`、
`docs/algorithm-tuning-guide` 或 `experiment/algo-lqr`。不要把用户名作为主分类。

任务分支完成后执行测试、push 并创建 PR：协作者目标为 `dev`，维护者核心任务目标为
`develop`；CI 与维护者 review 通过、获得合并授权后才合并，分支清理也需相应授权。
不要在一个分支中混入无关重构、多个独立功能或顺手修复。

## 算法开发流程

协作者算法成员的标准路径为：

```text
dev
  -> feature/algo-<short-name>
  -> unit test
  -> synthetic DRY_RUN
  -> push task branch / PR to dev
  -> software CI
  -> maintainer review
  -> maintainer-approved merge to dev
```

算法任务通常只修改算法、算法测试和必要算法文档。authority、ownership、Runtime safety、
hardware manager 和 hardware driver 不属于普通算法任务范围；确需修改时必须明确提出 API
或安全边界变化并接受维护者 review。

详细的控制器契约、测试命令和硬件边界见
[算法开发者指南](ALGORITHM_DEVELOPER_GUIDE.md)。

维护者核心算法任务仍按 `develop -> feature/algo-* -> PR to develop` 工作；协作者不得
自行将任务转向该主线。`dev` 成果进入 `develop` 需要维护者另行决定。

## Pull Request 与 CI

推荐的 PR 目标为：

| 来源 | 目标 | 适用范围 |
| --- | --- | --- |
| `feature/*`、`fix/*`、`docs/*`、`experiment/*` | `dev` | 协作者任务；默认从 `dev` 创建 |
| `feature/*`、`fix/*`、`docs/*`、`experiment/*` | `develop` | 维护者核心任务；从 `develop` 创建 |
| `release/*` | `master` | 维护者发布任务 |
| `hotfix/*` | `master` | 维护者稳定版本紧急修复 |

两条开发线之间不提供默认 PR 或自动同步路径，具体成果集成由维护者另行决定。

当前 `dev` 基线的 [CI workflow](../.github/workflows/ci.yml) 仅对 `master` 的 push/PR
自动触发，并保留 `workflow_dispatch` 入口；向 `dev` 创建 PR 暂不会自动触发该工作流。
维护者需另行安排对待合并提交的软件 CI 验证并关联准确 SHA，或在独立任务中配置 `dev`
的 PR 检查。没有 CI 结果不能视为 PASS，也不能据此跳过合并门槛；workflow 和 branch
protection 的调整需要独立任务授权。

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
PR、CI 和 `dev` 或 `develop` 集成，也不能据此启动 actuator。

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
回 `develop`，防止下一版本重新引入缺陷。上述操作由维护者组织并另行授权，不授权
协作者向 `master` 或 `develop` 自行合并。若 `dev` 也受同一缺陷影响，维护者另行决定
修复范围与验证方式，不自动执行 `dev` 与 `develop` 之间的代码同步。

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

## 推荐 GitHub branch protection

以下是建议配置，本文件不表示 GitHub 当前已经启用这些设置。

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

`dev` 推荐：

- Require pull request before merging；
- Require status checks，将 `WindArmor Software CI` 设为 required；
- Block force push 与 deletion；
- 由维护者 review，按团队安排要求 reviewer approval。

是否启用 reviewer 数量要求由维护者结合团队规模决定；不要把推荐状态写成已经生效的事实。

## Agent / Codex 分支限制

分支模型不会赋予 AI agent 任何隐式 Git 权限。任何 agent 在创建或切换分支、merge、
rebase、push、删除分支或执行其它 Git 状态变更前，都必须获得用户针对当前任务的明确授权。

用户授权某个任务分支后，agent 只能在该分支和约定 scope 内工作，不得擅自切换
`master`、扩大合并范围、force push 或删除分支。仓库存在 `dev` 或 `develop` 也不会改变
这一规则，不得自动在两条开发线之间 merge、rebase 或 cherry-pick。

历史交接、PR 和验证证据保留当时的分支与 SHA，不按当前协作者流程改写。例如
[`LATEST_FEEDBACK.md`](LATEST_FEEDBACK.md) 中 2026-08-27 任务的 `develop` 未创建说明
及后续步骤是该任务的历史记录，不能作为当前分支状态或新的 Git 操作授权。

## 常见场景示例

### 新算法功能

协作者从最新 `dev` 建立 `feature/algo-<short-name>`，完成算法、单元测试和 synthetic
DRY_RUN，通过 PR、CI 和维护者 review 合入 `dev`。维护者核心算法任务仍使用 `develop`
作为基线和 PR 目标。需要 actuator 冒烟测试时另行准备受限场景并取得用户授权。

### 普通运行时缺陷

协作者的普通修复从 `dev` 创建 `fix/<short-name>` 并通过 PR 合入 `dev`；维护者核心研发
修复仍从 `develop` 创建并返回 `develop`。如果缺陷影响当前已发布
版本且需要立即发布补丁，则改用从 `master` 建立的 `hotfix/*`。

### 文档更新

协作者独立文档工作从 `dev` 创建 `docs/<short-name>` 并通过 PR 合入 `dev`；维护者核心
文档任务仍从 `develop` 创建并返回 `develop`。发布冻结期间与当前版本直接相关的发布
文档修复可以进入相应 `release/*`。

### 下一版本发布

若不需要并行冻结，维护者可以直接将经过发布审查的 `develop` 通过 PR 提升到 `master`；
若需要继续其它开发，则先创建 `release/vX.Y.Z`。两种路径都必须完成 CI、集成审查、文档、
必要硬件验证和 release readiness review，之后才能在 `master` 创建 tag。
