from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Action(str, Enum):
    prepare_buy_order = "prepare_buy_order"
    prepare_sell_order = "prepare_sell_order"
    notify_only = "notify_only"
    block_order = "block_order"
    clarify_action = "clarify_action"


class ExecutionMode(str, Enum):
    notify_only = "notify_only"
    manual_confirm = "manual_confirm"


TriggerType = Literal[
    "price_drop_percent",
    "price_rise_percent",
    "recent_high_drop_percent",
    "moving_average_breakdown",
    "volatility_move_percent",
    "price_cross_above",
    "price_cross_below",
    "needs_clarification",
    "price_move_percent",
]

OrderMode = Literal[
    "amount",
    "shares",
    "position_fraction",
    "portfolio_or_position_percent",
    "required_before_activation",
]

MarketSession = Literal["regular", "pre_market", "after_hours"]

CancelConditionType = Literal[
    "quote_stale",
    "negative_news_requires_manual_review",
    "volume_spike_requires_manual_review",
    "provider_or_broker_unstable",
    "daily_drop_exceeds_percent",
]


class Asset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    name: str | None = None
    confidence: float | None = None


class Trigger(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: TriggerType
    reference: str | None = None
    percent: float | None = None
    price: float | None = None
    currency: str | None = "KRW"
    lookback_days: int | None = None
    reason: str | None = None
    direction: str | None = None

    @field_validator("percent")
    @classmethod
    def validate_percent(cls, value: float | None) -> float | None:
        if value is not None and value < 0:
            raise ValueError("percent must be non-negative")
        return value


class Order(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: OrderMode = "required_before_activation"
    value: float | None = None
    currency: str | None = "KRW"


class TimeWindow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    market_session: MarketSession = "regular"
    exclude_open_minutes: int | None = None
    exclude_morning: bool | None = None
    only_before_close_minutes: int | None = None
    expires: str | None = None
    requires_consecutive_days: int | None = None


class Cooldown(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_days_between_triggers: int | None = None
    min_minutes_between_triggers: int | None = 10


class CancelCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: CancelConditionType
    percent: float | None = None


class EmotionalRiskFlag(BaseModel):
    model_config = ConfigDict(extra="forbid")

    flag: str
    evidence: str
    response: str = "룰을 활성화하기 전에 감정이 가라앉은 상태에서 다시 확인해 주세요."


class Ambiguity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str
    question: str


class NormalizedFrom(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alert_only: str | None = None
    notification: str | None = None
    drawdown_from_high: str | None = None
    recent_high: str | None = None


class ParserMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    fallback_used: bool = False
    confidence: float | None = None
    structured_output_used: bool | None = None
    ambiguous_fields: list[str] = Field(default_factory=list)
    normalized_from: NormalizedFrom = Field(default_factory=NormalizedFrom)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ParsedRule(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"additionalProperties": False})

    asset: Asset
    trigger: Trigger
    action: Action
    order: Order = Field(default_factory=Order)
    execution_mode: ExecutionMode = ExecutionMode.manual_confirm
    time_window: TimeWindow = Field(default_factory=TimeWindow)
    cooldown: Cooldown = Field(default_factory=Cooldown)
    cancel_conditions: list[CancelCondition] = Field(
        default_factory=lambda: [CancelCondition(type="quote_stale")]
    )
    emotional_risk_flags: list[EmotionalRiskFlag] = Field(default_factory=list)
    ambiguities: list[Ambiguity] = Field(default_factory=list)
    parser: ParserMeta

    def to_legacy_dicts(self) -> dict[str, Any]:
        parser = self.parser.model_dump(exclude_none=True)
        if isinstance(parser.get("normalized_from"), dict):
            parser["normalized_from"] = dict(parser["normalized_from"])
        return {
            "asset": self.asset.model_dump(exclude_none=True),
            "trigger": self.trigger.model_dump(exclude_none=True),
            "action": self.action.value,
            "order": self.order.model_dump(exclude_none=True),
            "execution_mode": self.execution_mode.value,
            "time_window": self.time_window.model_dump(exclude_none=True),
            "cooldown": self.cooldown.model_dump(exclude_none=True),
            "cancel_conditions": [item.model_dump(exclude_none=True) for item in self.cancel_conditions],
            "emotional_risk_flags": [
                item.model_dump(exclude_none=True) for item in self.emotional_risk_flags
            ],
            "ambiguities": [item.model_dump(exclude_none=True) for item in self.ambiguities],
            "parser": parser,
        }
