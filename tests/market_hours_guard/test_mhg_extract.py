from datetime import time

import pytest
from market_hours_guard.extract import find_times, tokenize


@pytest.mark.parametrize("line, kind, value", [
    ('SOR_END = time(15, 30)', "call", time(15, 30)),
    ('t = datetime.time(hour=9, minute=0)', "call", time(9, 0)),
    ('private static final LocalTime CLOSE = LocalTime.of(20, 0);', "call", time(20, 0)),
    ('close_at: "15:30"', "literal", time(15, 30)),
    ('# 애프터마켓 16:00:00 시작', "literal", time(16, 0)),
    ('cron: "35 15 * * 1-5"', "cron", time(15, 35)),
    ('@Scheduled(cron = "0 5 20 * * MON-FRI")', "cron", time(20, 5)),
    ('closeTime = "153000"', "compact", time(15, 30)),
    ('if now.hour >= 16:', "hour_compare", time(16, 0)),
])
def test_find_times_detects_common_forms(line, kind, value):
    hits = find_times(line)
    assert [(k, v) for _, k, _, v in hits] == [(kind, value)]


@pytest.mark.parametrize("line", [
    'ts = "2026-11-18T15:30:00+09:00"',   # 특정 시점(타임스탬프)은 규칙이 아님
    'd = datetime(2026, 11, 18)',
    'x = get_time(15, 30)',
    'version = "1.15:30"',
    'year = "2026"',                       # 시각 이름이 없는 4자리 숫자
    'ratio = "a b c d e"',
])
def test_find_times_ignores_non_rules(line):
    assert find_times(line) == []


def test_range_yields_both_ends():
    hits = find_times('label: "애프터마켓 16:00~20:00"')
    assert [v for *_, v in hits] == [time(16, 0), time(20, 0)]


def test_tokenize_splits_identifiers():
    assert {"us", "open", "kst"} <= tokenize("US_OPEN_KST")
    assert {"is", "us", "regular", "open"} <= tokenize("isUsRegularOpen")
    assert "정규장" in tokenize("# KRX 정규장 마감")
