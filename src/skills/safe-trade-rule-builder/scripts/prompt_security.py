from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class PromptSecurityPattern:
    id: str
    pattern: str
    severity: str
    reason: str


INJECTION_PATTERNS = (
    PromptSecurityPattern("ignore_previous_instructions_ko", r"이전\s*지시\s*무시", "high", "PROMPT_INJECTION_DETECTED"),
    PromptSecurityPattern("ignore_prior_instructions_ko", r"앞(?:선|의)?\s*지시\s*무시", "high", "PROMPT_INJECTION_DETECTED"),
    PromptSecurityPattern("system_prompt_request_ko", r"시스템\s*프롬프트", "high", "PROMPT_INJECTION_DETECTED"),
    PromptSecurityPattern("developer_instruction_bypass_ko", r"개발자\s*지시\s*무시", "high", "PROMPT_INJECTION_DETECTED"),
    PromptSecurityPattern("ignore_previous_instructions_en", r"ignore\s+(?:all\s+)?previous", "high", "PROMPT_INJECTION_DETECTED"),
    PromptSecurityPattern("ignore_system_instructions_en", r"ignore\s+(?:the\s+)?(?:system|developer)\s+instructions?", "high", "PROMPT_INJECTION_DETECTED"),
    PromptSecurityPattern("disregard_previous_en", r"disregard\s+(?:all\s+)?previous", "high", "PROMPT_INJECTION_DETECTED"),
    PromptSecurityPattern("reveal_system_prompt_en", r"reveal\s+(?:the\s+)?(?:system\s+)?prompt", "high", "PROMPT_INJECTION_DETECTED"),
    PromptSecurityPattern("auto_order_request_ko", r"자동\s*주문\s*해", "high", "LIVE_ORDER_PROMPT_BLOCKED"),
    PromptSecurityPattern("automatic_order_request_ko", r"자동으로\s*주문", "high", "LIVE_ORDER_PROMPT_BLOCKED"),
    PromptSecurityPattern("immediate_order_request_ko", r"바로\s*주문", "high", "LIVE_ORDER_PROMPT_BLOCKED"),
    PromptSecurityPattern("live_order_request_ko", r"실주문", "high", "LIVE_ORDER_PROMPT_BLOCKED"),
    PromptSecurityPattern("live_order_request_en", r"live\s*order", "high", "LIVE_ORDER_PROMPT_BLOCKED"),
    PromptSecurityPattern("place_order_request_en", r"place\s+(?:the\s+)?order", "high", "LIVE_ORDER_PROMPT_BLOCKED"),
)


class PromptInjectionDetected(ValueError):
    pass


@dataclass(frozen=True)
class PromptSecurityResult:
    safe: bool
    matched_patterns: tuple[str, ...] = ()
    pattern_ids: tuple[str, ...] = ()
    severities: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()


def inspect_user_intent(intent: str) -> PromptSecurityResult:
    normalized = " ".join(intent.strip().split()).lower()
    matches = tuple(item for item in INJECTION_PATTERNS if re.search(item.pattern, normalized, re.IGNORECASE))
    return PromptSecurityResult(
        safe=not matches,
        matched_patterns=tuple(item.pattern for item in matches),
        pattern_ids=tuple(item.id for item in matches),
        severities=tuple(item.severity for item in matches),
        reasons=tuple(dict.fromkeys(item.reason for item in matches)),
    )


def raise_if_unsafe(intent: str) -> None:
    result = inspect_user_intent(intent)
    if not result.safe:
        raise PromptInjectionDetected(
            "Prompt injection or unsafe live-order instruction detected: "
            + ", ".join(result.pattern_ids)
        )
