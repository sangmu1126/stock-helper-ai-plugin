"""SARIF 출력 (GitHub code scanning)."""

import json
import os
import subprocess
import sys

from market_hours_guard.sarif import to_sarif
from market_hours_guard.scan import scan_repo

FAIL_ON = {"MISMATCH", "STALE", "DST_RISK"}
ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}


# ── SARIF ─────────────────────────────────────────────────────

def test_sarif_lists_problems_with_repo_relative_paths(examples, calendar):
    result = scan_repo(examples / "toy-broker", calendar)
    doc = to_sarif(result, FAIL_ON, base=examples.parents[3])
    assert doc["version"] == "2.1.0" and doc["$schema"].endswith("sarif-2.1.0.json")
    run = doc["runs"][0]
    assert run["tool"]["driver"]["name"] == "market-hours-guard"
    levels = sorted((r["ruleId"], r["level"]) for r in run["results"])
    assert levels == [("AMBIGUOUS", "warning"), ("DST_RISK", "error"), ("DST_RISK", "error"),
                      ("STALE", "error"), ("UNMAPPED", "note")]
    stale = next(r for r in run["results"] if r["ruleId"] == "STALE")
    location = stale["locations"][0]["physicalLocation"]
    assert location["artifactLocation"]["uri"] == \
        "src/skills/market-hours-guard/examples/toy-broker/toy_broker/order_router.py"
    assert location["region"]["startLine"] == 6
    rule_ids = [rule["id"] for rule in run["tool"]["driver"]["rules"]]
    assert all(run["tool"]["driver"]["rules"][r["ruleIndex"]]["id"] == r["ruleId"] for r in run["results"])
    assert "MATCH" not in rule_ids


def test_sarif_is_empty_for_a_clean_repo(examples, calendar):
    assert to_sarif(scan_repo(examples / "toy-broker-fixed", calendar), FAIL_ON)["runs"][0]["results"] == []


def test_cli_writes_sarif(tmp_path, examples, mhg_script, calendar_path):
    sarif = tmp_path / "out" / "mhg.sarif"
    proc = subprocess.run([sys.executable, str(mhg_script), "scan", "--repo", str(examples / "toy-broker"),
                           "--calendar", str(calendar_path), "--out", str(tmp_path / "out"), "--sarif", str(sarif),
                           "--sarif-base", str(examples)], capture_output=True, text=True, encoding="utf-8", env=ENV)
    assert proc.returncode == 1  # 실패 조건이 있으면 SARIF를 쓰고 종료 코드는 그대로 1
    results = json.loads(sarif.read_text(encoding="utf-8"))["runs"][0]["results"]
    assert {r["locations"][0]["physicalLocation"]["artifactLocation"]["uri"].split("/")[0] for r in results} == \
        {"toy-broker"}
