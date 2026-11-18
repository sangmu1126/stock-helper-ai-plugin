"""Replay pinned public KIS source inspections without executing broker code."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path, PurePosixPath
from urllib.request import urlopen

from market_hours_guard.calendar_model import load_calendar
from market_hours_guard.scan import scan_repo

EXAMPLE = Path(__file__).resolve().parents[1] / "examples/public-kis"
REPOSITORY = "koreainvestment/open-trading-api"
MAX_SOURCE_BYTES = 1_000_000


def load_manifest(path: Path = EXAMPLE / "manifest.json") -> dict:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest["repository"] != REPOSITORY or not re.fullmatch(r"[0-9a-f]{40}", manifest["revision"]):
        raise ValueError("Expected a pinned KIS repository revision.")
    for entries in manifest["cases"].values():
        seen = set()
        for item in entries:
            relative = PurePosixPath(item["path"])
            if (relative.is_absolute() or ".." in relative.parts or "\\" in item["path"]
                    or ":" in item["path"] or item["path"] in seen):
                raise ValueError("Unsafe or duplicate source path.")
            if not re.fullmatch(r"[0-9a-f]{64}", item["sha256"]):
                raise ValueError("Every public source needs a SHA-256 digest.")
            seen.add(item["path"])
    return manifest


def fetch_sources(manifest: dict, case: str, root: Path, *, fetch: bool = False, opener=urlopen) -> list[dict]:
    root = root.resolve()
    verified = []
    for item in manifest["cases"][case]:
        target = (root / item["path"]).resolve()
        if not target.is_relative_to(root):
            raise ValueError("Source target escapes the output directory.")
        if target.exists():
            data = target.read_bytes()
        elif fetch:
            url = f"https://raw.githubusercontent.com/{REPOSITORY}/{manifest['revision']}/{item['path']}"
            with opener(url, timeout=30) as response:
                if not response.geturl().startswith(f"https://raw.githubusercontent.com/{REPOSITORY}/"):
                    raise ValueError("Unexpected source redirect.")
                data = response.read(MAX_SOURCE_BYTES + 1)
        else:
            raise ValueError(f"Source not cached: {item['path']}. Add --fetch to download from GitHub.")
        if len(data) > MAX_SOURCE_BYTES or hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise ValueError(f"Source hash/size mismatch: {item['path']}; original left unchanged.")
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        verified.append({"path": item["path"], "sha256": item["sha256"], "verified": True})
    return verified


def finance_reference(data: bytes, item: dict) -> dict | None:
    tree = ast.parse(data)
    constants = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            for name in node.targets:
                if isinstance(name, ast.Name) and name.id in {"API_URL", "tr_id"}:
                    constants.setdefault(name.id, []).append((node.value.value, node.lineno))
    urls = [line for value, line in constants.get("API_URL", []) if value == item["endpoint"]]
    tr_ids = [line for value, line in constants.get("tr_id", []) if value == item["tr_id"]]
    calls = [node.lineno for node in ast.walk(tree)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "_url_fetch"
             and len(node.args) >= 2 and isinstance(node.args[0], ast.Name) and node.args[0].id == "API_URL"
             and isinstance(node.args[1], ast.Name) and node.args[1].id == "tr_id"]
    if not urls or not tr_ids or not calls:
        return None
    return {"status": "NOTICE_TARGET_REFERENCE", "name": item["name"], "path": item["path"],
            "line": urls[0], "call_lines": calls, "endpoint": item["endpoint"], "tr_id": item["tr_id"],
            "runtime_reachability": "not_verified", "live_api_called": False}


def audit(manifest: dict, case: str, root: Path) -> dict:
    revision = manifest["revision"]
    result = {
        "schema": "public-example-audit/v1", "case": case, "repository": REPOSITORY, "revision": revision,
        "checked_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source_executed": False, "live_api_called": False,
        "kakaopay_internal_system": False,
    }
    if case == "hours":
        calendar = load_calendar(EXAMPLE / "calendar.public.toml")
        scanned = scan_repo(root, calendar)
        result.update(
            check="Existing market-hours-guard scanner; retired exchange-label check only",
            calendar_digest=calendar.digest,
            all_scan_counts=scanned.counts(),
            scanned_files=scanned.stats.files_scanned,
            findings=[{"status": finding.status, "path": finding.path, "line": finding.line,
                       "found": finding.found, "rule": finding.boundary}
                      for finding in scanned.findings if finding.status == "STALE"],
            limitations=["A documentation finding is not proof of a broker execution defect.",
                         "Current support and data hours of each websocket TR are unverified.",
                         "No broker code, credentials, orders, or generated boundary tests are executed."],
        )
    else:
        findings = [finance_reference((root / item["path"]).read_bytes(), item) for item in manifest["cases"][case]]
        result.update(
            check="Static AST comparison of notice API names with pinned example URL/TR-ID/call sites",
            notice=manifest["notice"],
            findings=[finding for finding in findings if finding],
            limitations=["Not a general API-retirement detector; this case uses an explicit seven-API mapping.",
                         manifest["notice"]["verification"],
                         "References are present; runtime use, server rejection and downstream customer impact were not tested.",
                         "No replacement API or licensed alternative data feed is assumed."],
        )
    for finding in result["findings"]:
        finding["source_url"] = f"https://github.com/{REPOSITORY}/blob/{revision}/{finding['path']}#L{finding['line']}"
    result["finding_count"] = len(result["findings"])
    return result


def render_report(result: dict) -> str:
    lines = [f"# Public KIS example: {result['case']}", "", f"- Repository: `{result['repository']}`",
             f"- Pinned commit: `{result['revision']}`", f"- Check: {result['check']}",
             f"- Hash-verified original input: {len(result['verified_sources'])} files",
             "- Broker code executed / live API called: no / no", "- KakaoPay internal code: no",
             f"- Findings: **{result['finding_count']}**", ""]
    for finding in result["findings"]:
        label = finding.get("name") or finding["rule"]
        location = f"{finding['path']}:{finding['line']}"
        lines.append(f"- {finding['status']} [{location}]({finding['source_url']}) - {label}")
        if "endpoint" in finding:
            lines.append(f"  URL: `{finding['endpoint']}`; TR: `{finding['tr_id']}`; call lines: {finding['call_lines']}")
    lines += ["", "## Scope and remaining verification", ""]
    lines += [f"- {item}" for item in result["limitations"]]
    lines += ["", "Downloaded originals are not redistributed with this plugin."]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=["hours", "retired-finance"], default="hours")
    parser.add_argument("--out", type=Path, default=Path("mhg-output/public-kis"))
    parser.add_argument("--fetch", action="store_true", help="Download pinned source files from raw.githubusercontent.com.")
    args = parser.parse_args(argv)
    try:
        manifest = load_manifest()
        out = args.out.resolve() / args.case
        source = out / "source"
        verified = fetch_sources(manifest, args.case, source, fetch=args.fetch)
        result = audit(manifest, args.case, source)
        result["verified_sources"] = verified
        result["synthetic_input"] = False
        out.mkdir(parents=True, exist_ok=True)
        (out / "report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (out / "report.md").write_text(render_report(result), encoding="utf-8")
        print(f"[public-kis] {args.case}: verified {len(verified)} originals, findings {result['finding_count']}")
        for finding in result["findings"]:
            print(f"  {finding['status']} {finding['path']}:{finding['line']}")
        print(f"[public-kis] Report: {out / 'report.md'}")
        return 1 if result["findings"] else 0
    except (OSError, ValueError, KeyError, SyntaxError) as exc:
        print(f"Public example input error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
