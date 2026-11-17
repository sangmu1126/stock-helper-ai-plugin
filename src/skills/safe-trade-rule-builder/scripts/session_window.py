"""룰의 시간 조건 판정.

파서는 "장 초반 제외", "오전 제외", "장 마감 30분 전에만", "3일 연속"을 time_window에 담는다.
이 모듈은 시세 시각을 종목 시장(KRX·미국)의 현지 시각으로 바꿔 그 조건을 실제로 판정한다.
미국 종목은 America/New_York 기준이라 서머타임 전후에도 '마감 30분 전'이 정확히 계산된다.

조건이 없는 룰은 판정하지 않는다(기존 동작 유지). 판정할 수 없는 조건은 통과시키지 않고 WAIT로 둔다.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

SESSIONS_PATH = Path(__file__).resolve().parents[1] / "config" / "market_sessions.json"
CONSTRAINT_KEYS = ("exclude_open_minutes", "exclude_morning", "only_before_close_minutes", "requires_consecutive_days")


def load_sessions(path: Path | None = None) -> dict[str, Any]:
    return json.loads((path or SESSIONS_PATH).read_text(encoding="utf-8"))


def market_for_symbol(symbol: str, sessions: dict[str, Any]) -> str:
    upper = (symbol or "").upper()
    for market, spec in sessions["markets"].items():
        if any(upper.endswith(suffix) for suffix in spec["symbol_suffixes"]):
            return market
    return "US"


def has_constraints(time_window: dict[str, Any] | None) -> bool:
    return bool(time_window) and any(time_window.get(key) for key in CONSTRAINT_KEYS)


def _hhmm(text: str) -> time:
    hour, minute = text.split(":")
    return time(int(hour), int(minute))


def _shift(value: time, minutes: int) -> time:
    """하루 안의 시각을 분 단위로 이동한다(날짜·시간대와 무관한 벽시계 계산)."""
    total = (value.hour * 60 + value.minute + minutes) % (24 * 60)
    return time(total // 60, total % 60)


def evaluate_time_window(time_window: dict[str, Any], symbol: str, at: datetime,
                         sessions: dict[str, Any] | None = None) -> dict[str, Any]:
    """조건을 만족하면 status=OK, 아니면 WAIT와 이유를 돌려준다. at은 시간대 정보가 있어야 한다."""
    sessions = sessions or load_sessions()
    market = market_for_symbol(symbol, sessions)
    spec = sessions["markets"][market]
    local = at.astimezone(ZoneInfo(spec["tz"]))
    now, open_, close = local.time(), _hhmm(spec["open"]), _hhmm(spec["close"])
    details: dict[str, Any] = {
        "market": market,
        "local_time": local.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "regular_session": f"{spec['open']}~{spec['close']} {spec['tz']}",
        "sessions_version": sessions["version"],
        "constraints": {key: time_window.get(key) for key in CONSTRAINT_KEYS if time_window.get(key)},
    }

    def wait(reason: str, message: str) -> dict[str, Any]:
        return {"status": "WAIT", "reason": reason, "message": message, "details": details}

    if time_window.get("market_session", "regular") != "regular":
        return wait("SESSION_CONSTRAINT_NOT_SUPPORTED",
                    f"{time_window.get('market_session')} 세션의 시간 조건은 아직 판정하지 않습니다.")
    if local.weekday() >= 5 or not open_ <= now < close:
        return wait("OUTSIDE_REGULAR_SESSION", f"현지 시각 {now:%H:%M}은 정규장({spec['open']}~{spec['close']}) 밖입니다.")
    minutes = time_window.get("exclude_open_minutes")
    if minutes and now < _shift(open_, int(minutes)):
        return wait("WITHIN_OPENING_EXCLUSION", f"장 시작 후 {minutes}분 동안은 제외 조건입니다.")
    if time_window.get("exclude_morning") and now < _hhmm(spec["morning_end"]):
        return wait("MORNING_EXCLUDED", f"오전({spec['morning_end']} 전)은 제외 조건입니다.")
    minutes = time_window.get("only_before_close_minutes")
    if minutes and now < _shift(close, -int(minutes)):
        start = _shift(close, -int(minutes))
        return wait("BEFORE_CLOSING_WINDOW", f"장 마감 {minutes}분 전({start:%H:%M}) 이후에만 허용됩니다.")
    days = time_window.get("requires_consecutive_days")
    if days:
        return wait("CONSECUTIVE_DAYS_NOT_VERIFIED",
                    f"{days}일 연속 조건은 단일 시세로 확인할 수 없어 통과시키지 않습니다.")
    return {"status": "OK", "reason": "TIME_WINDOW_SATISFIED", "message": "시간 조건을 만족합니다.", "details": details}


def apply_time_window(trigger_evaluation: dict[str, Any] | None, time_window: dict[str, Any] | None,
                      symbol: str, quote_timestamp: int | None,
                      sessions: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """가격 조건이 MATCHED여도 시간 조건을 못 맞추면 WAIT로 바꾼다. 조건이 없으면 그대로 둔다."""
    if trigger_evaluation is None or not has_constraints(time_window):
        return trigger_evaluation
    if quote_timestamp is None:
        result = dict(trigger_evaluation)
        if result.get("status") == "MATCHED":
            result.update(status="WAIT", reason="TIME_WINDOW_NOT_EVALUATED")
        return result
    at = datetime.fromtimestamp(int(quote_timestamp), tz=UTC)
    window = evaluate_time_window(time_window, symbol, at, sessions)
    result = dict(trigger_evaluation)
    result["time_window"] = window
    if result.get("status") == "MATCHED" and window["status"] != "OK":
        result.update(status="WAIT", reason=f"TIME_WINDOW_{window['reason']}")
    return result
