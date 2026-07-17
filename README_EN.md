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

# Orbit: The OpenSpec × Superpowers Workflow Orchestrator

> **One slash command. End-to-end engineering pipeline for AI coding.**

---

## Sound familiar?

You ask your AI coding assistant to add OAuth login. It says "sure!" and then:

- Round 1: implements auth with no token refresh
- Round 2: adds token refresh, but misses the 401 error path
- Round 3: handles 401, but breaks session management
- Round 4: you start wondering if the requirements were ever right to begin with

**The AI isn't the problem. The lack of process is.** An AI coding assistant is a race car with no brakes — incredibly fast, but every turn is a gamble.

Orbit is the track.

---

## What is Orbit?

**Orbit is an Agent Skill.** Not an npm package. Not a CLI tool. Not a VS Code extension. It's a single `SKILL.md` file plus a few rule tables. Drop it into `~/.agents/skills/` and your AI coding assistant understands it immediately.

Its job is simple: **wire OpenSpec and Superpowers into one end-to-end pipeline.**

```
OpenSpec (the WHAT: requirements + spec management)
        ↕
    Orbit (orchestration layer: state machine + bridges + resume)
        ↕
Superpowers (the HOW: brainstorming + TDD + review + archiving)
```

Orbit rewrites nothing. It does exactly four things: **decide the stage, execute the bridge, control transitions, persist state.**

---

## Why Orbit Wins

### 1. Zero Dependencies. Pure Skill.

```
npm install   — not needed.
Node.js 20+   — not needed.
Bash scripts  — not needed.

Just one SKILL.md file.
```

No install command. No environment requirements. Works on any AI coding tool that supports Agent Skills.

### 2. State-Persistent. Never Lose Context.

Every change maintains a YAML state file at `openspec/changes/<change-id>/.orbit-state` tracking the current stage, substage, task progress, and commit history. **Session crashed? Type "continue" and resume exactly where you left off.**

### 3. Mandatory Human Review Gate

Stage 2's Blocking Human Review Gate **cannot be skipped**. Before the AI proceeds to planning and implementation, you must approve the generated OpenSpec artifacts. Tell the AI in plain English: "the third requirement is wrong" and Orbit locates the right file and fixes it.

No garbage in, no garbage out.

### 4. Approach Analysis

Complex changes trigger a pre-spec analysis showing 2–3 implementation approaches — each with pros/cons, effort estimates, and risk levels, plus a recommended pick. You choose the path, Orbit generates artifacts accordingly.

### 5. Atomic Rollback

Stage 4 commits each task independently. Review fails? `git reset --hard` + `git clean -fd` roll back to the last clean state. No messy git history.

### 6. Cross-Tool, One Skill

| Tool | Trigger | Global Setup |
|------|---------|-------------|
| **Codex** | `/orbit` or mention | `~/.agents/skills/orbit/` — auto-discovered |
| **Claude Code** | `/orbit` or mention | Same, plus `CLAUDE.md` reference |
| **Cursor** | `@orbit` | `.cursorrules` or `.cursor/rules/orbit.mdc` |
| **Windsurf** | "use Orbit" in natural language | `.windsurfrules` |

If a sub-skill file isn't available in a particular tool, Orbit provides inline fallback instructions.

### 7. Spec Gap Detection

If Stage 4 discovers the spec itself has a defect (not an implementation bug), Orbit auto-rewinds to Stage 2 to fix the spec, then re-runs Stage 3 → 4. You never code against a broken spec.

---

## The Pipeline at a Glance

6 stages. Three paths. Automatically selected by change type:

```
feature:  0 ──→ 1 ──→ 2 ──→ 3 ──→ 4 ──→ 5   (full pipeline)
bugfix:   0 ────────→ 2 ──→ 3 ──→ 4 ──→ 5   (skip design)
docs:     0 ────────→ 2 ──────────────→ 5   (lightweight)
```

| Stage | Name | What Happens | Applies To |
|-------|------|-------------|-----------|
| **Stage 0** | Bootstrap | Generate change-id, detect test command, classify type | all |
| **Stage 1** | Explore & Design | Brainstorming → design doc → confirm change-id | feature |
| **Stage 2** | Specify | Approach analysis (optional) → OpenSpec artifacts → **review gate** | all |
| **Stage 3** | Plan | Break into bite-sized tasks → tasks.md | feature, bugfix |
| **Stage 4** | Implement | TDD per task + spec compliance + auto commit/rollback | feature, bugfix |
| **Stage 5** | Verify & Complete | Run tests → archive → branch cleanup | all |

Every stage ends with `[ORBIT_CHECKPOINT]`. Sub-skill terminal jumps are intercepted — Orbit owns the routing.

---

## Quick Start

### Prerequisites

