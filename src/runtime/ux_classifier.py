from __future__ import annotations

from typing import Any


HARD_STOP_REASONS = {
    "BROKER_HEALTHCHECK_FAILED",
    "MISSING_QUOTE_TIMESTAMP",
    "INVALID_NEGATIVE_QUOTE_AGE",
    "INVALID_NEGATIVE_QUOTE_TIMESTAMP",
    "QUOTE_TIMESTAMP_IN_FUTURE",
    "STALE_QUOTE",
    "DAILY_LOSS_LIMIT_REACHED",
    "ORDER_AMOUNT_LIMIT_EXCEEDED",
    "DUPLICATE_ORDER_BLOCKED",
    "LIVE_ORDER_SUBMISSION_DISABLED",
    "PROMPT_INJECTION_DETECTED",
    "LIVE_ORDER_PROMPT_BLOCKED",
}
WAIT_REASONS = {
    "BROKER_LATENCY_LIMIT_EXCEEDED",
    "EXCHANGE_NOT_OPEN",
    "UNSUPPORTED_REFERENCE_PRICE",
    "Trigger condition not met.",
    "Trigger price not crossed.",
    "Recent-high drawdown not met.",
    "Moving-average breakdown not met.",
    "Volatility threshold not met.",
}
CLARIFY_REASONS = {
    "UNSUPPORTED_EXECUTION_MODE",
    "UNSUPPORTED_RULE_ACTION",
    "NOTIFY_ONLY_REQUIRES_NOTIFY_EXECUTION_MODE",
    "ORDER_PREPARATION_REQUIRES_MANUAL_CONFIRM",
    "UNSUPPORTED_TRIGGER_TYPE",
}


def classify(decision: str, reasons: list[str]) -> dict[str, Any]:
    reason_set = set(reasons)
    if decision in {"BLOCK", "STOP"} and reason_set & HARD_STOP_REASONS:
        return {
            "level": "hard_stop",
            "user_action": "진행하지 마세요. 안전 문제가 해결되거나 신뢰할 수 있는 새 신호가 들어올 때까지 대기하세요.",
        }
    if decision == "REQUIRE_CLARIFICATION" or reason_set & CLARIFY_REASONS:
        return {
            "level": "clarify",
            "user_action": "룰을 활성화하기 전에 조건을 더 명확히 입력하세요.",
        }
    if decision == "WAIT" or reason_set & WAIT_REASONS:
        return {
            "level": "wait",
            "user_action": "계속 모니터링하세요. 아직 주문 확인을 요청하지 마세요.",
        }
    if decision == "MANUAL_CONFIRM":
        return {
            "level": "confirm",
            "user_action": "설명과 확인 체크리스트를 보여주고 사용자의 수동 확인을 받으세요.",
        }
    if decision == "NOTIFY_ONLY":
        return {
            "level": "notify",
            "user_action": "알림만 제공하세요. 주문 후보를 만들거나 제출하지 마세요.",
        }
    return {
        "level": "inform",
        "user_action": "결정 결과를 보고하고 주문은 제출하지 마세요.",
    }
