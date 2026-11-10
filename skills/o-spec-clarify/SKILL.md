---
name: o-spec-clarify
description: |
  Clarification decision gate for the o-pipeline. Reads the OpenSpec trio
  o-spec drafted, turns every ambiguity the draft could not settle from
  evidence into a closed multiple-choice decision item (options + a
  recommended option + the evidence gap), renders them into a decision sheet,
  and folds the human's answers (from the approval panel's amend feedback)
  back into the spec dir. Unanswered items take their recommended option;
  deferred items are recorded as open and never re-trigger a round. No
  in-skill confirmation prompt — the human gate is the platform's.
kind: llm_skill
input:
  gitlab_url:
    type: str
    required: true
    description: "GitLab clone URL (.git). Re-cloned fresh — the spec dir arrives via the branch, not via a shared filesystem."
  branch:
    type: str
    required: true
    description: "Mission-input branch. Carries o-spec's openspec/ commit."
  spec_dir:
    type: str
    required: false
    description: "Spec dir name under openspec/ (e.g. 20260101-120000-foo). Omitted on the first round — the newest timestamped dir is used."
  max_decisions:
    type: int
    required: false
    description: "Upper bound on decision items this round. Default 12. Exceeding it is a script error, not a silent truncation."
output:
  exit_code:
    type: int
    required: true
    description: "0 success / 1 failure (spec dir unreadable or spec artifacts missing) / 2 blocked (push failed or spec artifacts missing)"
  status:
    type: str
    required: true
    description: "success | failure | blocked"
  block_reason:
    type: str
    required: false
    description: "Present only when exit_code=2 (e.g. spec_artifacts_missing, push_failed)"
  decision_sheet_path:
    type: str
    required: true
    description: "Path to decisions.md in the spec dir — the human-readable decision sheet."
  sheet_markdown:
    type: str
    required: true
    description: "The full decision sheet as markdown. The human only sees the node output in the approval panel, so this must be self-contained — never a pointer to a file."
  decisions_count:
    type: int
    required: true
    description: "Total decision items known (across rounds; a key answered in round 1 is not re-counted)."
  answered_count:
    type: int
    required: true
    description: "Items the human explicitly answered with an option or a custom answer."
  deferred_count:
    type: int
    required: true
    description: "Items the human explicitly deferred. These never block downstream work."
  pending_count:
    type: int
    required: true
    description: "Items still on their recommended option because the human did not answer them."
  round:
    type: int
    required: true
    description: "Clarification round: 1 = first pass, 2 = the last allowed pass."
  round_exhausted:
    type: bool
    required: true
    description: "true when this was the last allowed round. The human must approve or cancel the run — further amends are refused by the script."
  commit_hash:
    type: str
    required: true
    description: "SHA of this phase's commit (40 hex). Empty if blocked before commit."
tools:
  - bash
  - read_file
category: backend
domain: spec
---

# o-spec-clarify: Interactive Clarification Gate

> The human-interaction point of the o-pipeline. The platform's approval
> primitive is the interaction channel: this node finishes, its output is
> withheld, and a human approves, rejects, or amends. Amend injects the
> human's feedback into this node's context (`_approval_feedback`) and
> re-runs it. This node never asks anything on its own.

## What this node is for

`o-spec` is autonomous by design: it resolves what it can from evidence and
records the rest in `assumptions[]`, lowering `confidence`. That is right for
`o-build` and `o-review`, which consume a settled spec. It is wrong for the
spec phase itself — an assumption nobody agreed to becomes a blind
implementation, and the first signal of it is a failed review at the end.

This node turns "assumptions the human should have seen" into a bounded,
answerable list, and folds the answers back into the spec dir before
`o-build` starts.

**A decision item is a question the evidence cannot answer.** If the codebase,
the requirement doc, the API docs, or the repo conventions settle it, it is
not a decision item — it is an auto-settled ambiguity (recorded in
`assumptions[]` by `o-spec`). Asking a human something the repo already
answers is the fastest way to make them stop answering.

## Run

### 1. Clone + checkout

```bash
git clone <gitlab_url> /tmp/o-spec-clarify/repo
cd /tmp/o-spec-clarify/repo
git checkout <branch>
git pull --ff-only origin <branch>
```

- Branch missing on remote → `exit_code: 2`,
  `block_reason: branch_not_on_remote`, stop.
- Repo dirty after checkout → `exit_code: 2`,
  `block_reason: repo_dirty`, stop.

### 2. Locate the spec dir

```bash
if [ -n "<spec_dir>" ]; then
  spec_dir="openspec/<spec_dir>"
else
  spec_dir=$(ls -d openspec/[0-9]*/ 2>/dev/null | sort | tail -1)
fi
spec_dir="${spec_dir%/}"
```

