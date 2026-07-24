from __future__ import annotations

from schema import Ambiguity, ParsedRule


def enforce_safety(rule: ParsedRule) -> ParsedRule:
    data = rule.model_dump()
    warnings = list(data["parser"].get("warnings", []))
    ambiguities = list(data.get("ambiguities", []))
    has_emotional_risk = bool(data.get("emotional_risk_flags"))

    data["execution_mode"] = "manual_confirm"
    if data["action"] == "notify_only":
        data["execution_mode"] = "notify_only"

    if data["action"] not in {
        "prepare_buy_order",
        "prepare_sell_order",
        "notify_only",
        "block_order",
        "clarify_action",
    }:
        data["action"] = "clarify_action"
        warnings.append("UNSUPPORTED_ACTION_NORMALIZED_TO_CLARIFY")

    if not has_emotional_risk and data["action"] in {"prepare_buy_order", "prepare_sell_order"} and data["order"].get("mode") == "required_before_activation":
            ambiguities.append(
                Ambiguity(
                    field="order",
                    question="What maximum amount or share quantity should this rule prepare?",
                ).model_dump()
            )

    if has_emotional_risk:
        warnings.append("EMOTIONAL_RISK_REQUIRES_COOLING_OFF")
        warnings.append("EMOTIONAL_RISK_DOWNGRADED_ACTION_TO_CLARIFY")
        data["action"] = "clarify_action"
        data["execution_mode"] = "manual_confirm"
        data["order"] = {"mode": "required_before_activation", "value": None, "currency": "KRW"}
        ambiguities.append(
            Ambiguity(
                field="intent",
                question="Please rewrite the rule without urgency, loss-recovery, FOMO, or all-in wording before activation.",
            ).model_dump()
        )

    if not any(item.get("type") == "quote_stale" for item in data["cancel_conditions"]):
        data["cancel_conditions"].insert(0, {"type": "quote_stale", "percent": None})

    data["parser"]["warnings"] = sorted(set(warnings))
    data["ambiguities"] = ambiguities
    return ParsedRule.model_validate(data)
