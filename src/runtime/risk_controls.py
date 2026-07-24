from __future__ import annotations

from typing import Any

from config_provider import ConfigSnapshot, load_config

DEFAULT_RISK_LIMITS: dict[str, Any] = {
    "version": "risk.safe-trade.v2",
    "variables": {
        "max_daily_loss_pct": 3.0,
        "max_order_amount": 500000,
        "max_broker_latency_ms": 2000,
        "max_quote_age_seconds": 15,
        "allow_order_preparation": True,
        "allow_live_order_submission": False,
    },
    "rules": [
        {
            "id": "broker_latency",
            "condition": "broker_latency_exceeded",
            "reason": "BROKER_LATENCY_LIMIT_EXCEEDED"
        },
        {
            "id": "daily_loss",
            "condition": "daily_loss_reached",
            "reason": "DAILY_LOSS_LIMIT_REACHED"
        },
        {
            "id": "order_amount",
            "condition": "order_amount_exceeded",
            "reason": "ORDER_AMOUNT_LIMIT_EXCEEDED"
        },
        {
            "id": "duplicate_order",
            "condition": "duplicate_order",
            "reason": "DUPLICATE_ORDER_BLOCKED"
        },
        {
            "id": "order_prep",
            "condition": "order_preparation_disabled",
            "reason": "ORDER_PREPARATION_DISABLED_BY_RISK_LIMITS"
        },
        {
            "id": "live_order",
            "condition": "live_order_submission",
            "reason": "LIVE_ORDER_SUBMISSION_DISABLED"
        }
    ]
}


def load_risk_limits() -> dict[str, Any]:
    return load_risk_limits_snapshot().data


def load_risk_limits_snapshot(limits: dict[str, Any] | None = None) -> ConfigSnapshot:
    if limits is not None:
        active_limits = DEFAULT_RISK_LIMITS.copy()
        active_limits.update(limits)
        return ConfigSnapshot(
            kind="risk",
            data=active_limits,
            source="in_memory",
            version=str(active_limits.get("version", DEFAULT_RISK_LIMITS["version"])),
            loaded_at_epoch_seconds=0,
            fallback_used=False,
        )
    snapshot = load_config(
        kind="risk",
        default_data=DEFAULT_RISK_LIMITS,
        local_filename="risk_limits.json",
        env_path_name="SAFE_TRADE_RISK_LIMITS_PATH",
    )
    active_limits = DEFAULT_RISK_LIMITS.copy()
    active_limits.update(snapshot.data)
    return ConfigSnapshot(
        kind=snapshot.kind,
        data=active_limits,
        source=snapshot.source,
        version=str(active_limits.get("version", DEFAULT_RISK_LIMITS["version"])),
        loaded_at_epoch_seconds=snapshot.loaded_at_epoch_seconds,
        fallback_used=snapshot.fallback_used,
        error=snapshot.error,
    )


def _match_risk_condition(condition: str, broker: dict[str, Any], account: dict[str, Any], action: Any, execution_mode: Any, variables: dict[str, Any]) -> bool:
    if condition == "broker_latency_exceeded":
        broker_latency = broker.get("latency_ms")
        return broker_latency is not None and broker_latency > variables.get("max_broker_latency_ms", 2000)
    if condition == "daily_loss_reached":
        daily_loss_limit = account.get("max_daily_loss_pct") or variables.get("max_daily_loss_pct", 3.0)
        return account.get("daily_loss_pct", 0) <= -daily_loss_limit
    if condition == "order_amount_exceeded":
        max_order_amount = account.get("max_order_amount") or variables.get("max_order_amount", 500000)
        return max_order_amount > 0 and account.get("order_amount", 0) > max_order_amount
    if condition == "duplicate_order":
        return bool(account.get("duplicate_order"))
    if condition == "order_preparation_disabled":
        return action in {"prepare_buy_order", "prepare_sell_order"} and not variables.get("allow_order_preparation", True)
    if condition == "live_order_submission":
        return execution_mode == "live_order" and not variables.get("allow_live_order_submission", False)
    return False


def evaluate_runtime_risk(
    *,
    broker: dict[str, Any],
    account: dict[str, Any],
    action: Any,
    execution_mode: Any,
    limits: dict[str, Any] | None = None,
) -> dict[str, Any]:
    snapshot = load_risk_limits_snapshot(limits)
    active_limits = snapshot.data
    variables = dict(active_limits.get("variables", DEFAULT_RISK_LIMITS["variables"]))
    # Fallback to direct keys for backward compatibility if root keys are present
    for k in ["max_daily_loss_pct", "max_order_amount", "max_broker_latency_ms", "max_quote_age_seconds", "allow_order_preparation", "allow_live_order_submission"]:
        if k in active_limits:
            variables[k] = active_limits[k]
        
    stops: list[str] = []
    
    rules = active_limits.get("rules", DEFAULT_RISK_LIMITS["rules"])
    for rule in rules:
        if _match_risk_condition(rule.get("condition"), broker, account, action, execution_mode, variables):
            stops.append(rule.get("reason"))

    return {
        "status": "STOP" if stops else "PASS",
        "reasons": stops,
        "limits_version": active_limits["version"],
        "limits_source": snapshot.source,
        "limits_fallback_used": snapshot.fallback_used,
        "live_order_submission": "disabled" if not variables.get("allow_live_order_submission") else "enabled",
    }
