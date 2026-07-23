from __future__ import annotations

from models import RuleDraft


WARNING_MESSAGES = {
    "INSUFFICIENT_HISTORY_FOR_CONFIDENCE": "There are too few historical bars to trust this rule's behavior.",
    "NO_TRIGGER_EVENTS_FOUND": "This rule did not trigger in the tested period, so it may be too narrow or untested.",
    "TRIGGER_TOO_FREQUENT_FOR_BEGINNER_GUARDRAIL": "This rule would have fired often, which can create overtrading risk for a beginner.",
    "HIGH_VOLATILITY_PERIOD_INCLUDED": "The tested period includes unusually large price moves, so review whether the rule is reacting to stress rather than opportunity.",
}


WARNING_MESSAGES_KO = {
    "INSUFFICIENT_HISTORY_FOR_CONFIDENCE": "검증 가능한 과거 봉 수가 적어 룰의 행동을 신뢰하기 어렵습니다.",
    "NO_TRIGGER_EVENTS_FOUND": "검증 기간 동안 룰이 한 번도 발동하지 않아 조건이 지나치게 좁거나 검증되지 않았을 수 있습니다.",
    "TRIGGER_TOO_FREQUENT_FOR_BEGINNER_GUARDRAIL": "룰이 너무 자주 발동해 초보 투자자에게 과잉매매 위험을 만들 수 있습니다.",
    "HIGH_VOLATILITY_PERIOD_INCLUDED": "검증 기간에 큰 가격 변동이 포함되어 있어, 기회가 아니라 스트레스 상황에 반응하는 룰인지 확인해야 합니다.",
}


def render_markdown_report(draft: RuleDraft, *, locale: str = "ko") -> str:
    if locale == "ko":
        return render_korean_markdown_report(draft)
    parser_warnings = draft.parser.get("warnings") or []
    parser_notes = draft.parser.get("notes") or []
    lines: list[str] = [
        "# Safe Trade Rule Report",
        "",
        "This report explains a mechanical rule draft. It is not investment advice and does not submit an order.",
        "",
        "## 1. Extracted Rule",
        "",
        f"- Parser: `{draft.parser.get('source')}` (fallback: `{draft.parser.get('fallback_used')}`)",
        f"- Asset: `{draft.asset.get('name')}` (`{draft.asset.get('symbol')}`)",
        f"- Trigger: `{_trigger_text(draft.trigger)}`",
        f"- Action: `{draft.action}`",
        f"- Order size: `{_order_text(draft.order)}`",
        f"- Execution mode: `{draft.execution_mode}`",
        f"- Time window: `{_time_window_text(draft.time_window)}`",
        f"- Cooldown: `{_cooldown_text(draft.cooldown)}`",
        f"- Cancel conditions: `{_cancel_conditions_text(draft.cancel_conditions)}`",
    ]
    if parser_warnings:
        lines.append(f"- Parser warnings: `{', '.join(str(item) for item in parser_warnings)}`")
    if parser_notes:
        lines.append(f"- Parser notes: `{'; '.join(str(item) for item in parser_notes)}`")
    lines.extend(
        [
            "",
            "## 2. Safety Status",
            "",
            f"- Emotion check: {_emotion_status(draft)}",
            f"- Market data health: {_market_health_status(draft)}",
            f"- Trigger evaluation: {_trigger_status(draft)}",
            f"- Backtest safety: {_backtest_status(draft)}",
            f"- Policy decision: `{draft.policy_result.get('decision')}` / `{', '.join(draft.policy_result.get('reasons', []))}`",
            f"- Final decision: `{draft.decision_result.get('decision')}` / `{', '.join(draft.decision_result.get('reasons', []))}`",
            "",
            "## 3. Interpretation",
            "",
        ]
    )
    lines.extend(_interpretation_lines(draft))
    lines.extend(["", "## 4. Backtest Detail", ""])
    lines.extend(_backtest_lines(draft))
    lines.extend(["", "## 5. Next Questions", ""])
    if draft.ambiguities:
        lines.append("- Parser ambiguities:")
        lines.extend(f"  - {item.get('question')}" for item in draft.ambiguities)
    lines.extend(f"- {question}" for question in draft.user_questions)
    lines.extend(
        [
            "",
            "## 6. Guardrail Reminder",
            "",
            "- Do not treat this as a buy/sell recommendation.",
            "- Do not submit a live order from this prototype.",
            "- Continue only after manual confirmation and all missing limits are filled.",
        ]
    )
    return "\n".join(lines) + "\n"


