from datetime import time

import pytest
from market_hours_guard.calendar_model import CalendarError, load_calendar

MINIMAL = """
[meta]
local_tz = "Asia/Seoul"
basis_date = 2026-11-18

[sources]
S = "테스트 출처"

[[boundary]]
id = "A"
time = "{time}"
meaning = "정규장 마감"
keywords = ["krx"]
source = "{source}"
{extra}
"""


def write(tmp_path, text):
    path = tmp_path / "cal.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_demo_calendar_loads(calendar):
    assert len(calendar.active) == 13
    assert [b.id for b in calendar.retired] == ["SOR_END_UNTIL_20260913"]
    assert {p.id for p in calendar.probes} == {"krx_session", "sor_enabled", "us_regular_open"}
    assert calendar.digest.startswith("sha256:")


def test_us_boundary_local_equivalents_follow_dst(calendar):
    assert calendar.local_equivalents(calendar.get("US_REGULAR_OPEN")) == {"EST": time(23, 30), "EDT": time(22, 30)}
    assert calendar.local_equivalents(calendar.get("US_REGULAR_CLOSE")) == {"EST": time(6, 0), "EDT": time(5, 0)}


@pytest.mark.parametrize("time_value, source, extra, message", [
    ("25:00", "S", "", "시각 형식이 아닙니다"),
    ("15:30", "", "", "source가 없습니다"),
    ("15:30", "X", "", "[sources]에 없습니다"),
    ("15:30", "S", '[[retired]]\nid = "OLD"\ntime = "15:00"\nmeaning = "m"\nkeywords = ["k"]\nsource = "S"\nreplaced_by = "NOPE"',
     "replaced_by 'NOPE'"),
    ("15:30", "S", '[[boundary]]\nid = "A"\ntime = "16:00"\nmeaning = "m"\nkeywords = ["k"]\nsource = "S"', "id 중복"),
])
def test_invalid_calendar_reports_problem(tmp_path, time_value, source, extra, message):
    path = write(tmp_path, MINIMAL.format(time=time_value, source=source, extra=extra))
    with pytest.raises(CalendarError) as err:
        load_calendar(path)
    assert any(message in p for p in err.value.problems), err.value.problems


def test_probe_rejects_weekend_and_overlap(tmp_path):
    probe = """
[[probe]]
id = "p"
default = "CLOSED"
sample_dates = [2026-11-21]
  [[probe.window]]
  start = "09:00"
  end = "15:30"
  expect = "A"
  source = "S"
  [[probe.window]]
  start = "15:00"
  end = "16:00"
  expect = "B"
  source = "S"
"""
    path = write(tmp_path, MINIMAL.format(time="15:30", source="S", extra=probe))
    with pytest.raises(CalendarError) as err:
        load_calendar(path)
    joined = "\n".join(err.value.problems)
    assert "주말" in joined and "겹칩니다" in joined
