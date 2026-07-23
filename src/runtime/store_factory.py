from __future__ import annotations

from typing import Any

from decision_log_store import DynamoDBDecisionLogStore, InMemoryDecisionLogStore
from state_store import DynamoDBStateStore, InMemoryStateStore


def make_state_store(runtime_config: dict[str, Any]) -> Any:
    if runtime_config.get("state_backend") == "dynamodb":
        table_name = runtime_config.get("state_table_name")
        if not table_name:
            raise RuntimeError("SAFE_TRADE_STATE_TABLE is required when SAFE_TRADE_STATE_BACKEND=dynamodb.")
        return DynamoDBStateStore(str(table_name))
    return InMemoryStateStore()


def make_decision_log_store(runtime_config: dict[str, Any]) -> Any:
    if runtime_config.get("decision_log_backend") == "dynamodb":
        table_name = runtime_config.get("decision_log_table_name")
        if not table_name:
            raise RuntimeError("SAFE_TRADE_DECISION_LOG_TABLE is required when SAFE_TRADE_DECISION_LOG_BACKEND=dynamodb.")
        return DynamoDBDecisionLogStore(str(table_name))
    return InMemoryDecisionLogStore()
