"""룰 빌더 보강 테스트: 시간 조건 적용, 종목 인식 확대(국내·미국), 금액 표현 확대."""

from __future__ import annotations

import json
import sys
import tomllib
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "src" / "skills" / "safe-trade-rule-builder" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from intent_parser import detect_amount_krw, detect_asset
from session_window import (
    apply_time_window,
    evaluate_time_window,
    load_sessions,
)

KST = ZoneInfo("Asia/Seoul")
ET = ZoneInfo("America/New_York")


def kst(*args):
    return datetime(*args, tzinfo=KST)


# ── 시간 조건 ──────────────────────────────────────────────


@pytest.mark.parametrize("window, at, status, reason", [
    ({"only_before_close_minutes": 30}, kst(2026, 11, 18, 14, 59, 59), "WAIT", "BEFORE_CLOSING_WINDOW"),
    ({"only_before_close_minutes": 30}, kst(2026, 11, 18, 15, 0), "OK", "TIME_WINDOW_SATISFIED"),
    ({"exclude_open_minutes": 10}, kst(2026, 11, 18, 9, 9, 59), "WAIT", "WITHIN_OPENING_EXCLUSION"),
    ({"exclude_open_minutes": 10}, kst(2026, 11, 18, 9, 10), "OK", "TIME_WINDOW_SATISFIED"),
    ({"exclude_morning": True}, kst(2026, 11, 18, 11, 59), "WAIT", "MORNING_EXCLUDED"),
    ({"exclude_morning": True}, kst(2026, 11, 18, 12, 0), "OK", "TIME_WINDOW_SATISFIED"),
    ({"only_before_close_minutes": 30}, kst(2026, 11, 18, 15, 30), "WAIT", "OUTSIDE_SESSION"),
    ({"only_before_close_minutes": 30}, kst(2026, 11, 21, 15, 10), "WAIT", "OUTSIDE_SESSION"),  # 토요일
    ({"requires_consecutive_days": 3}, kst(2026, 11, 18, 10, 0), "WAIT", "CONSECUTIVE_DAYS_NOT_VERIFIED"),
])
def test_krx_time_window(window, at, status, reason):
    result = evaluate_time_window(window, "005930.KS", at)
    assert (result["status"], result["reason"]) == (status, reason)
    assert result["details"]["market"] == "KRX"


@pytest.mark.parametrize("at, status", [
    (kst(2026, 7, 16, 4, 45), "OK"),     # 서머타임 중: 뉴욕 15:45 = 한국 04:45
    (kst(2026, 11, 19, 4, 45), "WAIT"),  # 서머타임 해제 후: 한국 04:45 = 뉴욕 14:45 → 마감 30분 전 아님
    (kst(2026, 11, 19, 5, 45), "OK"),    # 서머타임 해제 후: 한국 05:45 = 뉴욕 15:45
])
def test_us_close_window_follows_dst(at, status):
    result = evaluate_time_window({"only_before_close_minutes": 30}, "TSLA", at)
    assert result["status"] == status
    assert result["details"]["market"] == "US"


def test_matched_trigger_is_held_when_time_window_fails():
    matched = {"status": "MATCHED", "reason": "PRICE_DROP_MATCHED", "details": {}}
    ts = int(kst(2026, 11, 18, 10, 0).timestamp())
    held = apply_time_window(matched, {"only_before_close_minutes": 30}, "005930.KS", ts)
    assert held["status"] == "WAIT" and held["reason"] == "TIME_WINDOW_BEFORE_CLOSING_WINDOW"
    assert held["time_window"]["status"] == "WAIT"
    ok = apply_time_window(matched, {"only_before_close_minutes": 30}, "005930.KS", int(kst(2026, 11, 18, 15, 10).timestamp()))
    assert ok["status"] == "MATCHED"


def test_rules_without_time_constraints_are_unchanged():
    matched = {"status": "MATCHED", "reason": "X", "details": {}}
    assert apply_time_window(matched, {"market_session": "regular"}, "005930.KS", 0) is matched
    assert apply_time_window(None, {"only_before_close_minutes": 30}, "005930.KS", 0) is None


