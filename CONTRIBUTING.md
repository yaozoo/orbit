# Contributing to Orbit

Orbit is an Agent Skill — a SKILL.md file, a few rule tables, and a state machine. This makes contributing refreshingly simple: there's no build system, no package dependencies, and no CI pipeline to navigate. If you've ever wished your AI coding assistant had better process, you're in the right place.

## What Makes a Good Contribution

Orbit's design philosophy is: **don't rewrite what already works.** Before opening a PR, ask:

- Does this improve the orchestration layer (routing, bridging, state machine)?
- Does this make the human experience smoother (clearer checkpoints, better error recovery)?
- Does it stay within Orbit's scope (no CI/CD hooks, no UI, no Git replacement)?

If the answer is yes, read on.

## Ways to Contribute

### Report a Bug

Found something off? Open an issue with:

- Your `.orbit-state` file (from `openspec/changes/<change-id>/.orbit-state`)
- The stage and substage where the problem occurred
- Any relevant conversation logs (what you asked, what Orbit did, what went wrong)
- The AI tool you're using (Codex, Claude Code, Cursor, Windsurf)

### Suggest a Feature

Describe:

- The scenario where this feature helps
- What you'd expect Orbit to do
- Why the existing behavior falls short

Feature requests that include a concrete use case are 10x more likely to lead to a good implementation.

### Improve the Docs

Found a confusing sentence? A missing explanation? A broken link? Pull requests to SKILL.md, README.md, or the reference files are always welcome. For the reference files (`references/`), make sure you're not breaking the bridge rules or state schema.

### Add a New Sub-Skill Bridge

Orbit bridges OpenSpec and Superpowers. If there's a Superpowers skill Orbit doesn't yet integrate, you can add it:

1. Add the skill to the legal skill table in `references/stage-transitions.md`
2. Add a terminal jump interception rule
3. Add an inline fallback in `SKILL.md` under Tool Compatibility
4. If the skill produces artifacts, add bridge rules in `references/bridge-rules.md`

### Improve Tool Compatibility

If you use Orbit on a tool we don't officially support, let us know! Submit a PR with:

- The tool name and setup instructions
- Any modifications needed for trigger phrases
- Notes on skill-loading behavior in that tool

## Development Workflow

### Running Orbit Locally

Since Orbit is a pure Skill, "running it" means loading it into your AI coding tool:

```bash
# Symlink the working copy into the skills directory
ln -sfn $(pwd) ~/.agents/skills/orbit

# Restart your AI tool
# Trigger Orbit: /orbit test the changes
```

### Testing Changes

Test manually by running through a simple feature or bugfix workflow. Focus on:

- Does Orbit correctly detect the change type at Stage 0?
- Does the stage transition logic work (0→1→2 etc.)?
- Do the `[ORBIT_CHECKPOINT]` markers fire at the right moments?
- Does the Blocking Human Review Gate appear and function?
- Does resume work after interrupting mid-flow?

### Before You Submit

- [ ] Verify your changes don't break the state schema (check `references/state-schema.yaml`)
- [ ] Run through at least one full workflow with a real AI tool
- [ ] If you modified bridge rules, test with both feature and bugfix paths
- [ ] Update the relevant reference files if you changed stage logic
- [ ] Check that inline fallback instructions still make sense

## Pull Request Guidelines

- **Keep PRs focused.** One feature or fix per PR.
- **Link to an issue.** If you're fixing a bug, reference the issue number.
- **Describe the change.** What, why, and how you tested it.
- **No unrelated refactors.** Orbit is small — keep changes scoped.

## Code of Conduct

Be kind. Be constructive. Orbit exists to make AI coding better for everyone.

## Questions?

Open a [Discussion](https://github.com/yaozoo/orbit/discussions) on GitHub. We read everything.

---

> Orbit is what happens when you stop fighting your AI and start giving it a process. Thanks for helping build that.
