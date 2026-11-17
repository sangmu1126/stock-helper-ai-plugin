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
    original = calendar_path.read_text(encoding="utf-8")
    assert "sample_dates = [2026-11-18, 2026-11-19]" in original
    text = original.replace("sample_dates = [2026-11-18, 2026-11-19]", "sample_dates = [2026-09-11]")
    path = tmp_path / "cal.toml"
    path.write_text(text, encoding="utf-8")
    krx = cases_for(load_calendar(path), "krx_session")
    assert "2026-09-11T16:00:00+09:00" not in krx           # 애프터마켓 개장 전 날짜
    assert krx["2026-09-11T15:30:00+09:00"] == "CLOSED"


def test_write_tests_keeps_existing_adapter(tmp_path, calendar):
    first = write_tests(calendar, tmp_path)
    assert first["adapter_created"] and first["cases"] == 37
    adapter = tmp_path / ADAPTER_NAME
    assert "'krx_session': None" in adapter.read_text(encoding="utf-8")
    adapter.write_text("PROBES = {}\n", encoding="utf-8")
    second = write_tests(calendar, tmp_path)
    assert not second["adapter_created"]
    assert adapter.read_text(encoding="utf-8") == "PROBES = {}\n"


def test_special_day_moves_regular_session_and_skips_unconfirmed_hours(calendar):
    krx = cases_for(calendar, "krx_session")
    # 수능일(2026-11-19): 정규장 10:00~16:30. 평소 경계(09:00, 15:30, 16:00)도 그날 기준으로 검사한다.
    assert krx["2026-11-19T09:00:00+09:00"] == "CLOSED"
    assert krx["2026-11-19T09:59:59+09:00"] == "CLOSED"
    assert krx["2026-11-19T10:00:00+09:00"] == "REGULAR"
    assert krx["2026-11-19T15:30:00+09:00"] == "REGULAR"
    assert krx["2026-11-19T16:29:59+09:00"] == "REGULAR"
    # 16:30 이후(애프터마켓 등)는 거래소 공지가 없어 기대값을 만들지 않는다.
    assert not [at for at in krx if at.startswith(("2026-11-19T16:3", "2026-11-19T19"))]
    # 평일 기준은 그대로
    assert krx["2026-11-18T09:00:00+09:00"] == "REGULAR"
    assert krx["2026-11-18T16:00:00+09:00"] == "AFTER"
