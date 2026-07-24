from __future__ import annotations

from typing import Any

from schema import ParsedRule

ASSET_SYMBOL_ALIASES = {
    "카카오": "035720.KS",
    "kakao": "035720.KS",
    "035720.KQ": "035720.KS",
    "카카오페이": "377300.KS",
    "kakao pay": "377300.KS",
    "377300.KQ": "377300.KS",
    "삼성전자": "005930.KS",
    "samsung electronics": "005930.KS",
    "005930.KQ": "005930.KS",
}


ACTION_ALIASES = {
    "buy": "prepare_buy_order",
    "prepare_buy": "prepare_buy_order",
    "buy_order": "prepare_buy_order",
    "prepare buy order": "prepare_buy_order",
    "매수": "prepare_buy_order",
    "매수 준비": "prepare_buy_order",
    "sell": "prepare_sell_order",
    "prepare_sell": "prepare_sell_order",
    "sell_order": "prepare_sell_order",
    "prepare sell order": "prepare_sell_order",
    "매도": "prepare_sell_order",
    "매도 준비": "prepare_sell_order",
    "alert": "notify_only",
    "notify": "notify_only",
    "notification": "notify_only",
    "alert_only": "notify_only",
    "notify_user": "notify_only",
    "알림": "notify_only",
    "알림만": "notify_only",
    "block": "block_order",
    "block_trade": "block_order",
    "reject": "block_order",
    "차단": "block_order",
    "clarify": "clarify_action",
    "ask_user": "clarify_action",
    "needs_clarification": "clarify_action",
}

EXECUTION_ALIASES = {
    "manual": "manual_confirm",
    "confirm": "manual_confirm",
    "manual confirmation": "manual_confirm",
    "manual_confirmation": "manual_confirm",
    "manual_review": "manual_confirm",
    "수동확인": "manual_confirm",
    "수동 확인": "manual_confirm",
    "alert": "notify_only",
    "notify": "notify_only",
    "notification": "notify_only",
    "notify_user": "notify_only",
    "알림": "notify_only",
    "알림만": "notify_only",
}

TRIGGER_TYPE_ALIASES = {
    "price_drop": "price_drop_percent",
    "drop_percent": "price_drop_percent",
    "percent_drop": "price_drop_percent",
    "falls_by_percent": "price_drop_percent",
    "decline_percent": "price_drop_percent",
    "price_rise": "price_rise_percent",
    "rise_percent": "price_rise_percent",
    "percent_rise": "price_rise_percent",
    "increases_by_percent": "price_rise_percent",
    "recent_high_drawdown": "recent_high_drop_percent",
    "drawdown_from_high": "recent_high_drop_percent",
    "high_drop_percent": "recent_high_drop_percent",
    "ma_breakdown": "moving_average_breakdown",
    "moving_average_cross_down": "moving_average_breakdown",
    "below_moving_average": "moving_average_breakdown",
    "volatility": "volatility_move_percent",
    "volatility_spike": "volatility_move_percent",
    "large_move": "volatility_move_percent",
    "cross_above": "price_cross_above",
    "price_above": "price_cross_above",
    "breakout": "price_cross_above",
    "cross_below": "price_cross_below",
    "price_below": "price_cross_below",
    "breakdown": "price_cross_below",
    "clarification_needed": "needs_clarification",
    "ambiguous": "needs_clarification",
}

REFERENCE_ALIASES = {
    "previous close": "previous_close",
    "prev_close": "previous_close",
    "yesterday_close": "previous_close",
    "전일종가": "previous_close",
    "전일 종가": "previous_close",
    "current": "current_price",
    "current price": "current_price",
    "현재가": "current_price",
    "average purchase": "average_purchase_price",
    "avg_purchase_price": "average_purchase_price",
    "평단": "average_purchase_price",
    "평균 매수가": "average_purchase_price",
    "moving average": "moving_average",
    "moving_avg": "moving_average",
    "ma": "moving_average",
    "이동평균": "moving_average",
    "recent high": "recent_high",
    "recent_high_price": "recent_high",
    "최근 고점": "recent_high",
}

