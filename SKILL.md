---
name: orbit
description: "OpenSpec + Superpowers unified workflow orchestrator. Use ONLY when the user explicitly invokes /orbit or mentions Orbit by name. Do NOT auto-activate for general feature/bugfix/change requests — those should use individual skills (brainstorming, openspec, TDD, etc.) directly. Keywords: /orbit, Orbit, 统一工作流, 端到端编排."
---

# Orbit: OpenSpec + Superpowers 统一工作流编排器

## Activation Gate

Orbit **MUST NOT** auto-activate unless explicitly invoked. If loaded without an explicit trigger, stay dormant and let the user use other skills directly.

| 触发方式 | 示例 | 兼容工具 |
|---------|------|---------|
| 斜杠命令 | `/orbit 我要做 OAuth 登录` | Codex, Claude Code |
| 显式提及名称 | "用 Orbit 帮我修复这个 bug" | 全部 |
| @ mention | `@orbit 实现用户认证模块` | Cursor, Windsurf |

**If no trigger is present → Orbit stays dormant.** Do not suggest using Orbit unless the user asks for an end-to-end orchestrated workflow.

If the user wants to do a single task (brainstorm, write a spec, implement with TDD, review code), use the individual skill directly instead of Orbit.

## Overview

Orbit 将 OpenSpec（变更制品管理）和 Superpowers（开发质量实践）串联为一条端到端工作流。用户发起一次，后续阶段自动衔接。

**设计哲学**：
- OpenSpec = WHAT（需求定义 + 变更追踪）
- Superpowers = HOW（设计方法 + 实现纪律 + 质量保障）
- Orbit = 编排层（WHAT 和 HOW 之间的胶水 + 状态持久化）

**不重写任何现有 skill**。Orbit 只做四件事：决定阶段、执行桥接、控制转换、持久化状态。

**状态更新规则**：每次写入 `.orbit-state` 时，同步更新 `updated_at` 时间戳。遵循"先写状态，再执行桥接"原则——确保即使桥接失败或对话中断，状态文件已记录最新进度。

## Quick Reference

