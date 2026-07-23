from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


class StateStore(Protocol):
    def has_idempotency_key(self, key: str) -> bool:
        """Return true when a decision with this idempotency key was already processed."""

    def record_idempotency_key(self, key: str) -> None:
        """Persist an idempotency key after processing."""

    def cooldown_active(self, rule_id: str, *, now: int, cooldown_seconds: int) -> bool:
        """Return true when the rule fired too recently."""

    def record_rule_fire(self, rule_id: str, *, now: int) -> None:
        """Persist the latest rule fire timestamp."""

    def record_decision_state(
        self, idempotency_key: str, rule_id: str | None = None, *, now: int = 0,
    ) -> None:
        """Atomically record idempotency key and optional rule fire."""


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
        if last_fire_at is None:
            return False
        return now - last_fire_at < cooldown_seconds

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

    def record_idempotency_key(self, key: str) -> None:
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

    def record_rule_fire(self, rule_id: str, *, now: int) -> None:
        state = self._read()
        state["last_rule_fire_at"][rule_id] = now
        self._write(state)

    def snapshot(self) -> dict[str, object]:
        state = self._read()
        return {
            "store": "FileStateStore",
            "path": str(self.path),
            "idempotency_key_count": len(state["idempotency_keys"]),
            "last_rule_fire_at": dict(state["last_rule_fire_at"]),
        }

    def record_decision_state(
        self, idempotency_key: str, rule_id: str | None = None, *, now: int = 0,
    ) -> None:
        """Atomically record idempotency key and optional rule fire."""
        if self.has_idempotency_key(idempotency_key):
            raise DuplicateStateRecordError(idempotency_key)
        self.record_idempotency_key(idempotency_key)
        if rule_id:
            self.record_rule_fire(rule_id, now=now)

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
    """Production adapter placeholder.

    Required DynamoDB behavior before connecting a broker workflow:
    - idempotency writes use ConditionExpression attribute_not_exists(pk)
    - cooldown reads use strongly consistent reads
    - transient rows include ttl_epoch_seconds for automatic expiry
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
