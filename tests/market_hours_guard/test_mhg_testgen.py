from market_hours_guard.calendar_model import load_calendar
from market_hours_guard.testgen import ADAPTER_NAME, build_cases, write_tests


def cases_for(calendar, probe):
    return {c["at"]: c["expect"] for c in build_cases(calendar) if c["probe"] == probe}


def test_us_open_shifts_with_dst_in_kst(calendar):
    us = cases_for(calendar, "us_regular_open")
    # 서머타임 중: 뉴욕 09:30 = 한국 22:30
    assert us["2026-07-15T22:29:59+09:00"] is False
    assert us["2026-07-15T22:30:00+09:00"] is True
    # 11/1 서머타임 해제 후: 뉴욕 09:30 = 한국 23:30, 마감 16:00 = 다음 날 06:00
    assert us["2026-11-02T23:29:59+09:00"] is False
    assert us["2026-11-02T23:30:00+09:00"] is True
    assert us["2026-11-19T05:59:59+09:00"] is True
    assert us["2026-11-19T06:00:00+09:00"] is False


def test_boundaries_are_half_open(calendar):
    krx = cases_for(calendar, "krx_session")
    assert krx["2026-11-18T15:29:59+09:00"] == "REGULAR"
    assert krx["2026-11-18T15:30:00+09:00"] == "CLOSED"
    assert krx["2026-11-18T16:00:00+09:00"] == "AFTER"
    assert krx["2026-11-18T20:00:00+09:00"] == "CLOSED"


def test_effective_from_excludes_window_before_cutover(tmp_path, calendar_path):
    text = calendar_path.read_text(encoding="utf-8").replace(
        "sample_dates = [2026-11-18]\n\n  [[probe.window]]\n  start = \"09:00\"\n  end = \"15:30\"",
        "sample_dates = [2026-09-11]\n\n  [[probe.window]]\n  start = \"09:00\"\n  end = \"15:30\"",
    )
    path = tmp_path / "cal.toml"
    path.write_text(text, encoding="utf-8")
    krx = cases_for(load_calendar(path), "krx_session")
    assert "2026-09-11T16:00:00+09:00" not in krx           # 애프터마켓 개장 전 날짜
    assert krx["2026-09-11T15:30:00+09:00"] == "CLOSED"


def test_write_tests_keeps_existing_adapter(tmp_path, calendar):
    first = write_tests(calendar, tmp_path)
    assert first["adapter_created"] and first["cases"] == 28
    adapter = tmp_path / ADAPTER_NAME
    assert "'krx_session': None" in adapter.read_text(encoding="utf-8")
    adapter.write_text("PROBES = {}\n", encoding="utf-8")
    second = write_tests(calendar, tmp_path)
    assert not second["adapter_created"]
    assert adapter.read_text(encoding="utf-8") == "PROBES = {}\n"
