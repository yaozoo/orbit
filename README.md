<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://img.shields.io/badge/Orbit-OpenSpec_%2B_Superpowers-blue?style=for-the-badge">

![Orbit Demo](demo.gif)
  <img alt="Orbit" src="https://img.shields.io/badge/Orbit-OpenSpec_%2B_Superpowers-blue?style=for-the-badge">
</picture>

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Agent Skills](https://img.shields.io/badge/Agent%20Skills-Compatible-brightgreen)]()
[![Codex](https://img.shields.io/badge/Codex-ready-8A2BE2)]()
[![Claude Code](https://img.shields.io/badge/Claude_Code-ready-orange)]()
[![Cursor](https://img.shields.io/badge/Cursor-ready-blue)]()
[![Windsurf](https://img.shields.io/badge/Windsurf-ready-teal)]()

</div>

# Orbit：OpenSpec + Superpowers 统一工作流编排器

> 一条命令，把 AI 编码从"即兴发挥"变成"工程流水线"。

---

## 你的 AI 编程助手是不是也这样？

你让它加个 OAuth 登录。它答应得很干脆，然后：

- 第一轮，写了个没带 token 刷新的实现
- 第二轮，token 刷新加上了，但错误处理没覆盖 401 场景
- 第三轮，401 处理好了，但 Session 管理又乱了
- 第四轮你开始怀疑——是不是一开始就没把需求理清楚

**问题不在 AI 不够聪明，而是缺少流程约束。** AI 编程助手是一辆没有刹车的跑车——快是真的快，但每次转弯你都在赌它不会飞出赛道。

Orbit 就是那条赛道。

---

## Orbit 是什么

**Orbit 是一个 Agent Skill**——不是一个 NPM 包、不是一个 CLI 工具、不是一个 VS Code 插件。它就是一个 `SKILL.md` 文件加上几个规则表，放在你的 `~/.agents/skills/` 目录下，你的 AI 编程助手就能理解并使用它。

它的工作很简单：**把 OpenSpec 和 Superpowers 串成一条端到端流水线。**

```
OpenSpec（管 WHAT：需求定义 + 规格管理）
        ↕
    Orbit（编排层：状态机 + 桥接规则 + 断点续传）
        ↕
Superpowers（管 HOW：头脑风暴 + TDD + Code Review + 归档）
```

Orbit 不重写任何一个 Skill。它只做四件事：**决定阶段、执行桥接、控制转换、持久化状态**。

---

## 核心优势

### 1. 零依赖，纯 Skill

```
npm install ×
Node.js 20+ ×
Bash 环境 ×

只需要一个 SKILL.md 文件。
```

没有安装命令，没有环境要求。任何支持 Agent Skills 的 AI 编程助手都能用。

### 2. 状态持久化 + 断点续传

每个变更在 `openspec/changes/<change-id>/.orbit-state` 维护一个 YAML 状态文件，记录当前阶段、子状态、任务进度、提交历史。**对话断了？输入"继续"就能从断点恢复。**

### 3. 强制人工审阅 Gate

Stage 2 的 Blocking Human Review Gate **不可跳过**。AI 生成 OpenSpec 制品后，必须经过你的审阅才能进入下一阶段。你可以在 Gate 中用自然语言说"第三个需求写偏了"，Orbit 会定位到对应文件并修改。

防止"垃圾进，垃圾出"。

### 4. 方案分析（Approach Analysis）

复杂变更在写制品之前会触发方案分析，展示 2-3 种实现方案——每种都带优缺点、工作量预估、风险评估，标注主推方案。你选一个，Orbit 再按你选的路线生成制品。

### 5. 原子回滚

Stage 4 每个 Task 独立 commit。Review 失败时，`git reset --hard` + `git clean -fd` 回滚到上一个稳定点，不污染 Git 历史。

### 6. 跨工具兼容

| 工具 | 触发方式 | 安装方式 |
|------|---------|---------|
| **Codex** | `/orbit` 或显式提及 | `~/.agents/skills/orbit/`，自动发现 |
| **Claude Code** | `/orbit` 或显式提及 | 同上，配合 `CLAUDE.md` 引用 |
| **Cursor** | `@orbit` | `.cursor/rules/orbit.mdc` |
| **Windsurf** | 自然语言"用 Orbit" | `.windsurfrules` |

即使某个子 Skill（如 brainstorming）在特定工具中不可用，Orbit 也提供了内联 fallback 指令。

### 7. Spec Gap 检测

如果 Stage 4 实现过程中发现 spec 本身有缺陷（不是实现 bug），Orbit 会自动回退到 Stage 2 重写 spec，然后重新走 Stage 3 → 4。不会带着有问题的 spec 硬写代码。

---

## 工作流总览

Orbit 把开发流程组织为 6 个阶段，根据变更类型自动选择路径：

```
feature:  0 ──→ 1 ──→ 2 ──→ 3 ──→ 4 ──→ 5   （全流程）
bugfix:   0 ────────→ 2 ──→ 3 ──→ 4 ──→ 5   （跳过设计阶段）
docs:     0 ────────→ 2 ──────────────→ 5   （轻量流程）
```

| 阶段 | 名称 | 做什么 | 适用类型 |
|------|------|--------|---------|
| **Stage 0** | Bootstrap | 生成 change-id，探测测试命令，分类变更类型 | 全部 |
| **Stage 1** | Explore & Design | 头脑风暴，产出设计文档，确认 change-id | feature |
| **Stage 2** | Specify | 方案分析（可选）→ 生成 OpenSpec 制品 → **人工审阅 Gate** | 全部 |
| **Stage 3** | Plan | 拆解为 bite-sized tasks，生成 tasks.md | feature, bugfix |
| **Stage 4** | Implement | TDD 实现 + Spec 合规检查 + 自动提交/回滚 | feature, bugfix |
| **Stage 5** | Verify & Complete | 验证测试 + 归档 + Git 分支收尾 | 全部 |

每个阶段结束时输出 `[ORBIT_CHECKPOINT]` 标记。子 Skill 的终端跳转会被 Orbit 拦截，**你不会被自动跳转到下一个 Skill**——跳转逻辑由 Orbit 统一管理。

---

## 安装

### 前置条件

- 使用支持 Agent Skills 的 AI 编程助手（Codex、Claude Code、Cursor、Windsurf）
- 已安装 [OpenSpec](https://github.com/Fission-AI/OpenSpec)（用于 spec 管理）
- 已安装 [Superpowers](https://github.com/obra/superpowers)（可选，Orbit 有内联 fallback）

### 30 秒快速安装

```bash
# 克隆仓库
git clone https://github.com/yaozoo/orbit.git /tmp/orbit-install

# 全局安装（推荐，所有项目共享）
mkdir -p ~/.agents/skills/orbit
cp /tmp/orbit-install/SKILL.md ~/.agents/skills/orbit/
cp -r /tmp/orbit-install/references ~/.agents/skills/orbit/

# 如果是 Claude Code，额外创建全局 CLAUDE.md
echo '# Custom Skills
Refer to ~/.agents/skills/orbit/SKILL.md for the Orbit workflow orchestrator.' >> ~/.claude/CLAUDE.md

# 清理临时文件
rm -rf /tmp/orbit-install
```

### 目录结构

```
~/.agents/skills/orbit/          # 或 .agents/skills/orbit/
├── SKILL.md                     # 主编排文件
└── references/
    ├── state-schema.yaml        # .orbit-state 字段定义
    ├── bridge-rules.md          # 阶段间制品格式桥接规则
    └── stage-transitions.md     # 阶段转换拦截规则表
```

安装后**重启你的 AI 编程助手**，新 Skill 才能被加载。

---

## 使用指南

### 触发 Orbit

Orbit **不会自动激活**。你必须显式触发它：

| 触发方式 | 示例 | 兼容工具 |
|---------|------|---------|
| 斜杠命令 | `/orbit 我要做 OAuth 登录` | Codex, Claude Code |
| 显式提及 | `用 Orbit 帮我修复支付校验的 bug` | 全部 |
| @ mention | `@orbit 实现用户认证模块` | Cursor, Windsurf |

> 如果你只想做一件事（头脑风暴、写 spec、TDD、Code Review），直接用对应的单个 Skill，不要用 Orbit。Orbit 是端到端编排器。

---

### 场景一：新增功能（feature 全流程）

**适用**：从零开始的新功能、重构、架构变更。

```text
你: /orbit 我要给系统增加 OAuth 登录功能

Orbit:
  Stage 0: 生成 change-id "add-oauth-login"，识别为 feature
  → 自动切换到分支 feature/add-oauth-login

  Stage 1: 启动头脑风暴
  → 和你进行 2-3 轮澄清对话
  → 产出设计文档 docs/superpowers/specs/2026-07-17-oauth-design.md
  → 确认 change-id 或让你重命名
  → [ORBIT_CHECKPOINT: Stage 1 complete]

  Stage 2: 生成 OpenSpec 制品
  → 如果实现路径有多种选择，展示方案分析（A/B/C + 主推）
  → 按选定方案生成 proposal.md + design.md + spec.md
  → 🚧 人工审阅 Gate —— 你必须确认或修改后再继续
  → [ORBIT_CHECKPOINT: Stage 2 complete]

  Stage 3: 拆解任务
  → 产出 tasks.md，每个 Task 引用计划文档的具体章节
  → [ORBIT_CHECKPOINT: Stage 3 complete]

  Stage 4: TDD 实现
  → 让你选择提交模式：auto（自动）或 review（每任务确认）
  → 逐个 Task：写测试 RED → 实现 GREEN → 重构 REFACTOR → 提交
  → 每个 Task 独立 commit，失败则原子回滚
  → 发现跨 Task bug 自动加入 hotfix_queue
  → [ORBIT_CHECKPOINT: Stage 4 complete]

  Stage 5: 验证与归档
  → 运行测试命令确认全部通过
  → 代码 vs spec 一致性检查
  → 归档 change，同步 delta specs → main specs
  → Git 分支收尾（merge/rebase/squash）
  → ✅ 完成
```

---

### 场景二：修复 Bug（bugfix 流程）

**适用**：缺陷修复、回归问题、跨模块 Bug。

```text
你: 用 Orbit 修复支付校验的 bug —— 金额为 0 时没有报错

Orbit:
  Stage 0: 生成 change-id "fix-payment-validation"，识别为 bugfix
  → 跳过 Stage 1（无需设计文档）

  Stage 2: 方案分析（自动触发）
  → 展示 2-3 种修复方案：
    方案 A：在 Controller 层加校验（主推）
    方案 B：在 Service 层加校验
    方案 C：在数据库约束层加校验
  → 你选 A
  → 生成 OpenSpec 制品
  → 🚧 人工审阅 Gate

  Stage 3 → 4 → 5: 同上
```

对于简单的 bugfix（单行修复、typo、机械变更），方案分析会自动跳过。

---

### 场景三：文档/配置变更（docs 轻量流程）

**适用**：README 更新、Dockerfile 调整、配置文件修改、注释补充。

```text
你: /orbit 更新 README，增加部署说明

Orbit:
  Stage 0: 生成 change-id "update-readme-deploy"，识别为 docs
  → 跳过 Stage 1（设计）、Stage 3（拆解）、Stage 4（实现）

  Stage 2: 直接从你的描述提取，生成 OpenSpec 制品
  → 🚧 人工审阅 Gate

  Stage 5: 验证 → 归档 → 分支收尾
  → ✅ 完成
```

docs 路径专为"不需要写代码"的变更设计，高效轻量。

---

### 断点续传

对话中断了？代码写完一半 IDE 崩了？没关系的。

```text
你: 继续

Orbit:
  → 扫描 openspec/changes/*/.orbit-state
  → 找到未完成的变更
  → 检查制品完整性（tasks.md 还在吗？plan_doc 还在吗？）
  → [ORBIT_RESUME] Resuming from Stage 4.3
  → 从断点继续
```

每个 `.orbit-state` 文件都记录了精确的 `stage`、`substage` 和 `updated_at`。Orbit 不会让你从零开始。

---

## 与类似项目的对比

### Orbit vs rpamis/comet

Orbit 最初命名为 Comet，后发现与 [rpamis/comet](https://github.com/rpamis/comet) 重名而更名。两者不是同一个项目：

| 维度 | rpamis/comet | Orbit |
|------|-------------|-------|
| **本质** | NPM CLI 工具 | Agent Skill（SKILL.md） |
| **安装** | `npm install -g @rpamis/comet` | 复制文件到 `~/.agents/skills/` |
| **依赖** | Node.js 20+、Bash | 仅需 AI 助手支持 Agent Skills |
| **使用方式** | 命令行 + Skill 命令 | 直接在对话中输入 `/orbit` |
| **状态持久化** | CLI + 文件系统 | YAML 状态文件 + 断点续传 |
| **跨工具** | 需 CLI 支持的平台 | Codex / Claude Code / Cursor / Windsurf |

### 与其他编排器的对比

| 项目 | 类型 | 依赖 | 独特之处 |
|------|------|------|---------|
| **Orbit** | Agent Skill | 仅 AI 助手 | 零依赖、纯 Skill、跨工具兼容 |
| superspec | OpenSpec Schema | OpenSpec + Superpowers | OpenSpec 作为编排器 |
| openflow | NPM CLI | Node.js | 多阶段命令 |
| sddflow | NPM CLI | Node.js | brainstorming → spec → build → close |
| easyflow | NPM CLI | Node.js 20+ | 8 阶段状态机 + 治理层 |

**Orbit 的独特定位**：在所有同类项目中，Orbit 是唯一一个纯 Skill 实现的方案。你不需要 `npm install` 任何东西。

---

## 设计哲学

### WHAT vs HOW 的分离与统一

AI 编程助手领域有两个著名的开源项目：

- **OpenSpec** 管 **WHAT**：需求定义、变更追踪、规格管理。
- **Superpowers** 管 **HOW**：头脑风暴方法、TDD 纪律、代码审查流程、归档策略。

它们各自都很强，但它们是孤岛。Orbit 的定位是两者之间的胶水——不重写任何一个，只是在它们之间建立一个轻量的编排层。

### 什么不该做

Orbit 坚持以下原则：

- **不重写任何子 Skill**：brainstorming、TDD、Code Review 的逻辑归它们自己的 SKILL.md
- **不做 UI 集成**：交互完全在对话中完成
- **不做 CI/CD 集成**：不触发 GitHub Actions、不管理 Docker 镜像
- **不替代 Git**：Git 操作由 `finishing-a-development-branch` 管理，Orbit 只负责确保正确的分支被 checkout
- **不记忆跨项目状态**：每个 `.orbit-state` 是 per-change 的，Orbit 不做全局状态管理

---

## 适合什么时候用？

### ✅ 推荐场景

| 场景 | 说明 | 推荐路径 |
|------|------|---------|
| 新增功能 | 需要完整的需求分析、设计、编码、测试、归档 | feature 全流程 |
| 复杂 Bug 修复 | 涉及多个模块、有多种实现方案可选 | bugfix 流程（含方案分析） |
| 简单 Bug 修复 | 一行改动、typo、明显机械修复 | bugfix 流程（方案分析自动跳过） |
| 文档/配置变更 | README、Dockerfile、配置文件 | docs 轻量流程 |
| 多人协作 | 需要清晰的 spec 和 task 拆分 | feature 或 bugfix 全流程 |
| 中断风险高 | 可能被打断、需要跨天完成 | 任意路径（利用断点续传） |

### ❌ 不推荐场景

| 场景 | 建议 |
|------|------|
| 只想做一次头脑风暴 | 直接用 `brainstorming` skill |
| 只想写一个 OpenSpec spec | 直接用 `openspec` skill |
| 只想做一次 TDD 编码 | 直接用 `test-driven-development` skill |
| 只想做一次 Code Review | 直接用 `requesting-code-review` skill |
| 临时实验性代码 | 不需要流程约束 |

**Orbit 是端到端编排器，不是单一任务执行器。**

---

## FAQ

**Q: Orbit 和 OpenSpec 的 openspec-proposal 有什么区别？**

OpenSpec 的 proposal 只覆盖 Stage 2 的制品生成。Orbit 覆盖从需求分析到归档的整个生命周期——包括头脑风暴（Stage 1）、实现（Stage 4）、验证归档（Stage 5）。

**Q: 如果我的项目没有 Superpowers skills 怎么办？**

Orbit 为每个子 Skill 提供了内联 fallback 指令。即使 Superpowers 的某个 skill 文件不存在，Orbit 也能靠内置指令完成对应阶段。

**Q: 我能在同一个项目同时跑多个 Orbit 变更吗？**

不建议。Orbit 的状态持久化是 per-change 的，但 Stage 4 的原子回滚依赖 Git 工作树的清洁状态。建议一个 change 一个 change 地推进。

**Q: Stage 4 的 review 模式太慢了，能切到 auto 吗？**

可以。在 review 模式的 Task 确认界面选 `4`，Orbit 会切换到 auto 模式，后续所有 Task 自动提交。

**Q: Orbit 会修改我的 Git 历史吗？**

不会。回滚使用 `git reset --hard`，但之前的 commit 仍在 reflog 中。你可以随时 `git reflog` 找回。

---

## 贡献

欢迎提交 Issue 和 Pull Request。

- **报告 Bug**：附上 `.orbit-state` 文件和相关的对话日志
- **建议新功能**：说明使用场景和预期收益
- **代码贡献**：确保修改后通过自检门禁（Pre-Action Guard）

---

## License

MIT License

---

## 致谢

- [OpenSpec](https://github.com/Fission-AI/OpenSpec) — 规范驱动开发框架
- [Superpowers](https://github.com/obra/superpowers) — AI 编程方法论与技能库
- [rpamis/comet](https://github.com/rpamis/comet) — 启发本项目最初的设计思路
