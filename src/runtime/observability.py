from __future__ import annotations

import json
import time
import uuid
from typing import Any


def start_trace(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "trace_id": str(event.get("trace_id") or uuid.uuid4()),
        "correlation_id": str(event.get("correlation_id") or uuid.uuid4()),
        "user_id": str(event.get("user_id") or "anonymous"),
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


def emit_emf_metrics(trace: dict[str, Any], metrics_data: dict[str, Any]) -> None:
    now_ms = int(time.time() * 1000)
    emf = {
        "_aws": {
            "Timestamp": now_ms,
            "CloudWatchMetrics": [
                {
                    "Namespace": "KakaoPay/SafeTrade",
                    "Dimensions": [["Decision"]],
                    "Metrics": [
                        {"Name": "StopCount", "Unit": "Count"},
                        {"Name": "DurationMs", "Unit": "Milliseconds"}
                    ]
                }
            ]
        },
        "Decision": metrics_data.get("decision", "UNKNOWN"),
        "PolicyDecision": metrics_data.get("policy_decision", "UNKNOWN"),
        "StopCount": metrics_data.get("stop_count", 0),
        "DurationMs": trace.get("duration_ms", 0),
        "TraceId": trace.get("trace_id", ""),
        "CorrelationId": trace.get("correlation_id", ""),
        "UserId": trace.get("user_id", "anonymous"),
    }
    print(json.dumps(emf, ensure_ascii=False))


def emit_async_decision_event(decision_log: dict[str, Any]) -> None:
    """Mock asynchronous event emission to EventBridge."""
    try:
        import boto3  # type: ignore[import-not-found]
        client = boto3.client("events")
        client.put_events(
            Entries=[
                {
                    "Source": "com.kakaopay.safetrade",
                    "DetailType": "DecisionMade",
                    "Detail": json.dumps(decision_log, ensure_ascii=False),
                    "EventBusName": "default",
                }
            ]
        )
    except Exception as exc:  # noqa: BLE001
        # Log failure but DO NOT block the synchronous response to the user.
        print(f"Failed to emit async event: {exc}")
