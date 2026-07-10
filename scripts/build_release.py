#!/usr/bin/env python3
"""Build portable Haruspex release archives from the source directory."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

EXCLUDED_PARTS = {".git", "dist", "__pycache__", ".pytest_cache"}


def source_root() -> Path:
    return Path(__file__).resolve().parent.parent


def files_to_package(root: Path):
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        if path.suffix == ".pyc":
            continue
        yield path, relative


def validate(root: Path) -> None:
    required = [
        root / "SKILL.md",
        root / "agents" / "openai.yaml",
        root / ".claude-plugin" / "plugin.json",
        root / "scripts" / "haruspex.py",
        root / "assets" / "repo-template" / ".haruspex" / "project.json",
    ]
    missing = [str(path.relative_to(root)) for path in required if not path.exists()]
    if missing:
        raise RuntimeError("missing required files: " + ", ".join(missing))

    skill = (root / "SKILL.md").read_text(encoding="utf-8")
    if not skill.startswith("---\n") or "\nname: haruspex\n" not in skill or "\ndescription:" not in skill:
        raise RuntimeError("SKILL.md frontmatter is invalid")

    manifest = json.loads((root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    if manifest.get("name") != "haruspex" or not manifest.get("version"):
        raise RuntimeError("Claude plugin manifest is invalid")

    for path, _ in files_to_package(root):
        if path.stat().st_size > 10 * 1024 * 1024:
            raise RuntimeError(f"unexpectedly large bundled file: {path}")
        if path.suffix == ".json":
            json.loads(path.read_text(encoding="utf-8"))


def run_self_test(root: Path) -> None:
    completed = subprocess.run(
        [sys.executable, str(root / "scripts" / "self_test.py")],
        cwd=root,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError("Haruspex self-test failed")


def build_zip(root: Path, output: Path, prefix: str | None) -> None:
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path, relative in files_to_package(root):
            arcname = Path(prefix) / relative if prefix else relative
            archive.write(path, arcname.as_posix())


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="dist")
    parser.add_argument("--skip-tests", action="store_true")
    args = parser.parse_args()

    root = source_root()
    output = Path(args.output).expanduser()
    if not output.is_absolute():
        output = root / output
    output.mkdir(parents=True, exist_ok=True)

    validate(root)
    if not args.skip_tests:
        run_self_test(root)

    skill_zip = output / "skill.zip"
    claude_zip = output / "haruspex-claude-plugin.zip"
    build_zip(root, skill_zip, root.name)
    build_zip(root, claude_zip, None)

    sums = output / "SHA256SUMS"
    sums.write_text(
        f"{checksum(skill_zip)}  {skill_zip.name}\n"
        f"{checksum(claude_zip)}  {claude_zip.name}\n",
        encoding="utf-8",
    )

    print(skill_zip)
    print(claude_zip)
    print(sums)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
