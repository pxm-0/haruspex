#!/usr/bin/env python3
"""Haruspex: repository-local project diligence and delivery gates.

This CLI intentionally uses only the Python standard library. It stores durable
state in .haruspex/ and records command evidence without relying on a hosted
service.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

HARUSPEX_VERSION = "0.1.0"
SCHEMA_VERSION = 1
GATE_ALIASES = {
    "ready-to-build": "ready_to_build",
    "ready_to_build": "ready_to_build",
    "verification": "verification",
    "ready-to-release": "ready_to_release",
    "ready_to_release": "ready_to_release",
    "close": "close",
}
STAGES = [
    "discovery",
    "specification",
    "ready_to_build",
    "build",
    "verification",
    "ready_to_release",
    "deployment",
    "live_validation",
    "closed",
]
STAGE_INDEX = {stage: index for index, stage in enumerate(STAGES)}
GATE_NEXT_STAGE = {
    "ready_to_build": "build",
    "verification": "ready_to_release",
    "ready_to_release": "deployment",
    "close": "closed",
}
HUMAN_GATES = {"ready_to_build", "ready_to_release"}
ASSUMPTION_RESOLVED = {"validated", "invalidated", "accepted_risk"}
QUESTION_RESOLVED = {"answered", "accepted_risk", "closed"}
REVIEW_COMPLETE = {"complete"}
REVIEW_WAIVED = {"waived", "not_applicable"}
CRITICAL_SEVERITIES = {"critical", "high"}
MARKER_START = "<!-- HARUSPEX:START -->"
MARKER_END = "<!-- HARUSPEX:END -->"


class HaruspexError(RuntimeError):
    """User-facing Haruspex error."""


@dataclass
class GateResult:
    gate: str
    passed: bool
    blockers: list[str]
    warnings: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "gate": self.gate,
            "status": "passed" if self.passed else "blocked",
            "blockers": self.blockers,
            "warnings": self.warnings,
        }


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_timestamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HaruspexError(f"Missing required file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise HaruspexError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise HaruspexError(f"Expected a JSON object in {path}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(payload)
        temp_name = handle.name
    os.replace(temp_name, path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_quiet(command: list[str], cwd: Path) -> tuple[int, str]:
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError:
        return 127, ""
    return completed.returncode, completed.stdout.strip()


def git_info(repo: Path) -> dict[str, Any]:
    code, inside = run_quiet(["git", "rev-parse", "--is-inside-work-tree"], repo)
    if code != 0 or inside != "true":
        return {
            "is_git": False,
            "branch": None,
            "commit": None,
            "dirty": None,
            "worktree_fingerprint": None,
            "checked_at": now_utc(),
        }

    _, commit = run_quiet(["git", "rev-parse", "HEAD"], repo)
    _, branch = run_quiet(["git", "branch", "--show-current"], repo)
    # Haruspex state and evidence are control-plane metadata. Exclude them from
    # the worktree fingerprint so recording a check does not invalidate itself.
    status_command = [
        "git", "status", "--porcelain=v1", "-z", "--untracked-files=all", "--", ".",
        ":(exclude).haruspex/**",
    ]
    _, status = run_quiet(status_command, repo)
    dirty = bool(status)

    digest = hashlib.sha256()
    diff_process = subprocess.run(
        ["git", "diff", "--binary", "HEAD", "--", ".", ":(exclude).haruspex/**"],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    digest.update(diff_process.stdout)
    digest.update(status.encode("utf-8", errors="replace"))

    # Include untracked file contents so dirty evidence can be matched later.
    for raw_entry in status.split("\0"):
        if not raw_entry.startswith("?? "):
            continue
        relative = raw_entry[3:]
        candidate = repo / relative
        digest.update(relative.encode("utf-8", errors="replace"))
        if candidate.is_file():
            try:
                digest.update(bytes.fromhex(sha256_file(candidate)))
            except OSError:
                digest.update(b"unreadable")

    return {
        "is_git": True,
        "branch": branch or None,
        "commit": commit or None,
        "dirty": dirty,
        "worktree_fingerprint": digest.hexdigest(),
        "checked_at": now_utc(),
    }


def script_root() -> Path:
    return Path(__file__).resolve().parent.parent


def template_root() -> Path:
    return script_root() / "assets" / "repo-template"


def integration_root() -> Path:
    return script_root() / "assets" / "integrations"


def require_templates() -> Path:
    root = template_root()
    if not root.exists():
        raise HaruspexError(
            "This command needs the Skill-bundled Haruspex CLI because the repository-local copy "
            "does not carry release templates. Invoke scripts/haruspex.py from the installed Skill."
        )
    return root


def resolve_repo(path: str | Path, require_harness: bool = True) -> Path:
    candidate = Path(path).expanduser().resolve()
    if candidate.is_file():
        candidate = candidate.parent
    if not require_harness:
        return candidate

    current = candidate
    while True:
        if (current / ".haruspex").is_dir():
            return current
        if current.parent == current:
            break
        current = current.parent
    raise HaruspexError(f"No .haruspex directory found from {candidate}. Run 'haruspex init' first.")


def state_paths(repo: Path) -> tuple[Path, Path]:
    return repo / ".haruspex" / "project.json", repo / ".haruspex" / "state.json"


def load_project_state(repo: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    project_path, state_path = state_paths(repo)
    return load_json(project_path), load_json(state_path)


def active_task_path(repo: Path, state: dict[str, Any]) -> Path | None:
    task_id = state.get("active_task")
    if not task_id:
        return None
    return repo / ".haruspex" / "tasks" / f"{task_id}.json"


def load_active_task(repo: Path, state: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    path = active_task_path(repo, state)
    if path is None:
        raise HaruspexError("No active task. Create or activate one with 'haruspex task'.")
    return path, load_json(path)


def update_state_metadata(state: dict[str, Any], by: str | None = None) -> None:
    state["last_updated_at"] = now_utc()
    if by:
        state["last_updated_by"] = by


def replace_marked_block(existing: str, block: str) -> str:
    block = block.strip() + "\n"
    if MARKER_START in existing and MARKER_END in existing:
        pattern = re.compile(re.escape(MARKER_START) + r".*?" + re.escape(MARKER_END), re.DOTALL)
        replaced = pattern.sub(block.strip(), existing, count=1)
        return replaced.rstrip() + "\n"
    if existing.strip():
        return existing.rstrip() + "\n\n" + block
    return block


def copy_template_tree(source: Path, repo: Path, force_managed: bool) -> list[str]:
    written: list[str] = []
    for source_path in source.rglob("*"):
        if source_path.is_dir():
            continue
        relative = source_path.relative_to(source)
        if relative.name.endswith(".fragment"):
            continue
        destination = repo / relative
        managed = str(relative).startswith(".haruspex/managed/")
        should_write = not destination.exists() or (force_managed and managed)
        if should_write:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, destination)
            written.append(str(relative))
    return written


def install_agent_block(repo: Path, fragment_path: Path, target_name: str) -> bool:
    block = fragment_path.read_text(encoding="utf-8")
    target = repo / target_name
    existing = target.read_text(encoding="utf-8") if target.exists() else ""
    updated = replace_marked_block(existing, block)
    changed = updated != existing
    if changed:
        target.write_text(updated, encoding="utf-8")
    return changed


def install_cli_copy(repo: Path) -> str:
    destination = repo / ".haruspex" / "bin" / "haruspex.py"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(Path(__file__).resolve(), destination)
    destination.chmod(destination.stat().st_mode | 0o111)
    return str(destination.relative_to(repo))


def write_lock(repo: Path) -> None:
    cli_path = repo / ".haruspex" / "bin" / "haruspex.py"
    lock = {
        "name": "haruspex",
        "version": HARUSPEX_VERSION,
        "schema_version": SCHEMA_VERSION,
        "installed_at": now_utc(),
        "cli": str(cli_path.relative_to(repo)),
        "cli_sha256": sha256_file(cli_path),
    }
    write_json(repo / ".haruspex" / "harness.lock", lock)


def command_init(args: argparse.Namespace) -> int:
    source = require_templates()
    repo = resolve_repo(args.path, require_harness=False)
    repo.mkdir(parents=True, exist_ok=True)
    harness_existed = (repo / ".haruspex").exists()
    written = copy_template_tree(source, repo, args.force_managed)

    project_path = repo / ".haruspex" / "project.json"
    project = load_json(project_path)
    if project.get("project", {}).get("name") == "__PROJECT_NAME__":
        project["project"]["name"] = args.project_name or repo.name
        write_json(project_path, project)
    elif args.project_name and not harness_existed:
        project.setdefault("project", {})["name"] = args.project_name
        write_json(project_path, project)

    for directory in [
        ".haruspex/tasks",
        ".haruspex/decisions",
        ".haruspex/assumptions",
        ".haruspex/evidence/checks",
    ]:
        (repo / directory).mkdir(parents=True, exist_ok=True)

    agents_changed = install_agent_block(repo, source / "AGENTS.md.fragment", "AGENTS.md")
    claude_changed = install_agent_block(repo, source / "CLAUDE.md.fragment", "CLAUDE.md")
    cli_relative = install_cli_copy(repo)
    write_lock(repo)

    ci_written = False
    if args.with_ci:
        ci_source = integration_root() / "github" / "haruspex.yml"
        ci_destination = repo / ".github" / "workflows" / "haruspex.yml"
        if not ci_destination.exists() or args.force_managed:
            ci_destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ci_source, ci_destination)
            ci_written = True

    mode = "Upgraded" if harness_existed else "Initialized"
    print(f"{mode} Haruspex {HARUSPEX_VERSION} in {repo}")
    if written:
        print(f"Wrote {len(written)} template file(s).")
    print(f"Installed CLI: {cli_relative}")
    if agents_changed or claude_changed:
        print("Updated AGENTS.md and CLAUDE.md Haruspex blocks.")
    if ci_written:
        print("Installed .github/workflows/haruspex.yml")
    print("Next: classify .haruspex/project.json, create an active task, and run doctor.")
    return 0


def command_upgrade(args: argparse.Namespace) -> int:
    args.force_managed = True
    return command_init(args)


def basic_structure_checks(repo: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    required_files = [
        ".haruspex/project.json",
        ".haruspex/state.json",
        ".haruspex/managed/PROTOCOL.md",
        ".haruspex/managed/gates.json",
        ".haruspex/managed/profiles.json",
        ".haruspex/bin/haruspex.py",
    ]
    for relative in required_files:
        if not (repo / relative).exists():
            errors.append(f"missing {relative}")

    if errors:
        return errors, warnings

    try:
        project, state = load_project_state(repo)
    except HaruspexError as exc:
        errors.append(str(exc))
        return errors, warnings

    if project.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"project.json schema_version must be {SCHEMA_VERSION}")
    if state.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"state.json schema_version must be {SCHEMA_VERSION}")
    if state.get("stage") not in STAGE_INDEX:
        errors.append(f"unknown state stage: {state.get('stage')!r}")
    if project.get("project", {}).get("risk") == "unclassified":
        warnings.append("project risk is unclassified")

    characteristics = project.get("characteristics", {})
    if not isinstance(characteristics, dict):
        errors.append("project characteristics must be an object")
    else:
        undecided = sorted(key for key, value in characteristics.items() if value is None)
        if undecided:
            warnings.append("unclassified characteristics: " + ", ".join(undecided))

    commands = project.get("commands", {})
    if not isinstance(commands, dict):
        errors.append("project commands must be an object")
    else:
        missing_commands = sorted(key for key, value in commands.items() if not value)
        if missing_commands:
            warnings.append("unconfigured commands: " + ", ".join(missing_commands))

    active = state.get("active_task")
    if active:
        task_path = repo / ".haruspex" / "tasks" / f"{active}.json"
        if not task_path.exists():
            errors.append(f"active task file does not exist: {task_path.relative_to(repo)}")
        else:
            try:
                task = load_json(task_path)
                if task.get("id") != active:
                    errors.append("active task id does not match its filename")
            except HaruspexError as exc:
                errors.append(str(exc))
    else:
        warnings.append("no active task")

    for instruction_file in ["AGENTS.md", "CLAUDE.md"]:
        path = repo / instruction_file
        if not path.exists() or MARKER_START not in path.read_text(encoding="utf-8", errors="replace"):
            warnings.append(f"{instruction_file} does not contain the Haruspex bootstrap block")

    lock_path = repo / ".haruspex" / "harness.lock"
    if lock_path.exists():
        try:
            lock = load_json(lock_path)
            if lock.get("version") != HARUSPEX_VERSION:
                warnings.append(
                    f"installed harness version is {lock.get('version')}; current CLI is {HARUSPEX_VERSION}"
                )
        except HaruspexError as exc:
            errors.append(str(exc))
    else:
        warnings.append("missing .haruspex/harness.lock")

    git = git_info(repo)
    if not git["is_git"]:
        warnings.append("repository is not a Git worktree; evidence cannot be commit-bound")

    return errors, warnings


def command_doctor(args: argparse.Namespace) -> int:
    repo = resolve_repo(args.path)
    errors, warnings = basic_structure_checks(repo)
    result = {"repo": str(repo), "errors": errors, "warnings": warnings}
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"HARUSPEX DOCTOR — {repo}")
        if errors:
            print("\nErrors:")
            for item in errors:
                print(f"  - {item}")
        if warnings:
            print("\nWarnings:")
            for item in warnings:
                print(f"  - {item}")
        if not errors and not warnings:
            print("No structural problems found.")
        elif not errors:
            print("\nStructure is valid; warnings remain.")
    return 1 if errors or (args.strict and warnings) else 0


def command_status(args: argparse.Namespace) -> int:
    repo = resolve_repo(args.path)
    project, state = load_project_state(repo)
    task_summary: dict[str, Any] | None = None
    if state.get("active_task"):
        try:
            _, task = load_active_task(repo, state)
            task_summary = {
                "id": task.get("id"),
                "title": task.get("title"),
                "status": task.get("status"),
                "risk": task.get("risk"),
            }
        except HaruspexError:
            task_summary = {"id": state.get("active_task"), "error": "task file missing or invalid"}

    result = {
        "repo": str(repo),
        "project": project.get("project", {}),
        "stage": state.get("stage"),
        "status": state.get("status"),
        "active_task": task_summary,
        "gates": state.get("gates", {}),
        "approvals": state.get("approvals", {}),
        "deployment": state.get("deployment", {}),
        "live_validation": state.get("live_validation", {}),
        "git": git_info(repo),
    }
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print("HARUSPEX — STATUS")
        print(f"Project: {project.get('project', {}).get('name', repo.name)}")
        print(f"Stage: {state.get('stage')} ({state.get('status')})")
        if task_summary:
            print(f"Task: {task_summary.get('id')} — {task_summary.get('title', '<missing>')} [{task_summary.get('status', 'unknown')}]")
        else:
            print("Task: none")
        print("Gates:")
        for name, entry in state.get("gates", {}).items():
            print(f"  {name}: {entry.get('status', 'unknown')}")
        print("Approvals:")
        for name, entry in state.get("approvals", {}).items():
            print(f"  {name}: {entry.get('status', 'unknown')}" + (f" by {entry.get('by')}" if entry.get("by") else ""))
    return 0


def sanitize_task_id(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9._-]+", value):
        raise HaruspexError("Task id may contain only letters, numbers, dot, underscore, and hyphen.")
    return value


def reset_gate_entry(entry: dict[str, Any]) -> None:
    entry["status"] = "pending"
    entry["checked_at"] = None
    entry["blockers"] = []
    entry["evidence"] = []
    entry["task"] = None
    entry["git"] = None


def reset_state_for_task(state: dict[str, Any], task_id: str) -> None:
    state["stage"] = "specification"
    state["status"] = "active"
    state["active_task"] = task_id
    for entry in state.get("gates", {}).values():
        if isinstance(entry, dict):
            reset_gate_entry(entry)
    for approval in state.get("approvals", {}).values():
        if isinstance(approval, dict):
            approval.update({"status": "pending", "by": None, "at": None, "note": None})
    state["deployment"] = {
        "status": "not_started",
        "environment": None,
        "commit": None,
        "task": None,
        "at": None,
        "by": None,
        "evidence": [],
        "note": None,
    }
    state["live_validation"] = {
        "status": "not_started",
        "at": None,
        "by": None,
        "evidence": [],
        "note": None,
    }
    update_state_metadata(state, "haruspex")


def command_task_create(args: argparse.Namespace) -> int:
    repo = resolve_repo(args.path)
    _, state = load_project_state(repo)
    task_id = sanitize_task_id(args.id or f"TASK-{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d-%H%M%S')}")
    destination = repo / ".haruspex" / "tasks" / f"{task_id}.json"
    if destination.exists() and not args.force:
        raise HaruspexError(f"Task already exists: {destination.relative_to(repo)}")
    template = load_json(repo / ".haruspex" / "templates" / "task.json")
    created = now_utc()
    template["id"] = task_id
    template["title"] = args.title
    template["created_at"] = created
    template["updated_at"] = created
    write_json(destination, template)
    reset_state_for_task(state, task_id)
    write_json(repo / ".haruspex" / "state.json", state)
    print(f"Created and activated {task_id}: {args.title}")
    print(destination.relative_to(repo))
    return 0


def command_task_activate(args: argparse.Namespace) -> int:
    repo = resolve_repo(args.path)
    _, state = load_project_state(repo)
    task_id = sanitize_task_id(args.id)
    task_path = repo / ".haruspex" / "tasks" / f"{task_id}.json"
    if not task_path.exists():
        raise HaruspexError(f"Task does not exist: {task_path.relative_to(repo)}")
    reset_state_for_task(state, task_id)
    write_json(repo / ".haruspex" / "state.json", state)
    print(f"Activated {task_id}; gates reset to pending.")
    return 0


def command_task_list(args: argparse.Namespace) -> int:
    repo = resolve_repo(args.path)
    _, state = load_project_state(repo)
    active = state.get("active_task")
    task_dir = repo / ".haruspex" / "tasks"
    rows: list[dict[str, Any]] = []
    for path in sorted(task_dir.glob("*.json")):
        try:
            task = load_json(path)
            rows.append({
                "id": task.get("id", path.stem),
                "title": task.get("title", ""),
                "status": task.get("status", "unknown"),
                "active": task.get("id", path.stem) == active,
            })
        except HaruspexError as exc:
            rows.append({"id": path.stem, "title": str(exc), "status": "invalid", "active": path.stem == active})
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        if not rows:
            print("No tasks.")
        for row in rows:
            marker = "*" if row["active"] else " "
            print(f"{marker} {row['id']} [{row['status']}] {row['title']}")
    return 0


def command_task_show(args: argparse.Namespace) -> int:
    repo = resolve_repo(args.path)
    _, state = load_project_state(repo)
    task_id = args.id or state.get("active_task")
    if not task_id:
        raise HaruspexError("No task id supplied and no active task.")
    task = load_json(repo / ".haruspex" / "tasks" / f"{sanitize_task_id(task_id)}.json")
    print(json.dumps(task, indent=2, ensure_ascii=False))
    return 0


def nonempty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def nonempty_list(value: Any) -> bool:
    return isinstance(value, list) and len(value) > 0


def review_is_complete(entry: Any) -> tuple[bool, str | None]:
    if not isinstance(entry, dict):
        return False, "review entry is missing or malformed"
    status = entry.get("status")
    if status in REVIEW_COMPLETE:
        if nonempty_text(entry.get("rationale")) or nonempty_list(entry.get("evidence")):
            return True, None
        return False, "completed review needs a rationale or evidence"
    if status in REVIEW_WAIVED:
        if nonempty_text(entry.get("rationale")):
            return True, None
        return False, f"review status {status!r} needs a rationale"
    return False, f"review status is {status!r}"


def normalize_gate(name: str) -> str:
    try:
        return GATE_ALIASES[name]
    except KeyError as exc:
        raise HaruspexError(f"Unknown gate: {name}") from exc


def latest_check_evidence(repo: Path, task_id: str) -> dict[str, dict[str, Any]]:
    evidence_dir = repo / ".haruspex" / "evidence" / "checks"
    latest: dict[str, dict[str, Any]] = {}
    if not evidence_dir.exists():
        return latest
    for path in sorted(evidence_dir.glob("*.json")):
        try:
            item = load_json(path)
        except HaruspexError:
            continue
        name = item.get("check")
        if not isinstance(name, str) or item.get("task") != task_id:
            continue
        item["_path"] = str(path.relative_to(repo))
        prior = latest.get(name)
        if prior is None or str(item.get("completed_at", "")) >= str(prior.get("completed_at", "")):
            latest[name] = item
    return latest


def check_evidence_current(
    item: dict[str, Any], current_git: dict[str, Any], task_id: str
) -> tuple[bool, str | None]:
    if item.get("task") != task_id:
        return False, f"evidence belongs to task {item.get('task')!r}, not active task {task_id}"
    if item.get("status") != "passed":
        return False, f"latest evidence status is {item.get('status')!r}"
    after = item.get("git_after", {})
    if current_git.get("is_git"):
        if after.get("commit") != current_git.get("commit"):
            return False, "evidence was generated for a different commit"
        if after.get("worktree_fingerprint") != current_git.get("worktree_fingerprint"):
            return False, "working tree changed after evidence was generated"
    return True, None


def gate_snapshot_issue(state: dict[str, Any], gate: str) -> str | None:
    entry = state.get("gates", {}).get(gate, {})
    if entry.get("status") != "passed":
        return f"{gate} gate has not passed."
    if not nonempty_text(entry.get("task")) or not isinstance(entry.get("git"), dict):
        return (
            f"{gate} was recorded without a task and Git snapshot. "
            "Rerun the gate with the current Haruspex version."
        )
    active_task = state.get("active_task")
    if entry.get("task") != active_task:
        return (
            f"{gate} passed for task {entry.get('task')}, but the active task is {active_task}. "
            "Rerun the gate for the active task."
        )
    return None


def evaluate_ready_to_build(repo: Path, project: dict[str, Any], state: dict[str, Any], task: dict[str, Any]) -> GateResult:
    blockers: list[str] = []
    warnings: list[str] = []

    if project.get("project", {}).get("risk") == "unclassified":
        blockers.append("Classify project risk in .haruspex/project.json.")
    if task.get("risk") == "unclassified":
        blockers.append("Classify active task risk.")

    characteristics = project.get("characteristics", {})
    if not isinstance(characteristics, dict):
        blockers.append("Project characteristics are malformed.")
        characteristics = {}
    undecided = [key for key, value in characteristics.items() if value is None]
    if undecided:
        blockers.append("Classify project characteristics: " + ", ".join(sorted(undecided)) + ".")

    if task.get("status") not in {"ready", "in_progress", "verifying", "ready_for_release", "deployed", "completed"}:
        blockers.append("Set task status to 'ready' after specification is complete.")

    problem = task.get("problem", {})
    if not nonempty_text(problem.get("summary")):
        blockers.append("Define the problem summary.")
    if not nonempty_text(problem.get("desired_outcome")):
        blockers.append("Define the desired outcome.")
    if not nonempty_list(problem.get("affected_actors")):
        blockers.append("Identify at least one affected actor.")
    if not nonempty_list(problem.get("success_metrics")):
        blockers.append("Define at least one success signal or metric.")

    scope = task.get("scope", {})
    if not nonempty_list(scope.get("included")):
        blockers.append("Define included scope.")
    if not nonempty_list(scope.get("excluded")):
        blockers.append("Define excluded scope.")

    criteria = task.get("acceptance_criteria")
    if not nonempty_list(criteria):
        blockers.append("Define at least one acceptance criterion.")
    else:
        for index, criterion in enumerate(criteria, start=1):
            if not isinstance(criterion, dict) or not nonempty_text(criterion.get("criterion")):
                blockers.append(f"Acceptance criterion {index} is empty or malformed.")

    for assumption in task.get("assumptions", []):
        if not isinstance(assumption, dict):
            blockers.append("An assumption entry is malformed.")
            continue
        if assumption.get("blocking") and assumption.get("status") not in ASSUMPTION_RESOLVED:
            blockers.append(
                f"Blocking assumption {assumption.get('id', '<unknown>')} is {assumption.get('status', 'unresolved')}."
            )
        if assumption.get("status") == "accepted_risk" and not nonempty_text(assumption.get("resolution")):
            blockers.append(f"Accepted-risk assumption {assumption.get('id', '<unknown>')} needs a resolution/rationale.")

    for question in task.get("open_questions", []):
        if not isinstance(question, dict):
            blockers.append("An open-question entry is malformed.")
            continue
        if question.get("blocking") and question.get("status") not in QUESTION_RESOLVED:
            blockers.append(f"Blocking question {question.get('id', '<unknown>')} remains open.")

    failure_modes = task.get("failure_modes", [])
    risk = str(task.get("risk", "unclassified")).lower()
    if risk in {"medium", "high", "critical"} and not nonempty_list(failure_modes):
        blockers.append("Medium-or-higher risk work needs at least one concrete failure mode.")
    for mode in failure_modes:
        if not isinstance(mode, dict):
            blockers.append("A failure-mode entry is malformed.")
            continue
        if not nonempty_text(mode.get("scenario")):
            blockers.append(f"Failure mode {mode.get('id', '<unknown>')} needs a concrete scenario.")
        severity = str(mode.get("severity", "")).lower()
        status = str(mode.get("status", "unresolved")).lower()
        if severity in CRITICAL_SEVERITIES and status not in {"addressed", "tested", "accepted_risk", "resolved", "closed"}:
            blockers.append(f"Failure mode {mode.get('id', '<unknown>')} is {severity} and unresolved.")

    review_coverage = task.get("review_coverage", {})
    core = review_coverage.get("core", {}) if isinstance(review_coverage, dict) else {}
    for name in [
        "product",
        "behavior_ux",
        "data_state",
        "security_privacy",
        "reliability",
        "operations",
        "performance_cost",
        "delivery_release",
        "maintainability",
    ]:
        complete, reason = review_is_complete(core.get(name))
        if not complete:
            blockers.append(f"Core review '{name}' is incomplete: {reason}.")

    profiles = review_coverage.get("profiles", {}) if isinstance(review_coverage, dict) else {}
    for name, active in characteristics.items():
        entry = profiles.get(name) if isinstance(profiles, dict) else None
        if active is True:
            complete, reason = review_is_complete(entry)
            if not complete:
                blockers.append(f"Activated profile '{name}' is incomplete: {reason}.")
        elif active is False and isinstance(entry, dict) and entry.get("status") not in {"not_activated", "not_applicable"}:
            warnings.append(f"Profile '{name}' is false but review status is {entry.get('status')!r}.")

    test_plan = task.get("test_plan", {})
    planned_tests = 0
    if isinstance(test_plan, dict):
        planned_tests = sum(len(value) for value in test_plan.values() if isinstance(value, list))
    if planned_tests == 0:
        blockers.append("Define a test plan with at least one concrete scenario.")

    required_checks = task.get("required_checks", [])
    if not nonempty_list(required_checks):
        blockers.append("Declare at least one required automated check.")
    else:
        commands = project.get("commands", {})
        for check in required_checks:
            if not nonempty_text(commands.get(check)):
                blockers.append(f"Required check '{check}' has no command in project.json.")

    approval = state.get("approvals", {}).get("ready_to_build", {})
    if approval.get("status") != "approved":
        blockers.append("Human approval for ready_to_build is pending.")

    return GateResult("ready_to_build", not blockers, blockers, warnings)


def unresolved_high_findings(items: Iterable[Any], label: str) -> list[str]:
    blockers: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        severity = str(item.get("severity", "")).lower()
        status = str(item.get("status", "open")).lower()
        if severity in CRITICAL_SEVERITIES and status not in {"resolved", "accepted_risk", "closed", "addressed", "tested"}:
            blockers.append(f"{label} {item.get('id', '<unknown>')} is {severity} and {status}.")
        if severity in CRITICAL_SEVERITIES and status == "accepted_risk" and not nonempty_text(item.get("rationale")):
            blockers.append(f"Accepted {severity} {label.lower()} {item.get('id', '<unknown>')} needs a rationale.")
    return blockers


def evaluate_verification(repo: Path, project: dict[str, Any], state: dict[str, Any], task: dict[str, Any]) -> GateResult:
    blockers: list[str] = []
    warnings: list[str] = []
    ready_result = evaluate_ready_to_build(repo, project, state, task)
    ready_snapshot_issue = gate_snapshot_issue(state, "ready_to_build")
    if ready_snapshot_issue:
        blockers.append(ready_snapshot_issue)
    if not ready_result.passed:
        blockers.extend(f"Ready-to-build contract is no longer valid: {item}" for item in ready_result.blockers)

    if task.get("status") not in {"verifying", "ready_for_release", "deployed", "completed"}:
        blockers.append("Set task status to 'verifying' before evaluating verification.")

    criteria = task.get("acceptance_criteria", [])
    for criterion in criteria:
        if not isinstance(criterion, dict):
            blockers.append("An acceptance criterion is malformed.")
            continue
        status = criterion.get("status")
        if status == "passed":
            evidence_items = criterion.get("evidence")
            if not nonempty_list(evidence_items):
                blockers.append(f"Criterion {criterion.get('id', '<unknown>')} passed without evidence.")
            else:
                for evidence_item in evidence_items:
                    if not isinstance(evidence_item, str) or not evidence_item.strip():
                        blockers.append(f"Criterion {criterion.get('id', '<unknown>')} has malformed evidence.")
                        continue
                    normalized = evidence_item.strip()
                    if normalized.startswith(("http://", "https://", "manual:", "external:", "check:")):
                        continue
                    if not (repo / normalized).exists():
                        blockers.append(
                            f"Criterion {criterion.get('id', '<unknown>')} evidence path does not exist: {normalized}."
                        )
        elif status == "waived":
            if not nonempty_text(criterion.get("waiver_reason")):
                blockers.append(f"Criterion {criterion.get('id', '<unknown>')} waiver lacks a reason.")
        else:
            blockers.append(f"Criterion {criterion.get('id', '<unknown>')} is {status or 'unverified'}.")

    active_task_id = state.get("active_task")
    if not nonempty_text(active_task_id):
        blockers.append("No active task is available for automated evidence evaluation.")
        active_task_id = "<missing>"
    latest = latest_check_evidence(repo, active_task_id)
    current_git = git_info(repo)
    for check in task.get("required_checks", []):
        item = latest.get(check)
        if not item:
            blockers.append(f"Required check '{check}' has no evidence for active task {active_task_id}.")
            continue
        current, reason = check_evidence_current(item, current_git, active_task_id)
        if not current:
            blockers.append(f"Required check '{check}' is not current: {reason}.")

    review = task.get("independent_review", {})
    status = review.get("status") if isinstance(review, dict) else None
    if status == "passed":
        if not nonempty_text(review.get("reviewer")):
            blockers.append("Independent review passed without a reviewer identity.")
    elif status == "waived":
        if not nonempty_text(review.get("waiver_reason")):
            blockers.append("Independent-review waiver lacks a reason.")
    else:
        blockers.append("Independent review has not passed or been explicitly waived.")
    if isinstance(review, dict):
        blockers.extend(unresolved_high_findings(review.get("findings", []), "Review finding"))

    blockers.extend(unresolved_high_findings(task.get("failure_modes", []), "Failure mode"))
    blockers.extend(unresolved_high_findings(task.get("known_issues", []), "Known issue"))

    return GateResult("verification", not blockers, blockers, warnings)


def evaluate_ready_to_release(repo: Path, project: dict[str, Any], state: dict[str, Any], task: dict[str, Any]) -> GateResult:
    blockers: list[str] = []
    warnings: list[str] = []
    verification_result = evaluate_verification(repo, project, state, task)
    verification_snapshot_issue = gate_snapshot_issue(state, "verification")
    if verification_snapshot_issue:
        blockers.append(verification_snapshot_issue)
    if not verification_result.passed:
        blockers.extend(f"Verification is no longer valid: {item}" for item in verification_result.blockers)
    if task.get("status") not in {"ready_for_release", "deployed", "completed"}:
        blockers.append("Set task status to 'ready_for_release' after verification.")

    release = task.get("release_plan", {})
    for field in ["deployment_steps", "rollback_steps", "smoke_tests", "monitoring", "ownership"]:
        if not nonempty_list(release.get(field) if isinstance(release, dict) else None):
            blockers.append(f"Release plan needs {field.replace('_', ' ')}.")

    characteristics = project.get("characteristics", {})
    if characteristics.get("schema_change") and not nonempty_list(release.get("migration")):
        blockers.append("Schema-change profile requires migration and ordering details.")
    if characteristics.get("new_service") and not nonempty_list(release.get("configuration")):
        blockers.append("New-service profile requires runtime configuration details.")

    approval = state.get("approvals", {}).get("ready_to_release", {})
    if approval.get("status") != "approved":
        blockers.append("Human approval for ready_to_release is pending.")

    return GateResult("ready_to_release", not blockers, blockers, warnings)


def evaluate_close(repo: Path, project: dict[str, Any], state: dict[str, Any], task: dict[str, Any]) -> GateResult:
    blockers: list[str] = []
    warnings: list[str] = []
    # Closeout artifacts are commonly written after deployment, so do not bind
    # this gate to the current HEAD. Trust the recorded release gate and verify
    # the deployed artifact through deployment and live evidence instead.
    release_snapshot_issue = gate_snapshot_issue(state, "ready_to_release")
    if release_snapshot_issue:
        blockers.append(release_snapshot_issue)

    deployment = state.get("deployment", {})
    if deployment.get("status") != "succeeded":
        blockers.append("Deployment is not recorded as succeeded.")
    if not nonempty_text(deployment.get("environment")):
        blockers.append("Deployment environment is missing.")
    if git_info(repo).get("is_git") and not nonempty_text(deployment.get("commit")):
        blockers.append("Deployment commit is missing.")
    if not nonempty_list(deployment.get("evidence")):
        blockers.append("Deployment has no evidence.")

    live = state.get("live_validation", {})
    if live.get("status") != "passed":
        blockers.append("Live validation has not passed.")
    if not nonempty_list(live.get("evidence")):
        blockers.append("Live validation has no evidence.")

    if task.get("status") != "completed":
        blockers.append("Set task status to 'completed' after live validation and handoff.")

    blockers.extend(unresolved_high_findings(task.get("known_issues", []), "Known issue"))
    for issue in task.get("known_issues", []):
        if not isinstance(issue, dict):
            continue
        severity = str(issue.get("severity", "low")).lower()
        status = str(issue.get("status", "open")).lower()
        if severity in {"medium", "high", "critical"} and status not in {"resolved", "closed"}:
            if not nonempty_text(issue.get("owner")):
                blockers.append(f"Known issue {issue.get('id', '<unknown>')} needs an owner.")
            if not nonempty_text(issue.get("follow_up")):
                blockers.append(f"Known issue {issue.get('id', '<unknown>')} needs a follow-up action.")

    handoff_relative = project.get("paths", {}).get("handoff")
    if not nonempty_text(handoff_relative):
        blockers.append("Project handoff path is not configured.")
    else:
        handoff = repo / handoff_relative
        if not handoff.exists() or not handoff.read_text(encoding="utf-8", errors="replace").strip():
            blockers.append(f"Handoff is missing or empty: {handoff_relative}.")

    return GateResult("close", not blockers, blockers, warnings)


def evaluate_gate(repo: Path, gate: str) -> GateResult:
    project, state = load_project_state(repo)
    _, task = load_active_task(repo, state)
    if gate == "ready_to_build":
        return evaluate_ready_to_build(repo, project, state, task)
    if gate == "verification":
        return evaluate_verification(repo, project, state, task)
    if gate == "ready_to_release":
        return evaluate_ready_to_release(repo, project, state, task)
    if gate == "close":
        return evaluate_close(repo, project, state, task)
    raise HaruspexError(f"Unsupported gate: {gate}")


def record_gate(repo: Path, result: GateResult) -> None:
    _, state = load_project_state(repo)
    task_path, task = load_active_task(repo, state)
    entry = state.setdefault("gates", {}).setdefault(result.gate, {})
    entry["status"] = "passed" if result.passed else "blocked"
    entry["checked_at"] = now_utc()
    entry["blockers"] = result.blockers
    entry["evidence"] = entry.get("evidence", [])
    entry["task"] = state.get("active_task")
    entry["git"] = git_info(repo)
    if result.passed:
        state["stage"] = GATE_NEXT_STAGE[result.gate]
        state["status"] = "closed" if result.gate == "close" else "active"
        if result.gate == "ready_to_build" and task.get("status") == "ready":
            task["status"] = "in_progress"
        elif result.gate == "verification":
            task["status"] = "ready_for_release"
        task["updated_at"] = now_utc()
        write_json(task_path, task)
    else:
        state["status"] = "blocked"
    update_state_metadata(state, "haruspex")
    write_json(repo / ".haruspex" / "state.json", state)


def command_gate(args: argparse.Namespace) -> int:
    repo = resolve_repo(args.path)
    gate = normalize_gate(args.gate)
    result = evaluate_gate(repo, gate)
    if args.record:
        record_gate(repo, result)
    if args.json:
        print(json.dumps(result.as_dict(), indent=2))
    else:
        print(f"HARUSPEX GATE — {gate}")
        print("PASSED" if result.passed else "BLOCKED")
        if result.blockers:
            print("\nBlockers:")
            for blocker in result.blockers:
                print(f"  - {blocker}")
        if result.warnings:
            print("\nWarnings:")
            for warning in result.warnings:
                print(f"  - {warning}")
        if args.record:
            print("\nRecorded gate result in .haruspex/state.json.")
    return 0 if result.passed else 1


def command_approve(args: argparse.Namespace) -> int:
    repo = resolve_repo(args.path)
    gate = normalize_gate(args.gate)
    if gate not in HUMAN_GATES:
        raise HaruspexError(f"Gate '{gate}' is not configured as a human approval gate.")
    _, state = load_project_state(repo)
    if gate == "ready_to_release" and not args.revoke:
        if state.get("gates", {}).get("verification", {}).get("status") != "passed":
            raise HaruspexError("Cannot approve ready_to_release before the verification gate passes.")
    entry = state.setdefault("approvals", {}).setdefault(gate, {})
    if args.revoke:
        entry.update({"status": "pending", "by": args.by, "at": now_utc(), "note": args.note or "approval revoked"})
        print(f"Revoked approval for {gate}.")
    else:
        entry.update({"status": "approved", "by": args.by, "at": now_utc(), "note": args.note})
        print(f"Recorded explicit human approval for {gate} by {args.by}.")
    update_state_metadata(state, args.by)
    write_json(repo / ".haruspex" / "state.json", state)
    return 0


def evidence_file_base(repo: Path, check_name: str) -> Path:
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", check_name).strip("-") or "check"
    return repo / ".haruspex" / "evidence" / "checks" / f"{safe_timestamp()}-{safe_name}"


def run_configured_check(repo: Path, check_name: str, timeout: int | None = None) -> tuple[int, dict[str, Any]]:
    project, state = load_project_state(repo)
    command = project.get("commands", {}).get(check_name)
    if not nonempty_text(command):
        raise HaruspexError(f"No command configured for check '{check_name}' in .haruspex/project.json")
    task_id = state.get("active_task")
    timeout_seconds = timeout or int(project.get("check_timeout_seconds", 900))
    started = now_utc()
    before = git_info(repo)
    base = evidence_file_base(repo, check_name)
    base.parent.mkdir(parents=True, exist_ok=True)
    log_path = Path(str(base) + ".log")
    evidence_path = Path(str(base) + ".json")

    environment = os.environ.copy()
    if task_id:
        environment["HARUSPEX_TASK_ID"] = str(task_id)
    environment["HARUSPEX_EVIDENCE_DIR"] = str(base.parent)

    timed_out = False
    try:
        completed = subprocess.run(
            command,
            cwd=repo,
            shell=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout_seconds,
            env=environment,
            check=False,
        )
        exit_code = completed.returncode
        output = completed.stdout or ""
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        exit_code = 124
        partial = exc.stdout or ""
        if isinstance(partial, bytes):
            partial = partial.decode("utf-8", errors="replace")
        output = str(partial) + f"\nHaruspex terminated the check after {timeout_seconds} seconds.\n"

    log_path.write_text(output, encoding="utf-8")
    after = git_info(repo)
    completed_at = now_utc()
    status = "passed" if exit_code == 0 else ("timed_out" if timed_out else "failed")
    evidence = {
        "schema_version": 1,
        "check": check_name,
        "command": command,
        "task": task_id,
        "repo": str(repo),
        "started_at": started,
        "completed_at": completed_at,
        "timeout_seconds": timeout_seconds,
        "exit_code": exit_code,
        "status": status,
        "git_before": before,
        "git_after": after,
        "log": str(log_path.relative_to(repo)),
    }
    write_json(evidence_path, evidence)
    if output:
        print(output, end="" if output.endswith("\n") else "\n")
    print(f"[{status}] {check_name} — evidence: {evidence_path.relative_to(repo)}")
    return exit_code, evidence


def command_check(args: argparse.Namespace) -> int:
    repo = resolve_repo(args.path)
    exit_code, _ = run_configured_check(repo, args.name, args.timeout)
    return exit_code


def command_verify(args: argparse.Namespace) -> int:
    repo = resolve_repo(args.path)
    _, state = load_project_state(repo)
    _, task = load_active_task(repo, state)
    checks = task.get("required_checks", [])
    if not nonempty_list(checks):
        raise HaruspexError("The active task has no required_checks.")
    failures = 0
    for check in checks:
        try:
            exit_code, _ = run_configured_check(repo, str(check), args.timeout)
        except HaruspexError as exc:
            print(f"[blocked] {check} — {exc}", file=sys.stderr)
            exit_code = 2
        if exit_code != 0:
            failures += 1
            if args.fail_fast:
                break
    if failures:
        print(f"Verification checks completed with {failures} failure(s).")
        return 1
    print("All configured automated checks passed for the current worktree.")
    print("Next: attach evidence to acceptance criteria, complete independent review, then run the verification gate.")
    return 0


def command_record_deployment(args: argparse.Namespace) -> int:
    repo = resolve_repo(args.path)
    _, state = load_project_state(repo)
    release_issue = gate_snapshot_issue(state, "ready_to_release")
    if release_issue:
        raise HaruspexError(release_issue)
    release_gate = state["gates"]["ready_to_release"]
    release_git = release_gate["git"]
    git = git_info(repo)
    deployment_commit = args.commit or git.get("commit")
    if release_git.get("is_git"):
        release_commit = release_git.get("commit")
        if not nonempty_text(release_commit):
            raise HaruspexError(
                "ready_to_release was recorded without a Git commit. Rerun the gate with the current Haruspex version."
            )
        if not git.get("is_git"):
            raise HaruspexError("The current repository is not the Git worktree that passed ready_to_release.")
        if not nonempty_text(deployment_commit):
            raise HaruspexError("A Git deployment must identify the deployed commit.")
        if deployment_commit != release_commit:
            raise HaruspexError(
                f"Deployment commit {deployment_commit} does not match ready_to_release commit {release_commit}."
            )
        if git.get("commit") != release_commit:
            raise HaruspexError(
                f"Current Git commit {git.get('commit')} does not match ready_to_release commit {release_commit}."
            )
        if git.get("worktree_fingerprint") != release_git.get("worktree_fingerprint"):
            raise HaruspexError(
                "The working tree changed after ready_to_release passed. Rerun verification and ready_to_release."
            )
    evidence = list(args.evidence or [])
    deployment = state.setdefault("deployment", {})
    deployment.update({
        "status": args.status,
        "environment": args.environment,
        "commit": deployment_commit,
        "task": state.get("active_task"),
        "at": now_utc(),
        "by": args.by,
        "evidence": evidence,
        "note": args.note,
    })
    if args.status == "succeeded":
        state["stage"] = "live_validation"
        state["status"] = "active"
    elif args.status == "failed":
        state["status"] = "blocked"
    update_state_metadata(state, args.by)
    write_json(repo / ".haruspex" / "state.json", state)
    print(f"Recorded deployment status {args.status} for {args.environment}.")
    return 0


def command_record_live(args: argparse.Namespace) -> int:
    repo = resolve_repo(args.path)
    _, state = load_project_state(repo)
    if state.get("deployment", {}).get("status") != "succeeded":
        raise HaruspexError("Cannot record live validation before a successful deployment is recorded.")
    live = state.setdefault("live_validation", {})
    live.update({
        "status": args.status,
        "at": now_utc(),
        "by": args.by,
        "evidence": list(args.evidence or []),
        "note": args.note,
    })
    state["stage"] = "live_validation"
    state["status"] = "active" if args.status == "passed" else "blocked"
    update_state_metadata(state, args.by)
    write_json(repo / ".haruspex" / "state.json", state)
    print(f"Recorded live validation status {args.status}.")
    return 0


def command_reopen(args: argparse.Namespace) -> int:
    repo = resolve_repo(args.path)
    stage = args.stage
    if stage not in STAGE_INDEX or stage == "closed":
        raise HaruspexError("Reopen stage must be one of discovery through live_validation.")
    _, state = load_project_state(repo)
    target_index = STAGE_INDEX[stage]

    gate_stage = {
        "ready_to_build": STAGE_INDEX["build"],
        "verification": STAGE_INDEX["ready_to_release"],
        "ready_to_release": STAGE_INDEX["deployment"],
        "close": STAGE_INDEX["closed"],
    }
    for gate, pass_index in gate_stage.items():
        if pass_index > target_index:
            reset_gate_entry(state.setdefault("gates", {}).setdefault(gate, {}))

    if target_index <= STAGE_INDEX["specification"]:
        for approval in state.get("approvals", {}).values():
            approval.update({"status": "pending", "by": None, "at": None, "note": None})
    elif target_index <= STAGE_INDEX["ready_to_release"]:
        release_approval = state.get("approvals", {}).get("ready_to_release")
        if isinstance(release_approval, dict):
            release_approval.update({"status": "pending", "by": None, "at": None, "note": None})

    state["stage"] = stage
    state["status"] = "active"
    state.setdefault("reopen_history", []).append({
        "stage": stage,
        "reason": args.reason,
        "by": args.by,
        "at": now_utc(),
    })
    update_state_metadata(state, args.by)
    write_json(repo / ".haruspex" / "state.json", state)
    print(f"Reopened project at {stage}: {args.reason}")
    return 0


def command_ci(args: argparse.Namespace) -> int:
    repo = resolve_repo(args.path)
    errors, warnings = basic_structure_checks(repo)
    if errors:
        print("Haruspex structural errors:")
        for item in errors:
            print(f"  - {item}")
        return 1
    for warning in warnings:
        print(f"warning: {warning}")

    _, state = load_project_state(repo)
    stage = state.get("stage")
    if stage not in STAGE_INDEX:
        print(f"Unknown stage: {stage}")
        return 1
    required: list[str] = []
    if stage in {"build", "verification"}:
        required.append("ready_to_build")
    elif stage == "ready_to_release":
        required.append("verification")
    elif stage in {"deployment", "live_validation"}:
        required.append("ready_to_release")
    elif stage == "closed":
        required.append("close")

    failed = False
    for gate in required:
        result = evaluate_gate(repo, gate)
        print(f"{gate}: {'passed' if result.passed else 'blocked'}")
        for blocker in result.blockers:
            print(f"  - {blocker}")
        failed = failed or not result.passed
    if not required:
        print("No progressed-stage gates require enforcement yet.")
    return 1 if failed else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="haruspex",
        description="Diagnose project blind spots and enforce evidence-backed delivery gates.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Install the repo-local Haruspex harness.")
    init.add_argument("path", nargs="?", default=".")
    init.add_argument("--project-name")
    init.add_argument("--with-ci", action="store_true")
    init.add_argument("--force-managed", action="store_true")
    init.set_defaults(func=command_init)

    upgrade = sub.add_parser("upgrade", help="Refresh managed files and the repo-local CLI.")
    upgrade.add_argument("path", nargs="?", default=".")
    upgrade.add_argument("--project-name")
    upgrade.add_argument("--with-ci", action="store_true")
    upgrade.set_defaults(func=command_upgrade)

    doctor = sub.add_parser("doctor", help="Validate harness structure and configuration.")
    doctor.add_argument("path", nargs="?", default=".")
    doctor.add_argument("--strict", action="store_true")
    doctor.add_argument("--json", action="store_true")
    doctor.set_defaults(func=command_doctor)

    status = sub.add_parser("status", help="Show project, task, gate, and deployment state.")
    status.add_argument("path", nargs="?", default=".")
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=command_status)

    task = sub.add_parser("task", help="Create, activate, list, or show tasks.")
    task_sub = task.add_subparsers(dest="task_command", required=True)
    task_create = task_sub.add_parser("create")
    task_create.add_argument("title")
    task_create.add_argument("path", nargs="?", default=".")
    task_create.add_argument("--id")
    task_create.add_argument("--force", action="store_true")
    task_create.set_defaults(func=command_task_create)
    task_activate = task_sub.add_parser("activate")
    task_activate.add_argument("id")
    task_activate.add_argument("path", nargs="?", default=".")
    task_activate.set_defaults(func=command_task_activate)
    task_list = task_sub.add_parser("list")
    task_list.add_argument("path", nargs="?", default=".")
    task_list.add_argument("--json", action="store_true")
    task_list.set_defaults(func=command_task_list)
    task_show = task_sub.add_parser("show")
    task_show.add_argument("id", nargs="?")
    task_show.add_argument("path", nargs="?", default=".")
    task_show.set_defaults(func=command_task_show)

    gate = sub.add_parser("gate", help="Evaluate a delivery gate.")
    gate.add_argument("gate", choices=sorted(GATE_ALIASES))
    gate.add_argument("path", nargs="?", default=".")
    gate.add_argument("--record", action="store_true")
    gate.add_argument("--json", action="store_true")
    gate.set_defaults(func=command_gate)

    approve = sub.add_parser("approve", help="Record explicit human approval for a human-controlled gate.")
    approve.add_argument("gate", choices=["ready-to-build", "ready-to-release", "ready_to_build", "ready_to_release"])
    approve.add_argument("path", nargs="?", default=".")
    approve.add_argument("--by", required=True)
    approve.add_argument("--note")
    approve.add_argument("--revoke", action="store_true")
    approve.set_defaults(func=command_approve)

    check = sub.add_parser("check", help="Run one configured check and record evidence.")
    check.add_argument("name")
    check.add_argument("path", nargs="?", default=".")
    check.add_argument("--timeout", type=int)
    check.set_defaults(func=command_check)

    verify = sub.add_parser("verify", help="Run every required check for the active task.")
    verify.add_argument("path", nargs="?", default=".")
    verify.add_argument("--timeout", type=int)
    verify.add_argument("--fail-fast", action="store_true")
    verify.set_defaults(func=command_verify)

    record = sub.add_parser("record", help="Record deployment or live-validation evidence.")
    record_sub = record.add_subparsers(dest="record_command", required=True)
    deployment = record_sub.add_parser("deployment")
    deployment.add_argument("status", choices=["succeeded", "failed", "rolled_back"])
    deployment.add_argument("environment")
    deployment.add_argument("path", nargs="?", default=".")
    deployment.add_argument("--commit")
    deployment.add_argument("--by", required=True)
    deployment.add_argument("--evidence", action="append")
    deployment.add_argument("--note")
    deployment.set_defaults(func=command_record_deployment)
    live = record_sub.add_parser("live")
    live.add_argument("status", choices=["passed", "failed"])
    live.add_argument("path", nargs="?", default=".")
    live.add_argument("--by", required=True)
    live.add_argument("--evidence", action="append")
    live.add_argument("--note")
    live.set_defaults(func=command_record_live)

    reopen = sub.add_parser("reopen", help="Move backward and invalidate downstream gates.")
    reopen.add_argument("stage", choices=STAGES[:-1])
    reopen.add_argument("path", nargs="?", default=".")
    reopen.add_argument("--reason", required=True)
    reopen.add_argument("--by", required=True)
    reopen.set_defaults(func=command_reopen)

    ci = sub.add_parser("ci", help="Validate all gates implied by the current stage.")
    ci.add_argument("path", nargs="?", default=".")
    ci.set_defaults(func=command_ci)

    version = sub.add_parser("version", help="Print the Haruspex version.")
    version.set_defaults(func=lambda _args: print(HARUSPEX_VERSION) or 0)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except HaruspexError as exc:
        print(f"haruspex: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("haruspex: interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
