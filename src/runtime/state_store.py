from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol


class StateStore(Protocol):
    def has_idempotency_key(self, key: str) -> bool: ...

    def record_idempotency_key(self, key: str, user_id: str | None = None) -> None: ...

    def cooldown_active(self, rule_id: str, *, now: int, cooldown_seconds: int) -> bool: ...

    def record_rule_fire(self, rule_id: str, *, now: int, user_id: str | None = None) -> None: ...

    def record_decision_state(
        self, idempotency_key: str, rule_id: str | None = None, *, now: int = 0, user_id: str | None = None,
    ) -> None: ...

    def query_by_user(self, user_id: str, limit: int = 50) -> list[dict[str, Any]]: ...


class DuplicateStateRecordError(RuntimeError):
    """Raised when a conditional idempotency write detects a duplicate."""


@dataclass
class InMemoryStateStore:
    idempotency_keys: set[str] = field(default_factory=set)
    last_rule_fire_at: dict[str, int] = field(default_factory=dict)

    def has_idempotency_key(self, key: str) -> bool:
        return key in self.idempotency_keys

    def record_idempotency_key(self, key: str, user_id: str | None = None) -> None:
        self.idempotency_keys.add(key)

    def cooldown_active(self, rule_id: str, *, now: int, cooldown_seconds: int) -> bool:
        last_fire_at = self.last_rule_fire_at.get(rule_id)
        return last_fire_at is not None and now - last_fire_at < cooldown_seconds

    def record_rule_fire(self, rule_id: str, *, now: int, user_id: str | None = None) -> None:
        self.last_rule_fire_at[rule_id] = now

    def record_decision_state(
        self, idempotency_key: str, rule_id: str | None = None, *, now: int = 0, user_id: str | None = None,
    ) -> None:
        """Atomically record idempotency key and optional rule fire."""
        if self.has_idempotency_key(idempotency_key):
            raise DuplicateStateRecordError(idempotency_key)
        self.record_idempotency_key(idempotency_key, user_id=user_id)
        if rule_id:
            self.record_rule_fire(rule_id, now=now, user_id=user_id)

    def query_by_user(self, user_id: str, limit: int = 50) -> list[dict[str, Any]]:
        # In-memory mock just returns empty for now
        return []

    def snapshot(self) -> dict[str, object]:
        return {
            "store": "InMemoryStateStore",
            "idempotency_key_count": len(self.idempotency_keys),
            "last_rule_fire_at": dict(self.last_rule_fire_at),
        }