- No `openspec/[0-9]*/` dir at all → `exit_code: 2`,
  `block_reason: spec_artifacts_missing: no openspec/<timestamp>-<slug> dir`, stop.
  This is the "upstream did not push" case — do not invent a spec.
- `proposal.md`, `design.md`, `tasks.md` missing or empty → `exit_code: 2`,
  `block_reason: spec_artifacts_missing: <file> missing in <spec_dir>`, stop.
- `spec_dir` given but absent → `exit_code: 2`,
  `block_reason: spec_artifacts_missing: <spec_dir> not found`, stop.

### 3. Collect the ambiguities

Read the trio, the requirement doc(s) (`doc_url` is not an input to this node
— read the spec dir's proposal for the requirement text), and the codebase
regions the spec touches.

You are looking for **one kind of thing**: a point where the spec must commit
to a behaviour or a value, and the available evidence leaves more than one
defensible answer. Typical shapes:

- an enumeration whose members the API doc does not pin down
- a default value, a threshold, a timeout, a page size
- which of two existing patterns to follow when both exist in the repo
- whether a change is additive or must migrate existing data
- which of two screens a new entry point replaces

Do **not** raise a decision item for:

- anything the requirement doc states explicitly
- anything the code or API docs already determine (read them; "verified" in
  the evidence below means you actually read the file, not that you inferred)
- anything about implementation style, naming, or file layout — that is
  `o-build`'s call
- anything you can settle from a repo convention you have actually observed
  (then settle it, and note it in the spec's assumptions)

If the trio has no unresolved point, `decisions` is `[]` and the run proceeds
with nothing to ask. That is a valid and common outcome.

### 4. Shape each decision item

Each item:

```json
{
  "key": "enum-values-for-order-status",
  "question": "订单状态在下拉里展示哪些取值？",
  "impact": "high | medium | low — 决定 A2 的验收标准能否写成可判定项",
  "options": [
    {"key": "A", "label": "只展示后端已确认的 4 个状态", "impact": "验收标准可直接写死这 4 个"},
    {"key": "B", "label": "展示全部 6 个状态，未确认的置灰", "impact": "需补一条置灰态验收"}
  ],
  "recommendation_key": "A",
  "recommendation_reason": "后端 orderStatus 枚举只返回这 4 个，其余 2 个是内部流转态",
  "evidence": [
    {"claim": "orderStatus 枚举只有 4 个对外值", "verified": true, "ref": "src/api/order.ts:42"},
    {"claim": "文档提到过 6 个状态但未区分内外", "verified": true, "ref": "DocSpec/prd.md:18"}
  ]
}
```

Rules the script enforces (violations exit 1 and write nothing):

- `key` non-empty and unique across rounds
- `question` non-empty
- `options` at least 2; each option has non-empty `key`, `label`, `impact`;
  option keys unique
- `recommendation_key` must be one of the option keys (omit it only when the
  question genuinely has no defensible default)
- `evidence` non-empty; each entry is `{claim, verified, ref}`; `verified: true`
  requires a `ref` you actually read

`impact` is `high` / `medium` / `low`. It drives nothing mechanically — it
tells the human where to spend attention. Sort your items by impact
descending so the important ones are at the top of the sheet.

**Mark the recommended option explicitly.** The human should be able to accept
the whole sheet by doing nothing. That is why every item needs a
`recommendation_key` and a `recommendation_reason` — not "a suggestion", but
the answer the phase believes is right, with the reason it believes it.

### 5. Run the script

Write `context.json` in the node's working directory:

```json
{
  "spec_dir": "<absolute path to the spec dir>",
  "decisions": [ ...the items from Step 4... ],
  "approval_feedback": "<context._approval_feedback verbatim, omit if absent>",
  "max_decisions": 12,
  "max_rounds": 2
}
```

`max_decisions` comes from this node's `max_decisions` input when present, else
12. `max_rounds` is 2 — the budget the mission allows.

Then:

```bash
python3 <plugin_dir>/scripts/decision_check.py --context context.json
```

The plugin directory is injected into the context; if you cannot find it,
look in `data/plugins/<run_id>/o-spec-clarify/`.

- Exit 0 → the script wrote `decision_output.json` next to `context.json`.
  **Take every field from it verbatim** — `decision_sheet_path`,
  `sheet_markdown`, `items`, `pending_count`, `answered_count`,
  `deferred_count`, `round`, `round_exhausted`. Do not recount, re-rank, or
  re-word. The script owns numbering, answer parsing, and the
  recommended-option fallback.
- Exit 1 → either the shape of `decisions` is invalid, or the round budget is
  exhausted. The script printed the reason to stderr and wrote nothing.
  - Shape invalid → fix `decisions` and re-run.
  - Round exhausted (`澄清轮次已耗尽`) → **this node is done**. Do not try
    to work around it. Emit `exit_code: 1`,
    `block_reason: clarification_rounds_exhausted`, and stop — the run fails
    and a human decides whether to cancel, re-run with a fresh spec dir, or
    accept the current state. Opening new questions here would defeat the
    whole point of the round budget.
- Exit 2 → the script itself failed. This node fails (`exit_code: 1`,
  `block_reason: decision_script_failed`). Do not hand-compute the counts.

`approval_feedback` is the human's amend text. The script parses
`D1=A, D2=自定:..., D3=待查` and applies it. An item the human did not mention
takes its recommended option. An item answered `待查` is deferred — recorded
as open, never blocking, never re-triggering a round.

**`sheet_markdown` must be emitted verbatim.** The human sees the node output
in the approval panel and cannot open `decisions.md` from there — the sheet in
the output *is* the questionnaire. If you paraphrase it, the human answers
questions that are not the ones you recorded.

### 6. Fold the answers into the spec dir

After the script runs, update the trio in place so the answers are part of
the spec `o-build` will read:

- **`decisions.md`** — written by the script. Leave it exactly as written.
  It is the record of what was asked, what was recommended, and what the
  human chose.
- **`proposal.md`** — where a decision settles the *what*, adjust the
  proposal lines that the decision covered. Write the chosen behaviour as a
  settled requirement, not as a question.
- **`design.md`** — where a decision settles the *how*, adjust the affected
  design section and the req→file map entries.
- **`tasks.md`** — where a decision changes what a task must produce, adjust
  that task's wording so its completion criterion matches the decision.

Every decision's outcome must be visible in the trio itself. A decision
answered in the approval panel but not reflected in the spec files is
unresolved — `o-build` reads the trio, not `decisions.md`.

Decisions marked `defer` (待查): leave the affected spec text on its
recommended option, and do **not** rewrite it to a question. The risk stays
visible through `confidence` and `assumptions[]` in `o-spec`'s output.

### 7. Commit + push

```bash
git add openspec/
git -c user.name=mozi_agent -c user.email=mozi_agent@local \
  commit -m "o-spec-clarify: record clarification decisions

round: <round>
decided: <answered_count> answered, <deferred_count> deferred, <pending_count> on recommendation"
git push origin <branch>
```

- Committer identity is the literal `mozi_agent` — do not read `git config`.
- Push fails → `exit_code: 2`, `block_reason: push_failed: <stderr one-liner>`,
  stop. (`o-build` needs this push — see ADR-0001.)
- On success, `commit_hash` = the SHA you just pushed.

## Rounds

The mission allows at most **two** clarification rounds. Round 1 is this
node's first execution; round 2 is its re-execution after the human amends.
The script tracks which round it is (`round` in `decision_output.json`) and
**refuses to run a third round** (`max_rounds: 2`).

The round budget is enforced by the script, not by the platform. The platform
does not bound the number of amends: the manual is explicit that the
approval loop has no upper bound and does not consume the node's
`max_attempts`. `max_approval_timeouts` bounds only the case where the
human goes silent — it is a different problem and does not stop a human who
keeps amending. The script's round gate is therefore the only thing that
actually enforces "at most two rounds".

What round 2 guarantees: a decision item whose `key` already exists in
`decisions.json` keeps its number and its choice, and round 2 only adds
items that a *newly read* piece of evidence (a human's custom answer, a
correction in the spec) made unavoidable. If you find yourself wanting to
add many new items in round 2, you are asking the human to re-answer what
they already answered — stop.

When `round_exhausted` is true, the human sees that this was the last
chance. The next amend is refused by the script and the node fails with
`clarification_rounds_exhausted` — the human then decides to approve,
cancel, or start a fresh run.

## Output

Emit the JSON object matching the `output:` contract above. `status` mirrors
`exit_code`. `commit_hash` is empty only when you blocked before the commit
step.

## Discipline

| Excuse | Reality |
|---|---|
| "The requirement doc is vague, so everything is a decision item" | Vagueness is not ambiguity. Most of it is answerable from the codebase — read it. A decision item needs *two defensible answers and no evidence to choose between them*. |
| "I'll ask the human to be safe" | Every item you raise that the repo could have answered trains the human to approve without reading. That is the failure mode this node exists to prevent. |
| "I'll ask one big question instead of several small ones" | One big question is unanswerable. A human can only pick among options they can see side by side. |
| "The recommended option is obvious, so I'll skip the reason" | The reason is what lets the human disagree with you efficiently. `recommendation_reason` is required in practice. |
| "The human didn't answer, so I'll leave the item open" | Unanswered means "take the recommendation". Leaving it open makes `o-build` guess, which is worse than taking a recorded default. |
| "I'll add the decision notes to proposal.md as questions" | The trio is the spec. A question in it is a hole in it. Write the chosen behaviour as a settled line. |
| "Round 2 is my chance to ask the things I forgot in round 1" | Round 2 exists to absorb answers, not to expand the questionnaire. Items you could have raised in round 1 are a signal that your Step 3 pass was too shallow. |