def render_korean_markdown_report(draft: RuleDraft) -> str:
    parser_warnings = draft.parser.get("warnings") or []
    parser_notes = draft.parser.get("notes") or []
    lines: list[str] = [
        "# 안전 매매 룰 리포트",
        "",
        "이 리포트는 자연어 매매 의도를 기계적인 룰 초안으로 설명합니다. 투자 조언이 아니며 주문을 제출하지 않습니다.",
        "",
        "## 1. 추출된 룰",
        "",
        f"- 파서: `{draft.parser.get('source')}` (fallback: `{draft.parser.get('fallback_used')}`)",
        f"- 종목: `{draft.asset.get('name')}` (`{draft.asset.get('symbol')}`)",
        f"- 조건: `{_trigger_text_ko(draft.trigger)}`",
        f"- 행동: `{_action_text_ko(draft.action)}`",
        f"- 주문 한도: `{_order_text_ko(draft.order)}`",
        f"- 실행 방식: `{_execution_text_ko(draft.execution_mode)}`",
        f"- 시간 조건: `{_time_window_text_ko(draft.time_window)}`",
        f"- 쿨다운: `{_cooldown_text_ko(draft.cooldown)}`",
        f"- 취소 조건: `{_cancel_conditions_text_ko(draft.cancel_conditions)}`",
    ]
    if parser_warnings:
        lines.append(f"- 파서 경고: `{', '.join(str(item) for item in parser_warnings)}`")
    if parser_notes:
        lines.append(f"- 파서 메모: `{'; '.join(str(item) for item in parser_notes)}`")
    lines.extend(
        [
            "",
            "## 2. 안전 상태",
            "",
            f"- 감정 점검: {_emotion_status_ko(draft)}",
            f"- 시장 데이터 헬스체크: {_market_health_status_ko(draft)}",
            f"- 현재 조건 평가: {_trigger_status_ko(draft)}",
            f"- 백테스트 안전성: {_backtest_status_ko(draft)}",
            f"- 정책 판단: `{draft.policy_result.get('decision')}` / `{', '.join(draft.policy_result.get('reasons', []))}`",
            f"- 최종 결정: `{draft.decision_result.get('decision')}` / `{', '.join(draft.decision_result.get('reasons', []))}`",
            "",
            "## 3. 해석",
            "",
        ]
    )
    lines.extend(_interpretation_lines_ko(draft))
    lines.extend(["", "## 4. 백테스트 상세", ""])
    lines.extend(_backtest_lines_ko(draft))
    lines.extend(["", "## 5. 확인 체크리스트", ""])
    lines.extend(_confirmation_lines_ko(draft))
    lines.extend(["", "## 6. 다음 확인 질문", ""])
    if draft.ambiguities:
        lines.append("- 파서가 확인해야 한다고 판단한 항목:")
        ambiguity_questions = [_question_text_ko(item.get("question")) for item in draft.ambiguities]
        lines.extend(f"  - {question}" for question in _unique(ambiguity_questions))
    user_questions = [
        _question_text_ko(question)
        for question in draft.user_questions
        if _question_text_ko(question) not in {_question_text_ko(item.get("question")) for item in draft.ambiguities}
    ]
    lines.extend(f"- {question}" for question in _unique(user_questions))
    lines.extend(
        [
            "",
            "## 7. 안전 고지",
            "",
            "- 이 결과를 매수/매도 추천으로 해석하지 마세요.",
            "- 이 프로토타입은 실주문을 제출하지 않습니다.",
            "- 모든 누락 한도와 중단 조건을 채운 뒤에도 다음 단계는 수동 확인입니다.",
        ]
    )
    return "\n".join(lines) + "\n"


