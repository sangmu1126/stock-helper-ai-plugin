from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config_provider import ConfigSnapshot, load_config


DEFAULT_RISK_LIMITS: dict[str, Any] = {
    "version": "risk.safe-trade.v1",
    "max_daily_loss_pct": 3.0,
    "max_order_amount": 500000,
    "max_broker_latency_ms": 2000,
    "max_quote_age_seconds": 15,
    "allow_order_preparation": True,
    "allow_live_order_submission": False,
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
    stops: list[str] = []
    broker_latency = broker.get("latency_ms")
    if broker_latency is not None and broker_latency > active_limits["max_broker_latency_ms"]:
        stops.append("BROKER_LATENCY_LIMIT_EXCEEDED")
    daily_loss_limit = account.get("max_daily_loss_pct") or active_limits["max_daily_loss_pct"]
    if account.get("daily_loss_pct", 0) <= -daily_loss_limit:
        stops.append("DAILY_LOSS_LIMIT_REACHED")
    max_order_amount = account.get("max_order_amount") or active_limits["max_order_amount"]
    if max_order_amount > 0 and account.get("order_amount", 0) > max_order_amount:
        stops.append("ORDER_AMOUNT_LIMIT_EXCEEDED")
    if account.get("duplicate_order"):
        stops.append("DUPLICATE_ORDER_BLOCKED")
    if action in {"prepare_buy_order", "prepare_sell_order"} and not active_limits["allow_order_preparation"]:
        stops.append("ORDER_PREPARATION_DISABLED_BY_RISK_LIMITS")
    if execution_mode == "live_order":
        stops.append("LIVE_ORDER_SUBMISSION_DISABLED")
    return {
        "status": "STOP" if stops else "PASS",
        "reasons": stops,
        "limits_version": active_limits["version"],
        "limits_source": snapshot.source,
        "limits_fallback_used": snapshot.fallback_used,
        "live_order_submission": "disabled",
    }
