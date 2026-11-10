# o-pipeline Glossary

The vocabulary of the o-pipeline: how a requirement becomes reviewed code, and
what each phase owes the next. Terms are defined once here; other documents
link back rather than redefine.

## Pipeline phases

**DocSpec**:
The folder (on the mission-input branch) where the user places the requirement
doc(s) for one run. May be a single `.md`/`.txt` file or a folder of them.
_Avoid_: spec, input doc, requirement folder.

**Relay**:
The state-transfer mechanism between nodes. Each node clones the remote
mission-input branch fresh, does its work, commits, and pushes back. The next
node's clone inherits the prior node's commit. There is no shared filesystem
across nodes in a run.
_Avoid_: shared workspace, workspace handoff, state file.

**OpenSpec trio**:
The three artifact files `o-spec` writes under a per-requirement spec dir
`openspec/<UTC-timestamp>-<slug>/`: `proposal.md` (what & why), `design.md`
(how), `tasks.md` (executable task list with done-checks). Each requirement
gets its own spec dir so multiple can accumulate on one branch; o-build/
o-review locate the newest by lexical sort of the timestamp prefix.
Dropped from upstream OpenSpec: spec deltas, the archive workflow, and the
ledger.
_Avoid_: change package, openspec change.

**working clone**:
A node's own fresh clone of the mission-input branch, created at the start of
that node's execution and discarded after. Lives in that node's temp space
only; never referenced by other nodes.
_Avoid_: workspace, worktree (implies persistence/shared).

**phase commit**:
The single commit each phase makes to the mission-input branch at the end of
its work. `o-spec` commits the OpenSpec trio; `o-build` commits code + tests +
updated `tasks.md`; `o-review` commits fixes + the spec dir's `REVIEW.md`. Every
phase commit is followed by a push; a failed push is a hard `exit_code: 2`.
_Avoid_: phase checkpoint.

## Node contracts

**exit_code**:
A plugin output field. `0` = success (downstream may proceed). `1` = failure
(the phase did its best and cannot continue; leave state for review).
`2` = blocked (a precondition is unmet — missing doc, no branch on remote,
push failed, upstream artifacts absent). `2` is the only value that means
"route to a human / retry-elsewhere".
_Avoid_: return code, rc.

**block_reason**:
A string emitted alongside `exit_code: 2`, naming why the phase blocked
(e.g. `doc_url_not_found`, `branch_not_on_remote`, `push_failed`,
`spec_artifacts_missing`). Machine-prefixed, human-suffixed.
_Avoid_: error message, failure reason.

**verdict**:
`o-review`'s terminal judgement: `pass` | `needs-rework` | `fail`.
`needs-rework` is the signal a mission-writer can wire a feedback edge back to
`o-build` on. `fail` is terminal.
_Avoid_: review result, approval.

**confidence**:
`o-spec`'s soft-ambiguity signal, a float in `[0,1]`, plus `assumptions[]`.
Never blocks on its own; a mission-writer may gate a conditional edge or
human-approval node on it.
_Avoid_: certainty, score.

## Interactive clarification

**decision item**:
One question the clarification phase could not settle from evidence and must
ask a human. Carries options, a recommended option, and the evidence gap that
made it unanswerable. Written to `decisions.md`; rendered into the approval
panel so the human can answer without opening files.
_Avoid_: question, todo, issue, blocker (a blocker is a hard `exit_code: 2`).

**option**:
One candidate answer to a decision item, with a key, a label, and its impact.
Options are closed sets — the human picks a key, writes a custom answer, or
defers.
_Avoid_: choice, candidate, alternative.

**recommended option**:
The option the clarification phase believes is correct, marked so the human
can accept it by doing nothing. Chosen automatically when the human does not
answer that item.
_Avoid_: default, fallback, guess.

**deferred decision**:
A decision item the human explicitly postpones. It never blocks downstream
work and never re-triggers a clarification round; it is recorded as open in
`decisions.md`.
_Avoid_: skipped, postponed, todo.

**clarification round**:
One pass of the clarification phase: draft the trio, produce decision items,
wait for the human, fold the answers back. The pipeline allows at most two
rounds; the second is the last.
_Avoid_: iteration, loop, cycle.

**auto-settled ambiguity**:
An ambiguity the clarification phase resolved itself from evidence (codebase,
docs, conventions). Recorded in `assumptions[]` and lowering `confidence`, not
raised as a decision item.
_Avoid_: assumption (the assumption is the recorded text; this is the act),
silent decision.

**human gate**:
The platform's approval primitive. A node declaring `human_approval: true`
has its output withheld until a human approves, rejects, or amends. Amend
injects the human's feedback into the node's context and re-runs the node.
Gate rounds are counted separately from the node's failure retries.
_Avoid_: approval (the approval is the decision; the gate is the mechanism),
interrupt, checkpoint.
