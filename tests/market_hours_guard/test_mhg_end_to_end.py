"""CLI 전체 흐름: scan 종료 코드 → gen-tests → 대상 저장소에서 pytest 실행 (수정 전 실패, 수정 후 통과)."""

import json
import os
import shutil
import subprocess
import sys

import pytest

ENV = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}


def run(*args, cwd=None):
    return subprocess.run([sys.executable, *map(str, args)], cwd=cwd, env=ENV, check=False,
                          capture_output=True, text=True, encoding="utf-8")


@pytest.mark.parametrize("repo, code", [("toy-broker", 1), ("toy-broker-fixed", 0)])
def test_scan_exit_code_and_outputs(tmp_path, mhg_script, calendar_path, examples, repo, code):
    out = tmp_path / "out"
    proc = run(mhg_script, "scan", "--repo", examples / repo, "--calendar", calendar_path, "--out", out)
    assert proc.returncode == code, proc.stdout + proc.stderr
    data = json.loads((out / "findings.json").read_text(encoding="utf-8"))
    assert data["schema"] == "market-hours-guard/findings@1"
    assert data["calendar"]["digest"].startswith("sha256:")
    assert "# 거래시간 변경 점검 결과" in (out / "report.md").read_text(encoding="utf-8")


def test_bad_calendar_exits_2(tmp_path, mhg_script, examples):
    bad = tmp_path / "bad.toml"
    bad.write_text("[meta]\nname = 'x'\n", encoding="utf-8")
    proc = run(mhg_script, "scan", "--repo", examples / "toy-broker", "--calendar", bad, "--out", tmp_path / "o")
    assert proc.returncode == 2 and "[[boundary]]" in proc.stderr


@pytest.mark.parametrize("repo, expect_ok, summary", [
    ("toy-broker", False, "13 failed, 24 passed"),
    ("toy-broker-fixed", True, "37 passed"),
])
def test_generated_boundary_tests(tmp_path, mhg_script, calendar_path, examples, repo, expect_ok, summary):
    target = tmp_path / repo
    shutil.copytree(examples / repo, target)
    gen = run(mhg_script, "gen-tests", "--calendar", calendar_path, "--out", target / "tests")
    assert gen.returncode == 0, gen.stderr
    proc = run("-m", "pytest", "-q", "-p", "no:cacheprovider", "tests", cwd=target)
    assert (proc.returncode == 0) is expect_ok, proc.stdout
    assert summary in proc.stdout
