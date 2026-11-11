---
name: o-build
description: |
  Implementation phase. Clones the mission branch (which now carries o-spec's
  openspec/ commit), reads proposal/design/tasks, and drives inline
  verification + implementation through every task in tasks.md with per-task
  rollback (real tests where a harness exists, lightweight bash assertions for
  static/config deliverables). Commits code + tests and pushes. No in-skill
  confirmation, no commit-mode prompt. Use as the second node of the o-pipeline
  mission.
kind: llm_skill
input:
  gitlab_url:
    type: str
    required: true
    description: "GitLab clone URL (.git). Re-cloned fresh — o-build does not inherit o-spec's filesystem."
  branch:
    type: str
    required: true
    description: "Mission-input branch. Cloned and checked out; carries o-spec's openspec/ commit."
output:
  exit_code:
    type: int
    required: true
    description: "0 success / 1 failure (tasks exhausted, leave for review) / 2 blocked"
  status:
    type: str
    required: true
    description: "success | failure | blocked"
  block_reason:
    type: str
    required: false
    description: "Present only when exit_code=2 (e.g. spec_artifacts_missing, push_failed)"
  tasks_total:
    type: int
    required: true
    description: "Number of tasks parsed from the spec dir's tasks.md"
  tasks_done:
    type: int
    required: true
    description: "Tasks that passed their test"
  tasks_failed:
    type: int
    required: true
    description: "Tasks that exhausted retries without passing"
  commit_hash:
    type: str
    required: true
    description: "SHA of o-build's phase commit (40 hex). Empty if blocked before commit."
tools:
  - bash
  - read_file
category: backend
domain: build
---

# o-build: Autonomous Implementation

> Second phase. **Never ask the user anything.** State arrives via the remote
> branch (relay, ADR-0001): clone fresh, read `openspec/`, implement, commit,
> push. There is no `.orbit-state` file and no shared workspace.
>
> **Session budget:** the CC session is capped by the runtime's `max_turns`
> (default 60) and the node's `execution_timeout` — whichever hits first
> kills the attempt, and a retry re-runs the node **from scratch**. Keep each
> task's verification tight (one test command, one assertion script); batch
> small related edits instead of one tool call per file. A tasks.md with
> dozens of fine-grained tasks will likely hit the cap and burn retries.

## Run

### 1. Clone + checkout

**Clone into this node's working directory, never a fixed `/tmp` path.** The
working directory is stable across re-runs (a retry re-runs the node from
scratch in the same place, so `git clone` into an existing dir fails — reuse
it), and `/tmp` is shared across the platform's concurrent runs
(`max_active_runs`, default 8) — two runs would collide there.

```bash
node_dir="$PWD"              # capture before any cd
repo_dir="$node_dir/repo"
if [ -d "$repo_dir/.git" ]; then
  cd "$repo_dir"
else
  git clone <gitlab_url> "$repo_dir"
  cd "$repo_dir"
fi
git checkout <branch>
git pull --ff-only origin <branch>
```

- Branch missing on remote → `exit_code: 2`,
  `block_reason: branch_not_on_remote`, stop.

### 2. Self-verify upstream artifacts

Resolve the spec dir o-spec created — the newest subfolder under
`openspec/`, keyed by its fixed-width timestamp prefix:

```bash
spec_dir=$(ls -d openspec/[0-9]*/ 2>/dev/null | sort | tail -1 | sed 's|/$||')
```

- No subfolder → `exit_code: 2`,
  `block_reason: spec_artifacts_missing: no openspec/[0-9]*/ dir — did o-spec push?`,
  stop.
- Then check `$spec_dir/proposal.md`, `$spec_dir/design.md`,
  `$spec_dir/tasks.md` all exist and are non-empty. Any missing →
  `exit_code: 2`,
  `block_reason: spec_artifacts_missing: $spec_dir/<file> absent — did o-spec push?`,
  stop. This is the guard against the old "spec committed but build found
  nothing" failure: if you cannot see o-spec's artifacts in your clone,
  block instead of inventing work.

### 3. Parse tasks

Read `$spec_dir/tasks.md`. Parse every `- [ ]` line into a task
(`file` + `intent`). `tasks_total` = the count. If `$spec_dir/tasks.md` has zero
tasks → `exit_code: 2`, `block_reason: tasks_empty`, stop.

### 3.5 Consume review feedback (only if REVIEW.md present)

If `$spec_dir/REVIEW.md` exists, a prior `o-review` pass ran and wrote
`## issues_remaining` — the work it explicitly handed back to you (this is
a re-pass driven by a `needs-rework` feedback edge). Read that section.
For each remaining issue, fold it into the work list instead of ignoring
it:

