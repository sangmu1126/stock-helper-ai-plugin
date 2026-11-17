"""JUnit 5 출력: Java·Kotlin 저장소용 경계 테스트 생성과 Java 시연 저장소."""

import os
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from java_junit import COPY_IGNORE, require_junit, run_junit
from market_hours_guard.junit import ADAPTER_CLASS, TEST_CLASS, java_string, write_junit_tests
from market_hours_guard.scan import scan_repo


def test_java_string_escapes_to_ascii():
    assert java_string('a"b\\c') == '"a\\"b\\\\c"'
    assert java_string("수능") == '"\\uc218\\ub2a5"'
    assert java_string("→") == '"\\u2192"'
    assert java_string("😀") == '"\\ud83d\\ude00"'  # UTF-16 서로게이트 쌍
    assert java_string(True) == '"true"' and java_string(False) == '"false"'


def test_junit_files_are_ascii_and_cover_every_case(tmp_path, calendar):
    info = write_junit_tests(calendar, tmp_path, package="com.example.trading")
    text = (tmp_path / f"{TEST_CLASS}.java").read_bytes().decode("ascii")  # 비ASCII가 있으면 실패
    assert text.startswith("// mhg:generated")
    assert "package com.example.trading;" in text
    assert text.count("Arguments.of(") == info["cases"] == 50
    assert '"krx_session@20261231-090000", "krx_session", "2026-12-31T09:00:00+09:00", "CLOSED"' in text
    assert '"us_regular_open@20261102-233000", "us_regular_open", "2026-11-02T23:30:00+09:00", "true"' in text

    adapter = tmp_path / f"{ADAPTER_CLASS}.java"
    assert all(f'PROBES.put("{p.id}", null);' in adapter.read_text(encoding="ascii") for p in calendar.probes)
    adapter.write_text("// connected\n", encoding="utf-8")
    assert not write_junit_tests(calendar, tmp_path)["adapter_created"]
    assert adapter.read_text(encoding="utf-8") == "// connected\n"


def test_cli_gen_tests_junit(tmp_path, mhg_script, calendar_path):
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.run([sys.executable, str(mhg_script), "gen-tests", "--calendar", str(calendar_path),
                           "--out", str(tmp_path), "--format", "junit"],
                          capture_output=True, text=True, encoding="utf-8", env=env)
    assert proc.returncode == 0, proc.stderr
    assert "50건 생성 (junit" in proc.stdout
    assert "package " not in (tmp_path / f"{TEST_CLASS}.java").read_text(encoding="ascii")  # 기본은 패키지 없음


@pytest.mark.parametrize("repo, expected, reviewed", [
    ("toy-broker-java", {"STALE": 1, "DST_RISK": 2, "AMBIGUOUS": 1, "UNMAPPED": 1, "MATCH": 4}, 0),
    ("toy-broker-java-fixed", {"MATCH": 16}, 15),
])
def test_scan_reads_java_and_spring_cron(examples, calendar, repo, expected, reviewed):
    """Java(LocalTime.of)·Spring 6필드 cron(application.yml)도 Python 예제와 같은 판정을 낸다."""
    findings = scan_repo(examples / repo, calendar).findings
    assert dict(Counter(f.status for f in findings)) == expected
    assert sum(f.reviewed for f in findings) == reviewed


@pytest.mark.parametrize("repo, code, counts", [
    ("toy-broker-java", 1, {"found": 50, "successful": 33, "failed": 17}),
    ("toy-broker-java-fixed", 0, {"found": 50, "successful": 50, "failed": 0}),
])
def test_generated_junit_tests_run_against_java_examples(tmp_path, examples, calendar, repo, code, counts):
    require_junit()
    target = tmp_path / repo
    shutil.copytree(examples / repo, target, ignore=COPY_IGNORE)
    write_junit_tests(calendar, target / "src" / "test" / "java" / "toybroker", package="toybroker")
    assert run_junit(target) == (code, counts)