| 场景 | 位置 | 关键决策点 |
|------|------|-----------|
| 确定变更类型 | [Stage 0](#stage-0-bootstrap) — Step 3 | feature / bugfix / docs → 路由表 → 不同阶段路径 |
| 方案分析触发 | [Stage 2](#stage-2-specify) — Step 3 | 3+ 架构决策 \| 5+ 文件跨模块 \| 新依赖 → 展示方案 |
| 制品审阅 Gate | [Stage 2](#stage-2-specify) — Step 6 | 阻塞式，不可跳过，需用户确认 |
| 断点续传 | [Resume](#resume-断点续传) | 扫描 `.orbit-state` → 完整性校验 → 跳转 |
| 提交模式选择 | [Stage 4](#pre-flight-commit-mode-selection) | auto（自动提交）/ review（逐任务确认） |
| 任务清单确认 | [Stage 4](#pre-flight-task-list-confirmation-gate) | 阻塞式 Gate，解析 tasks.md 后展示 |
| 回滚流程 | [Stage 4](#atomic-rollback) | reset --hard + clean -fd（需用户两次确认） |
| 状态完整性 | [Self-Check](#self-check-pre-action-guard) — Integrity Check | preliminary guard \| tasks.md 存在 \| plan_doc/current_task 一致性 |
| 桥接规则 | `references/bridge-rules.md` | 制品格式转换（设计文档 → proposal/design/spec） |
| 状态字段定义 | `references/state-schema.yaml` | `.orbit-state` 所有字段的类型和约束 |
| 阶段转换拦截 | `references/stage-transitions.md` | 合法 skill 映射 + 终端跳转拦截 + 异常回退 |

---

## Transition Authority

Orbit orchestrates the full workflow. When a sub-skill reaches its terminal state and instructs you to invoke another skill, you **MUST NOT** follow that instruction.

Instead, output the checkpoint marker:
```
[ORBIT_CHECKPOINT: Stage N complete]
```

Then return to Orbit's controller. Orbit decides what happens next.

**This rule overrides any sub-skill's terminal transition instruction.** Orbit carries the user's intent — the user chose a full orchestrated workflow — and that intent takes priority over sub-skill defaults.

---

## Core Routing

### Cold Start

When the user requests a change (e.g., "我要做 OAuth 登录", "修复支付校验 bug", "更新 README"):

1. Start at **Stage 0** — Bootstrap
2. Follow the stage sequence based on detected change type

### Resume (断点续传)

If the user says "继续" or "continue" without a new change request:

1. Scan `openspec/changes/*/.orbit-state` for files with `stage < 5` (or `stage == 5` and `substage != "complete"`)
2. If one found: auto-resume from that stage
3. If multiple found: list and let user choose
4. **Integrity check**: Before resuming, verify that artifacts referenced by `.orbit-state` still exist:
   - **preliminary guard**: If `stage >= 2` and `preliminary == true`: output `[ORBIT_RESUME_WARNING] stage={stage} but preliminary=true — Stage 1 never finalized the change-id.` and offer: (1) re-run Stage 1 brainstorming to finalize, (2) manually set `preliminary: false` and proceed at own risk.
   - If `stage >= 3`: check that `openspec/changes/<id>/tasks.md` exists
   - If `stage >= 4`: check that `.orbit-state.plan_doc` is not empty, and `current_task <= total_tasks`
   - If `stage == 4`: check that `.orbit-state.plan_doc` path exists
   - If `stage == 0`: the change was finalized (id + type written) but Stage 0 never transitioned out — read `.orbit-state.change_type` and take the Stage 0 **Transition** directly (feature → Stage 1; bugfix/docs → Stage 2). No artifacts to verify at Stage 0.
   - If any check fails: output `[ORBIT_RESUME_WARNING] 状态文件引用的制品缺失: {missing}` and ask user:
     ```
     请选择：
     1. 继续 — 忽略缺失警告，从断点继续执行
     2. 放弃 — 终止恢复，保持现状
     ```
5. Output: `[ORBIT_RESUME] Resuming from Stage {stage}.{substage}`
6. Jump to the corresponding stage's instructions below

---

## Stage Sequence by Change Type

| change_type | Stages | Skills Used |
|-------------|--------|-------------|
| feature | 0 → 1 → 2 → 3 → 4 → 5 | brainstorming, writing-plans, subagent-driven-development, tdd, finishing-a-development-branch |
| bugfix | 0 → 2 → 3 → 4 → 5 | writing-plans, subagent-driven-development, tdd, finishing-a-development-branch |
| docs | 0 → 2 → 5 | verification-before-completion, finishing-a-development-branch |

---

## Stage 0: Bootstrap

**Goal**: Classify change type, detect environment, then create change directory and persist state once.

**Design principle**: Confirm WHAT (change type) before recording HOW (state file). The `.orbit-state` is written a single time, after `change_type` is settled, so Stage 0 never produces a partial/intermediate state. If the conversation is interrupted during classification, no state file exists yet — the user simply re-invokes `/orbit`, which is the correct behavior since nothing durable was committed yet.

**Steps**:

1. **Generate change-id (in memory only)**: Parse user request → `<verb>-<noun>` (e.g., `add-oauth-login`). If ambiguous, use `change-YYYYMMDD-NNN`. Validate kebab-case. Conflict check with `ls openspec/changes/`. Do **not** create the directory yet — that happens in Step 4 after the type is settled.

2. **Detect test command** (does not depend on change type):
   *Prefer headless (CI-compatible) test scripts.* Check `package.json` for
   `test:unit` or `test:ci` first. If not found, fall back to `scripts.test`.
   If the detected script starts a dev server (e.g., `vite`), search for
   headless alternatives in sub-package scripts. Also check `pyproject.toml`
   → `pytest`, `Cargo.toml` → `cargo test`, `go.mod` → `go test ./...`,
   `Makefile` → `make test`. If none match, ask user. Hold the result in memory
   for the single state write in Step 4.

3. **Classify change type (tri-state)**: Scan the user's request against the keyword map:

   - `新增/添加/实现/重构/开发/做` → `feature`
   - `修复/修/bug/fix` → `bugfix`
   - `文档/README/Dockerfile/配置/注释` → `docs`

   Evaluate the signal strength:

   - **Explicit** — exactly one type's keywords match, and no keyword from another type is present. Auto-confirm, skip the prompt, go straight to Step 4.
   - **Ambiguous** — keywords from more than one type match (e.g., "修复这个新增功能的 bug" hits both `修复` and `新增`), or the request is clearly about a change type but the keyword signal is weak. Show the classification with reasoning and require user confirmation (see prompt below).
   - **Unknown** — no keyword matches. Go straight to the confirmation prompt and let the user pick.

   **On auto-confirm (explicit)**, output a single-line notice and continue without waiting:
   > "识别为 **{type}** 变更（匹配关键词：{keywords}）。执行路径：{route summary}。继续。"

   **On ambiguous / unknown**, show the classification and require user confirmation:
   > "识别为 **{type}** 变更（匹配关键词：{keywords}）。
   >  执行路径：{route summary}。
   >  请选择变更类型：
   >  1. feature — 新增功能，走 0→1→2→3→4→5 全流程
   >  2. bugfix — 缺陷修复，跳过 Stage 1，走 0→2→3→4→5
   >  3. docs — 文档变更，走 0→2→5 轻量流程
   >  4. 自定义类型 — 手动指定类型（需说明理由）"
   Wait for the user's selection before proceeding to Step 4.

4. **Create directory and write .orbit-state once**: Now that `change_id` and `change_type` are both settled:
   - `mkdir -p openspec/changes/<change-id>/`
   - Write a single complete `.orbit-state` in one pass with: `change_id`, `schema_version: "1.0.0"`, `change_type`, `branch_name` (generated as `<type>/<change-id>`, e.g., `feature/add-oauth-login`, `bugfix/fix-payment`, `docs/update-readme`), `origin_branch` (captured from `git branch --show-current`), `test_cmd` (from Step 2), `preliminary`, `stage: 0`, `created_at`, `updated_at`. Schema reference: `references/state-schema.yaml`.
   - `preliminary` is set by type: **feature** → `true` (the id is provisional until Stage 1 brainstorming may refine it; `preliminary: true` restricts the workflow to Stage 0 ↔ Stage 1, and Stage 2+ cannot proceed until Stage 1 finalizes the id and sets `preliminary: false`); **bugfix / docs** → `false` (no Stage 1, so the id is already final at Stage 0 and the workflow may proceed straight to Stage 2).

**Transition**: If `feature` → Stage 1. If `bugfix` or `docs` → Stage 2.

## Stage 1: Explore & Design

**Applies to**: `change_type == feature`

**Skill**: `brainstorming`

**Instructions**:

1. Update `.orbit-state`: `stage: 1, substage: exploring`

2. **Execute brainstorming** (load skill or use inline fallback — see Tool Compatibility):
   > "Follow brainstorming's full process (9 steps). When it tells you to invoke writing-plans, do NOT follow that. Instead, output [ORBIT_CHECKPOINT: Stage 1 complete] and return to Orbit's controller."

3. Run brainstorming through its full cycle: explore context → question rounds → design document → user review

4. At brainstorming's terminal state, output `[ORBIT_CHECKPOINT: Stage 1 complete]`

5. **Orbit takes over**:
   - Update `.orbit-state`: `stage: 2, substage: id_finalization`

   **Finalize change-id (smart-gated, not blanket-asked)**:
   The change-id was generated at Stage 0 from the initial (often vague) request. Brainstorming in Stage 1 can materially shift what the change is *about* — and this transition is the cheapest place to rename, because once Stage 2 writes artifacts the id becomes a directory/branch/reference key that is expensive to rewrite. So instead of asking every time, self-assess whether the id still fits:

   - **Still fits** — the verb-noun still accurately describes the refined change (the common case, since brainstorming refines but rarely inverts the subject). Auto-confirm, do not block. Output a one-line notice and proceed immediately:
     > "[ORBIT] Change ID: `{id}`（如需改名，现在说，否则继续进入 Stage 2）"
   - **Scope shifted** — brainstorming revealed the change is really about something different than the Stage 0 id suggests (different verb, different noun, or materially narrower/wider scope). Proactively propose a better id and block for one short confirmation:
     > "Stage 1 后理解发生变化，建议 Change ID 由 `{old}` 改为 `{proposed}`。
     >  1. 接受建议 — 使用 `{proposed}`
     >  2. 保留原 ID — 仍用 `{old}`
    >  3. 自定义 — 输入新 ID"
    On rename: `mv openspec/changes/<old>/ openspec/changes/<new>/`, update `.orbit-state.change_id`, and update `.orbit-state.branch_name` to `<type>/<new-id>` (derive the type prefix from `.orbit-state.change_type`, not a hardcoded `feature/`).

   The Stage 2 review gate (option 2 "修改文件") remains the safety net — a rename requested there is still cheap because artifacts were just written and references stay local to the change directory.

   - Set `preliminary: false`
   - Write `design_doc` path (from brainstorming output) to `.orbit-state.design_doc`

**Artifacts**: `docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md`

**Transition**: Stage 2

---

## Stage 2: Specify

**Applies to**: all change types

**Skill**: None. Orbit writes OpenSpec artifacts directly. **Do NOT call `openspec-new-change`** — the directory already exists from Stage 0.

**Instructions**:

1. Update `.orbit-state`: `stage: 2, substage: bridging`

2. Read design document (for features) or extract from user request (for bugfix/docs)

3. **Approach Analysis** (conditional):

   Update `.orbit-state`: `substage: approach_analysis`

   **Trigger** (present alternatives) when ANY of these countable signals is true:
   - `change_type == feature` AND the Stage 1 design doc lists 3+ distinct architectural decisions
   - The change modifies 5+ files across 2+ top-level modules/directories (detected by scanning the plan or the user request)
   - The change introduces a new module, abstraction layer, or external dependency
   - User request contains explicit uncertainty markers ("方案" / "怎么实现" / "哪种方式")

   **Skip** (go to Step 4) when ALL of:
   - `change_type != feature` (bugfix/docs are lower-risk by definition)
   - AND scope is ≤ 3 files in a single module
   - AND no new module/abstraction/dependency is being introduced

   Additionally, if the Stage 1 design doc already documents a selected approach with rationale, skip unless user explicitly asks.

   **When triggered**, present 2-3 approaches. For each: brief description (what changes + where), pros/cons (technical trade-offs), effort (S/M/L), risk (Low/Med/High with what could go wrong). Mark one as **主推 (Recommended)** with reasoning.

   ```
   === [ORBIT_APPROACH] 方案分析 ===

   需求摘要: <1-2 行>

   ── 方案 A (主推) ──
   描述: <what + where>
   优点: <pros>
   缺点: <cons>
   工作量: S/M/L
   风险: Low/Medium/High

   ── 方案 B ──
   描述: <what + where>
   优点 / 缺点 / 工作量 / 风险

   ── 方案 C ──
   描述: <what + where>
   优点 / 缺点 / 工作量 / 风险

   主推理由: <为什么推荐方案 A>

   请选择: A / B / C (或描述自定义方案)
   ```

   - User selects A/B/C → write `selected_approach` to `.orbit-state`, proceed to Step 4
   - User describes custom approach → treat as selected, proceed to Step 4

4. **Write OpenSpec artifacts** using the bridge rules in `references/bridge-rules.md`.
   Read change-id from `.orbit-state.change_id` and substitute into proposal.md title (`# Proposal: <change-id>`):
   If Step 3 was triggered, artifacts must reflect the selected approach. Artifact set varies by change type:
   - `openspec/changes/<change-id>/proposal.md` — Why / What Changes / Impact
   - `feature` / `bugfix` — `design.md` (Architecture / Data Flow) + `specs/<capability>/spec.md` (EARS-format requirements). bugfix 的 spec 描述"修复后应满足的正确行为"。
   - `docs` — 默认仅 `proposal.md`，跳过 `design.md` 与 `specs/`（纯文档/配置变更通常无 EARS 行为契约）。仅当文档变更隐含一条可验证的行为契约时才补 `specs/`，此时 `design.md` 仍可省略。详见 bridge-rules "Docs → proposal.md（轻量）"。

5. Validate: run `openspec status --change "<id>" --json`

6. **Blocking Human Review Gate** (CANNOT be skipped):
   ```
   === [ORBIT_GATE] Stage 2 制品已生成，请审阅 ===

   📄 proposal.md:
     Why: <1-2 行摘要>
     What: <要点列表>
     Impact: <1 行>

   📄 specs/<capability>/spec.md:
     Requirements: <编号列表，每条一行>

   📄 design.md:
     Architecture: <1-2 行>

   完整文件: openspec/changes/<change-id>/
   请选择：
   1. 确认 — 审阅通过，继续下一阶段
   2. 修改文件 — 用自然语言描述需要调整的内容
      示例: "proposal 的 Why 部分写偏了，实际问题是 XXX"
            "第三个需求描述不准确，应该是 YYY"
      Orbit 会根据描述定位到对应的 OpenSpec 制品并修改，
      修改完成后重新验证并展示给你确认
   3. 重新讨论方案 — 回到 Step 3 方案分析，重新选择实现路径
      适用于：审阅制品后发现技术方案需要调整
      Orbit 会清空当前制品，回到方案分析步骤
   4. 放弃 — 终止工作流，保留文件供手动处理
   ```
   - "1" → continue to step 7
   - "2" → understand user's intent in natural language, locate the corresponding OpenSpec artifacts using bridge rules, modify them, re-run `openspec status --change "<id>" --json` to validate, then **show a change summary** (which files were modified and what changed) before re-displaying the review gate
   - "3" → delete generated artifacts, set `substage: approach_analysis`, return to Step 3. Previously presented approaches can be revised based on review insights.
   - "4" → terminate, keep files for manual handling

7. Update `.orbit-state`: `stage: 3, substage: ready_for_plan`

**Transition**:
- `feature` or `bugfix` → Stage 3
- `docs` → Stage 5

---

## Stage 3: Plan

**Applies to**: `change_type == feature || change_type == bugfix`

**Skill**: `writing-plans`

**Instructions**:

1. Update `.orbit-state`: `substage: planning`

2. **Execute writing-plans** (load skill or use inline fallback — see Tool Compatibility):
   > "Read the OpenSpec artifacts in openspec/changes/<change-id>/ as your spec input. When you complete the plan and would normally invoke subagent-driven-development, instead output [ORBIT_CHECKPOINT: Stage 3 complete]."

3. Writing-plans runs: Scope check → File structure → Bite-sized tasks → Self-review

4. Output `[ORBIT_CHECKPOINT: Stage 3 complete]`

5. **Orbit takes over — Bridge to tasks.md**:
   - Parse the plan document for task sections
   - Write `openspec/changes/<change-id>/tasks.md` with **reference links** (NOT compressed summaries):
     ```markdown
     - [ ] 1. 实现认证模块 → 详见: docs/superpowers/plans/2026-07-16-oauth.md#task-1
     - [ ] 2. 实现授权中间件 → 详见: docs/superpowers/plans/2026-07-16-oauth.md#task-2
     ```
   - Read plan document path → write to `.orbit-state.plan_doc`
   - Parse total task count → write to `.orbit-state.total_tasks`

6. Update `.orbit-state`: `stage: 4, substage: implementing, current_task: 0`

**Artifacts**: `docs/superpowers/plans/YYYY-MM-DD-<name>.md`, `tasks.md`

**Transition**: Stage 4

---

## Stage 4: Implement

**Applies to**: `change_type == feature || change_type == bugfix`

**Skill**: `subagent-driven-development`, `test-driven-development`, `systematic-debugging`

### Pre-flight: Worktree Cleanliness Check

Before commit mode selection, verify the git worktree is clean:

1. Run `git status --porcelain`
2. If there are uncommitted changes:
   ```
   [ORBIT] 检测到工作区有未提交变更：
   <list modified files>
   
   请选择：
   1. 提交后再继续 — 输入 commit message，提交后进入下一步
   2. 暂停，我手动处理 — 工作流暂停，处理后输入 continue 恢复
   3. 丢弃变更，继续 — 警告：将丢失所有未提交内容（需二次确认）
   ```
   - `1` → user provides commit message → `git add . && git commit -m "..."` → proceed
   - `2` → pause, wait for "continue" → re-check cleanliness
   - `3` → show secondary confirmation:
     ```
     将丢弃所有未提交变更，此操作不可恢复。

     请选择：
     1. 确认丢弃 — 执行 git reset --hard + git clean -fd
     2. 取消 — 返回上一级选择
     ```
     → "1" → `git reset --hard` + `git clean -fd`
     → "2" → re-display worktree cleanliness options
3. If clean: proceed to commit mode selection

**Rationale**: Stage 4 atomic rollback records `git rev-parse HEAD` before each task. Uncommitted changes make the rollback point meaningless — a reset would lose work that was never part of any task.

### Pre-flight: Commit Mode Selection

Before the first task, require user to choose commit mode:
```
[ORBIT] Stage 4 开始。选择提交模式：

1. auto（推荐） — 每个 Task 完成后自动提交，全程无需干预
2. review — 每个 Task 完成后展示变更摘要，等待确认后再提交

请选择 (1/2)：
```
Write choice to `.orbit-state.commit_mode`.

### Pre-flight: Task List Confirmation Gate

Before entering the per-task loop, parse `tasks.md` and present the full task list for user confirmation:

```
=== [ORBIT_GATE] Stage 4 任务清单 ===

共 {total_tasks} 个任务：

1. <task-1 title>
2. <task-2 title>
...

完整详情: openspec/changes/<change-id>/tasks.md
参考: {plan_doc path}

请选择：
1. 确认 — 按此清单开始执行，依次完成所有任务
2. 修改任务 — 用自然语言描述需要调整的内容（新增/删除/重排/合并）
   Orbit 会回到 Stage 3 调整 plan 文档和 tasks.md，然后重新展示
```

- "1" → proceed to Record Stage 4 Baseline
- "2" → return to Stage 3, re-run writing-plans with the user's adjustment instructions, re-generate tasks.md, then re-display this gate

### Pre-flight: Record Stage 4 Baseline

Immediately before the per-task loop begins, capture the current HEAD as the Stage 4 rollback baseline:
```
git rev-parse HEAD → .orbit-state.stage4_baseline_commit
```
This is the rollback anchor for Task 1 (and the whole implementation phase). Every per-task `rollback_base` chains off it: Task 1's `rollback_base` == `stage4_baseline_commit`; Task N>1's `rollback_base` == `task_history[N-1].commit`.

### Per-Task Loop

For each task (1..total_tasks, sequential):

**Step 1 — Record Rollback Point**:
```
git rev-parse HEAD → write to .orbit-state.task_history[N].rollback_base
```
This is the pre-task HEAD — the exact commit a failed Task N would reset to. (For Task 1 it equals `stage4_baseline_commit`; the explicit write keeps the per-task target self-contained for resume.)

**Step 2 — Dispatch Implementer Subagent**:
**Execute subagent-driven-development** (load skill or use inline fallback — see Tool Compatibility) with task instructions. The subagent receives:
- Task description from `tasks.md` entry
- **Full plan section** from the plan document (read via reference link in tasks.md — DO NOT compress)
- TDD enforcement (loads `test-driven-development` internally)

Subagent internal flow: RED → VERIFY → GREEN → VERIFY → REFACTOR → SELF-REVIEW → **COMMIT (always — this is the prerequisite for atomic rollback)**

Subagent output handling:
- `DONE` → proceed to Step 3 (Spec Compliance Review)
- `DONE_WITH_CONCERNS` → proceed to Step 3, but log concerns in `.orbit-state.task_history[N].notes` for review attention
- `NEEDS_CONTEXT` → pause, relay subagent's questions to user, resume subagent with answers
- `BLOCKED` (cannot resolve a bug): Orbit **executes systematic-debugging** (load skill or use inline fallback — see Tool Compatibility) for root cause analysis. After analysis, user decides: retry task / skip task / terminate Stage 4

**Step 3 — Spec Compliance Review** (subagent-driven built-in):
- Pass → continue
- Fail → trigger atomic rollback

**Step 4 — Code Quality Review** (subagent-driven built-in):
- Pass → continue
- Fail → trigger atomic rollback

**Step 5 — Commit Confirmation** (commit already done in Step 2):

*auto mode*: Output summary only, continue.
```
[ORBIT] Task N 已完成，自动提交。
  变更文件: <list>
  Commit: <hash> <message>
```

*review mode*: Show diff, wait for user input.
```
[ORBIT] Task N 已完成。变更如下：
  <file>  (+N, -M)
  ...

请确认：
  1. 确认保留此提交 — 接受变更，继续下一个 Task
  2. 丢弃此变更 — 触发回滚，不可恢复（需二次确认）
  3. 暂停审阅 — 工作流暂停，输入 continue 恢复
  4. 切换为自动模式 — 剩余任务不再询问，自动提交

你的选择 (1/2/3/4)：
```
- `1` → confirm, output commit hash, continue
- `2` → show secondary confirmation:
   ```
   是否确认丢弃？此操作不可恢复。

   请选择：
   1. 确认丢弃 — 触发回滚，标记 Task 失败
   2. 取消 — 保留当前提交，返回审阅界面
   ```
   → "1" → trigger atomic rollback → mark task `failed`
   → "2" → return to review interface
- `3` → write `.orbit-state.substage = "review_paused_task_N"` → pause → on "continue", re-display review interface
- `4` → update `commit_mode: "auto"`, auto-commit this task + remaining tasks

**Step 6 — Orbit Sync**:
- Update `tasks.md` checkbox: `- [ ]` → `- [x]`
- `git rev-parse HEAD → write to .orbit-state.task_history[N].commit` (the post-task commit hash produced by Step 2's commit)
- Update `.orbit-state.task_history[N].status = done`
- `.orbit-state.current_task += 1`

### Atomic Rollback

When rollback is triggered (review failure or user chooses option 2):

1. Show what will be discarded:
   ```
   git status --short
   git status --short --untracked-files=normal
   git diff --stat HEAD
   ```
2. User confirmation:
   ```
[ORBIT_ROLLBACK] Task N 未通过 review。将回滚到 Task N 开始前的提交点（rollback_base）。
   将丢弃 {N} 个已修改文件和 {M} 个未跟踪文件。
   未跟踪文件: {list from git status --short --untracked-files=normal}

   请选择：
   1. 继续 — 执行回滚，丢弃当前 Task 的所有变更
   2. 放弃 — 不回滚，保留当前状态供手动检查
   ```
3. On "1": execute `git reset --hard <task_history[N].rollback_base>` first, then show untracked files again with `git status --short --untracked-files=normal`, then `git clean -fd` only with user acknowledgement of the listed files.
4. Mark `.orbit-state.task_history[N].status = failed`, `.rollback_to = task_history[N].rollback_base`
5. Pause for user decision: retry task / skip task / terminate Stage 4

**NEVER use `git stash`**. Rollback uses `reset --hard` + `clean -fd` with user confirmation before clean.

### Cross-Task Bugs (hotfix_queue)

When a bug is discovered in an already-completed task:

1. **Do NOT modify tasks.md list structure** (it's read-only during Stage 4 — only checkbox states change)
2. Append to `.orbit-state.hotfix_queue`:
   ```yaml
   hotfix_queue:
     - source_task: N
       description: "<bug description>"
       discovered_at_task: M
   ```
3. After all planned tasks complete (current_task == total_tasks), process `hotfix_queue` **FIFO**:
   - Each hotfix runs full TDD + review (same quality as planned tasks)
   - Commit mode follows `.orbit-state.commit_mode`
   - After each hotfix completes, **append entry to tasks.md** for audit trail:
     ```markdown
     - [x] Hotfix: <description>
     ```
     (Main task phase has ended, no parallel subagents — safe to modify)
   - New bugs discovered during hotfix → append to queue tail
   - When queue empty → Stage 5

### Spec Gap (Not Implementation Bug)

If a bug reveals a spec defect (not an implementation error):

1. Stop Stage 4
2. **Clear all Stage 3/4 state** in `.orbit-state`:
   ```yaml
   current_task: 0
   total_tasks: 0
   task_history: []
   hotfix_queue: []
   plan_doc: ""
   ```
3. Set `stage: 2, substage: spec_gap`
4. Preserve git history (no rebase — old commits kept in reflog)
5. Return to Stage 2 to update spec, then re-run Stage 3 → 4

**Transition**: Stage 5

---

## Stage 5: Verify & Complete

**Applies to**: all change types

**Skills**: `verification-before-completion`, `openspec-verify-change`, `openspec-archive-change`, `finishing-a-development-branch`

**Instructions**:

1. Update `.orbit-state`: `stage: 5, substage: verifying`

2. **Execute verification-before-completion** (load skill or use inline fallback — see Tool Compatibility): run `test_cmd` from `.orbit-state`, confirm all pass

3. **Execute openspec-verify-change** (load skill or use inline fallback — see Tool Compatibility): code vs spec consistency check

4. Update `.orbit-state`: `substage: archiving`

5. **Execute openspec-archive-change** (load skill or use inline fallback — see Tool Compatibility): archive change, sync delta specs → main specs

6. **Execute finishing-a-development-branch** (load skill or use inline fallback — see Tool Compatibility):
   - Read `.orbit-state.branch_name`
   - Read `.orbit-state.origin_branch`
   - Check if branch exists: `git show-ref --verify --quiet refs/heads/{branch_name}`
     - If exists & differs from current branch → `git checkout {branch_name}` (pause if current branch has uncommitted changes)
     - If exists & is current branch → proceed
     - If not exists → `git checkout -b {branch_name}` (create from current HEAD)
   - **Base branch routing**:
     - If `origin_branch` is `main` or `master` → delegate to `finishing-a-development-branch` skill normally (its auto-detection of base branch via `git merge-base` will be correct).
     - If `origin_branch` is something else (e.g., another feature branch like `feature/xxx`) → Orbit handles merge directly. `finishing-a-development-branch` hardcodes `git merge-base HEAD main/master` which would detect the wrong target. Orbit bypasses it:
       1. `git checkout {origin_branch}`
       2. `git merge {branch_name}`
       3. `git branch -d {branch_name}`
       4. Output:
          ```
          [ORBIT] 合并完成: {branch_name} → {origin_branch}
          
          ✓ 验证通过
          ✓ 制品已归档
          
          后续操作：
          1. Push — git push origin {origin_branch}
          2. 保留当前状态 — 不做任何操作
          
          [ORBIT] Stage 5 完成 ✓
          ```
   - Note: `finishing-a-development-branch` auto-detects the current branch via `git rev-parse`; there is no parameter-passing interface. Orbit must ensure the correct branch is checked out beforehand. When `origin_branch` is non-standard (not main/master), Orbit bypasses `finishing-a-development-branch` for the merge step to avoid base-branch detection errors.

7. Update `.orbit-state`: `substage: complete`

---

## Self-Check (Pre-Action Guard)

**Trigger**: Before executing `brainstorming`, `writing-plans`, `subagent-driven-development`, or `finishing-a-development-branch` (whether via native skill or inline fallback). Also runs on Resume and before every stage transition (Stage N → Stage N+1).

**Procedure (Stage Check)**:
1. Read `.orbit-state.stage`
2. Check against the legal stage table:

| Skill | Legal Stage | .orbit-state.stage Expectation |
|-------|------------|-------------------------------|
| `brainstorming` | Stage 1 | `stage == 1` |
| `writing-plans` | Stage 3 | `stage == 3` |
| `subagent-driven-development` | Stage 4 | `stage == 4` |
| `finishing-a-development-branch` | Stage 5 | `stage == 5` |

3. If mismatch:
   - Output: `[ORBIT_SELF_CHECK_FAILED] Attempted to load {skill} but stage={actual}, expected={expected}`
   - Do NOT load the skill
   - Re-read `.orbit-state` and jump to the correct stage

4. If match:
   - Output: `[ORBIT_SELF_CHECK_PASSED] Loading {skill}`
   - Load and execute

**Procedure (Integrity Check)**: After the stage check passes, verify cross-field consistency:
1. **preliminary guard**: If `stage >= 2` and `preliminary == true`: output `[ORBIT_INTEGRITY_FAILED] stage={stage} but preliminary is still true — Stage 1 never finalized the change-id.` → abort current action, prompt user to either re-run Stage 1 or manually set `preliminary: false`. This guard prevents the workflow from entering Stage 2+ with a provisional change-id.
2. **tasks.md existence**: If `stage >= 3`: check `openspec/changes/<change_id>/tasks.md` exists. Missing → `[ORBIT_INTEGRITY_FAILED] tasks.md missing for stage={stage}` → abort.
3. **Stage 4 consistency**: If `stage >= 4`: check `plan_doc` is not empty (empty → abort). Check `current_task <= total_tasks` (violated → abort). Output `[ORBIT_INTEGRITY_FAILED]` with the offending field values.
Output `[ORBIT_INTEGRITY_PASSED]` on success, then continue.

### Self-Check Hook for Sub-Skill Exit

If you ever find yourself executing a sub-skill's terminal target (e.g., `finishing-a-development-branch`) WITHOUT having output a `[ORBIT_CHECKPOINT]` first:
- STOP immediately
- Output: `[ORBIT_OVERRIDE] Detected illegal jump to {skill} without checkpoint. Returning to Orbit controller.`
- Re-read `.orbit-state` and resume from the correct stage

---

## Tool Compatibility

Orbit is designed to work across AI coding tools. The core workflow (state machine, bridge rules, user interactions) is tool-agnostic. Only the skill-loading mechanism adapts.

### Sub-Skill Loading

When Orbit instructs you to "load" or "execute" a sub-skill, follow this resolution order:

1. **Native skill** (if available): Read `.agents/skills/<name>/SKILL.md` or `~/.agents/skills/<name>/SKILL.md` and follow it with Orbit's override instruction.
2. **Inline instructions**: If the skill file is not found, use the inline fallback below.
3. **Ask user**: If neither is available and the inline fallback is insufficient, ask the user how they want to proceed.

### Inline Fallback Instructions

When a sub-skill file is not available, execute the following inline workflows:

**brainstorming** (Stage 1):
> Explore the user's request through 2-3 rounds of clarifying questions (one at a time). Understand: problem context, constraints, success criteria. Then produce a design document at `docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md` with sections: Problem Statement, Feature Description, Impact Analysis, Architecture Decisions, Functional Requirements (Given/When/Then), Non-functional Requirements. Get user approval before proceeding.

**writing-plans** (Stage 3):
> Read the OpenSpec artifacts in `openspec/changes/<change-id>/`. Break the work into bite-sized tasks (each completable in one focused session, ~30-60 min). For each task: title, file paths affected, implementation steps, code examples, dependencies on other tasks. Write to `docs/superpowers/plans/YYYY-MM-DD-<name>.md`. Self-review for completeness and correct ordering.

**test-driven-development** (Stage 4, inside subagent):
> For each task: Write a failing test first (RED). Run it, confirm it fails for the right reason. Write minimal implementation code to pass (GREEN). Run tests, confirm pass. Refactor if needed (REFACTOR). Run tests again. Self-review code quality.

**subagent-driven-development** (Stage 4):
> For each task in tasks.md: read the full task description (from plan doc reference link). Implement using TDD (RED-GREEN-REFACTOR). Run spec compliance check (does implementation match spec?). Run code quality check. Commit with descriptive message. Output status: DONE / DONE_WITH_CONCERNS / NEEDS_CONTEXT / BLOCKED.

**systematic-debugging** (Stage 4, on BLOCKED):
> Reproduce the bug. Identify root cause through: reading error messages, tracing execution flow, checking recent changes. Form a hypothesis. Test the hypothesis. If confirmed, fix. If not, iterate. Document the root cause and fix.

**verification-before-completion** (Stage 5):
> Run the test command from `.orbit-state.test_cmd`. Confirm all tests pass. Check for: uncommitted changes, incomplete TODOs, debug code left behind. Report status.

**openspec-verify-change** (Stage 5):
> Verify the implemented code against the OpenSpec specs in `openspec/changes/<change-id>/specs/<capability>/spec.md`. For each `### Requirement:` and its `#### Scenario:` (GIVEN/WHEN/THEN), check whether the implementation satisfies it. Report any requirement that the code does not fulfill, citing the spec requirement and the file/function where the gap is. If `openspec verify` CLI is available, prefer it; otherwise perform the manual spec-vs-code trace above.

**openspec-archive-change** (Stage 5):
> Archive the change: move the delta specs from `openspec/changes/<change-id>/specs/` into the main `openspec/specs/<capability>/spec.md` (merge ADDED requirements into the live spec), mark the change as archived, and confirm `openspec/changes/<change-id>/` no longer needs active tracking. If `openspec archive` CLI is available, prefer it; otherwise perform the merge manually: append each `### Requirement:` block from the change's delta spec into the corresponding main spec file (creating the capability file if absent), then leave the change directory in place as an audit record. Report what was merged where.

**finishing-a-development-branch** (Stage 5):
> Ensure the correct branch is checked out (from `.orbit-state.branch_name`). Determine integration strategy: merge to main, rebase, or squash-merge based on project conventions. Check for merge conflicts. If clean, proceed with merge. If conflicts, resolve them. Delete the feature branch after merge if project convention requires it.

### OpenSpec CLI Fallback

When Orbit instructs an `openspec` CLI command (`openspec status`, `openspec verify`, or `openspec archive`):
- If the `openspec` CLI is installed: run it as instructed.
- If not installed: use the inline fallback for the corresponding skill (`verification-before-completion` already covers `test_cmd`; `openspec-verify-change` and `openspec-archive-change` inline fallbacks above cover verify and archive respectively). For `openspec status` specifically, fall back to this validation checklist:
  1. Confirm `openspec/changes/<change-id>/` directory structure is complete
  2. Confirm `proposal.md` contains `## Why`, `## What Changes`, `## Impact` sections
  3. Confirm `specs/<capability>/spec.md` contains `## ADDED Requirements` and at least one `### Requirement:` — **required for `feature` and `bugfix`; for `docs` this is optional/skipped** (docs changes default to proposal.md only; see Stage 2 Step 4 and bridge-rules "Docs → proposal.md（轻量）")
  4. Confirm each `### Requirement:` has at least one `#### Scenario:` with GIVEN/WHEN/THEN
  5. Confirm spec files use valid EARS format (each requirement has a priority and description)
  6. Confirm capabilities referenced in `proposal.md` have corresponding `specs/<capability>/spec.md` files — **for `docs`, if no specs were written, skip this check**
  Report any validation failures with specific file and section references.

### Tool-Specific Setup

| Tool | Setup |
|------|-------|
| **Codex** | Place in `~/.agents/skills/orbit/` or `.agents/skills/orbit/`. Auto-discovered. |
| **Claude Code** | Reference this SKILL.md from `CLAUDE.md` or place in `.claude/commands/orbit.md`. |
| **Cursor** | Reference from `.cursor/rules/orbit.mdc` or `.cursorrules`. Use `@orbit` trigger. |
| **Windsurf** | Reference from `.windsurfrules`. Use "Orbit" in natural language. |
| **Generic / AGENTS.md** | Add `orbit` to `.agents/skills/` directory. Reference from `AGENTS.md`. |

---

## Reference Files

- `references/state-schema.yaml` — `.orbit-state` field definitions, types, and defaults
- `references/bridge-rules.md` — Artifact format conversion rules between stages
- `references/stage-transitions.md` — Stage transition rule table
