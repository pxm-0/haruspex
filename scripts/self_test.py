#!/usr/bin/env python3
"""End-to-end self-test for the Haruspex standard-library CLI."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

CLI = Path(__file__).resolve().with_name("haruspex.py")


def run(*args: str, cwd: Path | None = None, expect: int = 0) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        [sys.executable, str(CLI), *args],
        cwd=cwd,
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


def git(repo: Path, *args: str) -> None:
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


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="haruspex-self-test-") as temp:
        repo = Path(temp)
        git(repo, "init", "-q")
        git(repo, "config", "user.email", "haruspex@example.invalid")
        git(repo, "config", "user.name", "Haruspex Self Test")
        (repo / "README.md").write_text("# Fixture\n", encoding="utf-8")
        git(repo, "add", "README.md")
        git(repo, "commit", "-qm", "initial fixture")

        run("init", str(repo), "--with-ci")
        run("doctor", str(repo))
        run("task", "create", "Exercise full lifecycle", str(repo), "--id", "TASK-001")

        project_path = repo / ".haruspex" / "project.json"
        project = read_json(project_path)
        project["project"]["risk"] = "medium"
        for key in project["characteristics"]:
            project["characteristics"][key] = False
        project["characteristics"]["user_facing"] = True
        project["commands"]["unit_test"] = f'{sys.executable} -c "print(\'self-test check passed\')"'
        write_json(project_path, project)

        task_path = repo / ".haruspex" / "tasks" / "TASK-001.json"
        task = read_json(task_path)
        task["status"] = "ready"
        task["risk"] = "medium"
        task["problem"] = {
            "summary": "The fixture needs an evidence-backed delivery lifecycle.",
            "affected_actors": ["developer"],
            "current_behavior": "No durable gate state exists.",
            "desired_outcome": "The lifecycle passes only with current evidence.",
            "success_metrics": ["All four gates pass in the self-test."],
        }
        task["scope"] = {
            "included": ["Exercise initialization, checks, gates, deployment, and closeout."],
            "excluded": ["External services and network access."],
        }
        task["acceptance_criteria"] = [
            {
                "id": "AC-001",
                "criterion": "The full lifecycle can be completed with recorded evidence.",
                "status": "unverified",
                "evidence": [],
            }
        ]
        task["assumptions"] = [
            {
                "id": "ASM-001",
                "statement": "Python and Git are available.",
                "basis": "The self-test is currently running them.",
                "impact_if_false": "The local harness cannot operate.",
                "status": "validated",
                "blocking": True,
                "resolution": "Validated by process execution.",
                "evidence": ["self-test runtime"],
            }
        ]
        task["failure_modes"] = [
            {
                "id": "FM-001",
                "scenario": "Source changes after a passing check make the evidence stale.",
                "severity": "high",
                "status": "tested",
                "evidence": ["self-test stale-evidence branch"],
            }
        ]
        task["test_plan"]["unit"] = ["Run the configured unit_test command."]
        task["test_plan"]["negative_and_recovery"] = [
            "Change a source file after evidence and confirm verification blocks until reverted."
        ]
        task["required_checks"] = ["unit_test"]
        for entry in task["review_coverage"]["core"].values():
            entry.update({"status": "complete", "rationale": "Reviewed by self-test fixture.", "evidence": ["self-test"]})
        for key, entry in task["review_coverage"]["profiles"].items():
            if key == "user_facing":
                entry.update({"status": "complete", "rationale": "Fixture path reviewed.", "evidence": ["self-test"]})
            else:
                entry.update({"status": "not_activated", "rationale": "", "evidence": []})
        task["release_plan"] = {
            "deployment_steps": ["Record the fixture deployment."],
            "rollback_steps": ["Mark the fixture rolled back."],
            "smoke_tests": ["Run the lifecycle CLI."],
            "monitoring": ["Inspect command exit codes."],
            "configuration": ["No runtime configuration required."],
            "migration": ["No migration required."],
            "ownership": ["Haruspex self-test owns the fixture."],
        }
        write_json(task_path, task)

        docs = repo / "docs"
        docs.mkdir()
        (docs / "HANDOFF.md").write_text("# Handoff\n\nSelf-test fixture complete.\n", encoding="utf-8")

        # Approval is deliberately required.
        run("gate", "ready-to-build", str(repo), expect=1)
        run("approve", "ready-to-build", str(repo), "--by", "Haruspex Self Test")

        git(repo, "add", ".")
        git(repo, "commit", "-qm", "configure Haruspex fixture")

        run("gate", "ready-to-build", str(repo), "--record")

        task = read_json(task_path)
        task["status"] = "verifying"
        task["acceptance_criteria"][0]["status"] = "passed"
        task["acceptance_criteria"][0]["evidence"] = [".haruspex/evidence/checks/"]
        task["independent_review"] = {
            "status": "passed",
            "reviewer": "Haruspex Self Test Reviewer",
            "at": "fixture",
            "findings": [],
            "waiver_reason": None,
        }
        write_json(task_path, task)

        run("check", "unit_test", str(repo))

        # Prove source changes invalidate automated evidence.
        (repo / "README.md").write_text("# Fixture\n\nchanged after evidence\n", encoding="utf-8")
        run("gate", "verification", str(repo), expect=1)
        git(repo, "checkout", "--", "README.md")

        run("gate", "verification", str(repo), "--record")
        run("approve", "ready-to-release", str(repo), "--by", "Haruspex Self Test")
        run("gate", "ready-to-release", str(repo), "--record")
        run(
            "record",
            "deployment",
            "succeeded",
            "test",
            str(repo),
            "--by",
            "Haruspex Self Test",
            "--evidence",
            "self-test deployment record",
        )
        run(
            "record",
            "live",
            "passed",
            str(repo),
            "--by",
            "Haruspex Self Test",
            "--evidence",
            "self-test live observation",
        )

        task = read_json(task_path)
        task["status"] = "completed"
        write_json(task_path, task)
        run("gate", "close", str(repo), "--record")
        run("ci", str(repo))

        state = read_json(repo / ".haruspex" / "state.json")
        if state["stage"] != "closed" or state["gates"]["close"]["status"] != "passed":
            raise AssertionError("closeout state was not recorded")

        print("Haruspex self-test passed.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
