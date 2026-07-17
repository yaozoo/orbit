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

完整设计文档：[docs/superpowers/specs/2026-07-16-orbit-workflow-design.md](docs/superpowers/specs/2026-07-16-orbit-workflow-design.md)

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
   - If `stage >= 3`: check that `openspec/changes/<id>/tasks.md` exists
   - If `stage == 4`: check that `.orbit-state.plan_doc` path exists
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

**Goal**: Create change directory, detect environment, classify change type.

**Steps**:

1. **Generate change-id**: Parse user request → `<verb>-<noun>` (e.g., `add-oauth-login`). If ambiguous, use `change-YYYYMMDD-NNN`. Validate kebab-case. Conflict check with `ls openspec/changes/`. Create `openspec/changes/<change-id>/` directory.

2. **Write initial .orbit-state**: Set `change_id`, `schema_version: "1.0.0"`, `preliminary: true`, `stage: 0`, `created_at`, `updated_at`. Schema reference: `references/state-schema.yaml`.
   When `preliminary: true`, the workflow is restricted to Stage 0 ↔ Stage 1 only. Stage 2 and beyond cannot proceed until Stage 1 completes and `preliminary` is set to `false`.

3. **Detect test command**: 
   *Prefer headless (CI-compatible) test scripts.* Check `package.json` for
   `test:unit` or `test:ci` first. If not found, fall back to `scripts.test`.
   If the detected script starts a dev server (e.g., `vite`), search for
   headless alternatives in sub-package scripts. Also check `pyproject.toml`
   → `pytest`, `Cargo.toml` → `cargo test`, `go.mod` → `go test ./...`,
   `Makefile` → `make test`. If none match, ask user. Write to `.orbit-state.test_cmd`.

4. **Classify change type**: Keywords → type mapping:
   - `新增/添加/实现/重构/开发/做` → `feature`
   - `修复/修/bug/fix` → `bugfix`
   - `文档/README/Dockerfile/配置/注释` → `docs`
   
   **Show classification with reasoning** and require user confirmation:
   > "识别为 **{type}** 变更（匹配关键词：{keywords}）。
   >  执行路径：{route summary}。
   >  请选择变更类型：
   >  1. feature — 新增功能，走 0→1→2→3→4→5 全流程
   >  2. bugfix — 缺陷修复，跳过 Stage 1，走 0→2→3→4→5
   >  3. docs — 文档变更，走 0→2→5 轻量流程
   >  4. 自定义类型 — 手动指定类型（需说明理由）"

5. Write `change_type` to `.orbit-state`. Generate `branch_name` as `<type>/<change-id>` and write to `.orbit-state.branch_name` (e.g., `feature/add-oauth-login`, `bugfix/fix-payment`, `docs/update-readme`).

**Transition**: If `feature` → Stage 1. If `bugfix` or `docs` → Stage 2.

---

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
   - Update `.orbit-state`: `stage: 2, substage: id_confirmation`
  - Ask user: "Change ID 为 `{id}`，是否保留？（输入新 ID 可重命名）"
   - If renamed: `mv openspec/changes/<old>/ openspec/changes/<new>/`, update `.orbit-state.change_id`, update `.orbit-state.branch_name` to `feature/<new-id>`
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

   Self-assess whether this change has **meaningful alternative implementation approaches** — this is about HOW (technical paths), not WHAT (requirements, which are already defined):

   **Trigger** (present alternatives) when ANY of:
   - Multiple viable technical paths exist (modify existing module vs. create new abstraction)
   - Cross-module coordination required (composable + pages + components)
   - Approach affects existing behavior in non-obvious ways
   - Architectural decision with downstream consequences

   **Skip** (go to Step 4) when ANY of:
   - User request already specifies the approach explicitly
   - Single-line fix, typo, or obvious mechanical change
   - Pure docs/config change with no implementation choice
   - Stage 1 design document already selected and documented the approach

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
   If Step 3 was triggered, artifacts must reflect the selected approach:
   - `openspec/changes/<change-id>/proposal.md` — Why / What Changes / Impact
   - `openspec/changes/<change-id>/design.md` — Architecture / Data Flow
   - `openspec/changes/<change-id>/specs/<capability>/spec.md` — EARS-format requirements

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

### Per-Task Loop

For each task (1..total_tasks, sequential):

**Step 1 — Record Rollback Point**:
```
git rev-parse HEAD → append to .orbit-state.task_history
```

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
- Update `.orbit-state.task_history[N].status = done`
- `.orbit-state.current_task += 1`

### Atomic Rollback

When rollback is triggered (review failure or user chooses option 2):

1. Show what will be discarded:
   ```
   git status --short
   git diff --stat HEAD
   ```
2. User confirmation:
   ```
   Task N 未通过 review。将回滚到 Task N-1 的提交点。
   将丢弃 <N> 个已修改文件和 <M> 个未跟踪文件。

   请选择：
   1. 继续 — 执行回滚，丢弃当前 Task 的所有变更
   2. 放弃 — 不回滚，保留当前状态供手动检查
   ```
3. Execute: `git reset --hard <prev_commit>` + `git clean -fd`
4. Mark `.orbit-state.task_history[N].status = failed`, `.rollback_to = <prev_commit>`
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
   - Check if branch exists: `git show-ref --verify --quiet refs/heads/{branch_name}`
     - If exists & differs from current branch → `git checkout {branch_name}` (pause if current branch has uncommitted changes)
     - If exists & is current branch → proceed
     - If not exists → `git checkout -b {branch_name}` (create from current HEAD)
   - Then load the skill directly
   - Note: `finishing-a-development-branch` auto-detects the current branch via `git rev-parse`; there is no parameter-passing interface. Orbit must ensure the correct branch is checked out beforehand.

7. Update `.orbit-state`: `substage: complete`

---

## Self-Check (Pre-Action Guard)

**Trigger**: Before executing `writing-plans`, `subagent-driven-development`, or `finishing-a-development-branch` (whether via native skill or inline fallback).

**Procedure**:
1. Read `.orbit-state.stage`
2. Check against the legal stage table:

| Skill | Legal Stage | .orbit-state.stage Expectation |
|-------|------------|-------------------------------|
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

**Why only these three?** These are the "transition target" skills that sub-skills automatically point to. Blocking them covers all serious stage-drift scenarios. Brainstorming (Stage 1) and Stage 5 verification skills don't have this risk.

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

**finishing-a-development-branch** (Stage 5):
> Ensure the correct branch is checked out (from `.orbit-state.branch_name`). Determine integration strategy: merge to main, rebase, or squash-merge based on project conventions. Check for merge conflicts. If clean, proceed with merge. If conflicts, resolve them. Delete the feature branch after merge if project convention requires it.

### OpenSpec CLI Fallback

When Orbit instructs `openspec status --change "<id>" --json`:
- If `openspec` CLI is installed: run it as instructed.
- If not installed: manually execute the following validation checklist:
  1. Confirm `openspec/changes/<change-id>/` directory structure is complete
  2. Confirm `proposal.md` contains `## Why`, `## What Changes`, `## Impact` sections
  3. Confirm `specs/<capability>/spec.md` contains `## ADDED Requirements` and at least one `### Requirement:`
  4. Confirm each `### Requirement:` has at least one `#### Scenario:` with GIVEN/WHEN/THEN
  5. Confirm spec files use valid EARS format (each requirement has a priority and description)
  6. Confirm capabilities referenced in `proposal.md` have corresponding `specs/<capability>/spec.md` files
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
