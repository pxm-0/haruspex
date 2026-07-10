# Diagnostic Lenses

## Contents

1. Reading method
2. Core lenses
3. Conditional profiles
4. Assumption quality
5. Adversarial prompts

## 1. Reading method

For each lens:

1. Describe the actual system path in concrete terms.
2. Identify claims that path relies on.
3. Ask how each claim could be false.
4. Trace the consequence and detectability of failure.
5. Decide whether to validate, redesign, accept, defer, or exclude.
6. Define evidence for the decision.

Do not emit a generic wall of questions. Prioritize by consequence, uncertainty, and cost of discovering the error late.

## 2. Core lenses

### Product and outcome

- Who is affected and what observable problem exists now?
- What behavior or metric would show improvement?
- What is deliberately excluded?
- Could a smaller change satisfy the outcome?
- Which stakeholder decision is being smuggled into implementation?

### Behavior and experience

- Happy path, empty state, invalid input, cancellation, timeout, retry, partial completion, and recovery.
- Accessibility, permissions, user-visible errors, and operator experience.
- Cross-device, timezone, localization, ordering, and stale-state behavior where relevant.

### Data and state

- Source of truth, ownership, lifecycle, invariants, and state transitions.
- Duplicate execution, concurrency, partial writes, corruption, migration, backfill, retention, deletion, and restoration.
- Whether historical data and new code remain mutually compatible during rollout.

### Security and privacy

- Authentication, authorization, tenant boundaries, input validation, secrets, sensitive data, auditability, abuse paths, and dependency trust.
- Least privilege and the blast radius of compromised credentials or malformed input.

### Reliability

- Dependency outages, latency, timeouts, retry classification, backpressure, rate limits, idempotency, graceful degradation, and recovery.
- Whether a failure can be detected before users report it.

### Operations

- Logs, metrics, traces, health checks, alerts, dashboards, runbooks, ownership, incident response, and support diagnosis.
- What an operator sees when the system is partially healthy.

### Performance and cost

- Workload shape, latency budget, throughput, resource ceilings, storage growth, external API spend, AI token cost, and scaling triggers.
- Worst plausible input rather than only typical input.

### Delivery and release

- Configuration, credentials, environment parity, migration order, backward compatibility, feature flags, rollout, smoke tests, monitoring, backup, rollback, and post-release ownership.

### Maintainability

- Boundary clarity, testability, dependency direction, documentation, removal path, ownership, and future change cost.
- Whether a temporary workaround has an expiry condition.

## 3. Conditional profiles

Activate a profile when its characteristic is `true`. Mark the profile review complete only after every relevant item has a concrete answer, design, test, or recorded exclusion.

### `user_facing`

Require user journeys, error states, accessibility, analytics or success signal, support behavior, and live acceptance validation.

### `has_api`

Require request/response contracts, validation, authentication and authorization, compatibility, pagination or limits, idempotency where applicable, error semantics, observability, and consumer migration.

### `has_database`

Require schema ownership, invariants, indexes, transactions, concurrency, backup, restore, retention, and data-volume assumptions.

### `schema_change`

Require forward migration, deployment ordering, backward compatibility, backfill, validation, rollback or restore, and mixed-version behavior.

### `external_writes`

Require idempotency, retry classification, partial-success representation, rate limits, credential checks, persisted external identifiers, reconciliation, sandbox/live separation, and operator recovery.

### `uses_ai`

Require evaluation scenarios, output validation, prompt/model versioning, uncertainty behavior, refusals, sensitive-data policy, latency and cost limits, fallback, human override, and live sample evaluation.

### `handles_sensitive_data`

Require data classification, collection minimization, access controls, encryption, retention, deletion, logging redaction, regional or contractual constraints, and incident handling.

### `destructive_operations`

Require explicit confirmation, scoped authorization, preview or dry run, backups, irreversibility warning, audit record, rollback or compensation, and protected human approval.

### `new_service`

Require runtime configuration, health and readiness checks, supervision, resource limits, scaling, logging, monitoring, on-call ownership, dependency startup order, deployment, rollback, and disaster recovery.

### `scheduled_or_async`

Require queue or scheduler semantics, deduplication, poison-message handling, retries, deadlines, cancellation, observability, replay, and stuck-work recovery.

### `payments_or_money`

Require exact amounts and currency handling, idempotency, reconciliation, refunds or compensation, ledger/source of truth, authorization, fraud and abuse, auditability, and financial failure modes.

### `multi_tenant`

Require tenant isolation in every storage, cache, queue, search, logging, authorization, and administrative path.

## 4. Assumption quality

A useful assumption record answers:

- **Statement:** what must be true?
- **Basis:** why do we currently believe it?
- **Impact if false:** what breaks, and how badly?
- **Validation:** how will we test or confirm it?
- **Owner:** who can decide or verify?
- **Status:** unresolved, validated, invalidated, accepted risk, or deferred.
- **Blocking:** may work proceed without resolution?

Avoid assumptions such as "the API works." Prefer "the provider returns a stable idempotency key result for repeated create requests within 24 hours; otherwise retries can create duplicate customer-visible records."

## 5. Adversarial prompts

Use a separate pass with prompts like:

- What would have to be true for this plan to fail while all happy-path tests pass?
- Where can the system report success after only partial completion?
- Which requirement has been inferred rather than stated?
- Which existing user, integration, or historical data shape could this break?
- What does the design assume about time, ordering, identity, retries, or uniqueness?
- What production-only dependency or permission has not been exercised?
- How would an operator detect and repair the failure at 3 a.m.?
- What cannot be rolled back after the first real side effect?
- Which claim is supported only by the builder's own description?
- What is the smallest experiment that could invalidate the riskiest assumption now?
