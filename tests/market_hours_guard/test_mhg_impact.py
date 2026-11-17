"""기준표 변경 영향 미리보기 (mhg impact)."""

import json
import os
import subprocess
import sys

from market_hours_guard.calendar_model import load_calendar
from market_hours_guard.impact import new_failures, run_impact

FAIL_ON = {"MISMATCH", "STALE", "DST_RISK"}
ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}


# ── 기준표 변경 영향 미리보기 ───────────────────────────────────

def _calendar_with(tmp_path, calendar_path, old, new):
    text = calendar_path.read_text(encoding="utf-8")
    i = text.index('id = "SOR_END"')
    j = text.index(old, i)
    path = tmp_path / "new.toml"
    path.write_text(text[:j] + new + text[j + len(old):], encoding="utf-8")
    return load_calendar(path)


def test_impact_shows_annotated_sites_that_would_break(tmp_path, examples, calendar, calendar_path):
    new = _calendar_with(tmp_path, calendar_path, 'time = "20:00"', 'time = "21:00"')
    diff, changes, _ = run_impact(examples / "toy-broker-fixed", calendar, new)
    assert diff == ["변경: SOR_END 20:00 → 21:00"]
    failing = new_failures(changes, FAIL_ON)
    assert sorted((c.path, c.after.status) for c in failing) == [
        ("config/batch_jobs.yaml", "MISMATCH"), ("toy_broker/order_router.py", "MISMATCH")]
    shifted = [c for c in changes if c not in failing]
    assert [c.transition for c in shifted] == ["MATCH(SOR_END) → MATCH(KRX_AFTER_CLOSE)"]  # 주석 없는 설명 문구


def test_impact_is_empty_when_nothing_changes(examples, calendar):
    diff, changes, _ = run_impact(examples / "toy-broker-fixed", calendar, calendar)
    assert diff == [] and changes == []


def test_cli_impact_exit_code_and_report(tmp_path, examples, mhg_script, calendar_path):
    new = tmp_path / "cal21.toml"
    text = calendar_path.read_text(encoding="utf-8")
    i = text.index('id = "SOR_END"')
    j = text.index('time = "20:00"', i)
    new.write_text(text[:j] + 'time = "21:00"' + text[j + len('time = "20:00"'):], encoding="utf-8")
    out = tmp_path / "impact"
    proc = subprocess.run([sys.executable, str(mhg_script), "impact", "--repo", str(examples / "toy-broker-fixed"),
                           "--calendar", str(calendar_path), "--new-calendar", str(new), "--out", str(out)],
                          capture_output=True, text=True, encoding="utf-8", env=ENV)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "새로 실패 조건이 되는 곳 2개" in proc.stdout
    report = (out / "impact.md").read_text(encoding="utf-8")
    assert "변경: SOR_END 20:00 → 21:00" in report and "`config/batch_jobs.yaml:4`" in report
    assert len(json.loads((out / "impact.json").read_text(encoding="utf-8"))["changes"]) == 3
