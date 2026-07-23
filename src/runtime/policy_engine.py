from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from config_provider import ConfigSnapshot, load_config


POLICY_VERSION = "policy.safe-trade.v1"
DEFAULT_POLICY_CONFIG: dict[str, Any] = {
    "version": POLICY_VERSION,
    "investment_advice_patterns": ["추천", "뭐 사", "무슨 종목", "오를 종목", "수익 낼", "종목 골라", "best stock", "recommend"],
    "severe_emotional_flags": ["all_in"],
    "actions": {
        "investment_advice_request": "BLOCK",
        "severe_emotional_risk": "BLOCK",
        "emotional_risk": "REQUIRE_CLARIFICATION",
        "missing_order_limit": "REQUIRE_CLARIFICATION",
        "parser_ambiguity": "REQUIRE_CLARIFICATION",
        "notify_only": "ALLOW",
        "default": "ALLOW",
    },
}


@dataclass(frozen=True)
class PolicyResult:
    decision: str
    reasons: tuple[str, ...]
    downgraded_action: str | None = None
    policy_version: str = POLICY_VERSION
    human_review_required: bool = False
    blocked: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PolicyEngine:
    def __init__(self, policy_config: dict[str, Any] | None = None, config_snapshot: ConfigSnapshot | None = None) -> None:
        self.config_snapshot = config_snapshot or load_policy_config_snapshot(policy_config)
        self.config = self.config_snapshot.data
        self.version = str(self.config.get("version", POLICY_VERSION))
        self.actions = dict(DEFAULT_POLICY_CONFIG["actions"])
        self.actions.update(self.config.get("actions", {}))

    def evaluate(
        self,
        *,
        intent: str,
        action: str,
        execution_mode: str,
        order: dict[str, Any],
        trigger: dict[str, Any],
        emotional_flags: list[dict[str, str]],
        ambiguities: list[dict[str, Any]],
    ) -> PolicyResult:
        metadata = {
            "original_action": action,
            "execution_mode": execution_mode,
            "trigger_type": trigger.get("type"),
            "policy_config_version": self.version,
            "policy_config_source": self.config_snapshot.source,
            "policy_config_fallback_used": self.config_snapshot.fallback_used,
        }
        if _contains_investment_advice_request(intent, self.config):
            return PolicyResult(
                decision=self.actions["investment_advice_request"],
                reasons=("INVESTMENT_ADVICE_REQUEST_BLOCKED",),
                downgraded_action="clarify_action",
                policy_version=self.version,
                human_review_required=True,
                blocked=True,
                metadata=metadata,
            )
        if emotional_flags:
            flags = {item.get("flag", "") for item in emotional_flags}
            severe_flags = set(self.config.get("severe_emotional_flags", DEFAULT_POLICY_CONFIG["severe_emotional_flags"]))
            if flags & severe_flags:
                return PolicyResult(
                    decision=self.actions["severe_emotional_risk"],
                    reasons=("SEVERE_EMOTIONAL_RISK_BLOCKED",),
                    downgraded_action="clarify_action",
                    policy_version=self.version,
                    human_review_required=True,
                    blocked=True,
                    metadata={**metadata, "emotional_flags": sorted(flags)},
                )
            return PolicyResult(
                decision=self.actions["emotional_risk"],
                reasons=("EMOTIONAL_RISK_REQUIRES_REWRITE",),
                downgraded_action="clarify_action",
                policy_version=self.version,
                human_review_required=True,
                metadata={**metadata, "emotional_flags": sorted(flags)},
            )
        reasons: list[str] = []
        if action in {"prepare_buy_order", "prepare_sell_order"} and order.get("mode") == "required_before_activation":
            reasons.append("ORDER_LIMIT_REQUIRED")
        if trigger.get("type") in {"needs_clarification", "price_move_percent"}:
            reasons.append("TRIGGER_REQUIRES_CLARIFICATION")
        if ambiguities:
            reasons.append("PARSER_AMBIGUITY_REQUIRES_CLARIFICATION")
        if reasons:
            return PolicyResult(
                decision=self.actions["parser_ambiguity"],
                reasons=tuple(sorted(set(reasons))),
                policy_version=self.version,
                human_review_required=True,
                metadata=metadata,
            )
        if action == "notify_only":
            return PolicyResult(
                decision=self.actions["notify_only"],
                reasons=("NOTIFY_ONLY_WITH_NO_ORDER_PERMISSION",),
                policy_version=self.version,
                metadata=metadata,
            )
        return PolicyResult(
            decision=self.actions["default"],
            reasons=("POLICY_PASSED",),
            policy_version=self.version,
            metadata=metadata,
        )


def load_policy_config() -> dict[str, Any]:
    return load_policy_config_snapshot().data


def load_policy_config_snapshot(policy_config: dict[str, Any] | None = None) -> ConfigSnapshot:
    if policy_config is not None:
        config = DEFAULT_POLICY_CONFIG.copy()
        config.update(policy_config)
        return ConfigSnapshot(
            kind="policy",
            data=config,
            source="in_memory",
            version=str(config.get("version", POLICY_VERSION)),
            loaded_at_epoch_seconds=0,
            fallback_used=False,
        )
    snapshot = load_config(
        kind="policy",
        default_data=DEFAULT_POLICY_CONFIG,
        local_filename="policy_rules.json",
        env_path_name="SAFE_TRADE_POLICY_CONFIG_PATH",
    )
    config = DEFAULT_POLICY_CONFIG.copy()
    config.update(snapshot.data)
    return ConfigSnapshot(
        kind=snapshot.kind,
        data=config,
        source=snapshot.source,
        version=str(config.get("version", POLICY_VERSION)),
        loaded_at_epoch_seconds=snapshot.loaded_at_epoch_seconds,
        fallback_used=snapshot.fallback_used,
        error=snapshot.error,
    )


def _contains_investment_advice_request(intent: str, config: dict[str, Any]) -> bool:
    normalized = intent.lower()
    patterns = config.get("investment_advice_patterns", DEFAULT_POLICY_CONFIG["investment_advice_patterns"])
    return any(str(pattern).lower() in normalized for pattern in patterns)
