# o-pipeline

Three independent mozi plugins — `o-spec`, `o-build`, `o-review` — that chain
into a mission to take a GitLab branch + a requirement doc and produce
implemented, reviewed code. No in-skill human confirmation; failure routes to
a human via `exit_code: 2`.

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

## The three phases

| phase | reads | writes | commits |
|---|---|---|---|
| `o-spec` | `DocSpec/` doc(s) | `openspec/{proposal,design,tasks}.md` | the trio |
| `o-build` | `openspec/` | `src/`, `tests/`, updated `tasks.md` | code + tests |
| `o-review` | `openspec/` + code | `openspec/REVIEW.md` (+ fixes) | fixes + REVIEW.md |

Each phase's `exit_code`: `0` success / `1` failure (leave for review) /
`2` blocked (route to human). Every phase pushes; a failed push is a hard
`exit_code: 2`.

## Wire it on mozi

Publish the three plugins (Plugins → + publish → zip each `skills/o-*` dir),
then register this mission: [`examples/feature-pipeline.yaml`](examples/feature-pipeline.yaml).

The mission inputs (`gitlab_url`, `branch`, `doc_url`) are filled on Start
Run. `branch` must already exist on remote with the requirement doc under
`DocSpec/` — the user creates it, pushes, then configures the three fields on
the platform.

## Files

```
skills/o-spec/SKILL.md      # requirements analysis → OpenSpec trio
skills/o-build/SKILL.md     # inline verification + implementation, per-task rollback
skills/o-review/SKILL.md    # audit + auto-fix → REVIEW.md verdict
examples/feature-pipeline.yaml   # the mission接入
docs/adr/0001-relay-state-via-remote-branch.md
CONTEXT.md                  # glossary
```

## Note on `tools`

Each SKILL declares `tools: [bash, read_file]` — the two names confirmed
valid in the mozi docs. File writes/edits in the bodies use `bash` (heredocs,
`git checkout` for rollback) so publish won't 422 on an unrecognized tool
name. If your mozi build accepts `write_file`/`edit`, add them and the agent
will use them in preference to heredocs.