def _trigger_text(trigger: dict[str, object]) -> str:
    trigger_type = trigger.get("type")
    if trigger_type in {"price_drop_percent", "price_rise_percent"}:
        direction = "drops" if trigger_type == "price_drop_percent" else "rises"
        return f"price {direction} {trigger.get('percent')}% from {trigger.get('reference') or trigger.get('from')}"
    if trigger_type == "recent_high_drop_percent":
        return f"price drops {trigger.get('percent')}% from recent {trigger.get('lookback_days')}-day high"
    if trigger_type == "moving_average_breakdown":
        return f"price breaks below {trigger.get('lookback_days')}-day moving average"
    if trigger_type == "volatility_move_percent":
        return f"price moves {trigger.get('percent')}% or more"
    if trigger_type in {"price_cross_above", "price_cross_below"}:
        direction = "above" if trigger_type == "price_cross_above" else "below"
        return f"price crosses {direction} {trigger.get('price')} {trigger.get('currency')}"
    if trigger_type == "needs_clarification":
        return f"needs clarification: {trigger.get('reason')}"
    return str(trigger)


def _order_text(order: dict[str, object]) -> str:
    mode = order.get("mode")
    if mode == "amount":
        return f"{order.get('value')} {order.get('currency')}"
    if mode == "shares":
        return f"{order.get('value')} shares"
    if mode == "position_fraction":
        return f"{order.get('value')} of current position"
    if mode == "portfolio_or_position_percent":
        return f"{order.get('value')} percent of portfolio or position"
    return "required before activation"


def _time_window_text(time_window: dict[str, object]) -> str:
    parts = [f"session={time_window.get('market_session', 'regular')}"]
    if time_window.get("exclude_open_minutes"):
        parts.append(f"exclude first {time_window['exclude_open_minutes']} minutes")
    if time_window.get("exclude_morning"):
        parts.append("exclude morning")
    if time_window.get("only_before_close_minutes"):
        parts.append(f"only within {time_window['only_before_close_minutes']} minutes before close")
    if time_window.get("expires"):
        parts.append(f"expires={time_window['expires']}")
    if time_window.get("requires_consecutive_days"):
        parts.append(f"requires {time_window['requires_consecutive_days']} consecutive days")
    return ", ".join(parts)


def _cooldown_text(cooldown: dict[str, object]) -> str:
    if cooldown.get("min_days_between_triggers"):
        return f"{cooldown['min_days_between_triggers']} day(s) between triggers"
    if cooldown.get("min_minutes_between_triggers"):
        return f"{cooldown['min_minutes_between_triggers']} minute(s) between triggers"
    return "not configured"


def _cancel_conditions_text(conditions: list[dict[str, object]]) -> str:
    if not conditions:
        return "none"
    parts = []
    for condition in conditions:
        if condition.get("type") == "daily_drop_exceeds_percent":
            parts.append(f"daily drop exceeds {condition.get('percent')}%")
        else:
            parts.append(str(condition.get("type")))
    return ", ".join(parts)


def _emotion_status(draft: RuleDraft) -> str:
    if not draft.emotional_risk_flags:
        return "No emotional-risk phrase detected."
    parts = [
        f"`{flag['flag']}` from `{flag['evidence']}`"
        for flag in draft.emotional_risk_flags
    ]
    return "STOP before activation. Detected " + ", ".join(parts) + "."


