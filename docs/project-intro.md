# o-pipeline 自动化研发流水线 · 跨团队使用说明

| 项目 | 内容 |
|---|---|
| 文档编号 | OP-DOC-001 |
| 版本 | v1.0 |
| 适用对象 | 研发团队、平台工程团队、QA/测试团队、设计协作团队 |
| 适用范围 | 基于 GitLab 的代码仓库，需求以 Markdown/纯文本文档 + 可选 Figma 设计稿形式提供 |
| 维护入口 | 项目仓库 `docs/project-intro.md`，以仓库 README 与 ADR 为最终事实来源 |

**修订记录**

| 版本 | 日期 | 修订人 | 说明 |
|---|---|---|---|
| v1.0 | — | LYao | 首次发布 |

---

## 1. 概述

### 1.1 背景

软件开发中「需求文档 → 已实现、已审查的代码」这一链路长期依赖人工推进：需求分析、方案设计、任务拆解、实现、自测、代码审查各环节之间缺乏自动化衔接，交付周期与质量高度依赖个人经验。

本项目（下称 **o-pipeline**）在 mozi 平台上以三个独立插件（skill）的形式实现该链路的自动化：输入 GitLab 仓库、目标分支与需求文档，输出已实现、已通过内部审查并推回远端分支的代码，全程无需人工确认。

### 1.2 目标与非目标

**目标**

- 将需求分析的产物标准化，形成可执行、可审查、可追溯的规格工件；
- 实现阶段按任务清单逐项推进，配套自动化验证与失败回滚；
- 终审阶段对实现进行多轴审计，输出结构化审查结论；
- 全程零人工确认；仅在前置条件不满足时以明确信号转人工介入。

**非目标**

- 不替代团队评审会（review 结论为自动审计，最终合入策略由团队自行决定）；
- 不负责分支合入、发布与部署；
- 不处理无测试框架下的强测试保障（无框架时采用轻量断言降级验证，详见 3.3）；
- 不承担 Figma 设计的交互验证（仅验证视觉与结构静态一致性，详见第 5 章）。

### 1.3 术语表

| 术语 | 定义 |
|---|---|
| mozi | 承载本流水线的任务编排平台，支持发布插件（skill）与注册 mission（有向图流水线） |
| mission | mozi 上的一组节点（node）与边（edge）定义，即本流水线的运行实例 |
| DocSpec | 需求文档在目标分支上的存放目录（单文件或文件目录均可） |
| OpenSpec 三件套（trio） | o-spec 阶段产出的三个规格工件：`proposal.md`（做什么/为什么）、`design.md`（怎么做）、`tasks.md`（可执行任务清单） |
| 接力（relay） | 节点间状态传递机制：每个节点重新克隆目标分支、完成工作、提交并推送，下游节点通过克隆继承上游提交 |
| phase commit | 每个阶段结束时对目标分支产生的唯一一次提交（含推送） |
| exit_code | 节点输出中的退出码：`0` 成功 / `1` 失败 / `2` 阻塞（唯一转人工信号） |
| block_reason | 退出码为 `2` 时随附的机器可读阻塞原因标识 |
| verdict | o-review 阶段的终审结论：`pass` / `needs-rework` / `fail` |

---

## 2. 总体架构与设计原则

### 2.1 架构总览

```
┌──────────────────────────────────────────────────────────────────────┐
│                    使用方（人工）前置准备                                │
│   GitLab 建分支 → DocSpec/ 放入需求文档 → push → mozi 填写并启动 mission │
└──────────────────────────────────┬───────────────────────────────────┘
                                   ▼
     ┌────────────┐   push    ┌────────────┐   push    ┌────────────┐
     │  o-spec    │ ────────► │  o-build   │ ────────► │  o-review  │
     │  需求分析    │   接力     │  任务实现    │   接力     │  审计与终审  │
     └────────────┘           └────────────┘           └────────────┘
           │                        ▲                         │
           │        （可选反馈环）      │                         │
           └───── verdict=needs-rework 时，o-build 消费 REVIEW.md ┘
                          issues_remaining 再执行一轮
```

三个节点均为独立发布的插件（`skills/o-spec`、`skills/o-build`、`skills/o-review`），由 mission 定义文件（`examples/feature-pipeline.yaml`）串联为 `o-spec → o-build → o-review`，并以 `review` 节点为流水线成功终点。

### 2.2 设计原则

**原则一：阶段解耦，单点职责。**