def test_missing_quote_time_does_not_pass_time_constraints():
    matched = {"status": "MATCHED", "reason": "X", "details": {}}
    result = apply_time_window(matched, {"exclude_morning": True}, "005930.KS", None)
    assert result["status"] == "WAIT" and result["reason"] == "TIME_WINDOW_NOT_EVALUATED"


def test_build_rule_applies_time_window(monkeypatch):
    import market_data
    from builder import build_rule

    monkeypatch.setattr(market_data.time, "time", lambda: kst(2026, 11, 18, 10, 0).timestamp())
    draft = build_rule("삼성전자 3% 떨어지면 장 마감 30분 전에만 10만원만 매수", provider_name="demo-fixture",
                       with_market_data=True, parser_strategy="deterministic")
    assert draft.trigger_evaluation["time_window"]["reason"] == "BEFORE_CLOSING_WINDOW"
    assert draft.trigger_evaluation["status"] != "MATCHED"
    assert draft.decision_result["decision"] not in {"MANUAL_CONFIRM", "NOTIFY_ONLY"}


def test_sessions_match_market_hours_guard_calendar():
    """로컬 런타임의 세션 설정과 거래시간 점검기 기준표가 같은 값을 쓰는지 확인한다."""
    markets = load_sessions()["markets"]
    calendar_path = ROOT / "src" / "skills" / "market-hours-guard" / "assets" / "calendar.demo.toml"
    boundaries = {b["id"]: b for b in tomllib.loads(calendar_path.read_text(encoding="utf-8"))["boundary"]}
    krx, us = markets["KRX"], markets["US"]
    assert krx["sessions"]["regular"]["open"] == boundaries["KRX_REGULAR_OPEN"]["time"]
    assert krx["sessions"]["regular"]["close"] == boundaries["KRX_REGULAR_CLOSE"]["time"]
    assert krx["sessions"]["after_hours"]["open"] == boundaries["KRX_AFTER_OPEN"]["time"]
    assert krx["sessions"]["after_hours"]["close"] == boundaries["KRX_AFTER_CLOSE"]["time"]
    csat = next(s for s in krx["special_days"] if s["id"] == "CSAT_2026")
    assert csat["sessions"]["regular"]["open"] == boundaries["KRX_REGULAR_OPEN_CSAT_2026"]["time"]
    assert csat["sessions"]["regular"]["close"] == boundaries["KRX_REGULAR_CLOSE_CSAT_2026"]["time"]
    assert csat["sessions"]["after_hours"]["open"] == boundaries["KRX_AFTER_OPEN_CSAT_2026"]["time"]
    assert csat["sessions"]["after_hours"]["close"] == boundaries["KRX_AFTER_CLOSE"]["time"]
    early = {s["sessions"]["regular"]["close"] for s in us["special_days"]}
    assert early == {boundaries["US_EARLY_CLOSE"]["time"]}
    calendar = tomllib.loads(calendar_path.read_text(encoding="utf-8"))["holidays"]
    for market in ("KRX", "US"):  # 휴장일 달력도 기준표와 같아야 한다
        assert markets[market]["holidays"]["days"] == calendar[market]["days"]
        assert markets[market]["holidays"]["confirmed_through"] == calendar[market]["confirmed_through"].isoformat()
    assert krx["morning_end"] == boundaries["MORNING_END"]["time"]
    assert us["sessions"]["regular"]["open"] == boundaries["US_REGULAR_OPEN"]["time"]
    assert us["sessions"]["regular"]["close"] == boundaries["US_REGULAR_CLOSE"]["time"]
    assert us["tz"] == boundaries["US_REGULAR_OPEN"]["tz"]


# ── 애프터마켓·특수일 ─────────────────────────────────────


