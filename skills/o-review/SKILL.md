---
name: o-review
description: |
  Review phase. Clones the mission branch (which now carries o-spec's openspec/
  and o-build's code commits), audits code against the OpenSpec trio, runs
  tests, auto-fixes minor issues, writes the spec dir's REVIEW.md, then commits and
  pushes. Use as the terminal node of the o-pipeline mission.
kind: llm_skill
input:
  gitlab_url:
    type: str
    required: true
    description: "GitLab clone URL (.git). Re-cloned fresh — o-review does not inherit o-build's filesystem."
  branch:
    type: str
    required: true
    description: "Mission-input branch. Carries o-spec's openspec/ and o-build's code commit."
output:
  exit_code:
    type: int
    required: true
    description: "0 success / 1 failure / 2 blocked"
  status:
    type: str
    required: true
    description: "success | failure | blocked"
  block_reason:
    type: str
    required: false
    description: "Present only when exit_code=2 (e.g. spec_artifacts_missing, push_failed)"
  verdict:
    type: str
    required: true
    description: "pass | needs-rework | fail. needs-rework can drive a feedback edge back to o-build."
  issues_found:
    type: list
    required: true
    description: "All issues found. Each: {severity, file, line, message}. Empty list if none."
  issues_fixed:
    type: list
    required: true
    description: "Issues o-review auto-fixed. Same shape as issues_found. Empty list if none."
  issues_remaining:
    type: list
    required: true
    description: "Issues left for a build re-pass. Same shape. Empty list if none."
  commit_hash:
    type: str
    required: true
    description: "SHA of o-review's phase commit (fixes + REVIEW.md). Empty if blocked before commit."
  pushed:
    type: bool
    required: true
    description: "true if the push succeeded, false if it failed (exit_code=2, pushed_branch empty)"
  pushed_branch:
    type: str
    required: true
    description: "The branch pushed to on success; empty string on push failure."
tools:
  - bash
  - read_file
category: backend
domain: review
---

# o-review: Autonomous Audit + Auto-fix

> Terminal phase. **Never ask the user anything.** State arrives via the remote
> branch (relay, ADR-0001): clone fresh, audit, fix, commit, push. A
> `needs-rework` verdict is the signal a mission-wired feedback edge can route
> back to `o-build`.

## Run

### 1. Clone + checkout

```bash
git clone <gitlab_url> /tmp/o-review/repo
cd /tmp/o-review/repo
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

- No subfolder → `exit_code: 2`, `block_reason: spec_artifacts_missing`,
  stop.
- Confirm `$spec_dir/proposal.md`, `$spec_dir/design.md`,
  `$spec_dir/tasks.md` exist.
- Spec missing → `exit_code: 2`, `block_reason: spec_artifacts_missing`,
  stop.
- Gauge whether o-build actually ran for THIS requirement by reading
  `$spec_dir/tasks.md`: o-build marks each done task `- [x]` and writes a
  `> failed:` note per exhausted task. No `- [x]` AND no `> failed:` notes
  → o-build produced nothing → `verdict: fail`, `exit_code: 1` (not
  blocked — you can review an empty build; you just fail it). Still write
  REVIEW.md and commit it. Do NOT use "code beyond `$spec_dir/`" — on a
  multi-requirement branch, prior requirements' committed source also sits
  beyond this spec dir and would mask an empty build.

### 3. Audit

Three axes, record each issue in `issues_found[]`
(`{severity: high|med|low, file, line, message}`):

- **Spec conformance** — does the code implement what
  `$spec_dir/proposal.md` + `$spec_dir/tasks.md` describe? Each unchecked
  task in `$spec_dir/tasks.md` is a `med` issue.
- **Quality** — obvious bugs, error-handling gaps, injection/XSS/SQLi, dead
  code.
- **Tests** — run the suite if one exists. No harness (static HTML/config)
  → re-run o-build's lightweight bash assertions or a structural check.
  Failing tests/assertions are `high` issues. Missing verification for
  implemented behavior is `med`.
- **Visual conformance (only if `$spec_dir/figma/` exists)** — `read_file`
  each figma render (`<n>.png`) and compare the implemented UI against it:
  layout, text content, spacing, colour. o-review has no Figma token and
  never calls the API — it only consumes renders o-spec already fetched.
  Material divergence (missing element, wrong text, broken layout vs the
  design) is a `med`/`high` issue (`high` if a whole section is missing or
  the page structure doesn't match). Cosmetic-only drift → `low`.

```bash
# run whatever test command the repo uses; if none, re-run build's assertions
```

### 4. Auto-fix minor issues

Fix `low` and `med` issues that are safe and local (typos, missing null
check, a failing test fix, dead code removal). Do NOT attempt `high` or
architectural issues — those go to `issues_remaining[]` for a `o-build`
re-pass.

After fixing, re-run the suite to confirm you did not break anything.

Move each fixed issue from `issues_found` (conceptually) into
`issues_fixed[]`. Unfixed stay in `issues_remaining[]`.

### 5. Verdict

- `pass` — no `high` issues remain, suite green, tasks all checked.
- `needs-rework` — `issues_remaining[]` is non-empty and worth another
  `o-build` pass (this is the value a mission-writer wires a feedback edge
  on).
- `fail` — fundamental: spec unmet, suite red with `high` issues, or o-build
  produced nothing. Terminal.

### 6. Write REVIEW.md + commit + push

Write `$spec_dir/REVIEW.md`:

```md
# Review

verdict: <verdict>
tasks_done: <from tasks.md x count> / <total>
tests: <pass|fail|n/a>

## issues_found
- [high|med|low] path/file.ts:line — message
...

## issues_fixed
- ...

## issues_remaining
- ...
```

```bash
git add -A
git -c user.name=mozi_agent -c user.email=mozi_agent@local \
  commit -m "o-review: verdict=<verdict> [$(basename "$spec_dir")], fixed=<len issues_fixed>, remaining=<len issues_remaining>"
git push origin <branch>
```

- Committer is literal `mozi_agent`.
- Push failure → `exit_code: 2`, `block_reason: push_failed`, `pushed: false`,
  `pushed_branch: ""`. (Code is committed locally; the block surfaces it
  for a human, since no further phase depends on this push within the
  mission — but the result has not reached the remote.)
- Push success → `pushed: true`, `pushed_branch: <branch>`,
  `commit_hash: <sha>`.

### 7. exit_code mapping

- `verdict: pass` → `exit_code: 0`, `status: success`.
- `verdict: needs-rework` → `exit_code: 1`, `status: failure` (work is not
  done; a feedback edge may route back to `o-build`).
- `verdict: fail` → `exit_code: 1`, `status: failure`.
- Blocked (artifacts missing / push failed) → `exit_code: 2`, `status: blocked`.

## Output

Emit the JSON object matching `output:`. `commit_hash` empty only when
blocked before committing.
