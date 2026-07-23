from __future__ import annotations

import os
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class RuntimeConfig:
    state_table_name: str | None
    decision_log_table_name: str | None
    broker_secret_name: str | None
    environment: str
    state_backend: str
    decision_log_backend: str

    def to_dict(self) -> dict[str, str | None]:
        return asdict(self)


def load_runtime_config() -> RuntimeConfig:
    return RuntimeConfig(
        state_table_name=os.getenv("SAFE_TRADE_STATE_TABLE"),
        decision_log_table_name=os.getenv("SAFE_TRADE_DECISION_LOG_TABLE"),
        broker_secret_name=os.getenv("SAFE_TRADE_BROKER_SECRET"),
        environment=os.getenv("SAFE_TRADE_ENV", "local"),
        state_backend=os.getenv("SAFE_TRADE_STATE_BACKEND", "memory"),
        decision_log_backend=os.getenv("SAFE_TRADE_DECISION_LOG_BACKEND", "memory"),
    )
