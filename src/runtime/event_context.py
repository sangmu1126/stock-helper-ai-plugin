from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from providers import EventAccountProvider, EventBrokerProvider


@dataclass(frozen=True)
class RuntimeEvent:
    raw: dict[str, Any]
    rule: dict[str, Any]
    trigger: dict[str, Any]
    quote: dict[str, Any]
    exchange: dict[str, Any]
    asset: dict[str, Any]
    order: dict[str, Any]
    cooldown: dict[str, Any]
    action: Any
    execution_mode: Any
    broker_snapshot: dict[str, Any]
    account_snapshot: dict[str, Any]
    emotional_flags: list[dict[str, Any]]
    ambiguities: list[dict[str, Any]]

    @classmethod
    def from_event(cls, event: dict[str, Any]) -> RuntimeEvent:
        rule = _as_dict(event.get("rule"))
        quote = _as_dict(event.get("quote"))
        trigger = _as_dict(rule.get("trigger"))
        return cls(
            raw=event,
            rule=rule,
            trigger=trigger,
            quote=quote,
            exchange=_as_dict(event.get("exchange_status")),
            asset=_normalize_asset(event.get("asset") or rule.get("asset") or {"symbol": quote.get("symbol", "UNKNOWN")}),
            order=_as_dict(rule.get("order")),
            cooldown=_as_dict(rule.get("cooldown")),
            action=rule.get("action"),
            execution_mode=rule.get("execution_mode"),
            broker_snapshot=EventBrokerProvider(_as_dict(event.get("broker_health"))).get_health().to_dict(),
            account_snapshot=EventAccountProvider(_as_dict(event.get("account_limits"))).get_snapshot().to_dict(),
            emotional_flags=_as_list(rule.get("emotional_risk_flags", event.get("emotional_risk_flags", []))),
            ambiguities=_as_list(rule.get("ambiguities", event.get("ambiguities", []))),
        )


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _normalize_asset(asset: Any) -> dict[str, Any]:
    if isinstance(asset, dict):
        return asset
    if isinstance(asset, str):
        return {"symbol": asset}
    return {"symbol": "UNKNOWN"}