三个节点分别承担需求分析、任务实现、审计终审，产品形态为三个可独立发布、独立复用、独立升级的插件，节点间不共享运行上下文。

**原则二：状态经远端分支接力传递。**

依据 ADR-0001，mozi 各节点不共享文件系统（每个节点为独立会话与临时目录）。历史方案（y-spec/y-build/y-verify）因「上游未推送、下游无仓库地址」导致状态在节点边界丢失，表现为"规格已提交但实现阶段找不到产物"。本方案规定：每个节点以 `gitlab_url + branch` 为输入重新克隆目标分支，工作完成后提交并推送；下游节点克隆即继承上游提交。节点间 JSON 输出仅携带小型契约（退出码、提交哈希、计数、终审结论），不传递文件路径或文件内容。

**原则三：零人工确认，分级退出，阻塞即转人工。**

- 节点执行期间不发起任何询问（禁止向用户提问）；能决策则决策，不能决策则按规格阻塞。
- 退出码三级语义：`0` 成功（下游可继续）、`1` 失败（已完成可完成部分，现场留存供审查）、`2` 阻塞（前置条件不满足，唯一转人工信号，附机器可读 `block_reason`）。
- 软性歧义（需求有多种合理解读）不构成阻塞：取最优解读、记录于 `assumptions`、下调 `confidence`。
- 关键需求不得静默丢弃：例如文档含 Figma 链接但未提供 token 时直接阻塞，避免生成缺失视觉需求的规格。

**原则四：下游自检上游产物（契约保障）。**

o-build 与 o-review 在开展自身工作前，必须先验证 `openspec/<spec_dir>/` 下三件套工件存在且非空；校验失败即退出码 `2`（`spec_artifacts_missing`），将问题定位至上游未推送，而非自行编造工作内容。

**原则五：方法论内联，对齐行业标准工作流。**

阶段划分对齐 OpenSpec 与 superpowers 两套开源生态的标准生命周期（brainstorming → writing-plans → executing-plans → code-review / propose → apply → verify）。规格产物采用 OpenSpec 三件套格式；实现阶段在具备测试框架时采用 TDD（先写红测试）；审查阶段执行规格一致性、代码质量、测试三轴审计。相关方法论已内联于各 SKILL.md，插件自包含，不依赖运行时外部子技能。

**原则六：单需求隔离，支持多需求累积。**

每个需求在分支上建立独立规格目录 `openspec/<UTC时间戳>-<slug>/`。时间戳采用零填充定宽 UTC 格式，保证字典序即时间序；下游以 `openspec/[0-9]*/` 过滤后按字典序取最新目录，因此同一分支可顺序累积多个需求而不互相覆盖。

---

## 3. 流程定义

### 3.1 端到端流程

| 阶段 | 责任方 | 动作 |
|---|---|---|
| 准备 | 使用方（人工） | 在 GitLab 创建目标分支；将需求文档放入分支 `DocSpec/` 并推送；在 mozi 启动 mission 时填写 `gitlab_url`、`branch`、`doc_url`（含 Figma 设计稿时另填 `figma_token`） |
| 阶段一 | o-spec | 克隆并检出分支 → 解析并读取需求文档 → 对代码库进行 grounding（需求→文件映射）→ 合成 OpenSpec 三件套 → 覆盖率自检 → 提交并推送 |
| 阶段二 | o-build | 克隆并检出分支 → 自检上游规格产物 → 解析任务清单 → 逐任务「验证→实现→验证」→ 提交并推送 |
| 阶段三 | o-review | 克隆并检出分支 → 自检上游产物 → 多轴审计 → 自动修复低风险问题 → 出具终审结论 → 撰写 REVIEW.md 并推送 |
| 结果交付 | o-pipeline | 终审结论与相关工件已推送至目标分支；mission 输出含 `verdict`、`commit_hash`、`pushed_branch` 等字段 |

每个节点的执行模式完全一致：**克隆 → 自检上游产物 → 执行本阶段工作 → 提交 → 推送**。推送失败一律按阻塞处理（退出码 `2`），因为下游节点依赖本次推送。

### 3.2 阶段一：o-spec（需求分析）

