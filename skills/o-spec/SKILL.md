---
name: o-spec
description: |
  Requirements analysis phase. Clones a GitLab repo, checks out the mission
  branch, reads the requirement doc(s) under DocSpec/, judges what kind of
  input it is and synthesizes the OpenSpec trio (proposal.md, design.md,
  tasks.md), then commits and pushes to the branch. No in-skill confirmation.
  Use as the first node of the o-pipeline mission.
kind: llm_skill
input:
  gitlab_url:
    type: str
    required: true
    description: "GitLab clone URL (must end in .git). The repo to operate on."
  branch:
    type: str
    required: true
    description: "Mission-input branch. Must already exist on remote (user created it, put DocSpec/ docs on it, and pushed). Checked out, not created."
  doc_url:
    type: str
    required: true
    description: "Path to the requirement doc(s) inside the repo. Relative path to a file, a folder (globs **/*.md and **/*.txt), or a full GitLab UI URL."
  figma_token:
    type: str
    required: false
    description: "Figma personal access token. Optional — only used if the docs contain Figma links. Empty token + Figma links present → hard block."
output:
  exit_code:
    type: int
    required: true
    description: "0 success / 1 failure / 2 blocked (route to human)"
  status:
    type: str
    required: true
    description: "success | failure | blocked (mirrors exit_code)"
  block_reason:
    type: str
    required: false
    description: "Present only when exit_code=2 (e.g. doc_url_not_found, branch_not_on_remote, push_failed, figma_link_without_token, figma_token_invalid, figma_fetch_failed)"
  doc_type:
    type: str
    required: true
    description: "vague-requirement | detailed-change | task-list — how o-spec classified the input"
  confidence:
    type: float
    required: true
    description: "Soft-ambiguity signal 0..1. Never blocks; mission may gate an edge on it."
  assumptions:
    type: list
    required: true
    description: "Assumptions o-spec made when guessing. Empty list if none."
  commit_hash:
    type: str
    required: true
    description: "SHA of o-spec's phase commit (40 hex). Empty string only if blocked before commit."
tools:
  - bash
  - read_file
category: backend
domain: spec
---

# o-spec: Autonomous Spec Synthesis

> First phase of the o-pipeline. **Never ask the user anything.** Decide or
> block (`exit_code: 2`) — there is no third option. State reaches the next
> phase via the remote branch (relay), not via this node's filesystem.

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

- `git checkout <branch>` fails if the branch is not on remote (clone already
  fetched all remote branches, so a present branch checks out cleanly). If it
  fails → `exit_code: 2`, `block_reason: branch_not_on_remote: <branch> not on origin`,
  emit output, stop. Do not create the branch — the user's flow guarantees it
  exists; if it doesn't, a human must intervene.

### 2. Resolve doc_url

- Relative path (`apps/login/README.md` or `apps/login/`) → resolve against the
  repo root.
- Folder → glob `**/*.md` and `**/*.txt` (recursive), collect all matches.
- Full GitLab UI URL (`https://gitlab.../-/tree/<branch>/path`) → strip to the
  repo-relative path, resolve.
- If nothing resolves to at least one readable file → `exit_code: 2`,
  `block_reason: doc_url_not_found: <doc_url> resolved to 0 files`, stop.

### 3. Read + classify + ground

Read every resolved doc. Then ground in the codebase: walk the repo tree,
and for **each distinct requirement** in the doc, locate the concrete
file(s)/module(s) it will touch. Record this req→file map — it goes into
`design.md` in Step 4. A requirement you cannot locate anywhere in the
codebase is an assumption (if you can infer the target) or a hard block
(Step 6, `block_reason: requirement_unlocatable: <requirement>`). Do not
write a proposal against code you have not looked at.

Classify the input:

- **task-list** — the doc is already a breakdown of tasks.
- **detailed-change** — the doc describes a specific change with enough
  detail to implement directly.
- **vague-requirement** — the doc is high-level / one-line / aspirational;
  implementation must be inferred from the codebase.

