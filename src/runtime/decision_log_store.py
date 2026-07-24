from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
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

    def query_user_decisions(self, user_id: str, limit: int = 50, exclusive_start_key: dict[str, Any] | None = None) -> dict[str, Any]:
        # Simple mock implementation for in-memory
        results = [entry for entry in self.entries if entry.get("user_id") == user_id]
        results.sort(key=lambda x: x.get("created_at", 0), reverse=True)
        return {
            "items": results[:limit],
            "last_evaluated_key": None
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

    def query_user_decisions(self, user_id: str, limit: int = 50, exclusive_start_key: dict[str, Any] | None = None) -> dict[str, Any]:
        from boto3.dynamodb.conditions import Key  # type: ignore[import-not-found]
        kwargs = {
            "IndexName": "user-decisions-index",
            "KeyConditionExpression": Key("user_id").eq(user_id),
            "ScanIndexForward": False,
            "Limit": limit,
        }
        if exclusive_start_key:
            kwargs["ExclusiveStartKey"] = exclusive_start_key

        response = self.table.query(**kwargs)
        return {
            "items": list(response.get("Items", [])),
            "last_evaluated_key": response.get("LastEvaluatedKey"),
        }


def _load_boto3_table(table_name: str) -> object:
    try:
        import boto3  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("boto3 is required for DynamoDBDecisionLogStore.") from exc
    return boto3.resource("dynamodb").Table(table_name)


class FileDecisionLogStore:
    """Append-only local store for tests and single-node prototypes."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, decision_log: dict[str, Any]) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(decision_log, ensure_ascii=False, default=str) + "\n")

    def read_all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        entries: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                entries.append(json.loads(line))
        return entries

    def snapshot(self) -> dict[str, Any]:
        entries = self.read_all()
        return {
            "store": "FileDecisionLogStore",
            "path": str(self.path),
            "entry_count": len(entries),
        }

    def query_user_decisions(self, user_id: str, limit: int = 50, exclusive_start_key: dict[str, Any] | None = None) -> dict[str, Any]:
        results = [entry for entry in self.read_all() if entry.get("user_id") == user_id]
        results.sort(key=lambda x: x.get("created_at", 0), reverse=True)
        return {
            "items": results[:limit],
            "last_evaluated_key": None
        }


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
