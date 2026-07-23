from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from decision_log import stable_id
from state_store import DuplicateStateRecordError, InMemoryStateStore, StateStore, now_seconds


@dataclass(frozen=True)
class DecisionResult:
    decision: str
    reasons: tuple[str, ...]
    rule_id: str
    idempotency_key: str
    confirmation_required: bool
    state_checked: bool
    state_snapshot: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DecisionEngine:
    def __init__(self, state_store: StateStore | None = None) -> None:
        self.state_store = state_store or InMemoryStateStore()

    def decide(
        self,
        *,
        asset: dict[str, Any],
        trigger: dict[str, Any],
        action: str,
        execution_mode: str,
        cooldown: dict[str, Any],
        policy_result: dict[str, Any],
        trigger_evaluation: dict[str, Any] | None,
        now: int | None = None,
    ) -> DecisionResult:
        checked_at = now if now is not None else now_seconds()
        rule_id = stable_id(asset.get("symbol"), trigger, action)
        idempotency_key = make_idempotency_key(rule_id, trigger_evaluation)
        state_snapshot = self._snapshot()

        policy_decision = policy_result.get("decision")
        if policy_decision in {"BLOCK", "REQUIRE_CLARIFICATION"}:
            return self._result(
                str(policy_decision),
                tuple(policy_result.get("reasons", [str(policy_decision)])),
                rule_id,
                idempotency_key,
                False,
                state_snapshot,
            )
        if trigger_evaluation is None:
            return self._result("WAIT", ("TRIGGER_NOT_EVALUATED",), rule_id, idempotency_key, False, state_snapshot)
        if trigger_evaluation.get("status") == "STOP":
            return self._result("STOP", normalize_reasons(trigger_evaluation.get("reason")), rule_id, idempotency_key, False, state_snapshot)
        if trigger_evaluation.get("status") == "WAIT":
            return self._result("WAIT", normalize_reasons(trigger_evaluation.get("reason")), rule_id, idempotency_key, False, state_snapshot)

        if self.state_store.has_idempotency_key(idempotency_key):
            return self._result("WAIT", ("DUPLICATE_DECISION_BLOCKED",), rule_id, idempotency_key, False, state_snapshot)
        cooldown_seconds = cooldown_to_seconds(cooldown)
        if cooldown_seconds and self.state_store.cooldown_active(rule_id, now=checked_at, cooldown_seconds=cooldown_seconds):
            return self._result("WAIT", ("COOLDOWN_ACTIVE",), rule_id, idempotency_key, False, state_snapshot)

        is_order = action in {"prepare_buy_order", "prepare_sell_order"} and execution_mode == "manual_confirm"
        is_notify = action == "notify_only" or execution_mode == "notify_only"
        fire_rule_id = rule_id if (is_order or is_notify) else None

        try:
            self.state_store.record_decision_state(idempotency_key, fire_rule_id, now=checked_at)
        except DuplicateStateRecordError:
            return self._result("WAIT", ("DUPLICATE_DECISION_BLOCKED",), rule_id, idempotency_key, False, self._snapshot())

        if is_order:
            return self._result(
                "MANUAL_CONFIRM",
                ("TRIGGER_MATCHED_REQUIRES_MANUAL_CONFIRMATION",),
                rule_id,
                idempotency_key,
                True,
                self._snapshot(),
            )
        if is_notify:
            return self._result("NOTIFY_ONLY", ("TRIGGER_MATCHED_NOTIFY_ONLY",), rule_id, idempotency_key, True, self._snapshot())
        return self._result("REQUIRE_CLARIFICATION", ("UNSUPPORTED_ACTION_FOR_DECISION",), rule_id, idempotency_key, False, state_snapshot)

    def _snapshot(self) -> dict[str, Any]:
        if hasattr(self.state_store, "snapshot"):
            return getattr(self.state_store, "snapshot")()
        return {"store": self.state_store.__class__.__name__}

    def _result(
        self,
        decision: str,
        reasons: tuple[str, ...],
        rule_id: str,
        idempotency_key: str,
        confirmation_required: bool,
        state_snapshot: dict[str, Any],
    ) -> DecisionResult:
        return DecisionResult(decision, reasons, rule_id, idempotency_key, confirmation_required, True, state_snapshot)


def cooldown_to_seconds(cooldown: dict[str, Any]) -> int:
    if cooldown.get("min_days_between_triggers"):
        return int(cooldown["min_days_between_triggers"]) * 86400
    if cooldown.get("min_minutes_between_triggers"):
        return int(cooldown["min_minutes_between_triggers"]) * 60
    return 0


def normalize_reasons(reason: Any) -> tuple[str, ...]:
    if reason is None:
        return ("UNKNOWN_REASON",)
    if isinstance(reason, (list, tuple)):
        candidates = [str(item) for item in reason]
    else:
        candidates = str(reason).split(";")
    normalized = tuple(item.strip() for item in candidates if item and item.strip())
    return normalized or ("UNKNOWN_REASON",)


def make_idempotency_key(rule_id: str, trigger_evaluation: dict[str, Any] | None) -> str:
    details = (trigger_evaluation or {}).get("details", {})
    return stable_id(
        rule_id,
        (trigger_evaluation or {}).get("status"),
        (trigger_evaluation or {}).get("reason"),
        details.get("quote_timestamp"),
        details.get("quote_age_seconds"),
    )
