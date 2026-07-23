from __future__ import annotations

from dataclasses import asdict
from typing import Any

from backtesting import backtest_rule
from confirmation import build_confirmation_checklist
from decision_engine import DecisionEngine
from decision_log import create_decision_log
from evaluation import evaluate_trigger
from market_data import get_provider
from models import MarketDataProvider, MarketQuote, RuleDraft
from parser_strategy import parse_intent
from policy_engine import evaluate_policy
from templates import lambda_template, runtime_files


def build_rule(
    intent: str,
    *,
    provider_name: str = "yfinance",
    with_market_data: bool = False,
    backtest: bool = False,
    backtest_period: str = "6mo",
    backtest_interval: str = "1d",
    parser_strategy: str = "auto",
) -> RuleDraft:
    parsed = parse_intent(intent, parser_strategy)
    parts = parsed.to_legacy_dicts()
    asset = parts["asset"]
    action = parts["action"]
    trigger = parts["trigger"]
    order = parts["order"]
    execution_mode = parts["execution_mode"]
    time_window = parts["time_window"]
    cooldown = parts["cooldown"]
    cancel_conditions = parts["cancel_conditions"]
    emotional_flags = parts["emotional_risk_flags"]
    ambiguities = parts["ambiguities"]
    parser_meta = parts["parser"]

    quote: MarketQuote | None = None
    market_data: dict[str, Any] | None = None
    trigger_evaluation: dict[str, Any] | None = None
    backtest_result: dict[str, Any] | None = None
    provider: MarketDataProvider | None = None
    lookback_days = safe_lookback_days(trigger)

    if with_market_data and asset["symbol"] != "UNKNOWN":
        try:
            provider = get_provider(provider_name)
            quote = provider.get_quote(asset["symbol"], lookback_days=lookback_days)
            market_data = asdict(quote)
            trigger_evaluation = evaluate_trigger(trigger, quote)
        except Exception as exc:  # noqa: BLE001 - fail closed for market-data adapters
            market_data = {
                "provider": provider_name,
                "symbol": asset["symbol"],
                "health": {
                    "ok": False,
                    "errors": ["MARKET_DATA_PROVIDER_FAILED"],
                    "detail": str(exc),
                },
            }
            trigger_evaluation = {"status": "STOP", "reason": "MARKET_DATA_PROVIDER_FAILED"}
    elif with_market_data:
        market_data = {
            "provider": provider_name,
            "health": {"ok": False, "errors": ["UNKNOWN_ASSET_SYMBOL"]},
        }
        trigger_evaluation = {"status": "STOP", "reason": "UNKNOWN_ASSET_SYMBOL"}

    if backtest and asset["symbol"] != "UNKNOWN":
        try:
            if provider is None:
                provider = get_provider(provider_name)
            history = provider.get_history(asset["symbol"], backtest_period, backtest_interval)
            backtest_result = backtest_rule(trigger, history)
        except Exception as exc:  # noqa: BLE001 - fail closed for history adapters
            backtest_result = {
                "status": "STOP",
                "reason": "HISTORY_DATA_PROVIDER_FAILED",
                "details": {
                    "provider": provider_name,
                    "symbol": asset["symbol"],
                    "error": str(exc),
                },
            }
    elif backtest:
        backtest_result = {"status": "STOP", "reason": "UNKNOWN_ASSET_SYMBOL"}

    user_questions = build_user_questions(
        action,
        execution_mode,
        order,
        trigger,
        cooldown,
        cancel_conditions,
    ) + [localize_user_question(item["question"]) for item in ambiguities if item.get("question")]
    if emotional_flags:
        mindset_questions = [
            localize_user_question(item["question"])
            for item in ambiguities
            if item.get("field") == "intent" and item.get("question")
        ]
        user_questions = mindset_questions or [
            "활성화 전에 조급함, 손실 복구, FOMO, 몰빵 표현을 빼고 차분한 조건문으로 다시 작성해 주세요."
        ]

    guardrails = build_guardrails(emotional_flags, order, cancel_conditions)
    policy_result = evaluate_policy(
        intent=intent,
        action=action,
        execution_mode=execution_mode,
        order=order,
        trigger=trigger,
        emotional_flags=emotional_flags,
        ambiguities=ambiguities,
    )
    decision_result = DecisionEngine().decide(
        asset=asset,
        trigger=trigger,
        action=action,
        execution_mode=execution_mode,
        cooldown=cooldown,
        policy_result=policy_result,
        trigger_evaluation=trigger_evaluation,
    ).to_dict()
    confirmation_checklist = build_confirmation_checklist(
        decision_result["decision"],
        action=action,
    )
    decision_log = create_decision_log(
        rule_id=decision_result["rule_id"],
        parser=parser_meta,
        policy_result=policy_result,
        decision_result=decision_result,
        market_data=market_data,
        trigger_evaluation=trigger_evaluation,
        guardrails=guardrails,
    ).to_dict()

    return RuleDraft(
        asset=asset,
        trigger=trigger,
        action=action,
        order=order,
        execution_mode=execution_mode,
        time_window=time_window,
        cooldown=cooldown,
        cancel_conditions=cancel_conditions,
        ambiguities=ambiguities,
        parser=parser_meta,
        guardrails=guardrails,
        market_data=market_data,
        trigger_evaluation=trigger_evaluation,
        backtest=backtest_result,
        health_checks=build_health_checks(provider_name),
        emotional_risk_flags=emotional_flags,
        persuasion_process=build_persuasion_process(action, asset),
        serverless_shape=build_serverless_shape(provider_name),
        lambda_handler=lambda_template(),
        runtime_files=runtime_files(),
        policy_result=policy_result,
        decision_result=decision_result,
        decision_log=decision_log,
        confirmation_checklist=confirmation_checklist,
        user_questions=user_questions,
        disclaimer=(
            "이 기능은 매매 룰 초안을 정리해 드리는 도구이며, 투자 조언이나 실주문 시스템이 아닙니다. "
            "현재 시장 데이터는 프로토타입용 yfinance를 사용하므로 지연되거나 제공되지 않을 수 있습니다. "
            "실제 서비스 전에는 승인된 증권사 데이터와 주문 API로 교체해 주세요."
        ),
    )


