from __future__ import annotations

from typing import Any


ERRORS: dict[str, dict[str, str]] = {
    "BROKER_HEALTHCHECK_FAILED": {"severity": "high", "category": "broker", "user_message": "브로커 상태 점검에 실패했습니다."},
    "BROKER_LATENCY_LIMIT_EXCEEDED": {"severity": "medium", "category": "broker", "user_message": "브로커 응답이 기준보다 느려 잠시 대기합니다."},
    "EXCHANGE_NOT_OPEN": {"severity": "medium", "category": "market", "user_message": "현재 거래 가능한 정규 시장 상태가 아닙니다."},
    "MISSING_QUOTE_TIMESTAMP": {"severity": "high", "category": "market_data", "user_message": "시세 timestamp가 없어 진행할 수 없습니다."},
    "INVALID_NEGATIVE_QUOTE_AGE": {"severity": "high", "category": "market_data", "user_message": "시세 시간이 비정상입니다."},
    "QUOTE_TOO_OLD": {"severity": "high", "category": "market_data", "user_message": "시세가 오래되어 진행하지 않습니다."},
    "STALE_QUOTE": {"severity": "high", "category": "market_data", "user_message": "시세가 오래되어 진행하지 않습니다."},
    "QUOTE_TIMESTAMP_IN_FUTURE": {"severity": "high", "category": "market_data", "user_message": "시세 timestamp가 미래 시각입니다."},
    "INVALID_NEGATIVE_QUOTE_TIMESTAMP": {"severity": "high", "category": "market_data", "user_message": "시세 timestamp가 비정상입니다."},
    "DAILY_LOSS_LIMIT_REACHED": {"severity": "high", "category": "risk", "user_message": "일일 손실 한도에 도달해 진행하지 않습니다."},
    "ORDER_AMOUNT_LIMIT_EXCEEDED": {"severity": "high", "category": "risk", "user_message": "주문 후보 금액이 설정 한도를 초과했습니다."},
    "DUPLICATE_ORDER_BLOCKED": {"severity": "high", "category": "state", "user_message": "같은 조건의 중복 실행을 차단했습니다."},
    "LIVE_ORDER_SUBMISSION_DISABLED": {"severity": "high", "category": "execution", "user_message": "실주문 제출은 비활성화되어 있습니다."},
    "PROMPT_INJECTION_DETECTED": {"severity": "high", "category": "security", "user_message": "요청에 시스템 지시를 우회하려는 표현이 있어 진행하지 않습니다."},
    "LIVE_ORDER_PROMPT_BLOCKED": {"severity": "high", "category": "security", "user_message": "자동 주문 또는 실주문을 유도하는 표현이 있어 진행하지 않습니다."},
    "DUPLICATE_DECISION_BLOCKED": {"severity": "medium", "category": "state", "user_message": "동일한 룰 결정이 이미 처리되어 대기합니다."},
    "TRIGGER_MATCHED_REQUIRES_MANUAL_CONFIRMATION": {"severity": "info", "category": "rule", "user_message": "조건이 충족되어 수동 확인 단계로 넘어갈 수 있습니다."},
}


def describe_reasons(reasons: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "code": reason,
            **ERRORS.get(reason, {"severity": "info", "category": "rule", "user_message": reason}),
        }
        for reason in reasons
    ]
