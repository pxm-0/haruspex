# The Haruspex Protocol

## Contents

1. Purpose
2. State machine
3. Gate semantics
4. Evidence rules
5. Approval rules
6. Backward transitions
7. Build and verification loops
8. Risk handling

## 1. Purpose

Haruspex prevents software work from advancing because an agent feels finished. A transition requires durable artifacts, explicit decisions, and evidence appropriate to the project's risk and characteristics.

The repository is the system of record. Chat remains a reasoning surface, not the only location of decisions.

## 2. State machine

```text
discovery
  -> specification
  -> ready_to_build
  -> build
  -> verification
  -> ready_to_release
  -> deployment
  -> live_validation
  -> closed
```

The CLI uses four executable gates:

- `ready-to-build`: specification is sufficiently explicit and approved.
- `verification`: implementation is independently shown to meet the task contract.
- `ready-to-release`: release mechanics and production risk are prepared and approved.
- `close`: production behavior, known issues, and handoff are recorded.

A project may move backward at any time. Backward movement is corrective, not failure.

## 3. Gate semantics

A gate result is one of:

- **passed**: every mandatory condition is satisfied by current evidence.
- **blocked**: one or more mandatory conditions are missing, failed, stale, or contradictory.
- **pending**: the gate has not yet been evaluated for the current state.

### Ready to build

Require:

- Classified project risk and characteristics.
- Active task with a real problem, desired outcome, scope, and exclusions.
- Testable acceptance criteria.
- Blocking assumptions and questions resolved or explicitly accepted by the proper owner.
- Core review lenses completed.
- Every activated conditional profile completed or waived with rationale.
- A test plan covering the material behaviors and failures.
- Explicit human approval.

### Verification

Require:

- Ready-to-build gate passed.
- All configured task checks passed against the current commit.
- Acceptance criteria individually verified with evidence.
- Material failure paths tested or dispositioned.
- Independent review passed, or a justified human waiver exists.
- No unresolved critical or high-severity findings.

### Ready to release

Require:

- Verification gate passed.
- Deployment, rollback, smoke, monitoring, configuration, migration, and ownership plans appropriate to the activated profiles.
- Production side effects and credentials understood.
- Explicit human approval.

### Close

Require:

- Ready-to-release gate passed.
- Deployment record identifies environment and commit.
- Production smoke and intended live path passed.
- Known issues and follow-ups are recorded.
- Handoff exists and ownership is clear.

## 4. Evidence rules

Evidence must be:

- **Specific:** name the criterion, check, command, environment, or observation.
- **Reproducible:** provide a command, artifact path, or clear manual procedure.
- **Current:** automated evidence must belong to the active task and match the current Git commit and worktree fingerprint.
- **Durable:** store it under `.haruspex/evidence/` or link a durable external record.
- **Honest:** preserve failures and superseded evidence rather than overwriting history.

Evidence types include automated-check JSON, logs, screenshots, test reports, review notes, deployment records, and production observations.

A statement such as "tests pass" is not sufficient without a recorded command result. A successful deployment is not sufficient evidence that the user path works.

Every recorded gate result is bound to the active task and a Git snapshot, including the branch, commit, dirty state, worktree fingerprint, and check time. Non-Git repositories record an explicit non-Git snapshot. Later gates reject stale, cross-task, or legacy gate records that lack this binding.

A deployment in a Git repository must record the exact commit approved by `ready_to_release`, and the current worktree must still match that gate snapshot. Supplying an explicit commit does not bypass this check. Non-Git repositories enforce task binding but do not fabricate or compare commits.

## 5. Approval rules

Agents may recommend approval, collect evidence, and explain consequences. They must not approve a human-controlled gate.

The default human gates are:

- Ready to build.
- Ready to release.
- Acceptance of critical or high residual risk.
- Destructive data actions.
- Production migrations and irreversible side effects.

The local CLI records claims of approval but cannot authenticate identity. Enforce stronger guarantees with protected branches, required reviewers, deployment environments, or an external approval service when needed.

## 6. Backward transitions

Reopen an earlier stage when:

- The implementation contradicts a requirement or reveals missing scope.
- A material assumption is invalidated.
- A dependency or external contract changes.
- Verification exposes an architectural or product gap rather than a local defect.
- Release planning reveals missing rollback, migration, security, or operational design.
- Production behavior differs from acceptance criteria.

Choose the earliest stage whose output is no longer trustworthy. Do not patch the state file to preserve apparent progress.

## 7. Build and verification loops

### Build loop

```text
select criterion or vertical slice
-> plan exact change
-> implement
-> run targeted check
-> inspect diff and failure paths
-> record evidence
-> checkpoint
```

### Verification loop

```text
load original task contract
-> independently inspect implementation
-> run configured checks
-> exercise negative and recovery paths
-> evaluate every criterion
-> record findings
-> pass or reopen
```

Separate the build and verification passes even when the same model performs both. The verification pass must not assume the implementation narrative is correct.

## 8. Risk handling

Classify findings by consequence and reversibility:

- **critical:** plausible severe harm, irreversible loss, major security/privacy exposure, or unsafe production action. Blocks progression.
- **high:** likely material user, financial, data, availability, or compliance impact. Blocks unless explicitly accepted by an authorized human.
- **medium:** meaningful defect or operational burden with bounded impact. Resolve or create an owned follow-up before release.
- **low:** minor quality or maintainability issue. Record and prioritize proportionally.

Avoid checklist theater. A completed review means the relevant system path was examined and findings were either resolved or explicitly dispositioned.
