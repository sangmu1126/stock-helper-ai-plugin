from __future__ import annotations

import json

from llm_client import parse_with_openai
from normalizer import normalize_payload, normalize_rule
from prompt_security import raise_if_unsafe
from safety_validator import enforce_safety
from schema import ParsedRule


SYSTEM_INSTRUCTIONS = """You parse Korean or English beginner-investor trading intent into JSON.
Return JSON only. Do not recommend buying or selling. Do not create live order execution.
If a field is ambiguous, put a question in ambiguities instead of guessing.
Allowed action values: prepare_buy_order, prepare_sell_order, notify_only, block_order, clarify_action.
Allowed execution_mode values: notify_only, manual_confirm.
Always include quote_stale in cancel_conditions unless a stricter equivalent exists.
"""


def build_prompt(intent: str, schema_json: str) -> str:
    return (
        SYSTEM_INSTRUCTIONS
        + "\nJSON schema:\n"
        + schema_json
        + "\nUser intent:\n"
        + intent
        + "\nReturn a single JSON object matching the schema."
    )


def parse_llm(intent: str) -> ParsedRule:
    raise_if_unsafe(intent)
    schema_json = json.dumps(ParsedRule.model_json_schema(), ensure_ascii=False)
    prompt = build_prompt(intent, schema_json)
    structured_output_used = True
    try:
        payload = parse_with_openai(prompt, schema_model=ParsedRule)
    except Exception:  # noqa: BLE001 - fallback to legacy JSON parsing path
        structured_output_used = False
        payload = parse_with_openai(prompt)
    rule = normalize_llm_payload(payload, intent, structured_output_used=structured_output_used)
    return enforce_safety(normalize_rule(rule))


def normalize_llm_payload(payload: dict, intent: str, *, structured_output_used: bool) -> ParsedRule:
    normalized = normalize_payload(_apply_intent_overrides(payload, intent))
    normalized.setdefault("parser", {})
    normalized["parser"].update(
        {
            "source": "llm",
            "fallback_used": False,
            "structured_output_used": structured_output_used,
        }
    )
    rule = ParsedRule.model_validate(normalized)
    return enforce_safety(normalize_rule(rule))


def _apply_intent_overrides(payload: dict, intent: str) -> dict:
    data = dict(payload)
    lowered = intent.lower()
    has_buy_candidate = "매수" in intent and "후보" in intent
    has_sell_candidate = "매도" in intent and "후보" in intent
    if has_buy_candidate:
        data["action"] = "prepare_buy_order"
        data["execution_mode"] = "manual_confirm"
    elif has_sell_candidate:
        data["action"] = "prepare_sell_order"
        data["execution_mode"] = "manual_confirm"
    elif ("알림" in intent or "알려" in intent or "notify" in lowered) and "후보" not in intent:
        data.setdefault("action", "notify_only")
        if data.get("action") == "notify_only":
            data["execution_mode"] = "notify_only"
    return data