class FileStateStore:
    """Local durable store for tests and single-node prototypes.

    AWS Lambda should use DynamoDB or another external store instead of relying
    on the ephemeral function filesystem.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def has_idempotency_key(self, key: str) -> bool:
        return key in self._read()["idempotency_keys"]

    def record_idempotency_key(self, key: str, user_id: str | None = None) -> None:
        state = self._read()
        keys = set(state["idempotency_keys"])
        keys.add(key)
        state["idempotency_keys"] = sorted(keys)
        self._write(state)

    def cooldown_active(self, rule_id: str, *, now: int, cooldown_seconds: int) -> bool:
        last_fire_at = self._read()["last_rule_fire_at"].get(rule_id)
        if last_fire_at is None:
            return False
        return now - int(last_fire_at) < cooldown_seconds

    def record_rule_fire(self, rule_id: str, *, now: int, user_id: str | None = None) -> None:
        state = self._read()
        state["last_rule_fire_at"][rule_id] = now
        self._write(state)

    def record_decision_state(
        self, idempotency_key: str, rule_id: str | None = None, *, now: int = 0, user_id: str | None = None,
    ) -> None:
        """Atomically record idempotency key and optional rule fire."""
        if self.has_idempotency_key(idempotency_key):
            raise DuplicateStateRecordError(idempotency_key)
        self.record_idempotency_key(idempotency_key, user_id=user_id)
        if rule_id:
            self.record_rule_fire(rule_id, now=now, user_id=user_id)

    def query_by_user(self, user_id: str, limit: int = 50) -> list[dict[str, Any]]:
        # File store mock just returns empty
        return []

    def snapshot(self) -> dict[str, object]:
        state = self._read()
        return {
            "store": "FileStateStore",
            "path": str(self.path),
            "idempotency_key_count": len(state["idempotency_keys"]),
            "last_rule_fire_at": dict(state["last_rule_fire_at"]),
        }

    def _read(self) -> dict[str, object]:
        if not self.path.exists():
            return {"idempotency_keys": [], "last_rule_fire_at": {}}
        with self.path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return {
            "idempotency_keys": list(data.get("idempotency_keys", [])),
            "last_rule_fire_at": dict(data.get("last_rule_fire_at", {})),
        }

    def _write(self, state: dict[str, object]) -> None:
        temp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(state, handle, ensure_ascii=False, sort_keys=True)
        temp_path.replace(self.path)


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

    def record_idempotency_key(self, key: str, user_id: str | None = None) -> None:
        try:
            item: dict[str, Any] = {
                "pk": _idempotency_pk(key),
                "record_type": "idempotency",
                "idempotency_key": key,
                "created_at": now_seconds(),
                "ttl_epoch_seconds": now_seconds() + self.ttl_seconds,
            }
            if user_id:
                item["user_id"] = user_id
            self.table.put_item(
                Item=item,
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

    def record_rule_fire(self, rule_id: str, *, now: int, user_id: str | None = None) -> None:
        item: dict[str, Any] = {
            "pk": _rule_pk(rule_id),
            "record_type": "cooldown",
            "rule_id": rule_id,
            "last_fire_at": now,
            "created_at": now,
            "ttl_epoch_seconds": now + 90 * 86400,
        }
        if user_id:
            item["user_id"] = user_id
        self.table.put_item(Item=item)

    def record_decision_state(
        self, idempotency_key: str, rule_id: str | None = None, *, now: int = 0, user_id: str | None = None,
    ) -> None:
        """Atomically write idempotency key and cooldown via TransactWriteItems.

        If the idempotency key already exists the transaction is cancelled and
        DuplicateStateRecordError is raised.  Because both writes live inside a
        single transaction, a Lambda crash between the two can never leave an
        orphaned idempotency lock without the corresponding cooldown update.
        """
        client = self.table.meta.client
        now_ts = now_seconds()
        
        idemp_item: dict[str, Any] = {
            "pk": {"S": _idempotency_pk(idempotency_key)},
            "record_type": {"S": "idempotency"},
            "idempotency_key": {"S": idempotency_key},
            "created_at": {"N": str(now_ts)},
            "ttl_epoch_seconds": {"N": str(now_ts + self.ttl_seconds)},
        }
        if user_id:
            idemp_item["user_id"] = {"S": user_id}

        transact_items: list[dict[str, Any]] = [
            {
                "Put": {
                    "TableName": self.table_name,
                    "Item": idemp_item,
                    "ConditionExpression": "attribute_not_exists(pk)",
                }
            }
        ]
        if rule_id:
            rule_item: dict[str, Any] = {
                "pk": {"S": _rule_pk(rule_id)},
                "record_type": {"S": "cooldown"},
                "rule_id": {"S": rule_id},
                "last_fire_at": {"N": str(now)},
                "created_at": {"N": str(now)},
                "ttl_epoch_seconds": {"N": str(now + 90 * 86400)},
            }
            if user_id:
                rule_item["user_id"] = {"S": user_id}
            
            transact_items.append({
                "Put": {
                    "TableName": self.table_name,
                    "Item": rule_item,
                }
            })
        try:
            client.transact_write_items(TransactItems=transact_items)
        except Exception as exc:  # noqa: BLE001
            exc_name = type(exc).__name__
            if _is_conditional_check_failed(exc) or "TransactionCanceledException" in exc_name:
                raise DuplicateStateRecordError(idempotency_key) from exc
            raise

    def query_by_user(self, user_id: str, limit: int = 50) -> list[dict[str, Any]]:
        from boto3.dynamodb.conditions import Key  # type: ignore[import-not-found]
        response = self.table.query(
            IndexName="user-index",
            KeyConditionExpression=Key("user_id").eq(user_id),
            ScanIndexForward=False,
            Limit=limit,
        )
        return list(response.get("Items", []))

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
