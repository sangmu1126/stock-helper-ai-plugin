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


# ── 실제 공개 저장소 평가에서 찾은 오탐 유형 (src/docs/MARKET_HOURS_REAL_REPOS.md) ──

@pytest.mark.parametrize("line", [
    "pric_cnd: 가격조건 — 0:전체,1:5미만,2:10미만,3:10이상,4:10~20,5:20~50",   # API 코드 목록
    "dt: 기간 — 1:전일, 5:5일, 10:10일, 20:20일, 60:60일",
    "minx: N분전콤보값 (ex. 0:1분전, 4:10분전, 5:15분전)",
    "tic_scope: 틱범위 — 1:1틱, 3:3틱, 10:10틱",
    "tic_scope: 1:1분, 5:10분, 10:10분, 15:15분",
    "fid_input_cnt_1: 순위검색 입력값(1: 1위부터, 10:10위부터)",
    "# 조회구분 01:기본시세 02:10호가",
    "rf1_2 = rf1[9:21].rstrip()",                                              # 슬라이스
    "hts_kor_isnm = row[21:50].strip()",
    "end_dt='202606'",                                                        # 연월
    'live.run_strategy(["005930"], on_bar, timeout=3600)',                     # 종목코드
    "'1223': '매매체결처리시각',",                                              # 필드 번호
    'bars = provider.get_index_history("0001", start_date, end_date)',
    'frgnmem_trade_trend(fid_input_iscd="005930", fid_vol_cnt="1000")',        # 거래량
])
def test_find_times_ignores_code_lists_slices_and_numeric_codes(line):
    assert find_times(line) == []


@pytest.mark.parametrize("line, values", [
    ("#    - 미국 온라인국가 : 당일 장 종료후 08:40 ~ 08:45분 경", [time(8, 40), time(8, 45)]),
    ("국내주식 시간외 단일가(16:00~18:00) 시간대에 실시간호가 데이터 확인 가능합니다.", [time(16, 0), time(18, 0)]),
    ("kb.get_inquire_time_itemconclusion(itm_no=\"071050\", inqr_hour='100000')", [time(10, 0)]),
    ('if min_time <= "090000" or len(data) < 120:', [time(9, 0)]),
    ('"fid_input_hour_1": "100000"', [time(10, 0)]),
])
def test_find_times_keeps_real_times_next_to_code_like_text(line, values):
    assert [v for *_, v in find_times(line)] == values
