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
        rule_id = make_rule_id(asset, trigger, action)
        idempotency_key = make_idempotency_key(rule_id, trigger_evaluation)
        state_snapshot = _snapshot(self.state_store)

        policy_decision = policy_result.get("decision")
        if policy_decision == "BLOCK":
            return self._result(
                "BLOCK",
                tuple(policy_result.get("reasons", ["POLICY_BLOCKED"])),
                rule_id,
                idempotency_key,
                False,
                state_snapshot,
            )
        if policy_decision == "REQUIRE_CLARIFICATION":
            return self._result(
                "REQUIRE_CLARIFICATION",
                tuple(policy_result.get("reasons", ["POLICY_REQUIRES_CLARIFICATION"])),
                rule_id,
                idempotency_key,
                False,
                state_snapshot,
            )

        if trigger_evaluation is None:
            return self._result(
                "WAIT",
                ("TRIGGER_NOT_EVALUATED",),
                rule_id,
                idempotency_key,
                False,
                state_snapshot,
            )
        if trigger_evaluation.get("status") == "STOP":
            return self._result(
                "STOP",
                (str(trigger_evaluation.get("reason")),),
                rule_id,
                idempotency_key,
                False,
                state_snapshot,
            )
        if trigger_evaluation.get("status") == "WAIT":
            return self._result(
                "WAIT",
                (str(trigger_evaluation.get("reason")),),
                rule_id,
                idempotency_key,
                False,
                state_snapshot,
            )

        if self.state_store.has_idempotency_key(idempotency_key):
            return self._result(
                "WAIT",
                ("DUPLICATE_DECISION_BLOCKED",),
                rule_id,
                idempotency_key,
                False,
                state_snapshot,
            )

        cooldown_seconds = cooldown_to_seconds(cooldown)
        if cooldown_seconds and self.state_store.cooldown_active(rule_id, now=checked_at, cooldown_seconds=cooldown_seconds):
            return self._result(
                "WAIT",
                ("COOLDOWN_ACTIVE",),
                rule_id,
                idempotency_key,
                False,
                state_snapshot,
            )

        try:
            self.state_store.record_idempotency_key(idempotency_key)
        except DuplicateStateRecordError:
            return self._result(
                "WAIT",
                ("DUPLICATE_DECISION_BLOCKED",),
                rule_id,
                idempotency_key,
                False,
                _snapshot(self.state_store),
            )
        if action in {"prepare_buy_order", "prepare_sell_order"}:
            self.state_store.record_rule_fire(rule_id, now=checked_at)
            return self._result(
                "MANUAL_CONFIRM",
                ("TRIGGER_MATCHED_REQUIRES_MANUAL_CONFIRMATION",),
                rule_id,
                idempotency_key,
                True,
                _snapshot(self.state_store),
            )
        if action == "notify_only" or execution_mode == "notify_only":
            self.state_store.record_rule_fire(rule_id, now=checked_at)
            return self._result(
                "NOTIFY_ONLY",
                ("TRIGGER_MATCHED_NOTIFY_ONLY",),
                rule_id,
                idempotency_key,
                True,
                _snapshot(self.state_store),
            )

        return self._result(
            "REQUIRE_CLARIFICATION",
            ("UNSUPPORTED_ACTION_FOR_DECISION",),
            rule_id,
            idempotency_key,
            False,
            state_snapshot,
        )

    def _result(
        self,
        decision: str,
        reasons: tuple[str, ...],
        rule_id: str,
        idempotency_key: str,
        confirmation_required: bool,
        state_snapshot: dict[str, Any],
    ) -> DecisionResult:
        return DecisionResult(
            decision=decision,
            reasons=reasons,
            rule_id=rule_id,
            idempotency_key=idempotency_key,
            confirmation_required=confirmation_required,
            state_checked=True,
            state_snapshot=state_snapshot,
        )


def make_rule_id(asset: dict[str, Any], trigger: dict[str, Any], action: str) -> str:
    return stable_id(asset.get("symbol"), trigger, action)


def make_idempotency_key(rule_id: str, trigger_evaluation: dict[str, Any] | None) -> str:
    details = (trigger_evaluation or {}).get("details", {})
    return stable_id(
        rule_id,
        (trigger_evaluation or {}).get("status"),
        (trigger_evaluation or {}).get("reason"),
        details.get("quote_timestamp"),
        details.get("quote_age_seconds"),
    )


def cooldown_to_seconds(cooldown: dict[str, Any]) -> int:
    if cooldown.get("min_days_between_triggers"):
        return int(cooldown["min_days_between_triggers"]) * 86400
    if cooldown.get("min_minutes_between_triggers"):
        return int(cooldown["min_minutes_between_triggers"]) * 60
    return 0


def _snapshot(state_store: StateStore) -> dict[str, Any]:
    if hasattr(state_store, "snapshot"):
        return getattr(state_store, "snapshot")()
    return {"store": state_store.__class__.__name__}
