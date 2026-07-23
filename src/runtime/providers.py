from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class BrokerHealthSnapshot:
    ok: bool
    status: str
    latency_ms: int | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AccountSnapshot:
    daily_loss_pct: float
    max_daily_loss_pct: float
    order_amount: float
    max_order_amount: float
    duplicate_order: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EventBrokerProvider:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def get_health(self) -> BrokerHealthSnapshot:
        return BrokerHealthSnapshot(
            ok=bool(self.payload.get("ok")),
            status=str(self.payload.get("status", "UNKNOWN")),
            latency_ms=_optional_int(self.payload.get("latency_ms")),
            reason=self.payload.get("reason"),
        )


class EventAccountProvider:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def get_snapshot(self) -> AccountSnapshot:
        return AccountSnapshot(
            daily_loss_pct=_float(self.payload.get("daily_loss_pct"), 0.0),
            max_daily_loss_pct=_float(self.payload.get("max_daily_loss_pct"), 3.0),
            order_amount=_float(self.payload.get("order_amount"), 0.0),
            max_order_amount=_float(self.payload.get("max_order_amount"), 0.0),
            duplicate_order=bool(self.payload.get("duplicate_order", False)),
        )


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
