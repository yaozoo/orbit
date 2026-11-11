---
name: o-done
description: Terminal pass-through marker for the o-pipeline. Dispatched only when the reviewer's verdict is "pass" (the review→done edge carries that condition), so the mission's success node reflects the actual review outcome instead of mere node arrival. Deterministic python backend — no LLM, no side effects.
kind: python
output:
  ok:
    type: bool
    required: true
  note:
    type: str
    required: true
---

# o-done: terminal marker

There is no logic here by design. The mission gates this node on
`ctx.review.verdict == "pass"` and declares `success: done` — so the run's
"目标达成" badge reflects the reviewer's actual verdict: a run that ends on
needs-rework (or settles after the rework loop's budget is exhausted) never
dispatches this node and shows 目标未达成.
