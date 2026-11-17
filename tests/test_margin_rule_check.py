"""사내용 신용거래 규칙 점검 테스트 (가상 자료 사용)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "src" / "skills" / "margin-rule-check"
SCRIPT = SKILL / "scripts" / "margin_rule_check.py"
sys.path.insert(0, str(SKILL / "scripts"))
sys.path.insert(0, str(ROOT / "src" / "skills" / "safe-trade-rule-builder" / "scripts"))  # margin_guard

from margin_guard import load_margin_rules  # noqa: E402
from margin_rule_check import build_cases, lint_repo, lint_text  # noqa: E402

RULES = load_margin_rules()
ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}
ENV.pop("PYTHONPATH", None)


def statuses(text: str) -> list[tuple[str, str]]:
    return [(f.status, f.found) for f in lint_text("x.md", text, RULES)]


@pytest.mark.parametrize("line, expected", [
    ("담보비율이 120% 이상이면 반대매매는 되지 않습니다.", [("MISCONCEPTION", "120%")]),
    ("130%만 맞추면 반대매매 안 당해요", [("MISCONCEPTION", "130%")]),
    ("담보비율 125%면 안전합니다", [("MISCONCEPTION", "125%")]),
    ("담보유지비율은 140%입니다.", [("OK", "140%")]),
    ("담보유지비율은 130%입니다.", [("MISMATCH", "130%")]),
    ("120% 미만이면 당일 140%까지 채워야 하며, 채우지 않으면 D+1에 반대매매됩니다.",
     [("OK", "120%"), ("OK", "140%"), ("OK", "D+1")]),
    ("담보부족이 발생하면 D+3일에 반대매매됩니다.", [("MISMATCH", "D+3")]),
    ("D+1까지 추가 담보를 납부하지 않으면 D+2에 반대매매됩니다.", [("OK", "D+1"), ("OK", "D+2")]),
    ("한시 유예: 담보부족 2회차, 담보비율 130% 이상 140% 미만", [("OK", "130%"), ("OK", "140%")]),
    ("담보비율 알림 기준 135%", [("MISMATCH", "135%")]),
    ("담보비율 알림 기준 150%", [("OK", "150%")]),
    ("담보비율 155%", [("REVIEW", "155%")]),
    ("담보비율이 120% 이상이면 반대매매 없음 mrc: ignore", []),
    ("수익률 120%를 달성했습니다", []),  # 담보·신용 문맥이 아님
])
def test_lint_lines(line, expected):
    assert statuses(line) == expected


@pytest.mark.parametrize("line, expected", [
    ("  maintenance_ratio: 130", [("MISMATCH", "130%")]),
    ("  emergency_ratio: 120", [("OK", "120%")]),
    ("  watch_alert_ratio: 145", [("OK", "145%")]),
    ("  liquidation_after_business_days: 3", [("MISMATCH", "3")]),
    ("  deposit_deadline_business_days: 1", [("OK", "1")]),
])
def test_lint_config_keys(line, expected):
    assert statuses(line) == expected


def test_example_folders():
    before = lint_repo(SKILL / "examples" / "support-docs", RULES)
    after = lint_repo(SKILL / "examples" / "support-docs-fixed", RULES)
    bad = sorted((f.status, f.path, f.found) for f in before if f.status in ("MISCONCEPTION", "MISMATCH"))
    assert bad == [
        ("MISCONCEPTION", "app/margin_notice.yaml", "120%"),
        ("MISCONCEPTION", "counseling_script.md", "120%"),
        ("MISMATCH", "app/margin_notice.yaml", "130%"),
        ("MISMATCH", "app/margin_notice.yaml", "3"),
        ("MISMATCH", "counseling_script.md", "D+3"),
    ]
    assert {f.status for f in after} == {"OK"}


def test_generated_cases_follow_rules():
    cases = {c["id"]: c["expect"] for c in build_cases(RULES)}
    assert cases["classify-140"] == "WATCH" and cases["classify-139.9"] == "SHORTFALL"
    assert cases["classify-120"] == "SHORTFALL" and cases["classify-119.9"] == "EMERGENCY"
    assert cases["liquidation-shortfall-2026-11-20"] == "2026-11-24"   # 금요일 + 2영업일
    assert cases["liquidation-emergency-2026-11-20"] == "2026-11-23"
    assert cases["grace-135-2-2026-11-19"] == "ELIGIBLE"
    assert cases["grace-135-None-2026-11-19"] == "NEEDS_ROUND"
    assert cases["grace-135-2-2027-03-02"] == "NOT_ACTIVE"


def _run(*args, cwd=None):
    return subprocess.run([sys.executable, *map(str, args)], cwd=cwd, env=ENV, capture_output=True, text=True,
                          encoding="utf-8", check=False)


@pytest.mark.parametrize("folder, code", [("support-docs", 1), ("support-docs-fixed", 0)])
def test_lint_cli_exit_codes(tmp_path, folder, code):
    proc = _run(SCRIPT, "lint", "--repo", SKILL / "examples" / folder, "--out", tmp_path / "out")
    assert proc.returncode == code, proc.stdout + proc.stderr
    data = json.loads((tmp_path / "out" / "findings.json").read_text(encoding="utf-8"))
    assert data["rules_version"] == RULES["version"]


@pytest.mark.parametrize("folder, ok, summary", [
    ("toy-margin-service", False, "6 failed, 11 passed"),
    ("toy-margin-service-fixed", True, "17 passed"),
])
def test_generated_logic_tests_against_examples(tmp_path, folder, ok, summary):
    target = tmp_path / folder
    shutil.copytree(SKILL / "examples" / folder, target)
    assert _run(SCRIPT, "gen-tests", "--out", target / "tests").returncode == 0
    proc = _run("-m", "pytest", "-q", "-p", "no:cacheprovider", "tests", cwd=target)
    assert (proc.returncode == 0) is ok, proc.stdout
    assert summary in proc.stdout
