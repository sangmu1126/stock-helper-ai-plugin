from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


MAX_QUOTE_AGE_SECONDS = 15
OPEN_MARKET_STATES = {"OPEN", "REGULAR"}


@dataclass
class MarketQuote:
    provider: str
    symbol: str
    currency: str | None
    regular_market_price: float | None
    previous_close: float | None
    open_price: float | None
    day_high: float | None
    day_low: float | None
    recent_high: float | None
    moving_average: float | None
    move_percent: float | None
    market_state: str
    timestamp: int
    age_seconds: int
    health: dict[str, Any]


@dataclass
class RuleDraft:
    asset: dict[str, str]
    trigger: dict[str, Any]
    action: str
    order: dict[str, Any]
    execution_mode: str
    time_window: dict[str, Any]
    cooldown: dict[str, Any]
    cancel_conditions: list[dict[str, Any]]
    ambiguities: list[dict[str, Any]]
    parser: dict[str, Any]
    guardrails: dict[str, Any]
    market_data: dict[str, Any] | None
    trigger_evaluation: dict[str, Any] | None
    backtest: dict[str, Any] | None
    health_checks: list[dict[str, Any]]
    emotional_risk_flags: list[dict[str, str]]
    persuasion_process: list[dict[str, str]]
    serverless_shape: dict[str, Any]
    lambda_handler: str
    runtime_files: dict[str, str]
    policy_result: dict[str, Any]
    decision_result: dict[str, Any]
    decision_log: dict[str, Any]
    confirmation_checklist: dict[str, Any]
    user_questions: list[str]
    disclaimer: str


class MarketDataProvider(Protocol):
    name: str

    def get_quote(self, symbol: str, *, lookback_days: int = 20) -> MarketQuote:
        """Return quote data or raise a provider-specific error."""

    def get_history(self, symbol: str, period: str, interval: str) -> dict[str, Any]:
        """Return historical OHLCV data for backtesting."""