def build_guardrails(
    emotional_flags: list[dict[str, str]],
    order: dict[str, Any],
    cancel_conditions: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "max_order_amount": "required_before_activation"
        if order.get("mode") == "required_before_activation"
        else order,
        "max_daily_loss_percent": 3,
        "cooldown_minutes_after_trigger": 10,
        "manual_confirmation_required": True,
        "block_if_emotional_flags_present": bool(emotional_flags),
        "cancel_conditions": cancel_conditions,
        "live_order_submission": "disabled_in_prototype",
    }


def build_health_checks(provider_name: str) -> list[dict[str, Any]]:
    return [
        {
            "name": "market_data_provider",
            "provider": provider_name,
            "replaceable_with": "kakaopay-securities",
            "stop_if": "현재가, 전일 종가, 시각, 상태 정보를 확인할 수 없으면 진행하지 않습니다.",
        },
        {
            "name": "broker_api_health",
            "stop_if": "증권사 연결 상태가 불안정하거나 응답이 너무 늦으면 잠시 멈춥니다.",
        },
        {
            "name": "exchange_status",
            "stop_if": "정규장이 아니거나 거래가 중단된 상태이면 룰을 실행하지 않습니다.",
        },
        {
            "name": "quote_freshness",
            "stop_if": "시세가 15초 이상 오래된 경우에는 최신 정보가 들어올 때까지 기다립니다.",
        },
        {
            "name": "duplicate_order",
            "stop_if": "같은 종목과 조건의 룰이 쿨다운 시간 안에 이미 실행된 경우 중복으로 진행하지 않습니다.",
        },
        {
            "name": "volatility_spike",
            "stop_if": "짧은 시간 안에 변동성이 과도하게 커지면 초보 투자자 보호를 위해 멈춥니다.",
        },
    ]


def build_persuasion_process(action: str, asset: dict[str, str]) -> list[dict[str, str]]:
    return [
        {
            "step": "intent",
            "message": f"{asset['symbol']}에 대해 감정이 아니라 조건에 따라 움직이는 룰 초안을 만들고 있습니다.",
        },
        {
            "step": "emotion_check",
            "message": "조급함, 손실 복구, 몰빵처럼 감정적인 표현이 보이면 바로 진행하지 않고 다시 확인합니다.",
        },
        {
            "step": "market_context",
            "message": "시장 데이터는 조건 충족 여부를 확인하는 데만 사용하며, 수익을 예측하거나 보장하지 않습니다.",
        },
        {
            "step": "counter_case",
            "message": "가격이 움직였다는 이유만으로 매매가 정답이 되지는 않습니다. 위험 요인이 바뀌었는지 함께 확인해 주세요.",
        },
        {
            "step": "safe_next_action",
            "message": "모든 안전 점검을 통과해도 자동 주문은 하지 않고, 사용자의 수동 확인 단계까지만 안내합니다.",
        },
    ]