Record `doc_type` and, if you made interpretive leaps, `assumptions[]` and a
`confidence` below 1.0. Pure passthrough of an unambiguous task-list =
`confidence: 1.0`, empty `assumptions`.

If the doc cites another repository as a reference (repo URL + branch +
path, e.g. "参考 https://gitlab.../xxx.git main 分支上 apps/.../upload 模块"),
that is also code you must look at before drafting — see Step 3.6.

Derive a short slug from the requirement (ASCII lowercase, kebab-case, a
few words). Non-English requirements must be translated to English
keywords (e.g. 用户信息按钮 → `user-info-button`) so the slug stays ASCII
— non-ASCII would make same-second `sort` locale-dependent and is
fragile in git/shell paths. Establish the spec dir:

```bash
spec_dir="openspec/$(date -u +%Y%m%d-%H%M%S)-<slug>"
mkdir -p "$spec_dir"
```

The timestamp prefix is fixed-width and zero-padded, so lexical sort =
chronological. Use `-u` (UTC) so the sort is stable across runners in
different timezones — a local-time stamp can make a later requirement's
dir sort before an earlier one. o-build/o-review locate this dir with
`ls -d openspec/[0-9]*/ | sort | tail -1` — they key off the timestamp
prefix, not the slug; the `[0-9]*` filter ignores any non-spec dirs under
`openspec/` (e.g. a stray `archive/`). The slug is for human browsing of
the branch only.

### 3.5 Figma fetch (only if docs reference Figma)

Scan the resolved docs for Figma URLs (match
`figma.com/file/<key>/...` or `figma.com/design/<key>/...`, capturing the
`file_key` and any `node-id=<node_id>` query param).

- **No Figma URLs found** → skip this step entirely. Do not touch the token.
- **Figma URLs found, `figma_token` is empty/missing** → `exit_code: 2`,
  `block_reason: figma_link_without_token: <one url>`, stop. Do not proceed
  to synthesize a spec that silently drops the visual requirements.
- **Figma URLs found, token present** → validate before fetching. Pick the
  first URL's `file_key`, call:
  ```bash
  curl -sSL -o /dev/null -w '%{http_code}' \
    -H "X-Figma-Token: <figma_token>" \
    "https://api.figma.com/v1/files/<file_key>"
  ```
  - HTTP 401 / 403 → token is wrong/revoked → `exit_code: 2`,
    `block_reason: figma_token_invalid: API returned <code>`, stop.
  - HTTP 200 → token is good; proceed.
  - HTTP 404 / 400 → the file_key itself is bad → `exit_code: 2`,
    `block_reason: figma_fetch_failed: <url> returned <code>`, stop.

  Then for every Figma URL, make two API calls (both authenticated with
  `X-Figma-Token`, both against `api.figma.com`):
  ```bash
  mkdir -p "$spec_dir/figma"
  # 1) node tree — text, layout, fills, component refs (the real "read")
  curl -sSL -H "X-Figma-Token: <figma_token>" \
    "https://api.figma.com/v1/files/<file_key>/nodes?ids=<node_id>" \
    -o "$spec_dir/figma/<n>.json"
  # 2) rendered PNG — images endpoint returns {"images":{"<id>":"<url>"}}
  curl -sSL -H "X-Figma-Token: <figma_token>" \
    "https://api.figma.com/v1/images/<file_key>?ids=<node_id>&format=png&scale=2" \
    -o "$node_dir/figma-<n>.json"
  img_url=$(grep -oE 'https://[^"]+' "$node_dir/figma-<n>.json" | head -1)
  curl -sSL "$img_url" -o "$spec_dir/figma/<n>.png"
  ```
  Save the node JSON to `$spec_dir/figma/<n>.json` and the PNG to
  `$spec_dir/figma/<n>.png`. Reference each render
  in `design.md` beside the requirement it illustrates; quote any text
  content from the node JSON into the proposal so o-build can match it.