def _market_health_status(draft: RuleDraft) -> str:
    if draft.market_data is None:
        return "Not checked in this run."
    health = draft.market_data.get("health", {})
    if health.get("ok"):
        provider = draft.market_data.get("provider")
        state = draft.market_data.get("market_state")
        age = draft.market_data.get("age_seconds")
        demo = " Demo fixture, not live market data." if health.get("demo") else ""
        return f"Provider `{provider}` returned data. Market state `{state}`, quote age `{age}` seconds.{demo}"
    return "STOP. Provider did not return safe data: " + ", ".join(health.get("errors", []))


def _trigger_status(draft: RuleDraft) -> str:
    if draft.trigger_evaluation is None:
        return "Not evaluated in this run."
    status = draft.trigger_evaluation.get("status")
    reason = draft.trigger_evaluation.get("reason")
    if status == "MATCHED":
        return "Eligible for manual confirmation only. Automatic order submission remains disabled."
    if status == "WAIT":
        return f"WAIT. {reason}"
    return f"STOP. {reason}"


def _backtest_status(draft: RuleDraft) -> str:
    if draft.backtest is None:
        return "Not simulated in this run."
    if draft.backtest.get("status") != "SIMULATED":
        return f"STOP. {draft.backtest.get('reason')}"
    warnings = draft.backtest.get("safety_review", {}).get("warnings", [])
    if warnings:
        return "Review required: " + ", ".join(warnings)
    return "No configured backtest warning was triggered."


def _interpretation_lines(draft: RuleDraft) -> list[str]:
    if draft.emotional_risk_flags:
        return [
            "- Before any market check, this wording suggests emotional trading risk.",
            "- Rewrite the rule with a fixed amount, cooldown, and cancellation condition before activation.",
        ]
    if draft.trigger_evaluation and draft.trigger_evaluation.get("status") == "STOP":
        return [
            f"- This rule should not proceed now because `{draft.trigger_evaluation.get('reason')}`.",
            "- The appropriate next step is to report the stop reason and leave the order unsubmitted.",
        ]
    if draft.trigger_evaluation and draft.trigger_evaluation.get("status") == "MATCHED":
        return [
            "- The mechanical condition appears to be met.",
            "- This means manual confirmation may be shown; it does not mean the trade is recommended.",
        ]
    return [
        "- The rule is defined, but the evidence does not justify even a manual confirmation step yet.",
        "- Improve the rule by adding amount limits, reference price, cooldown, and cancellation criteria.",
    ]


def _backtest_lines(draft: RuleDraft) -> list[str]:
    if draft.backtest is None:
        return ["- Backtest was not requested."]
    if draft.backtest.get("status") != "SIMULATED":
        return [f"- Backtest stopped: `{draft.backtest.get('reason')}`."]

    history = draft.backtest.get("history", {})
    results = draft.backtest.get("results", {})
    lines = [
        f"- Provider: `{history.get('provider')}`",
        f"- Symbol: `{history.get('symbol')}`",
        f"- Period / interval: `{history.get('period')}` / `{history.get('interval')}`",
        f"- Evaluable bars: `{history.get('evaluable_bar_count')}`",
        f"- Trigger count: `{results.get('trigger_count')}`",
        f"- Trigger rate: `{results.get('trigger_rate')}`",
        f"- Min / max daily move: `{results.get('min_daily_move_percent')}` / `{results.get('max_daily_move_percent')}`",
    ]
    health = draft.backtest.get("history_health") or draft.backtest.get("health") or {}
    if history.get("provider") == "demo-fixture":
        lines.append("- Data mode: `DEMO FIXTURE` - this is synthetic data for warning demonstration, not live market data.")
    warnings = draft.backtest.get("safety_review", {}).get("warnings", [])
    if warnings:
        lines.append("- Warning interpretation:")
        lines.extend(f"  - `{warning}`: {WARNING_MESSAGES.get(warning, warning)}" for warning in warnings)
    events = results.get("sample_events", [])
    if events:
        lines.append("- Sample trigger events:")
        for event in events[:5]:
            metric = event.get("trigger_metric")
            metric_text = "" if metric is None else f", trigger metric `{metric}%`"
            lines.append(
                f"  - {event.get('date')}: close `{event.get('close')}`, move `{event.get('move_percent')}%`{metric_text}"
            )
    return lines


