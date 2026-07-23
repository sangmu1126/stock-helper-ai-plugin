from __future__ import annotations

import time
import uuid
from typing import Any


def start_trace(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "trace_id": str(event.get("trace_id") or uuid.uuid4()),
        "started_at_epoch_ms": int(time.time() * 1000),
        "source": str(event.get("source", "runtime")),
    }


def finish_trace(trace: dict[str, Any], *, decision: str, reasons: list[str]) -> dict[str, Any]:
    finished_at = int(time.time() * 1000)
    return {
        **trace,
        "finished_at_epoch_ms": finished_at,
        "duration_ms": max(0, finished_at - int(trace["started_at_epoch_ms"])),
        "decision": decision,
        "reason_count": len(reasons),
    }


def metrics(*, decision: str, reasons: list[str], policy_decision: str) -> dict[str, Any]:
    return {
        "decision": decision,
        "policy_decision": policy_decision,
        "stop_count": len([reason for reason in reasons if "FAILED" in reason or "EXCEEDED" in reason or "REACHED" in reason]),
        "manual_confirmation_requested": decision == "MANUAL_CONFIRM",
    }
