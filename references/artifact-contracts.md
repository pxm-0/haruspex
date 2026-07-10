# Artifact Contracts

## Contents

1. Ownership boundaries
2. Project configuration
3. State
4. Task
5. Reading
6. Evidence
7. Agent bootstrap files

## 1. Ownership boundaries

Harness-managed and replaceable on upgrade:

```text
.haruspex/managed/
.haruspex/bin/haruspex.py
```

Repository-owned and never overwritten by upgrade:

```text
.haruspex/project.json
.haruspex/state.json
.haruspex/tasks/
.haruspex/decisions/
.haruspex/assumptions/
.haruspex/evidence/
.haruspex/reading.md
project documentation
```

## 2. Project configuration

`.haruspex/project.json` declares:

- Harness and schema versions.
- Project name, owner, and risk.
- Characteristics that activate profile reviews.
- Exact local commands for checks.
- Paths to PRD, architecture, runbook, release plan, and handoff.
- Check timeout and optional policies.

Every characteristic must become `true` or `false` after diagnosis. `null` means not yet considered, not "not applicable."

## 3. State

`.haruspex/state.json` stores:

- Current stage and status.
- Active task id.
- Gate results and blockers, each bound to the active task and a timestamped Git snapshot.
- Human approvals.
- Deployment record identifying the active task, environment, and exact approved commit when Git is present.
- Live-validation record.
- Last update metadata.

State describes the project; it must not duplicate the full task specification.

## 4. Task

Each `.haruspex/tasks/<id>.json` contains:

- Problem, affected actors, current behavior, desired outcome, and success metrics.
- Included and excluded scope.
- Acceptance criteria with status and evidence.
- Assumptions, open questions, dependencies, and failure modes.
- Core and conditional review coverage.
- Test plan and required automated checks.
- Release plan.
- Independent review.
- Known issues and follow-ups.

Use stable ids such as `AC-001`, `ASM-001`, `Q-001`, and `FM-001`. Preserve records when their status changes.

## 5. Reading

`.haruspex/reading.md` is the human-readable snapshot. Include:

- Outcome and stage recommendation.
- Material assumptions by status.
- Blind spots and concrete failure modes.
- Activated profiles.
- Gate blockers.
- Ordered next actions.

The JSON task is authoritative for gate evaluation; the Reading is optimized for review.

## 6. Evidence

Automated check evidence lives under `.haruspex/evidence/checks/` and includes:

- Check name, command, and owning task id.
- Start and completion times.
- Exit code and status.
- Repository path, Git branch, commit, dirty-tree flag, worktree fingerprint, and snapshot time.
- Log path.

Manual evidence can be a JSON record or a link in an acceptance criterion. It must identify who observed what, where, when, and by what procedure.

Evidence is append-only. A newer pass supersedes an older failure for current gate evaluation, but the failure remains in history.

## 7. Agent bootstrap files

`AGENTS.md` and `CLAUDE.md` receive the same marked block. The block points both systems to `.haruspex/managed/PROTOCOL.md`, project configuration, state, and active task. Vendor files never hold separate task state.
