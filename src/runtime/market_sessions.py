"""룰의 세션·시간 조건 판정 (로컬 런타임과 스킬이 함께 쓴다).

- 세션: 정규장(regular), 애프터마켓(after_hours). 종목 시장(KRX·미국)의 현지 시각으로 판정한다.
- 특수일: 수능일·미국 조기 폐장처럼 거래소가 시간을 바꾼 날은 그날의 시각을 쓴다. 공지되지 않은 세션은 통과시키지 않는다.
- 휴장일: 거래소가 공지한 휴장일 달력(확인 범위 confirmed_through 포함)을 쓴다. 휴장일과 확인 범위 밖 날짜는 WAIT.
- 조건: 장 초반 제외, 오전 제외, 마감 N분 전에만, N일 연속(단일 시세로 확인 불가 → WAIT).

시간 조건이 없는 정규장 룰은 판정하지 않는다(기존 동작 유지). 외부 서비스에 접속하지 않는다.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

SESSIONS_PATH = Path(__file__).resolve().parent / "market_sessions.json"
CONSTRAINT_KEYS = ("exclude_open_minutes", "exclude_morning", "only_before_close_minutes", "requires_consecutive_days")
# 세션별로 허용하는 시세 제공자의 시장 상태 값
SESSION_MARKET_STATES = {
    "regular": frozenset({"OPEN", "REGULAR"}),
    "after_hours": frozenset({"OPEN", "REGULAR", "POST", "POSTPOST", "AFTER_HOURS"}),
    "pre_market": frozenset({"OPEN", "REGULAR", "PRE", "PREPRE", "PRE_MARKET"}),
}
SESSION_LABEL = {"regular": "정규장", "after_hours": "애프터마켓", "pre_market": "프리마켓"}


def load_sessions(path: Path | None = None) -> dict[str, Any]:
    return json.loads((path or SESSIONS_PATH).read_text(encoding="utf-8"))


def market_for_symbol(symbol: str, sessions: dict[str, Any]) -> str:
    upper = (symbol or "").upper()
    for market, spec in sessions["markets"].items():
        if any(upper.endswith(suffix) for suffix in spec["symbol_suffixes"]):
            return market
    return "US"


def allowed_market_states(time_window: dict[str, Any] | None) -> frozenset[str]:
    session = (time_window or {}).get("market_session") or "regular"
    return SESSION_MARKET_STATES.get(session, SESSION_MARKET_STATES["regular"])


def has_constraints(time_window: dict[str, Any] | None) -> bool:
    if not time_window:
        return False
    if (time_window.get("market_session") or "regular") != "regular":
        return True
    return any(time_window.get(key) for key in CONSTRAINT_KEYS)


def _hhmm(text: str) -> time:
    hour, minute = text.split(":")
    return time(int(hour), int(minute))


def _shift(value: time, minutes: int) -> time:
    total = (value.hour * 60 + value.minute + minutes) % (24 * 60)
    return time(total // 60, total % 60)


def market_holidays(market: str, sessions: dict[str, Any] | None = None) -> tuple[frozenset[date], date | None]:
    """거래소 휴장일과 달력 확인 범위의 끝(없으면 None)."""
    calendar = (sessions or load_sessions())["markets"][market].get("holidays")
    if not calendar:
        return frozenset(), None
    days = frozenset(date.fromisoformat(d) for d in calendar["days"])
    return days, date.fromisoformat(calendar["confirmed_through"])


def day_status(market_spec: dict[str, Any], day: date) -> dict[str, Any]:
    """그날이 거래일인지. status: TRADING_DAY / WEEKEND / HOLIDAY / UNCONFIRMED(휴장일 달력 확인 범위 밖)."""
    if day.weekday() >= 5:
        return {"status": "WEEKEND"}
    calendar = market_spec.get("holidays")
    if not calendar:
        return {"status": "TRADING_DAY"}
    name = calendar["days"].get(day.isoformat())
    if name:
        return {"status": "HOLIDAY", "name": name, "source": calendar["source"]}
    if day > date.fromisoformat(calendar["confirmed_through"]):
        return {"status": "UNCONFIRMED", "confirmed_through": calendar["confirmed_through"]}
    return {"status": "TRADING_DAY"}


def session_hours(market_spec: dict[str, Any], session: str, day: date) -> dict[str, Any]:
    """그날의 세션 시각. status: OK / NOT_AVAILABLE(없는 세션·시행 전) / UNCONFIRMED(특수일 미공지)."""
    special = next((s for s in market_spec.get("special_days", []) if s["date"] == day.isoformat()), None)
    if special and session in special.get("sessions", {}):
        hours = special["sessions"][session]
        return {"status": "OK", "open": hours["open"], "close": hours["close"], "special_day": special}
    if special and session in special.get("unconfirmed_sessions", []):
        return {"status": "UNCONFIRMED", "special_day": special}
    spec = market_spec["sessions"].get(session)
    if spec is None:
        return {"status": "NOT_AVAILABLE"}
    if spec.get("effective_from") and day < date.fromisoformat(spec["effective_from"]):
        return {"status": "NOT_AVAILABLE", "effective_from": spec["effective_from"]}
    return {"status": "OK", "open": spec["open"], "close": spec["close"], "special_day": special}


def evaluate_time_window(time_window: dict[str, Any], symbol: str, at: datetime,
                         sessions: dict[str, Any] | None = None) -> dict[str, Any]:
    """조건을 만족하면 status=OK, 아니면 WAIT와 이유를 돌려준다. at은 시간대 정보가 있어야 한다."""
    sessions = sessions or load_sessions()
    market = market_for_symbol(symbol, sessions)
    spec = sessions["markets"][market]
    session = time_window.get("market_session") or "regular"
    local = at.astimezone(ZoneInfo(spec["tz"]))
    hours = session_hours(spec, session, local.date())
    details: dict[str, Any] = {
        "market": market,
        "session": session,
        "local_time": local.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "sessions_version": sessions["version"],
        "constraints": {key: time_window.get(key) for key in CONSTRAINT_KEYS if time_window.get(key)},
    }
    if hours.get("special_day"):
        details["special_day"] = hours["special_day"]["name"]

    def wait(reason: str, message: str) -> dict[str, Any]:
        return {"status": "WAIT", "reason": reason, "message": message, "details": details}

    label = SESSION_LABEL.get(session, session)
    day = day_status(spec, local.date())
    if day["status"] == "HOLIDAY":
        details["holiday"] = day["name"]
        return wait("MARKET_HOLIDAY", f"{local.date()}은 {market} 휴장일({day['name']})입니다.")
    if day["status"] == "UNCONFIRMED":
        return wait("HOLIDAY_CALENDAR_UNCONFIRMED",
                    f"{market} 휴장일 달력은 {day['confirmed_through']}까지만 확인됐습니다. "
                    "거래소 공지로 달력을 갱신하기 전에는 판정하지 않습니다.")
    if hours["status"] == "UNCONFIRMED":
        return wait("SESSION_SCHEDULE_UNCONFIRMED",
                    f"{hours['special_day']['name']}의 {label} 시간은 거래소 공지로 확인되지 않아 판정하지 않습니다.")
    if hours["status"] == "NOT_AVAILABLE":
        since = f"({hours['effective_from']}부터)" if hours.get("effective_from") else ""
        return wait("SESSION_NOT_AVAILABLE", f"{market} 시장에서는 이날 {label}을 운영하지 않습니다{since}.")
    open_, close, now = _hhmm(hours["open"]), _hhmm(hours["close"]), local.time()
    details["session_hours"] = f"{hours['open']}~{hours['close']} {spec['tz']}"
    if local.weekday() >= 5 or not open_ <= now < close:
        return wait("OUTSIDE_SESSION", f"현지 시각 {now:%H:%M}은 {label}({hours['open']}~{hours['close']}) 밖입니다.")
    minutes = time_window.get("exclude_open_minutes")
    if minutes and now < _shift(open_, int(minutes)):
        return wait("WITHIN_OPENING_EXCLUSION", f"{label} 시작 후 {minutes}분 동안은 제외 조건입니다.")
    if time_window.get("exclude_morning") and session == "regular" and now < _hhmm(spec["morning_end"]):
        return wait("MORNING_EXCLUDED", f"오전({spec['morning_end']} 전)은 제외 조건입니다.")
    minutes = time_window.get("only_before_close_minutes")
    if minutes and now < _shift(close, -int(minutes)):
        start = _shift(close, -int(minutes))
        return wait("BEFORE_CLOSING_WINDOW", f"{label} 마감 {minutes}분 전({start:%H:%M}) 이후에만 허용됩니다.")
    days = time_window.get("requires_consecutive_days")
    if days:
        return wait("CONSECUTIVE_DAYS_NOT_VERIFIED",
                    f"{days}일 연속 조건은 단일 시세로 확인할 수 없어 통과시키지 않습니다.")
    return {"status": "OK", "reason": "TIME_WINDOW_SATISFIED", "message": "시간 조건을 만족합니다.", "details": details}


def apply_time_window(trigger_evaluation: dict[str, Any] | None, time_window: dict[str, Any] | None,
                      symbol: str, quote_timestamp: int | None,
                      sessions: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """가격 조건이 MATCHED여도 세션·시간 조건을 못 맞추면 WAIT로 바꾼다. 조건이 없으면 그대로 둔다."""
    if trigger_evaluation is None or not has_constraints(time_window):
        return trigger_evaluation
    result = dict(trigger_evaluation)
    if quote_timestamp is None:
        if result.get("status") == "MATCHED":
            result.update(status="WAIT", reason="TIME_WINDOW_NOT_EVALUATED")
        return result
    at = datetime.fromtimestamp(int(quote_timestamp), tz=UTC)
    window = evaluate_time_window(time_window or {}, symbol, at, sessions)
    result["time_window"] = window
    if result.get("status") == "MATCHED" and window["status"] != "OK":
        result.update(status="WAIT", reason=f"TIME_WINDOW_{window['reason']}")
    return result
