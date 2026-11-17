import pytest
from market_hours_guard.calendar_model import CalendarError, load_calendar
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
    assert "sample_dates = [2026-11-18, 2026-11-19, 2026-12-31]" in original
    text = original.replace("sample_dates = [2026-11-18, 2026-11-19, 2026-12-31]", "sample_dates = [2026-09-11]")
    path = tmp_path / "cal.toml"
    path.write_text(text, encoding="utf-8")
    krx = cases_for(load_calendar(path), "krx_session")
    assert "2026-09-11T16:00:00+09:00" not in krx           # 애프터마켓 개장 전 날짜
    assert krx["2026-09-11T15:30:00+09:00"] == "CLOSED"


def test_write_tests_keeps_existing_adapter(tmp_path, calendar):
    first = write_tests(calendar, tmp_path)
    assert first["adapter_created"] and first["cases"] == 50
    adapter = tmp_path / ADAPTER_NAME
    assert "'krx_session': None" in adapter.read_text(encoding="utf-8")
    adapter.write_text("PROBES = {}\n", encoding="utf-8")
    second = write_tests(calendar, tmp_path)
    assert not second["adapter_created"]
    assert adapter.read_text(encoding="utf-8") == "PROBES = {}\n"


def test_special_day_moves_regular_and_after_sessions(calendar):
    krx = cases_for(calendar, "krx_session")
    # 수능일(2026-11-19): 정규장 10:00~16:30, 애프터마켓 17:00~20:00. 평소 경계(09:00, 15:30, 16:00)도 그날 기준으로 검사한다.
    assert krx["2026-11-19T09:00:00+09:00"] == "CLOSED"
    assert krx["2026-11-19T09:59:59+09:00"] == "CLOSED"
    assert krx["2026-11-19T10:00:00+09:00"] == "REGULAR"
    assert krx["2026-11-19T15:30:00+09:00"] == "REGULAR"
    assert krx["2026-11-19T16:00:00+09:00"] == "REGULAR"
    assert krx["2026-11-19T16:30:00+09:00"] == "CLOSED"
    assert krx["2026-11-19T16:59:59+09:00"] == "CLOSED"
    assert krx["2026-11-19T17:00:00+09:00"] == "AFTER"
    assert krx["2026-11-19T20:00:00+09:00"] == "CLOSED"
    # 평일 기준은 그대로
    assert krx["2026-11-18T09:00:00+09:00"] == "REGULAR"
    assert krx["2026-11-18T16:00:00+09:00"] == "AFTER"


def test_confirmed_until_skips_unannounced_hours(tmp_path, calendar_path):
    """특수일 일부 시간대가 공지되지 않았으면 confirmed_until 이후는 기대값을 만들지 않는다."""
    text = calendar_path.read_text(encoding="utf-8").replace(
        'name = "2027학년도 수능일"', 'name = "2027학년도 수능일"\nconfirmed_until = "16:30"')
    krx = cases_for(load_calendar(write_calendar(tmp_path, text)), "krx_session")
    assert krx["2026-11-19T16:29:59+09:00"] == "REGULAR"
    assert not [at for at in krx if at.startswith(("2026-11-19T16:3", "2026-11-19T17", "2026-11-19T19"))]


def test_holiday_expects_closed_at_every_usual_boundary(calendar):
    krx = cases_for(calendar, "krx_session")
    holiday = {at: v for at, v in krx.items() if at.startswith("2026-12-31")}
    # 연말휴장일: 평소 경계(09:00, 15:30, 16:00, 20:00)의 1초 전·정각 모두 CLOSED
    assert len(holiday) == 8 and set(holiday.values()) == {"CLOSED"}
    case = next(c for c in build_cases(calendar) if c["at"] == "2026-12-31T09:00:00+09:00")
    assert case["why"].startswith("[휴장일 연말휴장일]")


def test_holiday_calendar_limits_sample_dates(tmp_path, calendar_path):
    text = calendar_path.read_text(encoding="utf-8")
    beyond = text.replace("sample_dates = [2026-11-18, 2026-11-19, 2026-12-31]", "sample_dates = [2028-01-04]")
    with pytest.raises(CalendarError, match="확인 범위"):
        load_calendar(write_calendar(tmp_path, beyond))
    weekend = text.replace('2026-12-31 = "연말휴장일"', '2026-12-31 = "연말휴장일"\n2026-12-26 = "토요일"')
    with pytest.raises(CalendarError, match="주말"):
        load_calendar(write_calendar(tmp_path, weekend))


def write_calendar(tmp_path, text):
    path = tmp_path / "cal.toml"
    path.write_text(text, encoding="utf-8")
    return path
