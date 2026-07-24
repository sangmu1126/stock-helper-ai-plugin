#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

REQUIRED_PATHS = [
    Path("src/.codex-plugin/plugin.json"),
    Path("src/skills/safe-trade-rule-builder/SKILL.md"),
    Path("src/runtime/lambda_handler.py"),
    Path("src/runtime/evaluation.py"),
    Path("README.md"),
    Path("logs"),
]

ALLOWED_LOG_SUFFIXES = {".md", ".txt", ".json", ".jsonl"}
EXCLUDED_NAMES = {"__pycache__", ".pytest_cache"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and create AX hackathon submission.zip.")
    parser.add_argument("--output", default="submission.zip", help="Output zip path.")
    parser.add_argument("--check-only", action="store_true", help="Validate structure without writing a zip.")
    args = parser.parse_args()

    root = Path.cwd()
    errors = validate(root)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    if args.check_only:
        print("Submission structure is valid.")
        return 0

    output = root / args.output
    if output.exists():
        output.unlink()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        add_tree(archive, root / "src", root)
        archive.write(root / "README.md", "README.md")
        add_tree(archive, root / "logs", root)
    print(f"Created {output}")
    return 0


def validate(root: Path) -> list[str]:
    errors: list[str] = []
    for rel_path in REQUIRED_PATHS:
        if not (root / rel_path).exists():
            errors.append(f"Missing required path: {rel_path}")

    src_root = root / "src"
    if (src_root / ".codex-plugin" / "plugin.json").exists() and not src_root.is_dir():
        errors.append("Plugin root must be the src directory.")

    log_files = [path for path in (root / "logs").rglob("*") if path.is_file()] if (root / "logs").exists() else []
    if not log_files:
        errors.append("logs/ must contain at least one conversation log file.")
    invalid_logs = [path for path in log_files if path.suffix.lower() not in ALLOWED_LOG_SUFFIXES]
    for path in invalid_logs:
        errors.append(f"Unsupported log file type: {path.relative_to(root)}")

    return errors


def add_tree(archive: zipfile.ZipFile, source: Path, root: Path) -> None:
    for path in sorted(source.rglob("*")):
        if should_exclude(path):
            continue
        if path.is_file():
            archive.write(path, path.relative_to(root).as_posix())


def should_exclude(path: Path) -> bool:
    return any(part in EXCLUDED_NAMES for part in path.parts)


if __name__ == "__main__":
    raise SystemExit(main())
