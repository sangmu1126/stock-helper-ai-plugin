"""Record real CLI demo outputs; this does not capture or simulate a GUI."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "src" / "skills"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "docs/media/demo-evidence")
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    records = []
    manifest = json.loads((ROOT / "src/.codex-plugin/plugin.json").read_text(encoding="utf-8"))
    source_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
    ).strip()
    changed_sources = subprocess.check_output(
        ["git", "diff", "--name-only", "HEAD", "--", "src"], cwd=ROOT, text=True,
    ).splitlines()

    with tempfile.TemporaryDirectory(prefix="safe-trade-demo-") as directory:
        work = Path(directory)

        def clean(value: str) -> str:
            for path, label in ((work, "<demo-temp>"), (ROOT, "<repo>")):
                value = value.replace(str(path), label).replace(path.as_posix(), label)
            profile = os.environ.get("USERPROFILE")
            if profile:
                value = value.replace(profile, "<user>").replace(profile.replace("\\", "/"), "<user>")
            return value

        def run(name, command, *, cwd=ROOT, expected=0, contains=None):
            result = subprocess.run(
                [sys.executable, *map(str, command)], cwd=cwd, env=env,
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90,
                check=False,
            )
            passed = result.returncode == expected and (contains is None or contains in result.stdout)
            transcript = (
                f"command: {subprocess.list2cmdline(['python', *map(str, command)])}\n"
                f"cwd: {cwd}\nexit_code: {result.returncode}\nexpected_exit_code: {expected}\n"
                f"expectation_met: {passed}\n\nSTDOUT\n{result.stdout}\nSTDERR\n{result.stderr}"
            )
            normalized = "\n".join(line.rstrip() for line in clean(transcript).splitlines()) + "\n"
            (out / f"{name}.txt").write_text(normalized, encoding="utf-8")
            records.append({"id": name, "exit_code": result.returncode, "expectation_met": passed})
            print(f"{name}: exit={result.returncode}, expectation_met={passed}")

        mhg = SKILLS / "market-hours-guard/scripts/mhg.py"
        calendar = SKILLS / "market-hours-guard/assets/calendar.demo.toml"
        for name, example, failures, scan_exit in (
            ("before", "toy-broker", "17 failed, 33 passed", 1),
            ("after", "toy-broker-fixed", "50 passed", 0),
        ):
            target = work / name
            shutil.copytree(
                SKILLS / "market-hours-guard/examples" / example, target,
                ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"),
            )
            run(f"mhg-{name}-scan", [mhg, "scan", "--repo", target, "--calendar", calendar,
                                     "--out", work / f"scan-{name}"], expected=scan_exit)
            run(f"mhg-{name}-generate", [mhg, "gen-tests", "--calendar", calendar,
                                         "--out", target / "tests"])
            run(f"mhg-{name}-tests", ["-m", "pytest", "-q", "--tb=short", "-p", "no:cacheprovider", "tests"],
                cwd=target, expected=scan_exit, contains=failures)

        run("mrc-lint", [SKILLS / "margin-rule-check/scripts/margin_rule_check.py", "lint", "--repo",
                         SKILLS / "margin-rule-check/examples/support-docs", "--out", work / "mrc"], expected=1)
        run("margin-guard", [SKILLS / "safe-trade-rule-builder/scripts/margin_check.py", "assess", "--account",
                             SKILLS / "safe-trade-rule-builder/examples/margin/misguided_after_deposit.json",
                             "--believed", "120"], expected=1)
        run("usd-rule", [SKILLS / "safe-trade-rule-builder/scripts/rule_builder.py", "--intent",
                         "테슬라가 200달러 아래로 내려가면 알려줘", "--format", "markdown"])

    summary = {
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "plugin_version": manifest["version"],
        "python_version": sys.version.split()[0],
        "source_commit": source_commit,
        "modified_tracked_source_files": changed_sources,
        "capture_kind": "cli_transcripts_not_gui_screenshots",
        "comparison": "existing before and fixed synthetic fixtures, not a recorded live edit",
        "redaction": "workspace and user-profile path prefixes only; AI conversation logs unchanged",
        "formatting": "line endings normalized and trailing whitespace removed",
        "steps": records,
        "all_expectations_met": all(record["expectation_met"] for record in records),
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if summary["all_expectations_met"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
