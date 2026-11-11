# o-pipeline

Three independent mozi plugins — `o-spec`, `o-build`, `o-review` — that chain
into a mission to take a GitLab branch + a requirement doc and produce
implemented, reviewed code. No in-skill human confirmation; failure routes to
a human via `exit_code: 2`.

Optionally, a fourth plugin — `o-spec-clarify` — inserts a human decision gate
between `o-spec` and `o-build`: the ambiguities the spec phase could not
settle from evidence become multiple-choice questions with a recommended
option, and the human answers them in the platform's approval panel. See
[ADR-0002](docs/adr/0002-interactive-clarification-via-human-gate.md).

## Why this exists

The prior `y-spec`/`y-build`/`y-verify` design kept failing with *"spec
committed but build found nothing."* Root cause: mozi does not share a
filesystem across nodes in a run, `y-spec` never pushed, and `y-build` was
given `inputs: {}` (no repo URL to re-clone). State died at the node
boundary. See [ADR-0001](docs/adr/0001-relay-state-via-remote-branch.md).

## The fix: relay via the remote branch

Every phase clones the mission-input branch fresh, works, commits, and
**pushes** before exiting. The next phase's clone inherits the prior phase's
commit. Inter-node output JSON carries only small contracts (exit_code,
status, commit_hash, counts, verdict) — never file paths.

## The phases

| phase | reads | writes | commits |
|---|---|---|---|
| `o-spec` | `DocSpec/` doc(s) + optional Figma links + reference repos cited in the doc | `openspec/<spec_dir>/{proposal,design,tasks}.md` (+ `figma/` renders) | the trio (+ renders) |
| `o-spec-clarify` | the trio (+ the human's answers) | answers folded into the trio (decision sheet + round state live in the gate node's run-local `decisions/` dir, never committed) | amended trio |
| `o-build` | `openspec/<spec_dir>/` (+ figma renders; `REVIEW.md` on a re-pass) | `src/`, `tests/`, updated `tasks.md` | code + tests |
| `o-review` | `openspec/<spec_dir>/` + code (+ figma renders) | `openspec/<spec_dir>/REVIEW.md` (+ fixes) | fixes + REVIEW.md |

`<spec_dir>` is `openspec/<UTC-timestamp>-<slug>` — a per-requirement
subfolder o-spec creates so multiple requirements can accumulate on one
branch without overwriting each other. o-build/o-review locate it as the
lexically-newest `openspec/[0-9]*/` dir (timestamp-prefixed).

Each phase's `exit_code`: `0` success / `1` failure (leave for review) /
`2` blocked (route to human). Every phase pushes; a failed push is a hard
`exit_code: 2`.

## Wire it on mozi

Publish the plugins (Plugins → + publish → zip each `skills/o-*` dir), then
register a mission:

- [`examples/feature-pipeline.yaml`](examples/feature-pipeline.yaml) — the
  three-phase, fully autonomous pipeline.
- [`examples/feature-pipeline-interactive.yaml`](examples/feature-pipeline-interactive.yaml) —
  the same pipeline with the `o-spec-clarify` human gate between `o-spec` and
  `o-build`.

The mission inputs (`gitlab_url`, `branch`, `doc_url`, and optional
`figma_token`) are filled on Start Run. `branch` must already exist on
remote with the requirement doc under `DocSpec/` — the user creates it,
pushes, then configures the fields on the platform. `figma_token` is only
read by `o-spec`; leave it blank when the docs have no Figma links — if
they do, a blank or invalid token hard-blocks (`exit_code: 2`).

Requirement docs may also cite other repos as references ("参考
\<repo-url\> \<branch\> \<path\>"). `o-spec` shallow-clones them read-only
into its own working directory, reads the cited code, and distills what
matters into `design.md` (with repo@SHA + read-time provenance) — the trio
stays self-contained and downstream nodes never see the reference repo.
Cross-project contracts win over the target repo's local structure when
the two disagree. A name-only citation or an unreachable reference is
recorded in `assumptions` with lower `confidence` (not a block) and
surfaced as a clarification item — never a guessed URL.

### The interactive variant

`o-spec-clarify` runs with `human_approval: true`, so the run pauses with the
decision sheet in the approval panel. The human answers with **amend** and
feedback like `D1=A, D2=自定:..., D3=暂缓`; items not mentioned fall back to
their recommended option, so approving without answering is a valid (if
unreviewed) outcome. At most **two** clarification rounds — the plugin's
script enforces the budget, because the platform does not bound how often a
human may amend.

Two operational caveats: a waiting run occupies one of the platform's
`max_active_runs` slots (default 8), and the human only sees the node's
output in the approval panel, so the decision sheet is carried in the output
itself rather than as a file path.

## Files

```
skills/o-spec/SKILL.md              # requirements analysis → OpenSpec trio
skills/o-spec-clarify/SKILL.md      # decision items → human gate → answers folded back
skills/o-spec-clarify/scripts/decision_check.py   # numbering / answer parsing / round gate
skills/o-build/SKILL.md             # inline verification + implementation, per-task rollback
skills/o-review/SKILL.md            # audit + auto-fix → REVIEW.md verdict
examples/feature-pipeline.yaml           # the autonomous mission接入
examples/feature-pipeline-interactive.yaml # the mission with the human gate
docs/adr/0001-relay-state-via-remote-branch.md
docs/adr/0002-interactive-clarification-via-human-gate.md
GLOSSARY.md                  # glossary
CONTEXT.md                  # glossary (legacy — see GLOSSARY.md)
```

Run the decision script's self-tests with:

```bash
python3 skills/o-spec-clarify/scripts/test_decision_check.py
```

## Note on `tools`

Each SKILL declares `tools: [bash, read_file]` — the two names confirmed
valid in the mozi docs. File writes/edits in the bodies use `bash` (heredocs,
`git checkout` for rollback) so publish won't 422 on an unrecognized tool
name. If your mozi build accepts `write_file`/`edit`, add them and the agent
will use them in preference to heredocs.