@pytest.mark.parametrize("window, at, status, reason", [
    ({"market_session": "after_hours"}, kst(2026, 11, 18, 16, 30), "OK", "TIME_WINDOW_SATISFIED"),
    ({"market_session": "after_hours"}, kst(2026, 11, 18, 15, 45), "WAIT", "OUTSIDE_SESSION"),
    ({"market_session": "after_hours", "only_before_close_minutes": 30}, kst(2026, 11, 18, 19, 40), "OK", "TIME_WINDOW_SATISFIED"),
    ({"market_session": "after_hours", "only_before_close_minutes": 30}, kst(2026, 11, 18, 19, 0), "WAIT", "BEFORE_CLOSING_WINDOW"),
    ({"market_session": "after_hours"}, kst(2026, 9, 11, 16, 30), "WAIT", "SESSION_NOT_AVAILABLE"),  # 개장 전
    ({"market_session": "pre_market"}, kst(2026, 11, 18, 8, 30), "WAIT", "SESSION_NOT_AVAILABLE"),   # KRX 프리마켓 없음
])
def test_krx_after_hours_session(window, at, status, reason):
    result = evaluate_time_window(window, "035720.KS", at)
    assert (result["status"], result["reason"]) == (status, reason)


def test_us_has_no_after_hours_session_configured():
    result = evaluate_time_window({"market_session": "after_hours"}, "TSLA", kst(2026, 11, 19, 7, 0))
    assert result["reason"] == "SESSION_NOT_AVAILABLE"


@pytest.mark.parametrize("window, at, status, reason", [
    ({"only_before_close_minutes": 30}, kst(2026, 11, 19, 15, 10), "WAIT", "BEFORE_CLOSING_WINDOW"),   # 평소면 통과할 시각
    ({"only_before_close_minutes": 30}, kst(2026, 11, 19, 16, 10), "OK", "TIME_WINDOW_SATISFIED"),
    ({"exclude_open_minutes": 10}, kst(2026, 11, 19, 9, 30), "WAIT", "OUTSIDE_SESSION"),               # 아직 개장 전
    ({"exclude_open_minutes": 10}, kst(2026, 11, 19, 10, 5), "WAIT", "WITHIN_OPENING_EXCLUSION"),
    ({"market_session": "after_hours"}, kst(2026, 11, 19, 16, 45), "WAIT", "OUTSIDE_SESSION"),         # 평소면 애프터마켓
    ({"market_session": "after_hours"}, kst(2026, 11, 19, 17, 0), "OK", "TIME_WINDOW_SATISFIED"),
])
def test_suneung_day_shifts_regular_session(window, at, status, reason):
    result = evaluate_time_window(window, "005930.KS", at)
    assert (result["status"], result["reason"]) == (status, reason)
    assert result["details"].get("special_day") == "2027학년도 수능일"


# ── 휴장일·조기 폐장 ───────────────────────────────────────


@pytest.mark.parametrize("symbol, at, reason, holiday", [
    ("005930.KS", kst(2026, 12, 31, 10, 0), "MARKET_HOLIDAY", "연말휴장일"),
    ("005930.KS", kst(2027, 5, 3, 10, 0), "MARKET_HOLIDAY", "노동절(대체휴일)"),
    ("TSLA", datetime(2026, 11, 26, 10, 0, tzinfo=ET), "MARKET_HOLIDAY", "Thanksgiving Day"),
    ("005930.KS", kst(2028, 1, 4, 10, 0), "HOLIDAY_CALENDAR_UNCONFIRMED", None),  # 공지된 달력 범위 밖
])
def test_holidays_hold_time_window_rules(symbol, at, reason, holiday):
    result = evaluate_time_window({"exclude_open_minutes": 10}, symbol, at)
    assert (result["status"], result["reason"]) == ("WAIT", reason)
    assert result["details"].get("holiday") == holiday


def test_trading_day_before_holiday_is_normal():
    result = evaluate_time_window({"only_before_close_minutes": 30}, "005930.KS", kst(2026, 12, 30, 15, 10))
    assert result["status"] == "OK"


