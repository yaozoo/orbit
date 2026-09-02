# Skill alignment: o-spec / o-build / o-review vs OpenSpec & superpowers

How the three self-contained phases map onto the skills in
[Fission-AI/OpenSpec](https://github.com/Fission-AI/OpenSpec) (the `openspec-*`
set) and [obra/superpowers](https://github.com/obra/superpowers) (the
`superpowers-*` set). This is a concept reference for the current
self-contained design — these sub-skills are **not invoked at runtime**; the
three SKILL.md bodies inline the relevant methodology instead.

## Per-phase alignment

### o-spec — requirements analysis → OpenSpec trio

| o-spec step | aligned skill | fit |
|---|---|---|
| read doc, classify, surface assumptions/confidence | `superpowers:brainstorming` | tight |
| ground in codebase, map each requirement to files | `openspec:explore`, `openspec:context-loading` | medium (we stress 落点) |
| write proposal.md + design.md + tasks.md | `openspec:propose` / `openspec:new-change` / `openspec:proposal-creation` | tight (same output shape) |
| coverage self-check (re-read doc, verify each req has a 落点) | — none | our own hard constraint |

### o-build — implementation → per-task verify + implement + rollback

| o-build step | aligned skill | fit |
|---|---|---|
| iterate tasks.md task by task | `superpowers:executing-plans` | tight |
| real TDD where a harness exists | `superpowers:tdd` | tight (harness-only) |
| fail → rollback → retry differently | `superpowers:debugging` | medium (we add git rollback) |
| per-task verification | `superpowers:verification` | tight |
| bash assertions when no harness | — none | our own fallback |
| apply spec delta to code | `openspec:apply-change` / `openspec:implementation` | tight (OpenSpec impl step) |
| resume interrupted run | `openspec:continue-change` | medium |

### o-review — audit → auto-fix → verdict

| o-review step | aligned skill | fit |
|---|---|---|
| code↔spec conformance audit | `openspec:verify-change` | tight (OpenSpec verify step) |
| code quality audit | `superpowers:code-review` | tight |
| run tests/assertions | `superpowers:verification` | tight |
| auto-fix minor issues | — none (code-review reports only) | our own extension |
| archive change (**currently omitted**) | `openspec:archive-change` / `openspec:archiving` | gap — to truly adopt OpenSpec, add at o-review end |

## Workflow correspondence

Both ecosystems' lifecycles are isomorphic and land on the same three phases:

```
superpowers:  brainstorming → writing-plans → executing-plans(+tdd/debug) → code-review(+verification)
openspec:     propose/new   → apply/impl    → verify                         → archive
ours:         o-spec        → o-build       → o-review
```

## Four misalignments (our own additions / gaps)

1. **o-spec coverage self-check** — neither ecosystem re-reads the source doc
   to verify every requirement landed. We added this to curb spec drift.
2. **o-build no-harness bash assertions** — `superpowers:tdd` assumes a test
   harness; static/config deliverables have no equivalent skill, so we
   degrade to bash assertions.
3. **o-review auto-fix** — `superpowers:code-review` is read-only; our
   auto-fix is closer to re-running a build pass.
4. **o-review omits archive** — OpenSpec's terminal step is
   `openspec:archive-change`. If we ever truly integrate OpenSpec, add it
   just before o-review's commit+push.

## If we ever move from "reference" to "real integration"

Highest-value real hooks (each optional, each with graceful degradation —
`command -v openspec && … || <inline fallback>`, never the old
Skill-Resolution-Order probing):

- `o-review` spec-conformance check → run `openspec verify-change` for a
  machine-enforced contract instead of LLM-judged conformance.
- `o-review` terminal step → `openspec archive-change` to close the change.
- `o-spec` synthesis → `openspec propose`/`new-change` to get real spec
  deltas (`specs/`) rather than hand-written proposal.md only.

The rest (brainstorming, executing-plans, tdd, code-review, verification)
stay inlined — invoking those superpowers sub-skills adds a resolution
dependency without much gain for a per-feature autonomous run.
