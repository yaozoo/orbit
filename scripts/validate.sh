#!/bin/sh
set -eu

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

ruby -e 'require "yaml"; YAML.load_file("references/state-schema.yaml")' \
  || fail "references/state-schema.yaml is not valid YAML"

[ -f LICENSE ] || fail "LICENSE file is missing"

if grep -R -n "自动切换到分支\|auto-checkout branch\|没有环境要求\|No environment requirements" README.md README_EN.md >/tmp/orbit-validate-stale.txt; then
  cat /tmp/orbit-validate-stale.txt >&2
  fail "README contains stale dependency or branch wording"
fi

if ! sed -n '/自检门禁表/,/## 变更类型/p' references/stage-transitions.md | grep -q '`brainstorming`'; then
  fail "stage-transitions self-check table is missing brainstorming"
fi

grep -q "openspec_available" references/state-schema.yaml \
  || fail "state schema is missing openspec_available"

grep -q 'schema_version: "1.1.0"' SKILL.md \
  || fail "SKILL.md must write schema_version 1.1.0"

grep -q 'default: "1.1.0"' references/state-schema.yaml \
  || fail "state schema default version must be 1.1.0"

if grep -q "Detect environment" SKILL.md; then
  fail "SKILL.md Step 2 heading is too broad; use a precise test/CLI detection heading"
fi

grep -q "openspec_available" SKILL.md \
  || fail "SKILL.md does not persist or consume openspec_available"

grep -q "command -v openspec" SKILL.md \
  || fail "SKILL.md does not define OpenSpec CLI detection"

grep -q "\\[ORBIT_FALLBACK\\].*inline fallback" SKILL.md \
  || fail "SKILL.md is missing explicit inline fallback warning"

if grep -n "Stage 4 Internal: Bugfix / Docs" references/bridge-rules.md >/tmp/orbit-validate-bridge.txt; then
  cat /tmp/orbit-validate-bridge.txt >&2
  fail "bridge-rules has stale Stage 4 heading for Stage 2 artifact generation"
fi

echo "OK: Orbit repository checks passed"
