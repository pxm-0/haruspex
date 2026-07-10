# Distribution

## Canonical source

Use one Git repository as the source of truth. Build immutable release artifacts from tags.

Recommended layout:

```text
haruspex/
├── SKILL.md
├── agents/openai.yaml
├── .claude-plugin/plugin.json
├── scripts/
├── references/
├── assets/
└── .github/workflows/release.yml
```

The same source directory is an Agent Skill and a single-skill Claude Code plugin. Keep vendor metadata thin; keep reasoning and harness logic shared.

## OpenAI

Package the directory as `skill.zip` and upload it through the Skills interface. Install the same release separately in each OpenAI product where needed because product installations may not synchronize. Keep GitHub as source and release history, not as a runtime dependency.

## Claude Code

For personal direct use, place or symlink the skill directory under `~/.claude/skills/haruspex/`. For a repository-specific copy, use `.claude/skills/haruspex/`.

For versioned distribution, keep `.claude-plugin/plugin.json` at the root and test with:

```bash
claude --plugin-dir /path/to/haruspex
```

A release zip can be tested with `--plugin-dir`; a trusted hosted zip can be loaded for a session with `--plugin-url`. Marketplace publication can come after real-project validation.

## GitHub releases

Publish:

```text
skill.zip
haruspex-claude-plugin.zip
SHA256SUMS
```

Release flow:

1. Run CLI self-tests.
2. Validate the Skill.
3. Package `skill.zip`.
4. Package a Claude plugin zip with the plugin directory at archive root.
5. Generate checksums.
6. Attach artifacts to an immutable semantic-version tag.

## External harnesses

Keep the local `.haruspex/` harness authoritative. Optional services may aggregate approvals, dashboards, organizational policies, or cross-repository learning through an API or MCP server, but the project must remain diagnosable when those services are unavailable.
