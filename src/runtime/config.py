from __future__ import annotations

import os
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class RuntimeConfig:
    environment: str
    state_backend: str
    decision_log_backend: str
    state_file: str | None
    decision_log_file: str | None

    def to_dict(self) -> dict[str, str | None]:
        return asdict(self)


def load_runtime_config() -> RuntimeConfig:
    """로컬 실행 설정. 기본값은 메모리 저장소이며 외부 서비스에 접속하지 않는다."""
    return RuntimeConfig(
        environment=os.getenv("SAFE_TRADE_ENV", "local"),
        state_backend=os.getenv("SAFE_TRADE_STATE_BACKEND", "memory"),
        decision_log_backend=os.getenv("SAFE_TRADE_DECISION_LOG_BACKEND", "memory"),
        state_file=os.getenv("SAFE_TRADE_STATE_FILE"),
        decision_log_file=os.getenv("SAFE_TRADE_DECISION_LOG_FILE"),
    )