`figma_token` is used only in this step. o-build and o-review never receive
it; they see the committed renders via the branch (relay, ADR-0001).

### 3.6 Reference repos (only if the doc cites one)

The doc may cite another repo as evidence — e.g. "参考
https://gitlab.example/saas/frontend/dealer-transformer-pc.git 项目中 main
分支上 apps/application/src/views/personal-new-car 中上传模块文件参数使用
规则", or "参见 xxx.git", or "沿用 dealer-transformer-pc 的上传逻辑". Every
such citation is an external evidence source: a reference you did not open is
an assumption, not evidence.

**Recognize and classify the citation:**

- **A — a full URL** (`https://.../<repo>.git` or a GitLab UI URL), with or
  without branch/path.
- **B — a repo name only** ("参考 dealer-transformer-pc 项目的…"), no URL.
- Vaguer phrasing ("参考业界常见做法") is not a citation — treat it as
  ordinary requirement text.

**A → clone and read.** Shallow-clone into this node's working directory —
never `/tmp` (the same concurrency rules as the main clone), never inside
the repo:

```bash
mkdir -p "$node_dir/refs"
git clone --depth 1 -b <branch> <repo_url> "$node_dir/refs/<name>"
```

- Branch given → clone that branch; branch missing → the default branch.
- Path given → read it, plus whatever it imports that the cited rules
  depend on. Path missing → locate the most relevant implementation by
  searching the clone for the requirement's domain keywords; if nothing
  convincing turns up, fall through to B's handling.
- **Record provenance** wherever you cite it: repo URL + branch + the
  cloned commit SHA + UTC read time (e.g.
  `dealer-transformer-pc@<sha> (main, read 2026-11-11T04:22Z):
  apps/.../personal-new-car/upload.vue`). The branch drifts between runs;
  the SHA + timestamp pin what you actually read this time.
- **Distill, don't point.** The rules go into `design.md` written out with
  the exact parameter and field names quoted — "遵循该模块的上传规则" is a
  pointer, not a rule. The trio must be self-contained: `o-build` and
  `o-review` never see the reference clone (relay, ADR-0001), so a rule
  that only exists there is a rule they don't have.