def build_serverless_shape(provider_name: str) -> dict[str, str]:
    return {
        "runtime": "AWS Lambda compatible Python",
        "runtime_file": "./runtime/lambda_handler.py",
        "runtime_support_files": "./runtime/evaluation.py, ./runtime/event_context.py, ./runtime/policy_engine.py, ./runtime/decision_engine.py, ./runtime/store_factory.py, ./runtime/state_store.py, ./runtime/decision_log.py, ./runtime/decision_log_store.py, ./runtime/confirmation.py, ./runtime/providers.py, ./runtime/policy_rules.json",
        "sample_event": "./runtime/sample_event.json",
        "trigger": "EventBridge schedule or broker/quote webhook",
        "market_data_provider": provider_name,
        "provider_contract": "MarketDataProvider.get_quote(symbol, lookback_days=20) -> MarketQuote",
        "broker_provider_contract": "BrokerProvider.get_health() -> BrokerHealthSnapshot",
        "account_provider_contract": "AccountProvider.get_snapshot() -> AccountSnapshot",
        "history_contract": "MarketDataProvider.get_history(symbol, period, interval) -> historical bars",
        "state": "DynamoDB table for cooldowns and fired rule ids",
        "decision_log_store": "DynamoDB table or append-only audit sink for immutable decision logs",
        "policy_rules": "./runtime/policy_rules.json",
        "secrets": "Broker credentials stored outside code, for example in Secrets Manager",
        "output": "STOP, WAIT, NOTIFY_ONLY, or MANUAL_CONFIRM decision object",
        "backtest": "Historical trigger simulation using provider.get_history()",
    }


def safe_lookback_days(trigger: dict[str, Any]) -> int:
    try:
        value = int(trigger.get("lookback_days") or 20)
    except (TypeError, ValueError):
        return 20
    return value if value > 0 else 20


def build_user_questions(
    action: str,
    execution_mode: str,
    order: dict[str, Any],
    trigger: dict[str, Any],
    cooldown: dict[str, Any],
    cancel_conditions: list[dict[str, Any]],
) -> list[str]:
    questions: list[str] = []
    # Ambiguities from the parser are appended in build_rule after this helper.
    if (
        order.get("mode") == "required_before_activation"
        and action in {"prepare_buy_order", "prepare_sell_order"}
        and execution_mode != "notify_only"
    ):
        questions.append("이 룰이 한 번에 준비할 수 있는 최대 주문 금액 또는 수량을 알려 주세요.")
    if trigger.get("type") in {"needs_clarification", "price_move_percent"}:
        questions.append(
            "조건을 전일 종가, 평균 매수가, 현재가, 이동평균, 사용자 지정가 중 무엇과 비교할지 알려 주세요."
        )
    if not cooldown:
        questions.append("이 룰이 한 번 동작한 뒤 다시 동작하기까지 얼마나 기다리면 좋을지 알려 주세요.")
    if len(cancel_conditions) <= 1:
        questions.append("가격 조건이 맞더라도 이 룰을 취소해야 하는 상황이 있다면 알려 주세요.")
    if not questions:
        questions.append("수동 확인 전에 실시간 시장 데이터, 백테스트, 또는 둘 다로 이 룰을 점검해 볼까요?")
    return questions


def localize_user_question(question: str) -> str:
    translations = {
        "What maximum amount or share quantity should this rule prepare?": "이 룰이 한 번에 준비할 수 있는 최대 주문 금액 또는 수량을 알려 주세요.",
        "Please rewrite the rule without urgency, loss-recovery, FOMO, or all-in wording before activation.": "활성화 전에 조급함, 손실 복구, FOMO, 몰빵 표현을 빼고 차분한 조건문으로 다시 작성해 주세요.",
    }
    return translations.get(question, question)