@pytest.mark.parametrize("at, status, reason", [
    (datetime(2026, 11, 27, 12, 40, tzinfo=ET), "OK", "TIME_WINDOW_SATISFIED"),      # 13:00 조기 폐장 30분 전
    (datetime(2026, 11, 27, 13, 30, tzinfo=ET), "WAIT", "OUTSIDE_SESSION"),          # 평소라면 장중
    (datetime(2026, 11, 30, 15, 40, tzinfo=ET), "OK", "TIME_WINDOW_SATISFIED"),      # 다음 거래일은 평소대로
])
def test_us_early_close(at, status, reason):
    result = evaluate_time_window({"only_before_close_minutes": 30}, "TSLA", at)
    assert (result["status"], result["reason"]) == (status, reason)


def test_unannounced_special_session_is_not_guessed():
    """특수일에 거래소가 공지하지 않은 세션은 추측하지 않고 WAIT로 둔다."""
    sessions = load_sessions()
    csat = sessions["markets"]["KRX"]["special_days"][0]
    del csat["sessions"]["after_hours"]
    csat["unconfirmed_sessions"] = ["after_hours"]
    result = evaluate_time_window({"market_session": "after_hours"}, "005930.KS", kst(2026, 11, 19, 17, 0), sessions)
    assert result["reason"] == "SESSION_SCHEDULE_UNCONFIRMED"


@pytest.mark.parametrize("text, session", [
    ("카카오 애프터마켓에서 3% 떨어지면 10만원만 매수", "after_hours"),
    ("삼성전자 시간외에 2% 오르면 알려줘", "after_hours"),
    ("카카오 프리마켓에서 3% 떨어지면 알려줘", "pre_market"),
    ("카카오 3% 떨어지면 장 마감 30분 전에만 매수", "regular"),
])
def test_parser_detects_session(text, session):
    from intent_parser import detect_time_window

    assert detect_time_window(text)["market_session"] == session


def test_runtime_handler_applies_time_window(monkeypatch):
    """로컬 런타임도 룰의 시간 조건을 판정한다(B1)."""
    import importlib.util

    runtime = ROOT / "src" / "runtime"
    monkeypatch.syspath_prepend(str(runtime))
    for path in runtime.glob("*.py"):  # 같은 이름의 스킬 모듈이 캐시돼 있으면 런타임 모듈로 다시 읽게 한다
        monkeypatch.delitem(sys.modules, path.stem, raising=False)
    monkeypatch.setenv("SAFE_TRADE_METRICS_LOG", "0")
    spec = importlib.util.spec_from_file_location("runtime_handler_b1", runtime / "runtime_handler.py")
    handler = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(handler)
    event = json.loads((runtime / "sample_events" / "matched_manual_confirm.json").read_text(encoding="utf-8"))
    now = int(kst(2026, 11, 18, 10, 0).timestamp())
    monkeypatch.setattr(handler.time, "time", lambda: now)
    event["quote"].update(timestamp=now, age_seconds=0)

    assert handler.handle_event(json.loads(json.dumps(event)))["decision"] == "MANUAL_CONFIRM"
    event["rule"]["time_window"] = {"market_session": "regular", "only_before_close_minutes": 30}
    held = handler.handle_event(json.loads(json.dumps(event)))
    assert held["decision"] == "WAIT"
    assert held["trigger_evaluation"]["reason"] == "TIME_WINDOW_BEFORE_CLOSING_WINDOW"


# ── 종목 인식 ──────────────────────────────────────────────


@pytest.mark.parametrize("text, symbol", [
    ("SK하이닉스 7% 오르면 절반 팔아줘", "000660.KS"),
    ("네이버 평단 대비 10% 손실이면 손절 알림", "035420.KS"),
    ("테슬라 5% 떨어지면 1주 매수 후보", "TSLA"),
    ("AAPL 3% 떨어지면 10만원만 매수", "AAPL"),
    ("TIGER 미국S&P500 2% 떨어지면 10만원만 매수", "360750.KS"),
    ("에코프로비엠 5% 떨어지면 알려줘", "247540.KQ"),   # '에코프로'보다 긴 이름 우선
    ("카카오뱅크 3% 오르면 알려줘", "323410.KS"),       # '카카오'보다 긴 이름 우선
    ("카카오 3% 떨어지면 100000원만 매수", "035720.KS"),  # 100000원은 종목코드가 아님
    ("086520 3% 떨어지면 알려줘", "086520.KQ"),
    ("123456 3% 떨어지면 알려줘", "123456.KS"),
    ("ETF 아무거나 사줘", "UNKNOWN"),
])
def test_detect_asset(text, symbol):
    assert detect_asset(text)["symbol"] == symbol


