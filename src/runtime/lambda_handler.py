"""AWS Lambda handler for safe trading-rule evaluation.

This runtime does not place orders. It validates policy, broker/account health,
market state, quote freshness, trigger status, idempotency, and confirmation
requirements before returning a decision object.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

# Ensure runtime directory is on sys.path for Lambda packaging.
_RUNTIME_DIR = Path(__file__).resolve().parent
if str(_RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(_RUNTIME_DIR))

import auth as _AUTH  # noqa: E402
import config as _CONFIG  # noqa: E402
import confirmation as _CONFIRMATION  # noqa: E402
import decision_engine as _DECISION  # noqa: E402
import decision_log as _DECISION_LOG  # noqa: E402
import error_taxonomy as _ERRORS  # noqa: E402
import event_context as _EVENT_CONTEXT  # noqa: E402
import observability as _OBSERVABILITY  # noqa: E402
import policy_engine as _POLICY  # noqa: E402
import prompt_security as _PROMPT_SECURITY  # noqa: E402
import redaction as _REDACTION  # noqa: E402
import response_schema as _RESPONSE  # noqa: E402
import risk_controls as _RISK  # noqa: E402
import store_factory as _STORE_FACTORY  # noqa: E402
import ux_classifier as _UX  # noqa: E402
from evaluation import OPEN_MARKET_STATES, evaluate_trigger, quote_age_status  # noqa: E402


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    is_api_gateway = "httpMethod" in event or "routeKey" in event or ("requestContext" in event and "http" in event.get("requestContext", {}))
    try:
        if is_api_gateway:
            auth_rejection = _AUTH.validate_api_key(event)
            if auth_rejection:
                return auth_rejection
            body = event.get("body", "{}")
            payload = json.loads(body) if isinstance(body, str) else body
        else:
            payload = event

        response_payload = _handle_event(payload, context)
        
        if is_api_gateway:
            return {
                "statusCode": 200,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps(response_payload, ensure_ascii=False),
            }
        return response_payload
    except Exception as exc:  # noqa: BLE001 - top-level fail-closed boundary
        error_payload = _RESPONSE.envelope({
            "decision": "STOP",
            "reasons": ["INTERNAL_ERROR"],
            "errors": _ERRORS.describe_reasons(["INTERNAL_ERROR"]),
            "stop_level": "critical",
            "user_action": "시스템 내부 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
            "internal_error": f"{type(exc).__name__}: {exc}",
        })
        if is_api_gateway:
            return {
                "statusCode": 500,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps(error_payload, ensure_ascii=False),
            }
        return error_payload


def _handle_event(event: dict[str, Any], context: Any) -> dict[str, Any]:
    trace = _OBSERVABILITY.start_trace(event)
    runtime_event = _EVENT_CONTEXT.RuntimeEvent.from_event(event)
    runtime_config = _CONFIG.load_runtime_config().to_dict()
    state_store = _STORE_FACTORY.make_state_store(runtime_config)
    log_store = _STORE_FACTORY.make_decision_log_store(runtime_config)
    prompt_security_snapshot = _PROMPT_SECURITY.load_prompt_security_config_snapshot()
    prompt_security_result = _PROMPT_SECURITY.inspect_user_intent(
        str(event.get("intent", "")),
        config_snapshot=prompt_security_snapshot,
    )
    risk_result = _RISK.evaluate_runtime_risk(
        broker=runtime_event.broker_snapshot,
        account=runtime_event.account_snapshot,
        action=runtime_event.action,
        execution_mode=runtime_event.execution_mode,
    )

    policy_engine = _POLICY.PolicyEngine()
    policy_result = policy_engine.evaluate(
        intent=str(event.get("intent", "")),
        action=str(runtime_event.action),
        execution_mode=str(runtime_event.execution_mode),
        order=runtime_event.order,
        trigger=runtime_event.trigger,
        emotional_flags=runtime_event.emotional_flags,
        ambiguities=runtime_event.ambiguities,
    ).to_dict()

    now = int(time.time())
    precheck_stops = _precheck_stops(
        intent=str(event.get("intent", "")),
        broker=runtime_event.broker_snapshot,
        exchange=runtime_event.exchange,
        quote=runtime_event.quote,
        account=runtime_event.account_snapshot,
        action=runtime_event.action,
        execution_mode=runtime_event.execution_mode,
        now=now,
        risk_result=risk_result,
        prompt_security_result=prompt_security_result,
    )
    if precheck_stops:
        trigger_result = {"status": "STOP", "reason": precheck_stops}
    else:
        trigger_result = evaluate_trigger(runtime_event.trigger, runtime_event.quote)
    trigger_result = _with_quote_snapshot(trigger_result, runtime_event.quote)

    decision_result = _DECISION.DecisionEngine(state_store=state_store).decide(
        asset=runtime_event.asset,
        trigger=runtime_event.trigger,
        action=str(runtime_event.action),
        execution_mode=str(runtime_event.execution_mode),
        cooldown=runtime_event.cooldown,
        policy_result=policy_result,
        trigger_evaluation=trigger_result,
        now=now,
        user_id=str(event.get("user_id", "anonymous")),
    ).to_dict()
    decision_log = _DECISION_LOG.create_decision_log(
        rule_id=decision_result["rule_id"],
        parser=event.get("parser", {"source": "runtime"}),
        policy_result=policy_result,
        decision_result=decision_result,
        market_data=_REDACTION.redact(runtime_event.quote),
        trigger_evaluation=trigger_result,
        guardrails={
            "broker_health": runtime_event.broker_snapshot,
            "exchange_status": runtime_event.exchange,
            "account_limits": runtime_event.account_snapshot,
            "risk_result": risk_result,
            "precheck_stops": precheck_stops,
            "prompt_security": prompt_security_result.to_dict(),
            "config_metadata": {
                "policy": policy_engine.config_snapshot.metadata(),
                "risk": {
                    "version": risk_result.get("limits_version"),
                    "source": risk_result.get("limits_source"),
                    "fallback_used": risk_result.get("limits_fallback_used"),
                },
                "prompt_security": prompt_security_snapshot.metadata(),
            },
        },
        user_id=str(event.get("user_id", "anonymous")),
    ).to_dict()
    log_store.append(decision_log)

    reasons = _response_reasons(decision_result, precheck_stops)
    ux = _UX.classify(decision_result["decision"], reasons)
    response = _RESPONSE.envelope({
        "decision": decision_result["decision"],
        "reasons": reasons,
        "errors": _ERRORS.describe_reasons(reasons),
        "stop_level": ux["level"],
        "user_action": ux["user_action"],
        "policy_result": policy_result,
        "decision_result": decision_result,
        "decision_log": decision_log,
        "decision_log_store": log_store.snapshot(),
        "confirmation_checklist": _CONFIRMATION.build_confirmation_checklist(
            decision_result["decision"],
            action=str(runtime_event.action),
        ),
        "trigger_evaluation": trigger_result,
        "broker_health": runtime_event.broker_snapshot,
        "account_limits": runtime_event.account_snapshot,
        "risk_result": risk_result,
        "runtime_config": _REDACTION.redact(runtime_config),
        "metrics": _OBSERVABILITY.metrics(
            decision=decision_result["decision"],
            reasons=reasons,
            policy_decision=policy_result["decision"],
        ),
        "trace": _OBSERVABILITY.finish_trace(
            trace,
            decision=decision_result["decision"],
            reasons=reasons,
        ),
        "next_step": ux["user_action"],
    })
    missing_fields = _RESPONSE.validate_response(response)
    if missing_fields:
        response["schema_validation_errors"] = missing_fields

    _OBSERVABILITY.emit_emf_metrics(response["trace"], response["metrics"])
    
    return response


def _precheck_stops(
    *,
    intent: str,
    broker: dict[str, Any],
    exchange: dict[str, Any],
    quote: dict[str, Any],
    account: dict[str, Any],
    action: Any,
    execution_mode: Any,
    now: int,
    risk_result: dict[str, Any],
    prompt_security_result: Any | None = None,
) -> list[str]:
    stops: list[str] = []
    prompt_security = prompt_security_result or _PROMPT_SECURITY.inspect_user_intent(intent)
    if not prompt_security.safe:
        stops.extend(reason for reason in prompt_security.reasons if reason not in stops)
    if not broker.get("ok"):
        stops.append("BROKER_HEALTHCHECK_FAILED")
    if exchange.get("status") not in OPEN_MARKET_STATES:
        stops.append("EXCHANGE_NOT_OPEN")
    age_status = quote_age_status(quote, now)
    if not age_status["ok"]:
        stops.append(age_status["reason"])
    stops.extend(risk_result.get("reasons", []))
    if execution_mode not in {"manual_confirm", "notify_only"}:
        stops.append("UNSUPPORTED_EXECUTION_MODE")
    if action not in {"prepare_buy_order", "prepare_sell_order", "notify_only"}:
        stops.append("UNSUPPORTED_RULE_ACTION")
    if action == "notify_only" and execution_mode != "notify_only":
        stops.append("NOTIFY_ONLY_REQUIRES_NOTIFY_EXECUTION_MODE")
    if action in {"prepare_buy_order", "prepare_sell_order"} and execution_mode != "manual_confirm":
        stops.append("ORDER_PREPARATION_REQUIRES_MANUAL_CONFIRM")
    return stops


def _with_quote_snapshot(trigger_result: dict[str, Any], quote: dict[str, Any]) -> dict[str, Any]:
    details = dict(trigger_result.get("details", {}))
    details["quote_timestamp"] = quote.get("timestamp")
    details["quote_age_seconds"] = quote.get("age_seconds")
    details["quote_provider"] = quote.get("provider")
    return {**trigger_result, "details": details}


def _response_reasons(decision_result: dict[str, Any], precheck_stops: list[str]) -> list[str]:
    reasons = list(decision_result.get("reasons", []))
    for reason in precheck_stops:
        if reason not in reasons:
            reasons.append(reason)
    return reasons