ORDER_MODE_ALIASES = {
    "krw_amount": "amount",
    "cash_amount": "amount",
    "fixed_amount": "amount",
    "금액": "amount",
    "quantity": "shares",
    "share_count": "shares",
    "stock_count": "shares",
    "주식수": "shares",
    "half": "position_fraction",
    "fraction": "position_fraction",
    "position_percent": "portfolio_or_position_percent",
    "portfolio_percent": "portfolio_or_position_percent",
    "percent": "portfolio_or_position_percent",
    "unspecified": "required_before_activation",
    "missing": "required_before_activation",
}

SESSION_ALIASES = {
    "regular_session": "regular",
    "market_open": "regular",
    "정규장": "regular",
    "pre-market": "pre_market",
    "premarket": "pre_market",
    "after-hours": "after_hours",
    "after_market": "after_hours",
}

CANCEL_CONDITION_ALIASES = {
    "stale_quote": "quote_stale",
    "quote_delay": "quote_stale",
    "delayed_quote": "quote_stale",
    "negative_news": "negative_news_requires_manual_review",
    "bad_news": "negative_news_requires_manual_review",
    "volume_spike": "volume_spike_requires_manual_review",
    "broker_unstable": "provider_or_broker_unstable",
    "provider_unstable": "provider_or_broker_unstable",
    "server_unstable": "provider_or_broker_unstable",
    "daily_drop_limit": "daily_drop_exceeds_percent",
    "daily_loss_drop": "daily_drop_exceeds_percent",
}


def normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    data = dict(payload)
    if isinstance(data.get("asset"), dict):
        asset = dict(data["asset"])
        symbol = asset.get("symbol")
        name = asset.get("name")
        normalized_symbol = _asset_alias(symbol) or _asset_alias(name)
        if normalized_symbol:
            asset["symbol"] = normalized_symbol
        data["asset"] = asset
    if isinstance(data.get("trigger"), dict):
        trigger = dict(data["trigger"])
        if "type" in trigger:
            trigger["type"] = _alias(TRIGGER_TYPE_ALIASES, trigger["type"])
        if "from" in trigger and "reference" not in trigger:
            trigger["reference"] = trigger["from"]
        trigger.pop("from", None)
        if "reference" in trigger:
            trigger["reference"] = _alias(REFERENCE_ALIASES, trigger["reference"])
        data["trigger"] = trigger
    if "action" in data:
        data["action"] = _alias(ACTION_ALIASES, data["action"])
    if "execution_mode" in data:
        data["execution_mode"] = _alias(EXECUTION_ALIASES, data["execution_mode"])
    if isinstance(data.get("order"), dict) and "mode" in data["order"]:
        order = dict(data["order"])
        order["mode"] = _alias(ORDER_MODE_ALIASES, order["mode"])
        data["order"] = order
    if isinstance(data.get("time_window"), dict) and "market_session" in data["time_window"]:
        time_window = dict(data["time_window"])
        time_window["market_session"] = _alias(SESSION_ALIASES, time_window["market_session"])
        data["time_window"] = time_window
    if isinstance(data.get("cancel_conditions"), list):
        normalized_conditions = []
        for condition in data["cancel_conditions"]:
            if isinstance(condition, str):
                normalized_conditions.append({"type": _alias(CANCEL_CONDITION_ALIASES, condition)})
            elif isinstance(condition, dict):
                item = dict(condition)
                if "type" in item:
                    item["type"] = _alias(CANCEL_CONDITION_ALIASES, item["type"])
                normalized_conditions.append(item)
        data["cancel_conditions"] = normalized_conditions
    data.setdefault("cancel_conditions", [{"type": "quote_stale"}])
    data.setdefault("parser", {"source": "unknown", "fallback_used": False})
    return data


def normalize_rule(rule: ParsedRule) -> ParsedRule:
    data = rule.model_dump()
    if data["action"] in {"notify_only", "block_order"}:
        data["execution_mode"] = "notify_only" if data["action"] == "notify_only" else "manual_confirm"
    if data["execution_mode"] not in {"notify_only", "manual_confirm"}:
        data["execution_mode"] = "manual_confirm"
    return ParsedRule.model_validate(data)


def _alias(table: dict[str, str], value: Any) -> Any:
    key = str(value).strip()
    normalized_key = key.lower().replace("-", "_")
    return table.get(key, table.get(normalized_key, value))


def _asset_alias(value: Any) -> str | None:
    if value is None:
        return None
    key = str(value).strip()
    normalized_key = key.lower().replace("-", "_")
    return ASSET_SYMBOL_ALIASES.get(key) or ASSET_SYMBOL_ALIASES.get(normalized_key)