**B → cannot clone, don't guess.** Never construct or guess a URL — a
fabricated URL is worse than an unread reference. Record it in
`assumptions[]` ("reference unreadable: <name>, doc gives no URL"), lower
`confidence`, settle the requirement on the main repo and doc alone, and
leave a one-line assumption note in `proposal.md` (e.g. "参照
dealer-transformer-pc 上传规则：文档未给 URL，未读取，按本仓现状实现"). That
visible note is what lets `o-spec-clarify` raise it as a decision item — the
human can supply the URL as a custom answer.

**Clone failure (A: no credentials, repo or branch gone) → same as B**:
`assumptions[]` + lower `confidence`, not a block. A reference is supporting
evidence, not a precondition — an unreachable reference must not kill the
run.

**When the target repo and the reference disagree**, split by kind:

- Cross-project **contracts** — parameter names, field semantics,
  request/response shapes, enum values — the **reference wins**: matching it
  is why the human cited it.
- Project-local **structure** — directory layout, component choices, naming
  conventions, existing patterns — the **target repo wins**: the reference's
  structure does not transplant.
- On any conflict, record in `assumptions[]` which side won and why.

**Never commit, never push** anything from `$node_dir/refs/` — it is
read-only evidence for this phase. Step 7's `git add openspec/` already
guarantees it cannot leak into the phase commit.

### 4. Synthesize the OpenSpec trio

Write three files under `$spec_dir/` (the dir was created in Step 3):

- `$spec_dir/proposal.md` — what & why. One paragraph of context, then the
  proposed change. For a vague-requirement, derive this from the codebase +
  the doc. For a detailed-change, adopt the doc's intent. For a task-list,
  write a minimal proposal that frames the tasks.
- `$spec_dir/design.md` — how. Approach, trade-offs, and the req→file map
  from Step 3 (each requirement → the file(s)/module(s) it touches). Skip
  the map for a task-list that already carries design.
- `$spec_dir/tasks.md` — executable task list. Markdown checklist; each task
  is one `- [ ]` line naming the file + intent. For a task-list input,
  light-validate and adopt. Derive from proposal/design for the other two
  types.
  **A UI task must name the design frame it implements.** If the task
  produces or changes markup, styling, layout, or a component's form, cite
  the frame(s) in the task line itself — `figma/<node-id>.png` — so
  `o-build` has a hard anchor instead of guessing which frame belongs to
  which task:

  ```md
  - [ ] app/components/pages/application/upload/PasswordDialog.vue — 密码弹窗；
        对齐 figma/907-752.png（底部 Sheet，非居中弹窗）
  - [ ] app/pages/application/index.vue — 自主进件流程页；参考 figma/905-237.png
        （登录）、figma/907-612.png（槽位）
  ```

  Cite **every** frame the task covers — a screen is often several frames
  (one per state: default / loading / error / success), and each is a
  separate frame file. When the requirement covers a whole screen, list
  that screen's frames; when it covers one component, list that
  component's frame. A UI task with no frame reference is an unfinished
  task: `o-build` cannot implement what it cannot see, and will silently
  substitute its own idea of the layout.

  Non-UI tasks (API layer, stores, middleware, config, scripts) carry no
  frame reference — a frame reference on them is noise.

Do NOT mutate anything outside `openspec/`. This phase writes docs only.

### 5. Coverage self-check

Re-read the original doc(s). For every distinct requirement (every bullet,
every constraint, every "should"), confirm it has a 落点 in the trio — a
matching line in `proposal.md` or a task in `tasks.md`, plus an entry in
the `design.md` req→file map. This is the guard against drift: the LLM
that drafted the spec can miss a requirement; this explicit re-read
catches whole-bullet gaps.

- A requirement with no 落点 → fill it (add a task / proposal line / map
  entry), then re-run this check.
- A requirement that cannot be given a 落点 because it is genuinely
  ambiguous or out of scope → `exit_code: 2`,
  `block_reason: requirement_uncovered: <requirement>`, stop. Do not let
  an unaddressed requirement silently flow to `o-build`.

**Frame-reference check (only when `$spec_dir/figma/` exists).** Every task
in `tasks.md` that touches UI must cite at least one `figma/<node-id>.png`,
and every cited frame file must actually exist in `$spec_dir/figma/`. A task
citing a frame that does not exist is a broken anchor — fix it to a real
frame or drop the citation and record the gap in `assumptions[]`; do not
invent a node-id. This check exists because an uncited UI task becomes an
unimplemented UI task: `o-build` cannot open a frame it was never told
about.

Only proceed to commit when every requirement has a 落点.

### 6. Hard-block checks

Before committing, if any of these hold, `exit_code: 2` with a `block_reason`
and stop (no commit, no push):

- The doc is unreadable / not actually a requirement (e.g. binary, empty).
- The target area cannot be located in the codebase at all.

Soft ambiguity (which interpretation?) is NOT a hard block — pick the best
read, record it in `assumptions`, lower `confidence`. Only route to a human
when you genuinely cannot proceed.

### 7. Commit + push

```bash
git add openspec/
git -c user.name=mozi_agent -c user.email=mozi_agent@local \
  commit -m "o-spec: synthesize <slug> openspec trio

doc_type: <doc_type>
confidence: <confidence>"
git push origin <branch>
```

- Committer identity is the literal `mozi_agent` — do not read `git config`.
- If `git push` fails → `exit_code: 2`,
  `block_reason: push_failed: <stderr one-liner>`, stop. (The next phase
  cannot proceed without this push — see ADR-0001.)
- On success, `commit_hash` = the SHA you just pushed.

## Output

Emit the JSON object matching the `output:` contract above. `status` mirrors
`exit_code` (`0→success`, `1→failure`, `2→blocked`). `commit_hash` is empty
only when you blocked before reaching the commit step.
