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
    ("toy-margin-service", False, "9 failed, 12 passed"),
    ("toy-margin-service-fixed", True, "21 passed"),
])
def test_generated_logic_tests_against_examples(tmp_path, folder, ok, summary):
    target = tmp_path / folder
    shutil.copytree(SKILL / "examples" / folder, target)
    assert _run(SCRIPT, "gen-tests", "--out", target / "tests").returncode == 0
    proc = _run("-m", "pytest", "-q", "-p", "no:cacheprovider", "tests", cwd=target)
    assert (proc.returncode == 0) is ok, proc.stdout
    assert summary in proc.stdout


# ── JUnit 5 출력 (Java·Kotlin 계산 코드) ─────────────────────

from docx_text import DocxError, read_docx_text  # noqa: E402
from java_junit import COPY_IGNORE, require_junit, run_junit  # noqa: E402
from mrc_junit import ADAPTER_CLASS, TEST_CLASS, write_junit_tests  # noqa: E402


def test_junit_files_are_ascii_and_cover_every_case(tmp_path):
    cases = build_cases(RULES)
    info = write_junit_tests(cases, RULES["version"], tmp_path, package="com.example.margin")
    text = (tmp_path / f"{TEST_CLASS}.java").read_bytes().decode("ascii")
    assert text.startswith("// mrc:generated") and "package com.example.margin;" in text
    assert text.count("Arguments.of(") == info["cases"] == len(cases) == 21
    assert 'Arguments.of("classify-139.9", 139.9, "SHORTFALL"' in text
    assert '"liquidation-shortfall-2026-12-30", "SHORTFALL", "2026-12-30", "2027-01-05"' in text
    assert 'Arguments.of("grace-135-None-2026-11-19", 135.0, null, "2026-11-19", "NEEDS_ROUND"' in text
    adapter = tmp_path / f"{ADAPTER_CLASS}.java"
    assert "classifyRatio = null;" in adapter.read_text(encoding="ascii")
    adapter.write_text("// connected\n", encoding="utf-8")
    assert not write_junit_tests(cases, RULES["version"], tmp_path)["adapter_created"]
    assert adapter.read_text(encoding="utf-8") == "// connected\n"


def test_cli_gen_tests_junit(tmp_path):
    proc = _run(SCRIPT, "gen-tests", "--out", tmp_path, "--format", "junit", "--java-package", "toymargin")
    assert proc.returncode == 0, proc.stderr
    assert "21건 생성(junit)" in proc.stdout
    assert "package toymargin;" in (tmp_path / f"{TEST_CLASS}.java").read_text(encoding="ascii")


@pytest.mark.parametrize("folder, code, counts", [
    ("toy-margin-service-java", 1, {"found": 21, "successful": 12, "failed": 9}),
    ("toy-margin-service-java-fixed", 0, {"found": 21, "successful": 21, "failed": 0}),
])
def test_generated_junit_tests_run_against_java_examples(tmp_path, folder, code, counts):
    require_junit()
    target = tmp_path / folder
    shutil.copytree(SKILL / "examples" / folder, target, ignore=COPY_IGNORE)
    assert _run(SCRIPT, "gen-tests", "--out", target / "src" / "test" / "java" / "toymargin",
                "--format", "junit", "--java-package", "toymargin").returncode == 0
    assert run_junit(target) == (code, counts)


# ── Word(.docx) 상담 스크립트 ───────────────────────────────

_W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def _docx(path: Path, body: str) -> Path:
    import zipfile

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml",
                         '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/'
                         'package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/>'
                         '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-'
                         'officedocument.wordprocessingml.document.main+xml"/></Types>')
        archive.writestr("word/document.xml",
                         f'<?xml version="1.0" encoding="UTF-8"?><w:document {_W}><w:body>{body}</w:body></w:document>')
    return path


def _p(*runs: str) -> str:
    return "<w:p>" + "".join(f"<w:r><w:t xml:space=\"preserve\">{r}</w:t></w:r>" for r in runs) + "</w:p>"


def test_docx_paragraphs_runs_and_tables_are_read(tmp_path):
    body = (_p("상담 스크립트")
            + _p("담보비율이 ", "120", "% 이상이면 반대매매는 되지 않습니다.")  # Word는 한 문장을 여러 run으로 나눈다
            + "<w:tbl><w:tr><w:tc>" + _p("담보유지비율은 140%입니다.") + "</w:tc></w:tr></w:tbl>")
    path = _docx(tmp_path / "script.docx", body)
    assert read_docx_text(path).split("\n") == [
        "상담 스크립트", "담보비율이 120% 이상이면 반대매매는 되지 않습니다.", "담보유지비율은 140%입니다."]


def test_lint_reads_docx_and_reports_paragraph_numbers(tmp_path):
    _docx(tmp_path / "script.docx", _p("안내") + _p("담보비율이 ", "120", "% 이상이면 반대매매는 되지 않습니다."))
    findings = lint_repo(tmp_path, RULES)
    assert [(f.status, f.path, f.line, f.found) for f in findings] == [("MISCONCEPTION", "script.docx", 2, "120%")]
    proc = _run(SCRIPT, "lint", "--repo", tmp_path, "--out", tmp_path / "out")
    assert proc.returncode == 1
    assert "문단 번호" in (tmp_path / "out" / "report.md").read_text(encoding="utf-8")


def test_unreadable_docx_is_flagged_for_review(tmp_path):
    (tmp_path / "broken.docx").write_bytes(b"not a zip")
    findings = lint_repo(tmp_path, RULES)
    assert [(f.status, f.path, f.kind) for f in findings] == [("REVIEW", "broken.docx", "docx")]
    with pytest.raises(DocxError):
        read_docx_text(tmp_path / "broken.docx")