def _trigger_text_ko(trigger: dict[str, object]) -> str:
    trigger_type = trigger.get("type")
    if trigger_type == "price_drop_percent":
        return f"{trigger.get('reference') or trigger.get('from')} 대비 {trigger.get('percent')}% 하락"
    if trigger_type == "price_rise_percent":
        return f"{trigger.get('reference') or trigger.get('from')} 대비 {trigger.get('percent')}% 상승"
    if trigger_type == "recent_high_drop_percent":
        return f"최근 {trigger.get('lookback_days')}일 고점 대비 {trigger.get('percent')}% 하락"
    if trigger_type == "moving_average_breakdown":
        return f"{trigger.get('lookback_days')}일 이동평균 하회"
    if trigger_type == "volatility_move_percent":
        return f"가격 변동폭 {trigger.get('percent')}% 이상"
    if trigger_type == "price_cross_above":
        return f"{trigger.get('price')} {trigger.get('currency')} 이상 돌파"
    if trigger_type == "price_cross_below":
        return f"{trigger.get('price')} {trigger.get('currency')} 이하 하회"
    if trigger_type == "needs_clarification":
        return f"추가 확인 필요: {trigger.get('reason')}"
    return str(trigger)


def _action_text_ko(action: str) -> str:
    return {
        "prepare_buy_order": "매수 후보 준비",
        "prepare_sell_order": "매도 후보 준비",
        "notify_only": "알림만 전송",
        "block_order": "주문 차단",
        "clarify_action": "추가 확인 필요",
    }.get(action, action)


def _execution_text_ko(execution_mode: str) -> str:
    return {
        "manual_confirm": "수동 확인",
        "notify_only": "알림 전용",
    }.get(execution_mode, execution_mode)


def _order_text_ko(order: dict[str, object]) -> str:
    mode = order.get("mode")
    if mode == "amount":
        return f"{order.get('value')} {order.get('currency')}"
    if mode == "shares":
        return f"{order.get('value')}주"
    if mode == "position_fraction":
        return f"보유 수량의 {order.get('value')}"
    if mode == "portfolio_or_position_percent":
        return f"포트폴리오 또는 보유 수량의 {order.get('value')}%"
    return "활성화 전 입력 필요"


def _time_window_text_ko(time_window: dict[str, object]) -> str:
    parts = [f"장 구분={time_window.get('market_session', 'regular')}"]
    if time_window.get("exclude_open_minutes"):
        parts.append(f"장 시작 후 {time_window['exclude_open_minutes']}분 제외")
    if time_window.get("exclude_morning"):
        parts.append("오전 제외")
    if time_window.get("only_before_close_minutes"):
        parts.append(f"장 마감 {time_window['only_before_close_minutes']}분 전만")
    if time_window.get("expires"):
        parts.append(f"만료={time_window['expires']}")
    if time_window.get("requires_consecutive_days"):
        parts.append(f"{time_window['requires_consecutive_days']}일 연속 필요")
    return ", ".join(parts)


def _cooldown_text_ko(cooldown: dict[str, object]) -> str:
    if cooldown.get("min_days_between_triggers"):
        return f"{cooldown['min_days_between_triggers']}일 간격"
    if cooldown.get("min_minutes_between_triggers"):
        return f"{cooldown['min_minutes_between_triggers']}분 간격"
    return "설정 없음"


