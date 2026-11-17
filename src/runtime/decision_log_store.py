"""결정 감사 로그 저장소 (append-only).

- InMemoryDecisionLogStore: 기본값. 프로세스 메모리에만 저장한다.
- FileDecisionLogStore: 로컬 JSONL 파일에 한 줄씩 추가한다.

외부 클라우드 저장소는 쓰지 않는다.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from decision_log import stable_id


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

    def query_user_decisions(self, user_id: str, limit: int = 50) -> dict[str, Any]:
        return _query(self.entries, user_id, limit)


class FileDecisionLogStore:
    """로컬 JSONL 파일에 결정을 한 줄씩 추가한다."""

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
        return {
            "store": "FileDecisionLogStore",
            "path": str(self.path),
            "entry_count": len(self.read_all()),
        }

    def query_user_decisions(self, user_id: str, limit: int = 50) -> dict[str, Any]:
        return _query(self.read_all(), user_id, limit)


def _query(entries: list[dict[str, Any]], user_id: str, limit: int) -> dict[str, Any]:
    """사용자 ID는 해시로만 비교한다(원문 ID를 로그에 남기지 않는다)."""
    user_hash = stable_id(user_id)
    results = [entry for entry in entries if entry.get("user_id_hash") == user_hash]
    results.sort(key=lambda entry: str(entry.get("created_at", "")), reverse=True)
    return {"items": results[:limit]}