def test_rule_json_market_suffix_is_corrected():
    from normalizer import normalize_payload

    payload = {"asset": {"symbol": "086520.KS", "name": "에코프로"}}
    assert normalize_payload(payload)["asset"]["symbol"] == "086520.KQ"
    assert normalize_payload({"asset": {"symbol": "테슬라"}})["asset"]["symbol"] == "TSLA"


# ── 금액 표현 ──────────────────────────────────────────────


@pytest.mark.parametrize("text, amount", [
    ("10만원만 매수", 100_000),
    ("50만원어치 사줘", 500_000),
    ("100만원 매수", 1_000_000),
    ("100만 원 매수", 1_000_000),
    ("1,000,000원 매수", 1_000_000),
    ("1억원 매수", 100_000_000),
    ("55000원만 매수", 55_000),
    ("카카오 4만원 아래로 내려가면 20만원어치 매수", 200_000),
    ("4만원 아래로 내려가면 알려줘", None),       # 가격 조건
    ("주가가 4만원 되면 알려줘", None),
    ("4만원에 사줘", None),                       # 지정가
])
def test_detect_amount(text, amount):
    assert detect_amount_krw(text) == amount


def test_market_sessions_have_sources():
    data = json.loads((ROOT / "src" / "runtime" / "market_sessions.json").read_text(encoding="utf-8"))
    for market in data["markets"].values():
        for session in market["sessions"].values():
            assert session["source"] in data["sources"]
        for special in market["special_days"]:
            assert special["source"] in data["sources"]
    assert data["morning_source"] in data["sources"]


# ── 달러 가격 조건 ─────────────────────────────────────────


@pytest.mark.parametrize("text, kind, price, currency", [
    ("테슬라 200달러 아래로 내려가면 알려줘", "price_cross_below", 200.0, "USD"),
    ("애플 $180 넘으면 알려줘", "price_cross_above", 180.0, "USD"),
    ("엔비디아 $1,050.5를 돌파하면 알려줘", "price_cross_above", 1050.5, "USD"),
    ("TSLA 300불 이하로 떨어지면 1주 매수", "price_cross_below", 300.0, "USD"),
    ("카카오가 4만원을 넘으면 알려줘", "price_cross_above", 40000.0, "KRW"),
    ("035720 55000원 아래로 내려가면 알림만 줘", "price_cross_below", 55000.0, "KRW"),
    ("카카오 10만원만 매수, 3% 이상 떨어지면", "price_drop_percent", None, None),  # 10만원은 주문 금액
])
def test_price_conditions_in_krw_and_usd(text, kind, price, currency):
    from intent_parser import detect_trigger

    trigger = detect_trigger(text)
    assert trigger["type"] == kind
    assert trigger.get("price") == price
    assert (trigger.get("currency") if price else None) == currency


def test_price_level_is_not_an_order_amount():
    assert detect_amount_krw("카카오가 4만원을 넘으면 알려줘") is None
    assert detect_amount_krw("카카오 4만원 아래로 내려가면 20만원어치 매수") == 200_000


def test_currency_mismatch_stops_price_trigger():
    from evaluation import evaluate_trigger_fields

    usd_quote = {"regular_market_price": 190.0, "currency": "USD"}
    krw_rule = {"type": "price_cross_below", "price": 200000.0, "currency": "KRW"}
    usd_rule = {"type": "price_cross_below", "price": 200.0, "currency": "USD"}
    assert evaluate_trigger_fields(krw_rule, usd_quote)["reason"] == "TRIGGER_CURRENCY_MISMATCH"
    assert evaluate_trigger_fields(usd_rule, usd_quote)["status"] == "MATCHED"
