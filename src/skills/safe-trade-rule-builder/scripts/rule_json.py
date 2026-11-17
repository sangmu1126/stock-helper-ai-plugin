"""Codex가 만든 룰 JSON을 검증해 ParsedRule로 만든다.

문장 이해는 Codex(대화형 AI)가 맡는다. Codex는 사용자 문장을 ParsedRule 형식의 JSON으로 만들어
`rule_builder.py --rule-json`으로 넘기고, 이 모듈은 형식 검증·정규화·안전 규칙 적용만 한다.
외부 AI API를 호출하지 않는다.

- 원래 문장에서 프롬프트 인젝션이 감지되면 JSON을 쓰지 않고 오프라인 파서로 해석한다.
- "매수 후보", "알려줘"처럼 문장에 명시된 행동은 JSON보다 우선한다.
- 형식이 맞지 않으면 RuleJsonError로 무엇이 틀렸는지 알려 준다(Codex가 고쳐서 다시 보낼 수 있게).
"""

from __future__ import annotations

from typing import Any

from deterministic_parser import parse_deterministic
from normalizer import normalize_payload, normalize_rule
from prompt_security import inspect_user_intent
from pydantic import ValidationError
from safety_validator import enforce_safety
from schema import ParsedRule

PARSER_SOURCE = "codex"


class RuleJsonError(ValueError):
    """Codex가 만든 룰 JSON이 스키마에 맞지 않을 때."""


def rule_json_schema() -> dict[str, Any]:
    return ParsedRule.model_json_schema()


def parse_rule_payload(payload: Any, intent: str) -> ParsedRule:
    security = inspect_user_intent(intent)
    if not security.safe:
        patterns = ", ".join(security.pattern_ids) or "unknown"
        return parse_deterministic(
            intent,
            fallback_used=True,
            warning=f"PROMPT_INJECTION_DETECTED: rule JSON ignored, deterministic parser used ({patterns})",
        )
    if not isinstance(payload, dict):
        raise RuleJsonError("rule JSON must be a JSON object")
    # "_sentence" 같은 밑줄로 시작하는 키는 설명용 메모로 보고 무시한다.
    payload = {key: value for key, value in payload.items() if not str(key).startswith("_")}

    data = normalize_payload(_apply_intent_overrides(payload, intent))
    parser = dict(data.get("parser") or {})
    notes = list(parser.get("notes") or [])
    notes.append("Structured by Codex from the user's sentence and validated against the ParsedRule schema.")
    parser.update({"source": PARSER_SOURCE, "fallback_used": False, "notes": notes})
    data["parser"] = parser
    try:
        rule = ParsedRule.model_validate(data)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}" for error in exc.errors()
        )
        raise RuleJsonError(f"rule JSON does not match the schema: {problems}") from exc
    return enforce_safety(normalize_rule(rule))


def _apply_intent_overrides(payload: dict[str, Any], intent: str) -> dict[str, Any]:
    """문장에 명시된 행동("매수 후보", "매도 후보", "알려줘")을 JSON보다 우선한다."""
    data = dict(payload)
    lowered = intent.lower()
    if "매수" in intent and "후보" in intent:
        data["action"] = "prepare_buy_order"
        data["execution_mode"] = "manual_confirm"
    elif "매도" in intent and "후보" in intent:
        data["action"] = "prepare_sell_order"
        data["execution_mode"] = "manual_confirm"
    elif ("알림" in intent or "알려" in intent or "notify" in lowered) and "후보" not in intent:
        data.setdefault("action", "notify_only")
        if data.get("action") == "notify_only":
            data["execution_mode"] = "notify_only"
    return data
