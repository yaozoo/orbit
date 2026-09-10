# Relay state between nodes via the remote branch, not a shared workspace

Each phase clones the mission-input branch fresh, works, commits, and pushes
before exiting. The next phase's clone inherits the prior phase's commit.
There is no shared filesystem path handed from node to node; inter-node
output JSON carries only small contracts (exit_code, status, commit_hash,
counts, verdict), never file paths or file contents.

## Why

The prior `y-spec`/`y-build`/`y-verify` design repeatedly failed with
"spec committed but build found nothing": `y-spec` committed in its own
process-local clone and never pushed, `y-build` was given `inputs: {}` (no
repo URL to re-clone), and mozi does not share a filesystem across nodes in
a run (each node is a separate CC session with its own temp space). State
was lost at the node boundary every time.

## Consequences

- Every node takes `gitlab_url` + `branch` as inputs and clones for itself.
  Only `o-spec` also takes `doc_url`.
- Every phase must push after its commit. A failed push is a hard
  `exit_code: 2` (`block_reason: push_failed`) — not a soft defer — because
  the next phase's clone depends on it.
- Artifact locations are repo-relative conventions (`openspec/<spec_dir>/`,
  located by timestamp-prefix sort, not absolute paths), so any node finds
  them in its own clone.
- Nodes re-clone per phase (3 clones per run). Accepted cost: seconds to
  minutes, and the only model that does not depend on an unconfirmed
  shared-filesystem guarantee from the platform.
