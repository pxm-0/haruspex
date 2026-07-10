#!/usr/bin/env python3
"""Regression tests for Haruspex task, evidence, and release integrity."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CLI = Path(__file__).resolve().with_name("haruspex.py")
SPEC = importlib.util.spec_from_file_location("haruspex_cli", CLI)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Could not load the Haruspex CLI module")
HARUSPEX = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = HARUSPEX
SPEC.loader.exec_module(HARUSPEX)


def run(*args: str, expect: int = 0) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        [sys.executable, str(CLI), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if completed.returncode != expect:
        raise AssertionError(
            f"command returned {completed.returncode}, expected {expect}: {args}\n{completed.stdout}"
        )
    return completed


def git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed:\n{completed.stdout}")
    return completed.stdout.strip()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


class IntegrityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directories: list[tempfile.TemporaryDirectory[str]] = []

    def tearDown(self) -> None:
        for temporary in self.temporary_directories:
            temporary.cleanup()

    def make_repo(self, *, use_git: bool = True) -> Path:
        temporary = tempfile.TemporaryDirectory(prefix="haruspex-integrity-")
        self.temporary_directories.append(temporary)
        repo = Path(temporary.name)

        if use_git:
            git(repo, "init", "-q")
            git(repo, "config", "user.email", "haruspex@example.invalid")
            git(repo, "config", "user.name", "Haruspex Integrity Test")
            (repo / "README.md").write_text("# Fixture\n", encoding="utf-8")
            git(repo, "add", "README.md")
            git(repo, "commit", "-qm", "initial fixture")

        run("init", str(repo))
        project_path = repo / ".haruspex" / "project.json"
        project = read_json(project_path)
        project["project"]["risk"] = "medium"
        for characteristic in project["characteristics"]:
            project["characteristics"][characteristic] = False
        project["commands"]["unit_test"] = f'{sys.executable} -c "print(\'integrity check passed\')"'
        write_json(project_path, project)

        if use_git:
            git(repo, "add", "AGENTS.md", "CLAUDE.md")
            git(repo, "commit", "-qm", "add Haruspex bootstrap instructions")

        self.create_task(repo, "TASK-A")
        return repo

    def create_task(self, repo: Path, task_id: str) -> Path:
        run("task", "create", f"Integrity fixture {task_id}", str(repo), "--id", task_id)
        task_path = repo / ".haruspex" / "tasks" / f"{task_id}.json"
        task = read_json(task_path)
        task["status"] = "ready"
        task["risk"] = "medium"
        task["problem"] = {
            "summary": "Integrity evidence must not cross task or Git boundaries.",
            "affected_actors": ["release operator"],
            "current_behavior": "The fixture has not yet passed its gates.",
            "desired_outcome": "Only current task-bound evidence authorizes release.",
            "success_metrics": ["Every configured integrity gate behaves as expected."],
        }
        task["scope"] = {
            "included": ["Exercise evidence and release integrity."],
            "excluded": ["External services."],
        }
        task["acceptance_criteria"] = [
            {
                "id": "AC-001",
                "criterion": "The integrity lifecycle is enforced.",
                "status": "unverified",
                "evidence": [],
            }
        ]
        task["failure_modes"] = [
            {
                "id": "FM-001",
                "scenario": "Stale or cross-task evidence authorizes a release.",
                "severity": "high",
                "status": "tested",
                "evidence": ["scripts/integrity_test.py"],
            }
        ]
        task["test_plan"]["unit"] = ["Run the configured unit_test command."]
        task["test_plan"]["negative_and_recovery"] = ["Reject stale evidence, then rerun the check."]
        task["required_checks"] = ["unit_test"]
        for entry in task["review_coverage"]["core"].values():
            entry.update(
                {"status": "complete", "rationale": "Covered by the integrity fixture.", "evidence": ["test"]}
            )
        for entry in task["review_coverage"]["profiles"].values():
            entry.update({"status": "not_activated", "rationale": "", "evidence": []})
        task["release_plan"] = {
            "deployment_steps": ["Record the fixture deployment."],
            "rollback_steps": ["Record a rollback if needed."],
            "smoke_tests": ["Run the fixture command."],
            "monitoring": ["Inspect command status."],
            "configuration": ["No external configuration."],
            "migration": ["No migration."],
            "ownership": ["Integrity test owner."],
        }
        write_json(task_path, task)
        return task_path

    def pass_ready_to_build(self, repo: Path) -> None:
        run("approve", "ready-to-build", str(repo), "--by", "Integrity Test")
        run("gate", "ready-to-build", str(repo), "--record")

    def mark_verifiable(self, repo: Path, task_id: str) -> None:
        task_path = repo / ".haruspex" / "tasks" / f"{task_id}.json"
        task = read_json(task_path)
        task["status"] = "verifying"
        task["acceptance_criteria"][0].update({"status": "passed", "evidence": ["check:unit_test"]})
        task["independent_review"] = {
            "status": "passed",
            "reviewer": "Integrity Test Reviewer",
            "at": "fixture",
            "findings": [],
            "waiver_reason": None,
        }
        write_json(task_path, task)

    def pass_ready_to_release(self, repo: Path, task_id: str = "TASK-A") -> None:
        self.pass_ready_to_build(repo)
        self.mark_verifiable(repo, task_id)
        run("check", "unit_test", str(repo))
        run("gate", "verification", str(repo), "--record")
        run("approve", "ready-to-release", str(repo), "--by", "Integrity Test")
        run("gate", "ready-to-release", str(repo), "--record")

    def record_deployment(self, repo: Path, *extra: str, expect: int = 0) -> subprocess.CompletedProcess[str]:
        return run(
            "record",
            "deployment",
            "succeeded",
            "test",
            str(repo),
            "--by",
            "Integrity Test",
            "--evidence",
            "fixture deployment",
            *extra,
            expect=expect,
        )

    def test_cross_task_evidence_is_rejected(self) -> None:
        repo = self.make_repo()
        self.pass_ready_to_build(repo)
        self.mark_verifiable(repo, "TASK-A")
        run("check", "unit_test", str(repo))

        self.create_task(repo, "TASK-B")
        self.pass_ready_to_build(repo)
        self.mark_verifiable(repo, "TASK-B")
        blocked = run("gate", "verification", str(repo), expect=1)
        self.assertIn("Required check 'unit_test' has no evidence for active task TASK-B.", blocked.stdout)

        run("check", "unit_test", str(repo))
        run("gate", "verification", str(repo))

    def test_deployment_rejects_post_gate_commit_and_recovers(self) -> None:
        repo = self.make_repo()
        self.pass_ready_to_release(repo)
        release_commit = git(repo, "rev-parse", "HEAD")

        (repo / "README.md").write_text("# Fixture\n\npost-gate change\n", encoding="utf-8")
        git(repo, "add", "README.md")
        git(repo, "commit", "-qm", "post-gate change")
        current_commit = git(repo, "rev-parse", "HEAD")
        blocked = self.record_deployment(repo, expect=2)
        self.assertIn(current_commit, blocked.stdout)
        self.assertIn(release_commit, blocked.stdout)

        run("check", "unit_test", str(repo))
        run("gate", "verification", str(repo), "--record")
        run("gate", "ready-to-release", str(repo), "--record")
        self.record_deployment(repo)

    def test_explicit_commit_cannot_bypass_release_binding(self) -> None:
        repo = self.make_repo()
        self.pass_ready_to_release(repo)
        release_commit = git(repo, "rev-parse", "HEAD")

        (repo / "README.md").write_text("# Fixture\n\nnew release candidate\n", encoding="utf-8")
        git(repo, "add", "README.md")
        git(repo, "commit", "-qm", "new release candidate")
        current_commit = git(repo, "rev-parse", "HEAD")

        wrong_commit = self.record_deployment(repo, "--commit", current_commit, expect=2)
        self.assertIn("does not match ready_to_release commit", wrong_commit.stdout)
        stale_worktree = self.record_deployment(repo, "--commit", release_commit, expect=2)
        self.assertIn("Current Git commit", stale_worktree.stdout)

    def test_untracked_directory_contents_invalidate_evidence(self) -> None:
        repo = self.make_repo()
        self.pass_ready_to_build(repo)
        self.mark_verifiable(repo, "TASK-A")
        untracked = repo / "generated" / "result.txt"
        untracked.parent.mkdir()
        untracked.write_text("first\n", encoding="utf-8")
        run("check", "unit_test", str(repo))
        first_fingerprint = HARUSPEX.git_info(repo)["worktree_fingerprint"]

        untracked.write_text("second\n", encoding="utf-8")
        self.assertNotEqual(first_fingerprint, HARUSPEX.git_info(repo)["worktree_fingerprint"])
        blocked = run("gate", "verification", str(repo), expect=1)
        self.assertIn("working tree changed after evidence was generated", blocked.stdout)

        run("check", "unit_test", str(repo))
        run("gate", "verification", str(repo))

    def test_haruspex_metadata_is_excluded_from_fingerprint(self) -> None:
        repo = self.make_repo()
        self.pass_ready_to_build(repo)
        self.mark_verifiable(repo, "TASK-A")
        run("check", "unit_test", str(repo))
        first_fingerprint = HARUSPEX.git_info(repo)["worktree_fingerprint"]

        metadata = repo / ".haruspex" / "evidence" / "metadata-change.txt"
        metadata.write_text("control-plane update\n", encoding="utf-8")
        self.assertEqual(first_fingerprint, HARUSPEX.git_info(repo)["worktree_fingerprint"])
        run("gate", "verification", str(repo))

    def test_gate_snapshots_are_task_bound_and_legacy_safe(self) -> None:
        repo = self.make_repo()
        self.pass_ready_to_release(repo)
        state_path = repo / ".haruspex" / "state.json"
        state = read_json(state_path)
        release_gate = state["gates"]["ready_to_release"]
        self.assertEqual("TASK-A", release_gate["task"])
        self.assertEqual(
            {"is_git", "branch", "commit", "dirty", "worktree_fingerprint", "checked_at"},
            set(release_gate["git"]),
        )

        state["active_task"] = "TASK-B"
        write_json(state_path, state)
        wrong_task = self.record_deployment(repo, expect=2)
        self.assertIn("ready_to_release passed for task TASK-A, but the active task is TASK-B", wrong_task.stdout)

        state["active_task"] = "TASK-A"
        release_gate.pop("task")
        release_gate.pop("git")
        write_json(state_path, state)
        legacy = self.record_deployment(repo, expect=2)
        self.assertIn(
            "ready_to_release was recorded without a task and Git snapshot. "
            "Rerun the gate with the current Haruspex version.",
            legacy.stdout,
        )

    def test_non_git_deployment_preserves_task_binding_without_commit(self) -> None:
        repo = self.make_repo(use_git=False)
        self.pass_ready_to_release(repo)
        state = read_json(repo / ".haruspex" / "state.json")
        release_gate = state["gates"]["ready_to_release"]
        self.assertEqual("TASK-A", release_gate["task"])
        self.assertFalse(release_gate["git"]["is_git"])

        self.record_deployment(repo)
        state = read_json(repo / ".haruspex" / "state.json")
        self.assertEqual("TASK-A", state["deployment"]["task"])
        self.assertIsNone(state["deployment"]["commit"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