| 步骤 | 内容 | 异常处理 |
|---|---|---|
| 1. 克隆与检出 | 克隆仓库并检出目标分支 | 分支不存在于远端 → `2 / branch_not_on_remote`（不代建分支） |
| 2. 解析 doc_url | 支持三种形式：仓库内相对路径、目录（递归匹配 `**/*.md`、`**/*.txt`）、GitLab UI 完整 URL | 解析结果为空 → `2 / doc_url_not_found` |
| 3. 阅读与 grounding | 读取全部需求文档；遍历代码库，为每条需求定位其将影响的具体文件/模块，形成 req→file 映射（写入 design.md） | 需求在代码库中完全无法定位 → 阻塞 |
| 4. 输入分类 | 判定 `doc_type`：`vague-requirement`（高层/一句话需求）/ `detailed-change`（描述明确可直接实现）/ `task-list`（文档本身即任务清单）；输出 `confidence`（0~1）与 `assumptions[]`；需求 slug 需 ASCII 化（非英文需求译为英文关键词） | 无歧义直译的 task-list → `confidence: 1.0` |
| 4a. Figma 抓取（可选） | 详见第 5 章 | token 缺失/无效 → 阻塞 |
| 5. 规格合成 | 输出三件套：`proposal.md`（背景与变更说明）、`design.md`（方案、权衡、req→file 映射）、`tasks.md`（每条 `- [ ]` = 文件 + 意图的可执行清单） | 仅允许写 `openspec/` 目录，不触碰其他文件 |
| 6. 覆盖率自检 | 回读原始需求文档，逐条核对每条需求在三件套中的落点（proposal 对应行 / tasks 对应任务 / design 映射项） | 存在无落点需求：补齐后复查；确属歧义或越界 → `2 / requirement_uncovered` |
| 7. 硬阻塞检查 | 文档不可读（二进制/空）、目标区域完全无法定位 | 软歧义不作硬阻塞（记 assumption、降 confidence） |
| 8. 提交与推送 | 以固定身份 `mozi_agent` 提交三件套并推送 | 推送失败 → `2 / push_failed` |

> 说明：第 6 步覆盖率自检为本方案原创的防漂移机制。LLM 起草规格存在漏项风险，显式回读原文档逐条核对可捕获整条需求的遗漏，确保规格对需求全覆盖后才进入实现阶段。

### 3.3 阶段二：o-build（任务实现）

| 步骤 | 内容 | 异常处理 |
|---|---|---|
| 1. 克隆与检出 | 重新克隆目标分支（不继承 o-spec 文件系统，但继承其提交） | 分支缺失 → `2 / branch_not_on_remote` |
| 2. 自检上游产物 | 定位 `openspec/` 最新规格目录，校验三件套齐全且非空 | 缺失 → `2 / spec_artifacts_missing`（指向上游） |
| 3. 解析任务清单 | 解析 tasks.md 全部 `- [ ]` 条目，计入 `tasks_total` | 任务数为零 → `2 / tasks_empty` |
| 3a. 消费审查反馈（复跑场景） | 若存在 REVIEW.md（上一轮 o-review 产出）：将已勾选任务按审查意见翻回未勾选并标注；新增问题补录任务条目；重复问题去重 | 仅在 needs-rework 反馈环触发时执行 |
| 4. 逐任务循环 | 每任务依次执行：① 编写验证——具备测试框架（jest/pytest/go test 等）时编写真实测试并要求先红；无框架（静态产物/配置/文档类交付）时采用轻量 bash 断言（文件存在、标记匹配、格式合法、结构校验）作为降级验证；② 实施满足验证的最小改动；③ 运行任务验证与全量测试套件 | 失败处理：仅回滚本任务触碰的文件（`git checkout --`），不回滚整树；换方案重试至多 3 次；超过 3 次则计入 `tasks_failed`，在 tasks.md 记录失败原因，继续后续任务（阶段不因单任务失败中止） |
| 4a. UI 任务消费 Figma 产物 | 任务对应 `figma/` 渲染图时，读取 PNG 与节点 JSON，按渲染图实现并逐字引用 JSON 中的文本 | 不持有 token、不调用 Figma API，仅消费分支上已有产物 |
| 5. 硬阻塞检查 | 任务无法定义任何可判定的完成判据 / 目标文件无法定位且无法创建 | 无测试框架不构成阻塞；任务难度不构成阻塞（记 `1`） |
| 6. 提交与推送 | 提交实现与更新后的 tasks.md | `tasks_failed == 0` → 退出码 `0`；存在失败任务 → 退出码 `1`（交由 o-review 审计） |

### 3.4 阶段三：o-review（审计与终审）

