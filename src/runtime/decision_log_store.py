from __future__ import annotations

from decimal import Decimal
from typing import Any


class InMemoryDecisionLogStore:
    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    def append(self, decision_log: dict[str, Any]) -> None:
        self.entries.append(dict(decision_log))

    def snapshot(self) -> dict[str, Any]:
        return {
            "store": "InMemoryDecisionLogStore",
            "entry_count": len(self.entries),
        }


class DynamoDBDecisionLogStore:
    def __init__(self, table_name: str, *, table: object | None = None) -> None:
        self.table_name = table_name
        self.table = table or _load_boto3_table(table_name)

    def append(self, decision_log: dict[str, Any]) -> None:
        self.table.put_item(
            Item=_to_dynamodb_safe(decision_log),
            ConditionExpression="attribute_not_exists(decision_id)",
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            "store": "DynamoDBDecisionLogStore",
            "table_name": self.table_name,
            "implemented": True,
        }


def _load_boto3_table(table_name: str) -> object:
    try:
        import boto3  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("boto3 is required for DynamoDBDecisionLogStore.") from exc
    return boto3.resource("dynamodb").Table(table_name)


def _to_dynamodb_safe(value: Any) -> Any:
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, tuple):
        return [_to_dynamodb_safe(item) for item in value]
    if isinstance(value, list):
        return [_to_dynamodb_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _to_dynamodb_safe(item) for key, item in value.items()}
    return value
