from __future__ import annotations

from intent_parser import (
    detect_action,
    detect_asset,
    detect_cancel_conditions,
    detect_cooldown,
    detect_emotional_flags,
    detect_execution_mode,
    detect_order,
    detect_time_window,
    detect_trigger,
)
from normalizer import normalize_payload, normalize_rule
from safety_validator import enforce_safety
from schema import ParsedRule


def parse_deterministic(intent: str, *, fallback_used: bool = False, warning: str | None = None) -> ParsedRule:
    payload = {
        "asset": detect_asset(intent),
        "trigger": detect_trigger(intent),
        "action": detect_action(intent),
        "order": detect_order(intent),
        "execution_mode": detect_execution_mode(intent),
        "time_window": detect_time_window(intent),
        "cooldown": detect_cooldown(intent),
        "cancel_conditions": detect_cancel_conditions(intent),
        "emotional_risk_flags": detect_emotional_flags(intent),
        "ambiguities": [],
        "parser": {
            "source": "deterministic_fallback" if fallback_used else "deterministic",
            "fallback_used": fallback_used,
            "confidence": 0.65,
            "warnings": [warning] if warning else [],
            "notes": ["Parsed by deterministic keyword and regex parser."],
        },
    }
    rule = ParsedRule.model_validate(normalize_payload(payload))
    return enforce_safety(normalize_rule(rule))