| 步骤 | 内容 | 异常处理 |
|---|---|---|
| 1. 克隆与检出 | 重新克隆目标分支（继承 o-build 提交） | 分支缺失 → `2 / branch_not_on_remote` |
| 2. 自检上游产物与实现 | 校验三件套存在；通过 tasks.md 判定 o-build 是否实际执行（无任何 `- [x]` 且无 `> failed:` 记录 → 视为空实现） | 产物缺失 → `2`；空实现 → `verdict: fail`、退出码 `1`（仍撰写并提交 REVIEW.md） |
| 3. 多轴审计 | ① 规格一致性：代码对照 proposal.md 与 tasks.md（未完成任务 = med）；② 代码质量：明显缺陷、错误处理缺口、注入/XSS/SQLi、死代码；③ 测试：有测试框架则运行套件（失败 = high），无框架则复跑 o-build 断言或结构检查；④ 视觉一致性（存在 `figma/` 时）：实现界面对照渲染图，核对布局、文本、间距、配色 | 全部问题记录于 `issues_found[]`：`{severity: high|med|low, file, line, message}` |
| 4. 自动修复 | 修复 low/med 级、改动安全且局部的问题（文字错误、缺失判空、测试修复、死代码清除）；不处理 high 与架构级问题 | 修复后重跑套件确认无回归；已修复问题移入 `issues_fixed[]`，其余留存 `issues_remaining[]` |
| 5. 终审结论 | `pass`：无 high 遗留、套件通过、任务全部勾选；`needs-rework`：存在值得返工一轮的遗留问题（可触发反馈环）；`fail`：规格未实现 / 套件失败且含 high 问题 / 空实现 | pass → 退出码 `0`；needs-rework、fail → 退出码 `1` |
| 6. 撰写 REVIEW.md 并推送 | REVIEW.md 记录结论、任务完成数、测试结果与三份问题清单；如实上报 `pushed` / `pushed_branch` | 推送失败 → `2 / push_failed`，`pushed: false` |

### 3.5 节点间衔接机制

1. **接力**：无共享工作区，全部状态经远端分支传递。每个节点执行 `克隆 → 工作 → 提交 → 推送`，推送失败为硬阻塞。
2. **产物定位公约**：节点间不传路径；规格目录以 `openspec/<UTC时间戳>-<slug>/` 命名，按时间戳前缀字典序取最新（`openspec` 下的非规格目录经 `[0-9]*` 过滤排除）。
3. **小型契约输出**：节点间 JSON 仅含 `exit_code / status / block_reason / commit_hash / 任务计数 / verdict` 等字段（详见第 4 章）。
4. **可选反馈环**：mission 支持配置 `review → build` 反馈边（条件 `verdict == "needs-rework"`），使 o-build 消费 REVIEW.md 的 `issues_remaining` 执行返工轮次；该能力已内置支持。
5. **节点级运行配置**：各节点 `retry: max_attempts: 3`；执行超时：o-spec 1800s、o-build 3600s、o-review 1800s。

---

## 4. 接口定义（输入与输出）

### 4.1 Mission 级输入

| 参数 | 类型 | 必填 | 消费节点 | 说明 |
|---|---|---|---|---|
| `gitlab_url` | str | 是 | 全部 | GitLab 克隆地址（`.git` 结尾），各节点据此重新克隆 |
| `branch` | str | 是 | 全部 | 目标开发分支。使用方需提前创建并在 `DocSpec/` 放入需求文档后推送到远端；流水线仅检出、不代建分支 |
| `doc_url` | str | 是 | 仅 o-spec | 需求文档定位：仓库内相对路径 / 目录（递归匹配 .md/.txt）/ GitLab UI URL |
| `figma_token` | str | 否 | 仅 o-spec | Figma 个人访问令牌。需求文档不含 Figma 链接时可留空；含链接时必填且须有效，否则硬阻塞（见第 5 章） |

### 4.2 节点级输出契约