- An AI coding tool with Agent Skills support (Codex, Claude Code, Cursor, Windsurf)
- [OpenSpec](https://github.com/Fission-AI/OpenSpec) installed
- [Superpowers](https://github.com/obra/superpowers) (optional — Orbit has inline fallbacks)

### 30-Second Install

```bash
git clone https://github.com/yaozoo/orbit.git /tmp/orbit-install

# Global install (recommended — shared across all projects)
mkdir -p ~/.agents/skills/orbit
cp /tmp/orbit-install/SKILL.md ~/.agents/skills/orbit/
cp -r /tmp/orbit-install/references ~/.agents/skills/orbit/

# For Claude Code, also create a global CLAUDE.md
echo '# Custom Skills
Refer to ~/.agents/skills/orbit/SKILL.md for the Orbit workflow orchestrator.' >> ~/.claude/CLAUDE.md

rm -rf /tmp/orbit-install
```

### Directory Structure

```
~/.agents/skills/orbit/
├── SKILL.md                  # main orchestrator
└── references/
    ├── state-schema.yaml     # .orbit-state field definitions
    ├── bridge-rules.md       # inter-stage artifact conversion
    └── stage-transitions.md  # stage transition interception table
```

**Restart your AI coding tool** after installation.

---

## Usage Guide

### Activation

Orbit **does not auto-activate**. You must explicitly invoke it:

| Method | Example | Tools |
|--------|---------|-------|
| Slash command | `/orbit add OAuth login` | Codex, Claude Code |
| Explicit mention | `Use Orbit to fix the payment validation bug` | all |
| @ mention | `@orbit implement user auth module` | Cursor, Windsurf |

> Doing a single task? Use the individual skill directly. Orbit is for end-to-end orchestration.

---

### Scenario 1: New Feature (Full Pipeline)

**For**: greenfield features, refactors, architectural changes.

```text
You: /orbit add OAuth login to the system

Orbit:
  Stage 0: change-id "add-oauth-login", classified as feature
  → auto-checkout branch feature/add-oauth-login

  Stage 1: brainstorming kicks in
  → 2-3 rounds of clarifying questions
  → produces design doc: docs/superpowers/specs/2026-07-17-oauth-design.md
  → confirm or rename change-id
  → [ORBIT_CHECKPOINT: Stage 1 complete]

  Stage 2: generate OpenSpec artifacts
  → if multiple approaches exist, present approach analysis (A/B/C + recommendation)
  → generate proposal.md + design.md + spec.md
  → 🚧 Human Review Gate — must approve before proceeding
  → [ORBIT_CHECKPOINT: Stage 2 complete]

  Stage 3: break into tasks
  → tasks.md with reference links to plan doc sections
  → [ORBIT_CHECKPOINT: Stage 3 complete]

  Stage 4: TDD implementation
  → choose commit mode: auto or review (per-task approval)
  → per task: RED → GREEN → REFACTOR → commit
  → independent commits, atomic rollback on failure
  → cross-task bugs auto-queued in hotfix_queue
  → [ORBIT_CHECKPOINT: Stage 4 complete]

  Stage 5: verify & complete
  → run test command, confirm all pass
  → spec compliance check
  → archive change, sync delta specs → main specs
  → branch cleanup (merge/rebase/squash)
  → ✅ Done
```

---

### Scenario 2: Bug Fix

**For**: defects, regressions, cross-module bugs.

```text
You: Use Orbit to fix the payment validation bug — $0 amounts pass through

Orbit:
  Stage 0: change-id "fix-payment-validation", classified as bugfix
  → skip Stage 1 (no design doc needed)

  Stage 2: approach analysis triggers automatically
  → 2-3 fix strategies:
    Approach A: add validation at Controller layer (recommended)
    Approach B: add validation at Service layer
    Approach C: add database constraint
  → you pick A
  → generate OpenSpec artifacts
  → 🚧 Human Review Gate

  Stage 3 → 4 → 5: same as feature
```

Simple fixes (one-liners, typos) skip approach analysis automatically.

---

### Scenario 3: Docs / Config Change (Lightweight)

**For**: README updates, Dockerfile tweaks, configs, comments.

```text
You: /orbit update README with deployment instructions

Orbit:
  Stage 0: change-id "update-readme-deploy", classified as docs
  → skip Stage 1 (design), Stage 3 (planning), Stage 4 (implementation)

  Stage 2: extract from your description, generate OpenSpec artifacts
  → 🚧 Human Review Gate

  Stage 5: verify → archive → branch cleanup
  → ✅ Done
```

---

### Resume from Interruption

Session crashed? IDE restarted? No problem.

```text
You: continue

Orbit:
  → scans openspec/changes/*/.orbit-state
  → finds incomplete changes
  → integrity check (tasks.md still there? plan_doc still there?)
  → [ORBIT_RESUME] Resuming from Stage 4.3
  → picks up where you left off
```

Every `.orbit-state` file records exact `stage`, `substage`, and `updated_at`. You never start over.

---

## Comparisons

### Orbit vs. rpamis/comet

Orbit was originally named Comet, renamed after discovering [rpamis/comet](https://github.com/rpamis/comet). They are unrelated projects:

| Aspect | rpamis/comet | Orbit |
|--------|-------------|-------|
| **Nature** | NPM CLI tool | Agent Skill (SKILL.md) |
| **Install** | `npm install -g @rpamis/comet` | copy file to `~/.agents/skills/` |
| **Dependencies** | Node.js 20+, Bash | AI tool with Agent Skills support |
| **Usage** | CLI + skill commands | `/orbit` in conversation |
| **State** | CLI + filesystem | YAML state file + resume |
| **Cross-tool** | CLI-capable platforms | Codex / Claude Code / Cursor / Windsurf |

### Orbit vs. Other Orchestrators

| Project | Type | Dependencies | Distinction |
|---------|------|-------------|-------------|
| **Orbit** | Agent Skill | AI tool only | Zero deps, pure skill, cross-tool |
| superspec | OpenSpec Schema | OpenSpec + Superpowers | OpenSpec as orchestrator |
| openflow | NPM CLI | Node.js | Multi-stage commands |
| sddflow | NPM CLI | Node.js | brainstorming → spec → build → close |
| easyflow | NPM CLI | Node.js 20+ | 8-stage state machine + governance |

**Orbit's unique position**: the only pure-Skill orchestrator. No `npm install` required.

---

## Design Philosophy

### WHAT vs. HOW — Separated, Then United

Two powerful open-source projects exist in the AI coding space:

- **OpenSpec** handles the **WHAT**: requirements, change tracking, spec management.
- **Superpowers** handles the **HOW**: brainstorming methods, TDD discipline, review process, archiving strategy.

Both are excellent. Both are silos. **Orbit is the glue between them** — a lightweight orchestration layer that connects them without rewriting either.

### What Orbit Won't Do

- **Rewrites no sub-skill**: brainstorming, TDD, and code review logic live in their own SKILL.md files.
- **No UI integration**: all interaction stays in the conversation.
- **No CI/CD hooks**: doesn't trigger Actions, doesn't manage Docker.
- **No Git replacement**: Git operations belong to `finishing-a-development-branch`.
- **No cross-project memory**: each `.orbit-state` is per-change.

---

## When to Use Orbit

### ✅ Good Fits

| Situation | Path |
|-----------|------|
| New feature | feature (full pipeline) |
| Complex bug (multi-module, multiple approaches) | bugfix + approach analysis |
| Simple bug (one-liner, typo, mechanical fix) | bugfix (analysis auto-skipped) |
| Docs / config / README | docs (lightweight) |
| Multi-person collaboration (needs clear spec + tasks) | feature or bugfix |
| High interruption risk (multi-day work) | any path (resume works) |

### ❌ Skip Orbit When

| Situation | Use Instead |
|-----------|------------|
| Just brainstorming | `brainstorming` skill directly |
| Just writing a spec | `openspec` skill directly |
| Just TDD coding | `test-driven-development` skill directly |
| Just code review | `requesting-code-review` skill directly |
| Throwaway experiments | no process needed |

**Orbit is an end-to-end orchestrator, not a single-task runner.**

---

## FAQ

**Q: How is this different from OpenSpec's openspec-proposal?**

OpenSpec's proposal covers only Stage 2 artifact generation. Orbit covers the entire lifecycle — from brainstorming (Stage 1) through implementation (Stage 4) to verification and archiving (Stage 5).

**Q: What if my project doesn't have Superpowers skills?**

Orbit ships inline fallback instructions for every sub-skill. Even if a particular Superpowers SKILL.md is absent, Orbit completes the stage using its built-in directives.

**Q: Can I run multiple Orbit changes simultaneously in the same project?**

Not recommended. Orbit's state is per-change, but Stage 4 atomic rollback depends on a clean git worktree. Work one change at a time.

**Q: Stage 4's review mode is too slow. Can I switch to auto?**

Yes. In the review interface, choose option `4` to switch to auto mode. All remaining tasks commit automatically.

**Q: Does Orbit rewrite my git history?**

No. Rollback uses `git reset --hard`, but previous commits remain in the reflog. You can always `git reflog` to recover.

---

## Contributing

Issues and pull requests welcome.

- **Report bugs**: include your `.orbit-state` file and relevant conversation logs
- **Suggest features**: describe the use case and expected benefit
- **Code contributions**: ensure changes pass the Pre-Action Guard

---

## License

MIT

---

## Acknowledgments

- [OpenSpec](https://github.com/Fission-AI/OpenSpec) — spec-driven development framework
- [Superpowers](https://github.com/obra/superpowers) — AI coding methodology & skill library
- [rpamis/comet](https://github.com/rpamis/comet) — inspired the original design direction