def _cancel_conditions_text_ko(conditions: list[dict[str, object]]) -> str:
    if not conditions:
        return "없음"
    labels = {
        "quote_stale": "시세 지연",
        "negative_news_requires_manual_review": "악재 뉴스 수동 검토",
        "volume_spike_requires_manual_review": "거래량 급증 수동 검토",
        "provider_or_broker_unstable": "데이터/브로커 불안정",
        "daily_drop_exceeds_percent": "일일 하락폭 초과",
    }
    parts = []
    for condition in conditions:
        label = labels.get(str(condition.get("type")), str(condition.get("type")))
        if condition.get("type") == "daily_drop_exceeds_percent":
            label = f"{label} {condition.get('percent')}%"
        parts.append(label)
    return ", ".join(parts)


def _emotion_status_ko(draft: RuleDraft) -> str:
    if not draft.emotional_risk_flags:
        return "감정적 표현이 감지되지 않았습니다."
    parts = [f"`{flag['flag']}` (`{flag['evidence']}`)" for flag in draft.emotional_risk_flags]
    return "활성화 전 중단. 감지된 표현: " + ", ".join(parts)


def _market_health_status_ko(draft: RuleDraft) -> str:
    if draft.market_data is None:
        return "이번 실행에서는 확인하지 않았습니다."
    health = draft.market_data.get("health", {})
    if health.get("ok"):
        provider = draft.market_data.get("provider")
        state = draft.market_data.get("market_state")
        age = draft.market_data.get("age_seconds")
        demo = " 데모 fixture이며 실제 시장 데이터가 아닙니다." if health.get("demo") else ""
        return f"`{provider}`가 데이터를 반환했습니다. 장 상태 `{state}`, 시세 나이 `{age}`초.{demo}"
    return "중단. 데이터 provider가 안전한 데이터를 반환하지 못했습니다: " + ", ".join(health.get("errors", []))


def _trigger_status_ko(draft: RuleDraft) -> str:
    if draft.trigger_evaluation is None:
        return "이번 실행에서는 평가하지 않았습니다."
    status = draft.trigger_evaluation.get("status")
    reason = draft.trigger_evaluation.get("reason")
    if status == "MATCHED":
        return "조건은 충족됐지만 다음 단계는 자동 주문이 아니라 수동 확인 또는 알림입니다."
    if status == "WAIT":
        return f"대기. {reason}"
    return f"중단. {reason}"


def _backtest_status_ko(draft: RuleDraft) -> str:
    if draft.backtest is None:
        return "이번 실행에서는 시뮬레이션하지 않았습니다."
    if draft.backtest.get("status") != "SIMULATED":
        return f"중단. {draft.backtest.get('reason')}"
    warnings = draft.backtest.get("safety_review", {}).get("warnings", [])
    if warnings:
        return "검토 필요: " + ", ".join(warnings)
    return "설정된 백테스트 경고는 발생하지 않았습니다."


def _interpretation_lines_ko(draft: RuleDraft) -> list[str]:
    if draft.emotional_risk_flags:
        return [
            "- 시장 데이터 확인보다 먼저, 문장에 감정적 매매 위험이 있습니다.",
            "- 주문 금액보다 먼저 조급함, 손실 복구, 몰빵 표현을 제거한 규칙으로 다시 작성해야 합니다.",
        ]
    if draft.trigger_evaluation and draft.trigger_evaluation.get("status") == "STOP":
        return [
            f"- 지금 이 룰은 `{draft.trigger_evaluation.get('reason')}` 때문에 진행하면 안 됩니다.",
            "- 적절한 다음 단계는 중단 사유를 사용자에게 설명하고 주문을 만들지 않는 것입니다.",
        ]
    if draft.trigger_evaluation and draft.trigger_evaluation.get("status") == "MATCHED":
        return [
            "- 기계적인 조건은 충족된 것으로 보입니다.",
            "- 이는 투자 추천이 아니라 수동 확인 또는 알림을 보여줄 수 있다는 뜻입니다.",
        ]
    return [
        "- 룰은 정의됐지만, 현재 정보만으로는 수동 확인 단계로 넘어갈 근거가 충분하지 않습니다.",
        "- 금액 한도, 기준가, 쿨다운, 취소 조건을 더 명확히 하면 룰이 안전해집니다.",
    ]


