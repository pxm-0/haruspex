---
name: haruspex
description: diagnose software-project blind spots and standardize agentic delivery from task intake through live validation. use when starting, planning, building, reviewing, testing, deploying, or closing coding work; when converting chat into a prd or implementation task; when auditing assumptions, edge cases, risks, dependencies, security, reliability, data, operations, release safety, or evidence; or when installing and operating a repo-local .haruspex harness shared by codex, claude code, humans, and ci.
---

# Haruspex

Haruspex performs a **Reading** of software work: expose hidden assumptions, classify material risks, define evidence, and prevent a project from advancing on confidence alone. Keep durable state in the repository so different agents and humans inherit the same record.

## Choose the operation

- **New repository or no `.haruspex/` directory:** bootstrap the harness.
- **New task, vague request, chat discussion, or draft PRD:** perform a Reading and create or update the active task.
- **Implementation request:** inspect state first, confirm the build gate, then work only within the active task.
- **Review or testing request:** evaluate acceptance criteria and failure paths independently of the implementation narrative.
- **Deployment request:** run the release gate before changing production.
- **Existing project audit:** perform a fresh Reading; reopen an earlier stage when new evidence invalidates it.
- **Closeout request:** require production evidence, known-issue disposition, and handoff before closing.

## Use the bundled CLI

Resolve `scripts/haruspex.py` relative to this `SKILL.md` and run it with an absolute path. The CLI uses only Python's standard library.

Common commands:

```bash
python3 /absolute/path/to/scripts/haruspex.py init /path/to/repo
python3 /absolute/path/to/scripts/haruspex.py doctor /path/to/repo
python3 /absolute/path/to/scripts/haruspex.py status /path/to/repo
python3 /absolute/path/to/scripts/haruspex.py task create "Task title" /path/to/repo
python3 /absolute/path/to/scripts/haruspex.py gate ready-to-build /path/to/repo --record
python3 /absolute/path/to/scripts/haruspex.py verify /path/to/repo
python3 /absolute/path/to/scripts/haruspex.py gate ready-to-release /path/to/repo --record
python3 /absolute/path/to/scripts/haruspex.py gate close /path/to/repo --record
```

Use the repository-local copy at `.haruspex/bin/haruspex.py` after initialization for ordinary checks. Use the bundled Skill copy for `init` and `upgrade` because it carries the managed templates.

## Bootstrap workflow

1. Inspect the repository root, existing instruction files, package manifests, CI, deployment files, and documentation.
2. Run `haruspex.py init <repo>`. Do not overwrite repository-owned Haruspex state. Add the marked Haruspex block to `AGENTS.md` and `CLAUDE.md` without replacing existing instructions.
3. Update `.haruspex/project.json` with real commands, project risk, paths, and every characteristic set to `true` or `false`; do not leave material characteristics `null` after the Reading.
4. Run `doctor` and resolve structural errors. Warnings may remain only when explicitly recorded as follow-up work.

## The Reading

Read [references/diagnostic-lenses.md](references/diagnostic-lenses.md) before diagnosing unfamiliar or material work.

1. **Ground the task.** Inspect the request, repository, relevant runtime behavior, prior decisions, current branch, tests, deployments, and external contracts. Separate facts from claims and guesses.
2. **Define the outcome.** State the affected actor, present problem, desired behavior, success signal, scope, exclusions, and constraints.
3. **Classify characteristics.** Set all project characteristics and activate the matching profile reviews.
4. **Extract assumptions.** Record each material assumption with its basis, impact if false, blocking status, and intended validation. Include assumptions made by the requester, specification, existing code, and agent.
5. **Probe failure modes.** Examine unhappy paths, partial success, retries, concurrency, permissions, data transitions, recovery, observability, rollout, and rollback. Do not stop at generic questions; tie each concern to the actual system path.
6. **Resolve or disposition.** Mark assumptions as validated, invalidated, accepted risk, or deferred. A blocking assumption or question must not remain unresolved at the build gate.
7. **Define evidence.** Turn the desired behavior and material failure modes into acceptance criteria and a test plan. State what evidence will prove each criterion.
8. **Write the record.** Create or update the active task JSON under `.haruspex/tasks/`, the PRD/decision documents named in `project.json`, and `.haruspex/reading.md` for the human-readable summary.
9. **Challenge the draft.** Perform a separate adversarial pass that assumes the plan is incomplete. Add newly discovered assumptions and failure modes before recommending the build gate.

