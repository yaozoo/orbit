# ADR-0002: Interactive clarification via a human gate, not open questions

## Context

`o-spec` was written as a fully autonomous phase: "**Never ask the user
anything.** Decide or block (`exit_code: 2`) — there is no third option."
That contract is correct for `o-build` and `o-review`, which are downstream of
a settled spec. But it is wrong for the spec phase itself, where the input is
a human-authored requirement document that is routinely under-specified.

The current failure mode is not that `o-spec` crashes. It is that `o-spec`
silently resolves ambiguities — recording them in `assumptions[]` and lowering
`confidence` — and then `o-build` implements against a spec nobody agreed to.
The assumption is never surfaced to a human, so the first signal of a bad
assumption is a failed review at the end of the whole pipeline.

The platform already has the primitive needed to fix this: a node with
`human_approval: true` has its output withheld until a human approves,
rejects, or amends; amend injects the human's feedback into the node's
context and re-runs it. Gate rounds are counted separately from the node's
failure retries, and `max_approval_timeouts` bounds how long the platform
waits for a human.

## Decision

Split the spec phase into a drafting node and a clarification node, and put a
human gate between them. The drafting node produces the OpenSpec trio plus a
list of **decision items** — closed multiple-choice questions, each with
options, a recommended option, and the evidence gap that made it
unanswerable. The clarification node runs the mechanical part of the gate
(numbering, answer parsing, defaulting to the recommended option, rendering
the sheet) and its output is what the human actually sees in the approval
panel.

The human answers by amending: `D1=A, D2=自定:..., D3=待查`. Items the human
does not mention fall back to their recommended option. Deferred items are
recorded as open and never re-trigger a round.

The pipeline allows **at most two clarification rounds**. The bound is
enforced by the mission's `approval_timeout` × `max_approval_timeouts`
settings (the platform's own streak counter), not by a self-imposed check
inside the plugin.

`o-spec`, `o-build`, and `o-review` keep their existing autonomous contracts.
Only the spec phase gains an interaction point.

## Why not the alternatives

**Keep `o-spec` autonomous, add a human gate to the same node.** Fewer
moving parts, but the node's output is the trio's file paths and counters —
the approval panel would show paths, not content, and the human would have to
open files to review anything. The decision items would have to be squeezed
into a field of the trio node, which mixes "spec content" with "questions
about the spec".

**Let the plugin ask questions in free text and wait.** The platform has no
channel for this: nodes do not stream output, and the engine only parses
SKILL.md frontmatter. A plugin cannot suspend itself mid-execution and wait
for a human. The only human-in-the-loop primitives are the gate (after the
node finishes) and feedback edges (after a reviewer node finishes).

**Let the agent iterate with itself until it converges, then ask once.**
Cheaper in human attention, but the questions that survive self-iteration are
exactly the ones where the agent lacks evidence — asking them as one batch at
the end is what this decision does, so this alternative is a subset, not a
replacement.

## Consequences

- The spec phase gains a node that can be blocked waiting for a human. The
  platform's `max_active_runs` (default 8) is the real limit: eight runs
  waiting for human approval block the whole platform.
- Decision items are a new artifact (`decisions.md` in the spec dir) that
  `o-build` and `o-review` must not treat as requirements. It is a record of
  what was asked and what was chosen, not a source of scope.
- An unanswered item is not a blocker. It silently takes its recommended
  option, so a missing human degrades quality rather than stalling the
  pipeline. `confidence` and `assumptions[]` continue to carry the signal
  that the spec was not fully agreed.
- The `o-spec` plugin body, its exit-code contract, and its relay behaviour
  are unchanged. The interaction lives in a separate plugin so that the
  autonomous contract stays testable in isolation.