- Issue tied to a task already marked `- [x]` → re-open it: flip the task
  back to `- [ ]` and annotate (`> review: <severity>: <message>`) so you
  reprocess that task with the finding in mind. Without this the bug sits
  on a checked task that Step 4 would otherwise skip.
- Issue not tied to any task → add a new `- [ ]` line (file + intent from
  the issue's `file`/`message`) under the related task or at the list end.
- Issues that merely mirror already-`- [ ]` tasks → dedupe; they are
  already in the work list, do not double-count or re-add.

After folding, re-parse the updated `$spec_dir/tasks.md` so `tasks_total`
and the pending list reflect the re-opened + added tasks before Step 4.
Skip this step silently if no REVIEW.md exists (first pass).

### 4. Per-task verification + implementation loop (sequential, inline)

For each task, in order:

1. **Identify or write a verification** for this task's intent.
   - Repo has a test harness (jest / pytest / go test / etc.) → write a real
     test. Run it; it should fail — red.
   - No harness (static HTML/CSS, config, docs, single-file deliverables) →
     the verification is a lightweight bash assertion: file exists, contains
     the expected marker, valid JSON/HTML, structure check. This is NOT a
     block (see Step 5).
   - Task touches UI and `$spec_dir/figma/` exists → `read_file` the PNG
     (`<n>.png`) the task maps to (multimodal — you see the image) and its
     `<n>.json` for exact text/colours/structure. Implement to match the
     render; quote text content verbatim from the node JSON. o-build has no
     Figma token and never calls the API — it only consumes what o-spec
     already fetched onto the branch.
     **UI fidelity is a first-class requirement, not a nice-to-have — the
     render is the source of truth for FORM, not just content.** Before
     marking any UI task done, re-open the PNG and check your
     implementation against this list (each item is a divergence class
     that has shipped as a "low" bug before):
     - **Form**: dialog vs bottom-sheet vs popover vs inline — match the
       frame exactly. A centered dialog where the design shows a bottom
       sheet is a failed task even when every string is identical.
     - **Hierarchy**: which button is primary (filled) vs secondary, and
       their order and placement — copy the frame, don't "improve" it.
     - **Presence**: icons, illustrations, hero images, empty-state art —
       if the frame shows it, it ships. "Missing illustration" is a
       defect, not a simplification.
     - **Text**: quote strings verbatim from the node JSON — Spanish copy,
       punctuation, and casing included.
     - **Values**: colours, radii, and spacing from the node JSON's fills
       and layout — never from memory or a "close enough" palette.
     Never rationalize a mismatch as "仅形态差异" — the form is the first
     thing the user sees.
2. **Implement** the smallest change that makes the verification pass (green).
3. **Run the task's verification** (and the broader suite if one exists).

On failure (test still red, or implementation error):

- **Rollback** only the files this task touched:
  ```bash
  git checkout -- <touched-files>
  ```
  Do NOT reset the whole working tree — prior tasks' committed work stays.
- Retry this task up to **3** attempts (different approach each time).
- After 3 failed attempts: increment `tasks_failed`, write a one-line note
  into `$spec_dir/tasks.md` under the task (`> failed: <reason>`), and
  continue to the next task. Do not abort the whole phase on one task
  failing — finish what you can, leave the rest for `o-review`.

When a task passes: mark it `- [x]` in `$spec_dir/tasks.md`, increment
`tasks_done`.

### 5. Hard-block checks

`exit_code: 2` (no commit) only if:

- A task has no verifiable outcome at all — you cannot state any check that
  would distinguish done from not-done (`block_reason: task_unverifiable: <task>`).
- A task's target file does not exist and cannot be created
  (`block_reason: task_target_unresolvable: <task>`).

No test harness is NOT a block — use lightweight bash assertions. A task
simply being hard is NOT a block — it's `tasks_failed`, `exit_code: 1`.

### 6. Commit + push

```bash
git add -A
git -c user.name=mozi_agent -c user.email=mozi_agent@local \
  commit -m "o-build: implement <tasks_done>/<tasks_total> tasks [$(basename "$spec_dir")]

failed: <tasks_failed>"
git push origin <branch>
```

- Committer is literal `mozi_agent`.
- Push failure → `exit_code: 2`, `block_reason: push_failed: <one-liner>`,
  stop.
- `exit_code`: `0` if `tasks_failed == 0`; `1` if some tasks failed (work is
  committed, `o-review` will audit). Never `0` with failed tasks.

## Output

Emit the JSON object matching `output:`. `commit_hash` = the pushed SHA, or
empty if you blocked before committing.