| 字段 | o-spec | o-build | o-review | 用途 |
|---|---|---|---|---|
| `exit_code` | ✓ | ✓ | ✓ | `0` 继续 / `1` 留现场 / `2` 转人工 |
| `status` | ✓ | ✓ | ✓ | success / failure / blocked，与 exit_code 对应 |
| `block_reason` | 仅 `2` | 仅 `2` | 仅 `2` | 机器可读阻塞原因（如 `doc_url_not_found`、`push_failed`、`figma_token_invalid`），供平台判断与人工定位 |
| `commit_hash` | ✓ | ✓ | ✓ | 本阶段提交 SHA（40 位十六进制），用于审计追溯 |
| `doc_type` | ✓ | — | — | 需求分类结果，供 mission 按需分流 |
| `confidence` / `assumptions[]` | ✓ | — | — | 需求歧义度信号（0~1）与推测记录，可供条件边（如低置信度加人工审批）使用 |
| `tasks_total` / `tasks_done` / `tasks_failed` | — | ✓ | — | 任务总数 / 通过数 / 失败数，供审查节点与人工查阅进度 |
| `verdict` | — | — | ✓ | 终审结论：pass / needs-rework / fail；needs-rework 为反馈环触发条件 |
| `issues_found` / `issues_fixed` / `issues_remaining` | — | — | ✓ | 审计问题明细：发现 / 已自动修复 / 留存待返工（`{severity, file, line, message}`） |
| `pushed` / `pushed_branch` | — | — | ✓ | 终审推送是否成功及目标分支 |

### 4.3 阻塞原因清单（block_reason 常用值）

| 标识 | 含义 | 处置建议 |
|---|---|---|
| `branch_not_on_remote` | 目标分支不在远端 | 检查分支创建与推送 |
| `doc_url_not_found` | doc_url 未解析到任何文件 | 核对路径/目录/URL |
| `spec_artifacts_missing` | 上游规格产物缺失 | 确认 o-spec 是否成功推送 |
| `push_failed` | 阶段推送失败 | 检查远端权限/网络 |
| `tasks_empty` | 任务清单为空 | 检查 o-spec 产物 |
| `task_unverifiable` / `task_target_unresolvable` | 任务无判据 / 目标无法定位 | 人工评估任务描述 |
| `figma_link_without_token` | 检测到 Figma 链接但未提供 token | 补充 token 后重跑 |
| `figma_token_invalid` / `figma_fetch_failed` | token 失效 / 文件拉取失败 | 检查 token 权限与分享设置 |

---

## 5. Figma 设计稿接入规范

### 5.1 处理边界与原则

- **触发条件**：仅在需求文档中检测到 Figma 链接（`figma.com/file/<key>/...` 或 `figma.com/design/<key>/...`，提取 `file_key` 与可选 `node-id`）时才启用 Figma 处理；未检测到链接时整步跳过，不涉及令牌。
- **令牌边界**：`figma_token` 仅由 o-spec 消费；o-build 与 o-review 不持有令牌、不调用 Figma API，仅消费 o-spec 抓取并提交至分支的静态产物（接力机制的体现）。
- **完整性约束**：检测到 Figma 链接但令牌为空 → 硬阻塞（`figma_link_without_token`），禁止生成遗漏视觉需求的规格。

### 5.2 o-spec 抓取流程

```
检测到 Figma 链接？
 ├─ 否 → 跳过本步骤
 ├─ 是 + 令牌为空 → exit_code=2, figma_link_without_token
 └─ 是 + 令牌有效 → ① 令牌校验：GET /v1/files/<file_key>
                      ├─ 401/403 → exit_code=2, figma_token_invalid
                      ├─ 200     → 继续
                      └─ 400/404 → exit_code=2, figma_fetch_failed（file_key 无效）
                    ② 对每个链接执行两次 API 调用，产物落盘至 $spec_dir/figma/：
                      a. 节点树读取：GET /v1/files/<file_key>/nodes?ids=<node_id>
                         → 节点 JSON（文本、布局、填充、组件引用，即结构化"读取"）
                      b. 渲染图获取：GET /v1/images/<file_key>?ids=<node_id>&format=png&scale=2
                         → 渲染图 URL → 下载 PNG（2x 缩放）
```

产物为 `$spec_dir/figma/<n>.json` 与 `<n>.png`，随 o-spec 阶段提交推送至分支。design.md 中在各需求旁引用对应渲染图；proposal.md 中逐字引用节点 JSON 的文本内容，供实现阶段精确对齐。

### 5.3 下游节点消费方式

- **o-build（实现）**：任务涉及 UI 且存在对应渲染图时，读取 PNG（模型可多模态查看）与节点 JSON，按渲染图实现；文本内容自节点 JSON 逐字引用，保证与设计稿一致。
- **o-review（审计）**：实现界面对照渲染图执行视觉一致性审计，核对布局、文本、间距、配色；明显偏离（元素缺失、文本不符、布局破坏）记为 med/high 问题（整块缺失或页面结构不符 = high），轻微外观漂移记为 low。

