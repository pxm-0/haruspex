# Haruspex

Haruspex is an agent-neutral software-delivery diligence system. It performs a **Reading** of a task, exposes hidden assumptions and failure modes, and requires durable evidence before work advances through build, verification, release, and closeout.

The Skill supplies the reasoning workflow. The repository-local `.haruspex/` directory supplies shared state. The standard-library CLI supplies deterministic checks. `AGENTS.md` and `CLAUDE.md` point Codex and Claude Code to the same record.

## What v0 includes

- A portable `SKILL.md` for diagnosis and delivery orchestration.
- A single-skill Claude Code plugin manifest.
- A dependency-free Python CLI.
- Repo-local project, task, gate, approval, deployment, and evidence files.
- Conditional diagnostic profiles for APIs, databases, schema changes, external writes, AI, sensitive data, destructive operations, services, async work, payments, and multi-tenancy.
- Optional GitHub Actions enforcement.
- End-to-end self-tests, including stale-evidence detection.

## Local development

```bash
python3 scripts/self_test.py
python3 scripts/haruspex.py version
```

Initialize a fixture or application repository:

```bash
python3 scripts/haruspex.py init /path/to/repo --with-ci
python3 /path/to/repo/.haruspex/bin/haruspex.py doctor /path/to/repo
python3 /path/to/repo/.haruspex/bin/haruspex.py task create "Describe the task" /path/to/repo
```

The Skill then performs the Reading, updates `.haruspex/project.json` and the active task, and recommends or blocks the ready-to-build gate.

## Distribution

Build release artifacts from the repository root:

```bash
python3 scripts/build_release.py --output dist
```

This creates:

```text
dist/skill.zip
  OpenAI Agent Skill package with a top-level haruspex/ directory

dist/haruspex-claude-plugin.zip
  Claude Code plugin archive with plugin files at archive root

dist/SHA256SUMS
  Release checksums
```

Use immutable semantic-version tags for releases. Install the same tagged source separately in each product; the local `.haruspex/` state remains the continuity layer.

## Trust boundary

The local CLI can record a claimed human approval, but it cannot authenticate identity. For consequential production systems, pair Haruspex with protected branches, required reviewers, protected deployment environments, or an external approval service.

Haruspex does not require a hosted service. An external dashboard, policy service, or MCP server can be added later without replacing the repository as the durable project record.
