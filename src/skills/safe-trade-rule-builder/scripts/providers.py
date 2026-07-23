from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Protocol


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


class BrokerProvider(Protocol):
    def get_health(self) -> BrokerHealthSnapshot:
        """Return broker health before a rule can proceed."""


class AccountProvider(Protocol):
    def get_snapshot(self) -> AccountSnapshot:
        """Return account limits and duplicate-order state."""


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


class KakaoPaySecuritiesBrokerProvider:
    """Future adapter boundary for KakaoPay Securities broker health."""

    def __init__(self, api_base_url: str, timeout_seconds: float = 2.0) -> None:
        self.api_base_url = api_base_url
        self.timeout_seconds = timeout_seconds

    def get_health(self) -> BrokerHealthSnapshot:
        raise NotImplementedError("Connect to approved KakaoPay Securities broker-health API.")


class KakaoPaySecuritiesAccountProvider:
    """Future adapter boundary for KakaoPay Securities account/risk limits."""

    def __init__(self, api_base_url: str, account_id: str, timeout_seconds: float = 2.0) -> None:
        self.api_base_url = api_base_url
        self.account_id = account_id
        self.timeout_seconds = timeout_seconds

    def get_snapshot(self) -> AccountSnapshot:
        raise NotImplementedError("Connect to approved KakaoPay Securities account API.")


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
