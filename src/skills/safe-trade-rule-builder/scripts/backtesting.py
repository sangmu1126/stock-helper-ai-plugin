from __future__ import annotations

from typing import Any

SUPPORTED_TRIGGERS = {
    "price_drop_percent",
    "price_rise_percent",
    "recent_high_drop_percent",
    "moving_average_breakdown",
    "price_cross_above",
    "price_cross_below",
    "volatility_move_percent",
}


def backtest_rule(
    trigger: dict[str, Any],
    history: dict[str, Any],
    *,
    max_events: int = 10,
) -> dict[str, Any]:
    health = history.get("health", {})
    if not health.get("ok"):
        return {
            "status": "STOP",
            "reason": "HISTORY_DATA_HEALTHCHECK_FAILED",
            "history": {
                "provider": history.get("provider"),
                "symbol": history.get("symbol"),
                "period": history.get("period"),
                "interval": history.get("interval"),
                "bar_count": len(history.get("bars", [])),
                "health": health,
            },
        }

    bars = history.get("bars", [])
    trigger_type = trigger.get("type")
    trigger_percent = _float_or_none(trigger.get("percent")) or 0.0
    if trigger_type not in SUPPORTED_TRIGGERS:
        return {
            "status": "WAIT",
            "reason": "UNSUPPORTED_TRIGGER_FOR_BACKTEST",
            "supported_triggers": sorted(SUPPORTED_TRIGGERS),
        }

    events: list[dict[str, Any]] = []
    moves: list[float] = []
    closes: list[float] = []
    current_no_trigger_streak = 0
    longest_no_trigger_streak = 0
    trigger_count = 0
    evaluable_bars = 0
    lookback_days = _int_or_default(trigger.get("lookback_days"), 20)
    cross_price = trigger.get("price")
    trigger_price = _float_or_none(cross_price)

    for bar in bars:
        close = _float_or_none(bar.get("close"))
        move = bar.get("move_percent")
        move_float = _float_or_none(move)
        if move_float is not None:
            moves.append(move_float)
        matched, metric = _matches_trigger(
            trigger_type=trigger_type,
            trigger_percent=trigger_percent,
            trigger_price=trigger_price,
            close=close,
            move_percent=move_float,
            prior_closes=closes,
            lookback_days=lookback_days,
        )
        if close is not None:
            closes.append(close)
        if metric is None:
            continue
        evaluable_bars += 1
        if matched:
            trigger_count += 1
            current_no_trigger_streak = 0
            if len(events) < max_events:
                event = {
                    "date": bar.get("date"),
                    "close": close,
                    "previous_close": bar.get("previous_close"),
                    "move_percent": move_float,
                    "trigger_metric": round(metric, 4),
                }
                events.append(event)
        else:
            current_no_trigger_streak += 1
            longest_no_trigger_streak = max(longest_no_trigger_streak, current_no_trigger_streak)

    trigger_rate = (trigger_count / evaluable_bars) if evaluable_bars else 0
    max_daily_move = max(moves) if moves else None
    min_daily_move = min(moves) if moves else None
    max_abs_move = max((abs(move) for move in moves), default=0)

    warnings: list[str] = []
    if evaluable_bars < 20:
        warnings.append("INSUFFICIENT_HISTORY_FOR_CONFIDENCE")
    if trigger_count == 0:
        warnings.append("NO_TRIGGER_EVENTS_FOUND")
    if trigger_rate > 0.2:
        warnings.append("TRIGGER_TOO_FREQUENT_FOR_BEGINNER_GUARDRAIL")
    if max_abs_move >= 10:
        warnings.append("HIGH_VOLATILITY_PERIOD_INCLUDED")

    return {
        "status": "SIMULATED",
        "history": {
            "provider": history.get("provider"),
            "symbol": history.get("symbol"),
            "period": history.get("period"),
            "interval": history.get("interval"),
            "bar_count": len(bars),
            "evaluable_bar_count": evaluable_bars,
        },
        "rule": {
            "trigger_type": trigger_type,
            "trigger_percent": trigger_percent,
            "trigger_price": trigger_price,
            "lookback_days": lookback_days if trigger_type in {"recent_high_drop_percent", "moving_average_breakdown"} else None,
            "reference": trigger.get("reference") or trigger.get("from"),
        },
        "results": {
            "trigger_count": trigger_count,
            "trigger_rate": round(trigger_rate, 4),
            "longest_no_trigger_streak": longest_no_trigger_streak,
            "min_daily_move_percent": None if min_daily_move is None else round(min_daily_move, 4),
            "max_daily_move_percent": None if max_daily_move is None else round(max_daily_move, 4),
            "sample_events": events,
        },
        "safety_review": {
            "purpose": "safety_behavior_review",
            "not_profit_forecast": True,
            "warnings": warnings,
            "recommendation": (
                "Review warnings and require manual confirmation. This backtest only checks "
                "historical trigger behavior, not profitability or future performance."
            ),
        },
    }


def _matches_trigger(
    *,
    trigger_type: str,
    trigger_percent: float,
    trigger_price: float | None,
    close: float | None,
    move_percent: float | None,
    prior_closes: list[float],
    lookback_days: int,
) -> tuple[bool, float | None]:
    if trigger_type == "price_drop_percent":
        if move_percent is None:
            return False, None
        return move_percent <= -trigger_percent, move_percent
    if trigger_type == "price_rise_percent":
        if move_percent is None:
            return False, None
        return move_percent >= trigger_percent, move_percent
    if trigger_type == "price_cross_above":
        if close is None or trigger_price is None:
            return False, None
        return close >= trigger_price, close
    if trigger_type == "price_cross_below":
        if close is None or trigger_price is None:
            return False, None
        return close <= trigger_price, close
    if trigger_type == "recent_high_drop_percent":
        if close is None or len(prior_closes) < lookback_days:
            return False, None
        recent_high = max(prior_closes[-lookback_days:])
        if recent_high == 0:
            return False, None
        drawdown_percent = ((close - recent_high) / recent_high) * 100
        return drawdown_percent <= -trigger_percent, drawdown_percent
    if trigger_type == "moving_average_breakdown":
        if close is None or len(prior_closes) < lookback_days:
            return False, None
        moving_average = sum(prior_closes[-lookback_days:]) / lookback_days
        if moving_average == 0:
            return False, None
        distance_percent = ((close - moving_average) / moving_average) * 100
        return close < moving_average, distance_percent
    if trigger_type == "volatility_move_percent":
        if move_percent is None:
            return False, None
        return abs(move_percent) >= trigger_percent, abs(move_percent)
    return False, None


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_default(value: Any, default: int) -> int:
    try:
        if value is None or value == "":
            return default
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default
