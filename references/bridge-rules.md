# Bridge Rules — 制品格式桥接规则

Orbit 在阶段之间执行制品格式转换。本文件定义了完整的字段映射规则。

---

## Stage 1 → Stage 2: Brainstorming Design Doc → OpenSpec Artifacts

### Source: Brainstorming Design Document

Brainstorming 产出的设计文档（`docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md`）包含以下结构：

```
# 设计文档：<功能名称>

## 问题陈述 / 背景
...

## 功能描述 / 变更内容
...

## 影响分析
...

## 架构决策 / 组件设计 / 数据流
...

## 功能性需求（Given/When/Then）
...

## 非功能性需求（性能 / 安全 / 可访问性）
...
```

### Target: OpenSpec Artifacts

#### proposal.md

| 源字段 | 目标字段 | 说明 |
|--------|---------|------|
| 问题陈述 / 背景 | `## Why` | 为什么要做这个变更 |
| 功能描述 / 变更内容 | `## What Changes` | 变更内容概述 |
| 影响分析 | `## Impact` | 影响范围说明 |

格式模板：
```markdown
# Proposal: <change-id>

## Why
<从设计文档的问题陈述/背景提取>

## What Changes
<从设计文档的功能描述/变更内容提取>

## Impact
<从设计文档的影响分析提取>
```

#### design.md

| 源字段 | 目标字段 | 说明 |
|--------|---------|------|
| 架构决策 / 组件设计 / 数据流 | 全文 | 保持 OpenSpec design.md 格式 |

#### specs/<capability>/spec.md

| 源字段 | 目标字段 | 说明 |
|--------|---------|------|
| 功能性需求（Given/When/Then） | `## ADDED Requirements` | 转换为 `### Requirement:` + `#### Scenario:` 格式 |
| 非功能性需求 | `## ADDED Requirements` | 性能/安全/可访问性类 Requirement |

EARS 格式模板：
```markdown
# Spec: <capability-name>

## ADDED Requirements

### Requirement: <需求标题>
**Priority**: P0 / P1 / P2
**Description**: <用 EARS 模式描述>

#### Scenario: <场景名称>
- **GIVEN** <前置条件>
- **WHEN** <触发动作>
- **THEN** <预期结果>
```

---

## Stage 3 → Stage 4: Writing-Plans → tasks.md

### Source: Writing-Plans Plan Document

Writing-plans 产出的计划文档（`docs/superpowers/plans/YYYY-MM-DD-<name>.md`）包含详细的 bite-sized task 描述，每个 task 有：
- 任务编号和标题
- 详细的实现步骤和代码示例
- 文件路径和修改范围
- 依赖关系

### Target: tasks.md

**关键原则：不压缩，使用引用链接。**

tasks.md 条目保留对 plan 文档的引用路径，Stage 4 分发 subagent 时从引用路径读取完整段落并注入上下文。

```markdown
## 实现任务

- [ ] 1. 实现认证模块 → 详见: docs/superpowers/plans/2026-07-16-oauth.md#task-1
- [ ] 2. 实现授权中间件 → 详见: docs/superpowers/plans/2026-07-16-oauth.md#task-2
- [ ] 3. 实现 Token 刷新 → 详见: docs/superpowers/plans/2026-07-16-oauth.md#task-3
```

每个引用路径指向 plan 文档中的具体 task 锚点段落。

---

## Stage 4 Internal: Bugfix / Docs → proposal.md

当 `change_type == bugfix` 或 `change_type == docs` 时，无 Stage 1 设计文档。Orbit 从用户请求中直接提取信息：

| 源 | 目标字段 | 说明 |
|----|---------|------|
| 用户请求中的问题描述 | `proposal.md ## Why` | Bug 的现象 / 文档缺失的内容 |
| 用户请求中的修复方案 | `proposal.md ## What Changes` | 修复内容 / 修改范围 |
| 推断 | `proposal.md ## Impact` | 影响范围 |

**注意**：如果 Stage 2 Step 3 方案分析被触发且用户选定了方案，`## What Changes` 和 `design.md` 的架构部分必须反映用户选定的 `selected_approach`，而非 AI 自行决定的方案。方案分析的产出是 HOW 层面的约束，制品写入时必须遵守。

---

## tasks.md → Subagent Context Injection

Stage 4 Step 2 分发 subagent 时，Orbit 执行以下注入流程：

1. 读取 `tasks.md` 当前条目：`- [ ] N. <标题> → 详见: <reference-path>`
2. 解析 `reference-path` → 定位到 plan 文档的具体段落
3. 读取该段落（包括所有实现细节和代码示例）
4. 将完整段落注入 subagent 的 system prompt / task description

**效果**：tasks.md 保持简洁（一行引用），但 subagent 拿到 writing-plans 的全部信息（零信息丢失）。
