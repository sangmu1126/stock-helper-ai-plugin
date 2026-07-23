from __future__ import annotations

import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol


class StateStore(Protocol):
    def has_idempotency_key(self, key: str) -> bool: ...

    def record_idempotency_key(self, key: str) -> None: ...

    def cooldown_active(self, rule_id: str, *, now: int, cooldown_seconds: int) -> bool: ...

    def record_rule_fire(self, rule_id: str, *, now: int) -> None: ...

    def record_decision_state(
        self, idempotency_key: str, rule_id: str | None = None, *, now: int = 0,
    ) -> None: ...


class DuplicateStateRecordError(RuntimeError):
    """Raised when a conditional idempotency write detects a duplicate."""


@dataclass
class InMemoryStateStore:
    idempotency_keys: set[str] = field(default_factory=set)
    last_rule_fire_at: dict[str, int] = field(default_factory=dict)

    def has_idempotency_key(self, key: str) -> bool:
        return key in self.idempotency_keys

    def record_idempotency_key(self, key: str) -> None:
        self.idempotency_keys.add(key)

    def cooldown_active(self, rule_id: str, *, now: int, cooldown_seconds: int) -> bool:
        last_fire_at = self.last_rule_fire_at.get(rule_id)
        return last_fire_at is not None and now - last_fire_at < cooldown_seconds

    def record_rule_fire(self, rule_id: str, *, now: int) -> None:
        self.last_rule_fire_at[rule_id] = now

    def record_decision_state(
        self, idempotency_key: str, rule_id: str | None = None, *, now: int = 0,
    ) -> None:
        """Atomically record idempotency key and optional rule fire."""
        if self.has_idempotency_key(idempotency_key):
            raise DuplicateStateRecordError(idempotency_key)
        self.record_idempotency_key(idempotency_key)
        if rule_id:
            self.record_rule_fire(rule_id, now=now)

    def snapshot(self) -> dict[str, object]:
        return {
            "store": "InMemoryStateStore",
            "idempotency_key_count": len(self.idempotency_keys),
            "last_rule_fire_at": dict(self.last_rule_fire_at),
        }


class DynamoDBStateStore:
    """Production state adapter contract.

    Required DynamoDB behavior:
    - idempotency writes use ConditionExpression attribute_not_exists(pk)
    - cooldown reads use consistent reads when checking the latest fire time
    - records include ttl_epoch_seconds so stale keys expire automatically
    """

    def __init__(self, table_name: str, *, table: object | None = None, ttl_seconds: int = 86400) -> None:
        self.table_name = table_name
        self.ttl_seconds = ttl_seconds
        self.table = table or _load_boto3_table(table_name)

    def has_idempotency_key(self, key: str) -> bool:
        response = self.table.get_item(
            Key={"pk": _idempotency_pk(key)},
            ConsistentRead=True,
            ProjectionExpression="pk",
        )
        return "Item" in response

    def record_idempotency_key(self, key: str) -> None:
        try:
            self.table.put_item(
                Item={
                    "pk": _idempotency_pk(key),
                    "record_type": "idempotency",
                    "idempotency_key": key,
                    "created_at": now_seconds(),
                    "ttl_epoch_seconds": now_seconds() + self.ttl_seconds,
                },
                ConditionExpression="attribute_not_exists(pk)",
            )
        except Exception as exc:  # noqa: BLE001 - boto3 exposes provider-specific subclasses
            if _is_conditional_check_failed(exc):
                raise DuplicateStateRecordError(key) from exc
            raise

    def cooldown_active(self, rule_id: str, *, now: int, cooldown_seconds: int) -> bool:
        response = self.table.get_item(
            Key={"pk": _rule_pk(rule_id)},
            ConsistentRead=True,
            ProjectionExpression="last_fire_at",
        )
        item = response.get("Item")
        if not item:
            return False
        last_fire_at = int(item.get("last_fire_at", 0))
        return now - last_fire_at < cooldown_seconds

    def record_rule_fire(self, rule_id: str, *, now: int) -> None:
        self.table.put_item(
            Item={
                "pk": _rule_pk(rule_id),
                "record_type": "cooldown",
                "rule_id": rule_id,
                "last_fire_at": now,
                "ttl_epoch_seconds": now + 90 * 86400,
            }
        )

    def record_decision_state(
        self, idempotency_key: str, rule_id: str | None = None, *, now: int = 0,
    ) -> None:
        """Atomically write idempotency key and cooldown via TransactWriteItems.

        If the idempotency key already exists the transaction is cancelled and
        DuplicateStateRecordError is raised.  Because both writes live inside a
        single transaction, a Lambda crash between the two can never leave an
        orphaned idempotency lock without the corresponding cooldown update.
        """
        client = self.table.meta.client
        now_ts = now_seconds()
        transact_items: list[dict[str, Any]] = [
            {
                "Put": {
                    "TableName": self.table_name,
                    "Item": {
                        "pk": {"S": _idempotency_pk(idempotency_key)},
                        "record_type": {"S": "idempotency"},
                        "idempotency_key": {"S": idempotency_key},
                        "created_at": {"N": str(now_ts)},
                        "ttl_epoch_seconds": {"N": str(now_ts + self.ttl_seconds)},
                    },
                    "ConditionExpression": "attribute_not_exists(pk)",
                }
            }
        ]
        if rule_id:
            transact_items.append({
                "Put": {
                    "TableName": self.table_name,
                    "Item": {
                        "pk": {"S": _rule_pk(rule_id)},
                        "record_type": {"S": "cooldown"},
                        "rule_id": {"S": rule_id},
                        "last_fire_at": {"N": str(now)},
                        "ttl_epoch_seconds": {"N": str(now + 90 * 86400)},
                    },
                }
            })
        try:
            client.transact_write_items(TransactItems=transact_items)
        except Exception as exc:  # noqa: BLE001
            exc_name = type(exc).__name__
            if _is_conditional_check_failed(exc) or "TransactionCanceledException" in exc_name:
                raise DuplicateStateRecordError(idempotency_key) from exc
            raise

    def snapshot(self) -> dict[str, object]:
        return {
            "store": "DynamoDBStateStore",
            "table_name": self.table_name,
            "ttl_seconds": self.ttl_seconds,
        }


def now_seconds() -> int:
    return int(time.time())


def _load_boto3_table(table_name: str) -> object:
    try:
        import boto3  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("boto3 is required for DynamoDBStateStore.") from exc
    return boto3.resource("dynamodb").Table(table_name)


def _idempotency_pk(key: str) -> str:
    return f"IDEMPOTENCY#{key}"


def _rule_pk(rule_id: str) -> str:
    return f"RULE#{rule_id}"


def _is_conditional_check_failed(exc: Exception) -> bool:
    response = getattr(exc, "response", {})
    if isinstance(response, dict):
        return response.get("Error", {}).get("Code") == "ConditionalCheckFailedException"
    return exc.__class__.__name__ == "ConditionalCheckFailedException"
