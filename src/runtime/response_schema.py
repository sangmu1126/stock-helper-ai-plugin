from __future__ import annotations

from typing import Any


RESPONSE_SCHEMA_VERSION = "safe-trade-runtime-response.v1"


def envelope(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": RESPONSE_SCHEMA_VERSION,
        **payload,
    }


def validate_response(payload: dict[str, Any]) -> list[str]:
    required = {
        "schema_version",
        "decision",
        "reasons",
        "policy_result",
        "decision_result",
        "decision_log",
        "trigger_evaluation",
        "stop_level",
        "user_action",
        "next_step",
    }
    return sorted(required - set(payload))
