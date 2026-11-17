"""중복 실행 방지(idempotency)와 쿨다운 상태 저장소.

- InMemoryStateStore: 기본값. 프로세스 메모리에만 저장한다.
- FileStateStore: 로컬 JSON 파일에 저장해 실행 간에도 중복 차단·쿨다운을 유지한다.

외부 클라우드 저장소는 쓰지 않는다.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


class StateStore(Protocol):
    def has_idempotency_key(self, key: str) -> bool: ...

    def record_idempotency_key(self, key: str, user_id: str | None = None) -> None: ...

    def cooldown_active(self, rule_id: str, *, now: int, cooldown_seconds: int) -> bool: ...

    def record_rule_fire(self, rule_id: str, *, now: int, user_id: str | None = None) -> None: ...

    def record_decision_state(
        self, idempotency_key: str, rule_id: str | None = None, *, now: int = 0, user_id: str | None = None
    ) -> None: ...


class DuplicateStateRecordError(RuntimeError):
    """같은 idempotency key가 이미 기록되어 있을 때 발생한다."""


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
        self, idempotency_key: str, rule_id: str | None = None, *, now: int = 0, user_id: str | None = None
    ) -> None:
        """idempotency key와(있으면) 쿨다운 시각을 함께 기록한다. 이미 있으면 DuplicateStateRecordError."""
        if self.has_idempotency_key(idempotency_key):
            raise DuplicateStateRecordError(idempotency_key)
        self.record_idempotency_key(idempotency_key, user_id=user_id)
        if rule_id:
            self.record_rule_fire(rule_id, now=now, user_id=user_id)

    def snapshot(self) -> dict[str, object]:
        return {
            "store": "InMemoryStateStore",
            "idempotency_key_count": len(self.idempotency_keys),
            "last_rule_fire_at": dict(self.last_rule_fire_at),
        }


class FileStateStore:
    """로컬 JSON 파일 저장소. 한 대의 PC에서 실행 간 상태를 유지할 때 쓴다."""

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
        self, idempotency_key: str, rule_id: str | None = None, *, now: int = 0, user_id: str | None = None
    ) -> None:
        """idempotency key와(있으면) 쿨다운 시각을 한 번의 파일 쓰기로 기록한다."""
        state = self._read()
        if idempotency_key in state["idempotency_keys"]:
            raise DuplicateStateRecordError(idempotency_key)
        state["idempotency_keys"] = sorted({*state["idempotency_keys"], idempotency_key})
        if rule_id:
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


def now_seconds() -> int:
    return int(time.time())
