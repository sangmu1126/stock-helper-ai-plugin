"""런타임 설정에 맞는 로컬 저장소를 만든다.

backend 값:
- memory (기본값): 호출마다 새 메모리 저장소. 같은 프로세스 안의 테스트·데모용.
- file: 로컬 파일에 저장해 실행 간에도 중복 차단·쿨다운·감사 로그를 유지.
"""
from __future__ import annotations

from typing import Any

from decision_log_store import FileDecisionLogStore, InMemoryDecisionLogStore
from state_store import FileStateStore, InMemoryStateStore

SUPPORTED_BACKENDS = ("memory", "file")


def make_state_store(runtime_config: dict[str, Any]) -> Any:
    backend = _backend(runtime_config, "state_backend")
    if backend == "file":
        return FileStateStore(_required_path(runtime_config, "state_file", "SAFE_TRADE_STATE_FILE"))
    return InMemoryStateStore()


def make_decision_log_store(runtime_config: dict[str, Any]) -> Any:
    backend = _backend(runtime_config, "decision_log_backend")
    if backend == "file":
        return FileDecisionLogStore(_required_path(runtime_config, "decision_log_file", "SAFE_TRADE_DECISION_LOG_FILE"))
    return InMemoryDecisionLogStore()


def _backend(runtime_config: dict[str, Any], key: str) -> str:
    backend = str(runtime_config.get(key) or "memory").strip().lower()
    if backend not in SUPPORTED_BACKENDS:
        raise ValueError(f"Unsupported {key}: {backend!r} (supported: {', '.join(SUPPORTED_BACKENDS)})")
    return backend


def _required_path(runtime_config: dict[str, Any], key: str, env_name: str) -> str:
    path = runtime_config.get(key)
    if not path:
        raise RuntimeError(f"{env_name} is required when the file backend is selected.")
    return str(path)