### 5.4 常见阻塞场景

| 场景 | 结果 |
|---|---|
| 文档含 Figma 链接，token 未填 | `2 / figma_link_without_token` |
| token 失效或权限不足 | `2 / figma_token_invalid`（API 401/403） |
| 文件未分享给 token 对应账号 / file_key 错误 | `2 / figma_fetch_failed`（API 400/404） |

---

## 6. 接入指引（使用方操作手册）

### 6.1 前置条件

1. mozi 平台已发布 `o-spec`、`o-build`、`o-review` 三个插件（发布方式：Plugins → + publish → 依次打包上传 `skills/o-*` 目录的 zip）。
2. 已注册 mission（示例定义：`examples/feature-pipeline.yaml`）。
3. 目标分支已在 GitLab 创建，需求文档已放置于分支 `DocSpec/` 并推送至远端。

### 6.2 启动流程

1. 在 mozi Start Run 界面填写 mission 输入：`gitlab_url`、`branch`、`doc_url`；需求文档含 Figma 链接时一并填写 `figma_token`。
2. 启动运行。三个节点依序执行，全程无需人工确认。
3. 运行结束后，从 mission 输出读取终审字段（`status`、`exit_code`、`verdict`、`commit_hash`、`pushed_branch`），或在目标分支上查看 `openspec/<spec_dir>/REVIEW.md` 与代码变更。

### 6.3 可选配置

| 需求 | 配置方式 |
|---|---|
| 阻塞或失败时跳过后续阶段 | 为下游边配置条件表达式（示例：`ctx.build.exit_code == 0`） |
| needs-rework 自动返工闭环 | 增加 `review → build` 反馈边，条件 `ctx.review.verdict == "needs-rework"`（o-build 已内置 REVIEW.md 消费逻辑） |
| 低置信度需求人工复核 | 基于 `confidence` 配置条件边或人工审批节点 |

---

## 7. 已知限制与演进方向

| 编号 | 限制 | 说明 | 演进方向 |
|---|---|---|---|
| L1 | Figma 仅静态一致性 | 仅覆盖节点结构、文本、配色、布局；不验证交互动效、组件变体、响应式行为 | 按需扩展交互评审能力 |
| L2 | 无归档步骤 | OpenSpec 标准生命周期含 archive 收尾，当前省略 | 在 o-review 末尾补充归档步骤 |
| L3 | 每轮三次克隆开销 | 每节点独立克隆（每轮 3 次），耗时秒级至分钟级 | 平台若提供可靠的共享存储契约可评估优化 |
| L4 | 单分支串行累积 | 多个需求按时间戳顺序在同一分支累积，一次运行处理最新需求 | 支持多需求并行或任务级并发 |
| L5 | 无测试框架时验证降级 | 静态/配置类交付采用 bash 断言，覆盖强度低于真实测试 | 按交付类型沉淀断言模板库 |

---

## 8. 附录

### 8.1 与业内方法论对照

| 本方案环节 | 对照生态 |
|---|---|
| o-spec 需求探索与假设显式化 | superpowers: brainstorming |
| OpenSpec 三件套产物 | openspec: propose / new-change |
| o-spec 覆盖率自检 | 本方案原创（两大生态均无"写完回读逐条核对"） |
| o-build 逐任务执行 | superpowers: executing-plans |
| o-build 有测试框架时 TDD | superpowers: tdd |
| o-build 无框架断言降级 | 本方案原创 |
| o-review 规格-代码一致性审计 | openspec: verify-change |
| o-review 代码质量审计 | superpowers: code-review |
| o-review 自动修复低风险问题 | 本方案扩展（code-review 生态仅报告不修复） |

### 8.2 相关文档索引

| 文档 | 位置 | 说明 |
|---|---|---|
| 项目说明 | `README.md` | 总体介绍与运行说明 |
| 术语表 | `CONTEXT.md` | 全项目术语规范 |
| 架构决策记录 ADR-0001 | `docs/adr/0001-relay-state-via-remote-branch.md` | 节点间状态接力方案论证 |
| 方法论对齐 | `docs/skill-alignment.md` | 与 OpenSpec / superpowers 的逐环节对照 |
| 插件定义 | `skills/o-spec/SKILL.md`、`skills/o-build/SKILL.md`、`skills/o-review/SKILL.md` | 各节点详细执行规范 |
| 流水线定义 | `examples/feature-pipeline.yaml` | mission 注册示例与可选项配置 |