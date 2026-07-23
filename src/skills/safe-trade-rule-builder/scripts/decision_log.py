from __future__ import annotations

import hashlib
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


DECISION_LOG_SCHEMA_VERSION = "decision-log.v1"


@dataclass(frozen=True)
class DecisionLog:
    decision_id: str
    rule_id: str
    user_id_hash: str
    schema_version: str
    rule_version: str
    parser_version: str
    policy_version: str
    market_snapshot: dict[str, Any] | None
    trigger_evaluation: dict[str, Any] | None
    guardrail_evaluation: dict[str, Any]
    decision: str
    reasons: tuple[str, ...]
    confirmation_required: bool
    idempotency_key: str
    created_at: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def create_decision_log(
    *,
    rule_id: str,
    parser: dict[str, Any],
    policy_result: dict[str, Any],
    decision_result: dict[str, Any],
    market_data: dict[str, Any] | None,
    trigger_evaluation: dict[str, Any] | None,
    guardrails: dict[str, Any],
    user_id: str = "anonymous",
    rule_version: str = "draft",
) -> DecisionLog:
    decision_id = str(uuid.uuid4())
    idempotency_key = decision_result.get("idempotency_key") or stable_id(
        rule_id,
        decision_result.get("decision"),
        trigger_evaluation,
    )
    return DecisionLog(
        decision_id=decision_id,
        rule_id=rule_id,
        user_id_hash=stable_id(user_id),
        schema_version=DECISION_LOG_SCHEMA_VERSION,
        rule_version=rule_version,
        parser_version=str(parser.get("source", "unknown")),
        policy_version=str(policy_result.get("policy_version", "unknown")),
        market_snapshot=market_data,
        trigger_evaluation=trigger_evaluation,
        guardrail_evaluation=guardrails,
        decision=str(decision_result.get("decision")),
        reasons=tuple(decision_result.get("reasons", [])),
        confirmation_required=bool(decision_result.get("confirmation_required")),
        idempotency_key=idempotency_key,
        created_at=datetime.now(timezone.utc).isoformat(),
        metadata={
            "policy_decision": policy_result.get("decision"),
            "fallback_used": parser.get("fallback_used"),
        },
    )


def stable_id(*parts: Any) -> str:
    payload = "|".join(repr(part) for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]
