from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from config_provider import ConfigSnapshot, load_config


POLICY_VERSION = "policy.safe-trade.v1"
DEFAULT_POLICY_CONFIG: dict[str, Any] = {
    "version": POLICY_VERSION,
    "actions": {
        "parser_ambiguity": "REQUIRE_CLARIFICATION",
        "default": "ALLOW",
    },
    "rules": [
        {
            "id": "investment_advice_request",
            "type": "terminal",
            "decision": "BLOCK",
            "reason": "INVESTMENT_ADVICE_REQUEST_BLOCKED",
            "downgraded_action": "clarify_action",
            "human_review_required": True,
            "blocked": True,
            "condition": {
                "type": "intent_match",
                "patterns": ["추천", "뭐 사", "무슨 종목", "오를 종목", "수익 낼", "종목 골라", "best stock", "recommend"]
            }
        },
        {
            "id": "severe_emotional_risk",
            "type": "terminal",
            "decision": "BLOCK",
            "reason": "SEVERE_EMOTIONAL_RISK_BLOCKED",
            "downgraded_action": "clarify_action",
            "human_review_required": True,
            "blocked": True,
            "condition": {
                "type": "emotional_flag_match",
                "flags": ["all_in"]
            }
        },
        {
            "id": "emotional_risk",
            "type": "terminal",
            "decision": "REQUIRE_CLARIFICATION",
            "reason": "EMOTIONAL_RISK_REQUIRES_REWRITE",
            "downgraded_action": "clarify_action",
            "human_review_required": True,
            "blocked": False,
            "condition": {
                "type": "has_emotional_flags"
            }
        },
        {
            "id": "order_limit_required",
            "type": "accumulate",
            "reason": "ORDER_LIMIT_REQUIRED",
            "condition": {
                "type": "order_mode",
                "actions": ["prepare_buy_order", "prepare_sell_order"],
                "mode": "required_before_activation"
            }
        },
        {
            "id": "trigger_requires_clarification",
            "type": "accumulate",
            "reason": "TRIGGER_REQUIRES_CLARIFICATION",
            "condition": {
                "type": "trigger_type",
                "types": ["needs_clarification", "price_move_percent"]
            }
        },
        {
            "id": "parser_ambiguity",
            "type": "accumulate",
            "reason": "PARSER_AMBIGUITY_REQUIRES_CLARIFICATION",
            "condition": {
                "type": "has_ambiguities"
            }
        },
        {
            "id": "notify_only",
            "type": "terminal",
            "decision": "ALLOW",
            "reason": "NOTIFY_ONLY_WITH_NO_ORDER_PERMISSION",
            "condition": {
                "type": "action_match",
                "actions": ["notify_only"]
            }
        }
    ]
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
        self.actions = dict(DEFAULT_POLICY_CONFIG.get("actions", {}))
        self.actions.update(self.config.get("actions", {}))
        self.rules = self.config.get("rules", DEFAULT_POLICY_CONFIG.get("rules", []))

    def _match_condition(self, condition: dict[str, Any], intent: str, action: str, order: dict[str, Any], trigger: dict[str, Any], emotional_flags: list[dict[str, str]], ambiguities: list[dict[str, Any]]) -> bool:
        ctype = condition.get("type")
        if ctype == "intent_match":
            normalized = intent.lower()
            return any(str(pattern).lower() in normalized for pattern in condition.get("patterns", []))
        if ctype == "emotional_flag_match":
            flags = {item.get("flag", "") for item in emotional_flags}
            return bool(flags & set(condition.get("flags", [])))
        if ctype == "has_emotional_flags":
            return bool(emotional_flags)
        if ctype == "order_mode":
            return action in condition.get("actions", []) and order.get("mode") == condition.get("mode")
        if ctype == "trigger_type":
            return trigger.get("type") in condition.get("types", [])
        if ctype == "has_ambiguities":
            return bool(ambiguities)
        if ctype == "action_match":
            return action in condition.get("actions", [])
        return False

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
        
        accumulated_reasons: list[str] = []
        
        for rule in self.rules:
            condition = rule.get("condition", {})
            if self._match_condition(condition, intent, action, order, trigger, emotional_flags, ambiguities):
                if rule.get("type") == "terminal":
                    if rule.get("reason") in ["SEVERE_EMOTIONAL_RISK_BLOCKED", "EMOTIONAL_RISK_REQUIRES_REWRITE"]:
                        metadata["emotional_flags"] = sorted({item.get("flag", "") for item in emotional_flags})
                    
                    return PolicyResult(
                        decision=rule.get("decision", "BLOCK"),
                        reasons=(rule.get("reason"),),
                        downgraded_action=rule.get("downgraded_action"),
                        policy_version=self.version,
                        human_review_required=rule.get("human_review_required", False),
                        blocked=rule.get("blocked", False),
                        metadata=metadata,
                    )
                elif rule.get("type") == "accumulate":
                    accumulated_reasons.append(rule.get("reason"))

        if accumulated_reasons:
            return PolicyResult(
                decision=self.actions.get("parser_ambiguity", "REQUIRE_CLARIFICATION"),
                reasons=tuple(sorted(set(accumulated_reasons))),
                policy_version=self.version,
                human_review_required=True,
                metadata=metadata,
            )

        return PolicyResult(
            decision=self.actions.get("default", "ALLOW"),
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
