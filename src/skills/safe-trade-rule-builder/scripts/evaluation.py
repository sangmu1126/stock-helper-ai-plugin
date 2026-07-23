from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from models import MAX_QUOTE_AGE_SECONDS, OPEN_MARKET_STATES, MarketQuote


def evaluate_trigger(trigger: dict[str, Any], quote: MarketQuote | dict[str, Any] | None) -> dict[str, Any] | None:
    if quote is None:
        return None
    quote_data = _quote_to_dict(quote)
    health = quote_data.get("health", {})
    if not health.get("ok"):
        return {
            "status": "STOP",
            "reason": "MARKET_DATA_HEALTHCHECK_FAILED",
            "details": health,
        }
    market_state = quote_data.get("market_state")
    if market_state not in OPEN_MARKET_STATES:
        return {
            "status": "STOP",
            "reason": "MARKET_NOT_OPEN",
            "details": {
                "market_state": market_state,
                "allowed_states": sorted(OPEN_MARKET_STATES),
            },
        }
    age_seconds = int_or_none(quote_data.get("age_seconds"))
    if age_seconds is None:
        return {"status": "STOP", "reason": "MISSING_QUOTE_AGE"}
    if age_seconds < 0:
        return {"status": "STOP", "reason": "INVALID_NEGATIVE_QUOTE_AGE"}
    if age_seconds > MAX_QUOTE_AGE_SECONDS:
        return {
            "status": "STOP",
            "reason": "STALE_QUOTE",
            "details": {
                "age_seconds": age_seconds,
                "max_quote_age_seconds": MAX_QUOTE_AGE_SECONDS,
            },
        }
    return evaluate_trigger_fields(trigger, quote_data)


def evaluate_trigger_fields(trigger: dict[str, Any], quote: dict[str, Any]) -> dict[str, Any]:
    trigger_type = trigger.get("type")
    reference = trigger.get("reference") or trigger.get("from")
    current_price = float_or_none(
        quote.get("regular_market_price")
        or quote.get("current_price")
        or quote.get("price")
    )
    previous_close = float_or_none(quote.get("previous_close"))
    day_high = float_or_none(quote.get("day_high"))
    trigger_percent = float_or_none(trigger.get("percent")) or 0.0
    trigger_price = float_or_none(trigger.get("price"))

    if trigger_type in {"price_drop_percent", "price_rise_percent"}:
        if reference != "previous_close":
            return {
                "status": "WAIT",
                "reason": "UNSUPPORTED_REFERENCE_PRICE",
                "details": {"reference": reference, "supported_reference": "previous_close"},
            }
        if current_price is None or previous_close in (None, 0):
            return {"status": "STOP", "reason": "MISSING_PRICE_FOR_TRIGGER_EVALUATION"}
        move_percent = ((current_price - previous_close) / previous_close) * 100
        matched = (
            trigger_type == "price_drop_percent"
            and move_percent <= -trigger_percent
            or trigger_type == "price_rise_percent"
            and move_percent >= trigger_percent
        )
        return _trigger_result(
            matched,
            "Trigger condition matched.",
            "Trigger condition not met.",
            {
                "current_move_percent": round(move_percent, 4),
                "required_trigger_percent": trigger_percent,
                "reference_price": previous_close,
                "current_price": current_price,
            },
        )

    if trigger_type in {"price_cross_above", "price_cross_below"}:
        if current_price is None or trigger_price is None:
            return {"status": "STOP", "reason": "MISSING_PRICE_FOR_TRIGGER_EVALUATION"}
        matched = (
            trigger_type == "price_cross_above"
            and current_price >= trigger_price
            or trigger_type == "price_cross_below"
            and current_price <= trigger_price
        )
        return _trigger_result(
            matched,
            "Trigger price crossed.",
            "Trigger price not crossed.",
            {"current_price": current_price, "trigger_price": trigger_price},
        )

    if trigger_type == "recent_high_drop_percent":
        reference_high = float_or_none(quote.get("recent_high")) or day_high
        if current_price is None or reference_high in (None, 0):
            return {"status": "STOP", "reason": "MISSING_RECENT_HIGH_FOR_TRIGGER_EVALUATION"}
        drawdown_percent = ((current_price - reference_high) / reference_high) * 100
        matched = drawdown_percent <= -trigger_percent
        return _trigger_result(
            matched,
            "Recent-high drawdown matched.",
            "Recent-high drawdown not met.",
            {
                "drawdown_percent": round(drawdown_percent, 4),
                "required_trigger_percent": trigger_percent,
                "reference_high": reference_high,
            },
        )

    if trigger_type == "moving_average_breakdown":
        moving_average = float_or_none(quote.get("moving_average"))
        if current_price is None or moving_average in (None, 0):
            return {"status": "STOP", "reason": "MISSING_MOVING_AVERAGE_FOR_TRIGGER_EVALUATION"}
        distance_percent = ((current_price - moving_average) / moving_average) * 100
        matched = current_price < moving_average
        return _trigger_result(
            matched,
            "Moving-average breakdown matched.",
            "Moving-average breakdown not met.",
            {"distance_percent": round(distance_percent, 4), "moving_average": moving_average},
        )

    if trigger_type == "volatility_move_percent":
        move_percent = float_or_none(quote.get("move_percent"))
        if move_percent is None and current_price is not None and previous_close not in (None, 0):
            move_percent = ((current_price - previous_close) / previous_close) * 100
        if move_percent is None:
            return {"status": "STOP", "reason": "MISSING_MOVE_FOR_VOLATILITY_EVALUATION"}
        matched = abs(move_percent) >= trigger_percent
        return _trigger_result(
            matched,
            "Volatility threshold matched.",
            "Volatility threshold not met.",
            {
                "absolute_move_percent": round(abs(move_percent), 4),
                "required_trigger_percent": trigger_percent,
            },
        )

    return {
        "status": "WAIT",
        "reason": "UNSUPPORTED_TRIGGER_TYPE",
        "details": {"trigger_type": trigger_type},
    }


def int_or_none(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def float_or_none(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _quote_to_dict(quote: MarketQuote | dict[str, Any]) -> dict[str, Any]:
    if isinstance(quote, dict):
        return quote
    if is_dataclass(quote):
        return asdict(quote)
    return {
        "regular_market_price": getattr(quote, "regular_market_price", None),
        "previous_close": getattr(quote, "previous_close", None),
        "day_high": getattr(quote, "day_high", None),
        "market_state": getattr(quote, "market_state", None),
        "age_seconds": getattr(quote, "age_seconds", None),
        "health": getattr(quote, "health", {}),
    }


def _trigger_result(
    matched: bool,
    matched_reason: str,
    wait_reason: str,
    details: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": "MATCHED" if matched else "WAIT",
        "reason": matched_reason if matched else wait_reason,
        "details": details,
    }