def _backtest_lines_ko(draft: RuleDraft) -> list[str]:
    if draft.backtest is None:
        return ["- 백테스트를 요청하지 않았습니다."]
    if draft.backtest.get("status") != "SIMULATED":
        return [f"- 백테스트 중단: `{draft.backtest.get('reason')}`."]
    history = draft.backtest.get("history", {})
    results = draft.backtest.get("results", {})
    lines = [
        f"- Provider: `{history.get('provider')}`",
        f"- 종목: `{history.get('symbol')}`",
        f"- 기간 / 간격: `{history.get('period')}` / `{history.get('interval')}`",
        f"- 평가 가능 봉 수: `{history.get('evaluable_bar_count')}`",
        f"- 발동 횟수: `{results.get('trigger_count')}`",
        f"- 발동 비율: `{results.get('trigger_rate')}`",
        f"- 일일 최소 / 최대 변동률: `{results.get('min_daily_move_percent')}` / `{results.get('max_daily_move_percent')}`",
    ]
    if history.get("provider") == "demo-fixture":
        lines.append("- 데이터 모드: `DEMO FIXTURE` - 경고 동작 시연용 합성 데이터이며 실제 시장 데이터가 아닙니다.")
    warnings = draft.backtest.get("safety_review", {}).get("warnings", [])
    if warnings:
        lines.append("- 경고 해석:")
        lines.extend(f"  - `{warning}`: {WARNING_MESSAGES_KO.get(warning, warning)}" for warning in warnings)
    events = results.get("sample_events", [])
    if events:
        lines.append("- 샘플 발동 이벤트:")
        for event in events[:5]:
            metric = event.get("trigger_metric")
            metric_text = "" if metric is None else f", 트리거 지표 `{metric}%`"
            lines.append(
                f"  - {event.get('date')}: 종가 `{event.get('close')}`, 일일 변동 `{event.get('move_percent')}%`{metric_text}"
            )
    return lines


def _confirmation_lines_ko(draft: RuleDraft) -> list[str]:
    items = draft.confirmation_checklist.get("items", [])
    if not items:
        return ["- 현재 결정에는 사용자 확인 체크리스트가 필요하지 않습니다."]
    lines = [
        f"- 적용 결정: `{draft.confirmation_checklist.get('required_for_decision')}`",
    ]
    for item in items:
        required = "필수" if item.get("required") else "선택"
        lines.append(f"- [{required}] {item.get('label')}")
    return lines


def _question_text_ko(question: object) -> str:
    text = str(question)
    translations = {
        "What maximum amount or share quantity should this rule prepare?": "이 룰이 한 번에 준비할 수 있는 최대 금액 또는 주식 수는 얼마인가요?",
        "What is the maximum amount this rule may prepare for a single order?": "이 룰이 단일 주문 후보로 준비할 수 있는 최대 금액은 얼마인가요?",
        "Should the trigger compare against previous close, average purchase price, current price, a moving average, or a user-defined price?": "조건은 전일 종가, 평균 매수가, 현재가, 이동평균, 사용자 지정가 중 무엇과 비교해야 하나요?",
        "What condition would make you cancel the rule even if the price trigger is met?": "가격 조건이 충족되어도 이 룰을 취소해야 하는 조건은 무엇인가요?",
        "Do you want to evaluate this rule with live market data, a backtest, or both before manual confirmation?": "수동 확인 전에 실시간 시장 데이터, 백테스트, 또는 둘 다로 이 룰을 평가할까요?",
        "Please rewrite the rule without urgency, loss-recovery, FOMO, or all-in wording before activation.": "활성화 전에 조급함, 손실 복구, FOMO, 몰빵 표현을 제거해 룰을 다시 작성해 주세요.",
    }
    return translations.get(text, text)


def _unique(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result