When a decision genuinely requires the user, present the smallest concrete decision with a recommendation and consequences. Otherwise use a reversible default, record it as an assumption, and continue.

## Build workflow

Read [references/protocol.md](references/protocol.md) for gate semantics.

1. Run `doctor`, then `gate ready-to-build`.
2. Do not implement while the gate is blocked. Resolve concrete blockers or obtain explicit human approval where required.
3. Implement vertical slices that satisfy named acceptance criteria.
4. After each slice, run targeted checks and record evidence with `haruspex.py check <name>`.
5. Keep the task, decisions, assumptions, and test plan synchronized with discoveries. Reopen specification when implementation reveals a material contradiction or new scope.
6. Never convert an unverified claim into a passed criterion. Link criterion evidence to a check artifact, review, screenshot, log, or reproducible command.

## Independent verification

Treat verification as a new reading of the result, not a summary of the build agent's work.

1. Compare implementation to the original outcome, exclusions, acceptance criteria, and material failure modes.
2. Inspect the diff and runtime behavior. Verify negative paths and recovery behavior, not only the happy path.
3. Run `haruspex.py verify <repo>` to execute all configured required checks and record commit-bound evidence.
4. Mark each acceptance criterion passed or failed with evidence.
5. Complete the independent review with findings and reviewer identity, or record a justified human waiver.
6. Run `gate verification --record`. A stale check, dirty-tree mismatch, missing command, unverified criterion, or unresolved finding blocks passage.

## Release and live validation

1. Complete deployment, rollback, smoke-test, monitoring, configuration, migration, and ownership details before `ready-to-release`.
2. Never self-approve a human gate. Record approval only after the user or authorized human explicitly approves that named gate.
3. Run `gate ready-to-release --record` before production actions.
4. Record the deployed commit and environment with the CLI. Execute production smoke tests and inspect relevant logs, metrics, data, and external side effects.
5. Record live validation as passed only when the intended real path works. Deployment success alone is insufficient.
6. Roll back or reopen the appropriate stage when production evidence contradicts the plan.

## Closeout and learning

1. Record known issues, follow-up ownership, and operational warnings.
2. Write the handoff and update durable documentation.
3. Convert any repeated surprise into a Haruspex profile, gate rule, deterministic check, or template improvement.
4. Run `gate close --record`. Do not call a project closed merely because code was merged or deployed.

## Integrity rules

- Treat `.haruspex/managed/` as harness-managed. Change it only through `upgrade` or deliberate harness development.
- Treat `.haruspex/project.json`, `state.json`, tasks, decisions, assumptions, and evidence as repository-owned history.
- Do not erase prior failed evidence; append new evidence.
- Bind automated evidence to the current Git commit and record whether the working tree was dirty.
- Do not hide scope expansion inside implementation. Amend the task and rerun the affected gate.
- Do not mark a review `not_applicable` without a concise rationale.
- Do not approve on behalf of a human, fabricate test execution, or infer production success from local behavior.
- If the harness conflicts with a stricter repository or organizational policy, follow the stricter policy and record the conflict.

## Standard response

For a Reading or gate review, report:

```text
HARUSPEX — THE READING
Stage: <stage>
Recommendation: PROCEED | PROCEED WITH CONDITIONS | BLOCK

Outcome
<one concise paragraph>

Material assumptions
<validated, unresolved, invalidated, or accepted-risk assumptions>

Blind spots and failure modes
<system-specific findings ordered by consequence>

Gate blockers
<exact missing decisions or evidence>

Next actions
<smallest ordered actions that move the project forward>
```

Keep the chat summary concise; write detail into repository artifacts.

## References

- [references/protocol.md](references/protocol.md): stages, gates, approvals, backward transitions, and evidence rules.
- [references/diagnostic-lenses.md](references/diagnostic-lenses.md): core review lenses and conditional profiles.
- [references/artifact-contracts.md](references/artifact-contracts.md): required project, task, state, and evidence fields.
- [references/distribution.md](references/distribution.md): direct installation and GitHub release layout for OpenAI and Claude Code.
