"""룰 빌더 보강 테스트: 시간 조건 적용, 종목 인식 확대(국내·미국), 금액 표현 확대."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import tomllib

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
    ({"only_before_close_minutes": 30}, kst(2026, 11, 18, 15, 30), "WAIT", "OUTSIDE_REGULAR_SESSION"),
    ({"only_before_close_minutes": 30}, kst(2026, 11, 21, 15, 10), "WAIT", "OUTSIDE_REGULAR_SESSION"),  # 토요일
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
    """룰 빌더와 거래시간 점검기가 같은 정규장 기준을 쓰는지 확인한다."""
    sessions = load_sessions()["markets"]
    calendar_path = ROOT / "src" / "skills" / "market-hours-guard" / "assets" / "calendar.demo.toml"
    boundaries = {b["id"]: b for b in tomllib.loads(calendar_path.read_text(encoding="utf-8"))["boundary"]}
    assert sessions["KRX"]["open"] == boundaries["KRX_REGULAR_OPEN"]["time"]
    assert sessions["KRX"]["close"] == boundaries["KRX_REGULAR_CLOSE"]["time"]
    assert sessions["US"]["open"] == boundaries["US_REGULAR_OPEN"]["time"]
    assert sessions["US"]["close"] == boundaries["US_REGULAR_CLOSE"]["time"]
    assert sessions["US"]["tz"] == boundaries["US_REGULAR_OPEN"]["tz"]


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


def test_llm_output_market_suffix_is_corrected():
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
    data = json.loads((ROOT / "src" / "skills" / "safe-trade-rule-builder" / "config" / "market_sessions.json").read_text(encoding="utf-8"))
    for market in data["markets"].values():
        assert market["source"] in data["sources"]
