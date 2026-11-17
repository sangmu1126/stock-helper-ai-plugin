"""신용거래 반대매매 가드.

신용(빚투) 고객이 반대매매를 피하려면 '언제까지, 얼마를' 넣어야 하는지 알아야 하지만,
기준(140% 유지·120% 긴급·D+1/D+2·한시 유예)이 복잡해 상담 과정에서도 틀린 안내가 나온 사례가 있다.
이 모듈은 config/margin_rules.json(출처·적용 기간 포함)의 규칙만으로 계산한다.

- assess_account: 담보비율, 상태, 140% 회복에 필요한 입금/상환액, 납부 기한·반대매매 예정일, 한시 유예 판정
- pre_trade_check: 신용 매수 후 담보비율과 '몇 % 하락하면 담보부족/긴급 구간인지'
- build_alert_rule: '담보비율 N% 아래로 내려가면 알려줘' 알림 룰(NOTIFY_ONLY)
- explain_rules: 규칙 설명과 흔한 오해('120%만 넘기면 된다') 교정

투자 권유나 주문을 하지 않는다. 표준 라이브러리만 사용한다.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

RULES_PATH = Path(__file__).resolve().parents[1] / "config" / "margin_rules.json"

CREDIT_WORDS = ("신용", "빚투", "융자", "미수", "레버리지", "margin")
CREDIT_EXCLUDE = ("신용카드", "신용등급", "신용점수")
BUY_WORDS = ("매수", "사줘", "살래", "사고", "살게", "buy")
ALERT_WORDS = ("알려", "알림", "경고", "notify")
ALERT_RE = re.compile(
    r"담보\s*(?:유지\s*)?비율\s*(?:이|가)?\s*(\d{2,3}(?:\.\d+)?)\s*%?\s*(?:보다\s*)?(?:아래|이하|미만|밑|낮|떨어)"
)
BELIEF_RE = re.compile(r"(\d{2,3}(?:\.\d+)?)\s*%\s*(?:만|이상이면|넘(?:기|으)면|맞추면|유지하면|이면|면\s*되)")

STATUS_LABEL = {
    "SAFE": "여유 있음",
    "WATCH": "주의 (140%에 근접)",
    "SHORTFALL": "담보부족 (140% 미만)",
    "EMERGENCY": "긴급 (120% 미만)",
}


class MarginInputError(ValueError):
    pass


def _today() -> date:
    return datetime.now().astimezone().date()


# ── 규칙 ────────────────────────────────────────────────────


def load_margin_rules(path: Path | None = None) -> dict[str, Any]:
    rules = json.loads((path or RULES_PATH).read_text(encoding="utf-8"))
    sources = rules.get("sources", {})
    missing = [
        name for name, item in _rule_items(rules)
        if item.get("source") not in sources
    ]
    if missing:
        raise MarginInputError(f"출처가 없는 규칙: {', '.join(missing)}")
    return rules


def _rule_items(rules: dict[str, Any]):
    for key, item in rules.get("thresholds", {}).items():
        yield f"thresholds.{key}", item
    for key in ("shortfall", "emergency", "valuation", "liquidation_haircut", "margin_rate_by_grade", "formula"):
        yield key, rules.get(key, {})
    for i, item in enumerate(rules.get("temporary_grace", [])):
        yield f"temporary_grace[{i}]", item


def _threshold(rules: dict[str, Any], name: str) -> float:
    return float(rules["thresholds"][name]["value"])


def _source_list(rules: dict[str, Any], ids: list[str]) -> list[dict[str, str]]:
    seen: list[str] = []
    for source_id in ids:
        if source_id not in seen:
            seen.append(source_id)
    return [{"id": s, **rules["sources"][s]} for s in seen]


# ── 의도 감지 ───────────────────────────────────────────────


@dataclass(frozen=True)
class MarginIntent:
    kind: str | None  # "collateral_alert" | "credit_buy" | "rule_question" | None
    threshold_pct: float | None = None
    believed_safe_pct: float | None = None


def detect_margin_intent(intent: str) -> MarginIntent:
    text = intent.strip()
    lowered = text.lower()
    about_collateral = "담보" in text or "반대매매" in text
    belief = BELIEF_RE.search(text) if about_collateral else None
    believed = float(belief.group(1)) if belief else None

    alert = ALERT_RE.search(text)
    if alert and any(word in lowered for word in ALERT_WORDS):
        return MarginIntent("collateral_alert", threshold_pct=float(alert.group(1)), believed_safe_pct=believed)
    credit = any(word in lowered for word in CREDIT_WORDS) and not any(word in text for word in CREDIT_EXCLUDE)
    if credit and any(word in lowered for word in BUY_WORDS):
        return MarginIntent("credit_buy", believed_safe_pct=believed)
    if about_collateral:
        return MarginIntent("rule_question", believed_safe_pct=believed)
    return MarginIntent(None)


# ── 계좌 ────────────────────────────────────────────────────


@dataclass(frozen=True)
class Holding:
    name: str
    quantity: float
    prev_close: float
    grade: str | None = None

    @property
    def value(self) -> float:
        return self.quantity * self.prev_close


@dataclass(frozen=True)
class MarginAccount:
    as_of: date
    credit_loan: float
    cash: float
    holdings: tuple[Holding, ...]
    accrued_interest: float = 0.0
    shortfall_round: int | None = None
    shortfall_date: date | None = None   # 처음 140% 미만이 된 날
    emergency_date: date | None = None   # 120% 미만이 된 날 (이후 일부 입금해도 당일 140% 회복 의무가 남음)
    holidays: frozenset[date] = field(default_factory=frozenset)

    @property
    def stock_value(self) -> float:
        return sum(h.value for h in self.holdings)

    @property
    def collateral(self) -> float:
        return self.stock_value + self.cash

    @property
    def debt(self) -> float:
        return self.credit_loan + self.accrued_interest

    @property
    def ratio_pct(self) -> float:
        return self.collateral / self.debt * 100


def _date(value: Any, name: str) -> date:
    try:
        return value if isinstance(value, date) else date.fromisoformat(str(value))
    except ValueError as exc:
        raise MarginInputError(f"{name}: 날짜 형식(YYYY-MM-DD)이 아닙니다 ({value!r})") from exc


def _number(data: dict[str, Any], key: str, *, minimum: float = 0.0, required: bool = True) -> float:
    if key not in data:
        if required:
            raise MarginInputError(f"{key}가 필요합니다")
        return 0.0
    try:
        value = float(data[key])
    except (TypeError, ValueError) as exc:
        raise MarginInputError(f"{key}: 숫자가 아닙니다 ({data[key]!r})") from exc
    if value < minimum:
        raise MarginInputError(f"{key}: {minimum} 이상이어야 합니다 ({value})")
    return value


def parse_account(data: dict[str, Any]) -> MarginAccount:
    holdings = []
    for i, raw in enumerate(data.get("holdings", [])):
        quantity = _number(raw, "quantity")
        price = _number(raw, "prev_close")
        if price <= 0:
            raise MarginInputError(f"holdings[{i}].prev_close는 0보다 커야 합니다")
        holdings.append(Holding(
            name=str(raw.get("name") or raw.get("symbol") or f"holding{i + 1}"),
            quantity=quantity, prev_close=price,
            grade=str(raw["grade"]).upper() if raw.get("grade") else None,
        ))
    credit_loan = _number(data, "credit_loan")
    if credit_loan <= 0:
        raise MarginInputError("credit_loan(신용융자금)이 0보다 커야 담보비율을 계산할 수 있습니다")
    shortfall_round = data.get("shortfall_round")
    return MarginAccount(
        as_of=_date(data.get("as_of") or _today(), "as_of"),
        credit_loan=credit_loan,
        cash=_number(data, "cash", required=False),
        holdings=tuple(holdings),
        accrued_interest=_number(data, "accrued_interest", required=False),
        shortfall_round=int(shortfall_round) if shortfall_round not in (None, "") else None,
        shortfall_date=_date(data["shortfall_date"], "shortfall_date") if data.get("shortfall_date") else None,
        emergency_date=_date(data["emergency_date"], "emergency_date") if data.get("emergency_date") else None,
        holidays=frozenset(_date(d, "holidays") for d in data.get("holidays", [])),
    )


def load_account(path: Path) -> MarginAccount:
    return parse_account(json.loads(Path(path).read_text(encoding="utf-8")))


# ── 계산 ────────────────────────────────────────────────────


def add_business_days(start: date, days: int, holidays: frozenset[date] = frozenset()) -> date:
    current, added = start, 0
    while added < days:
        current += timedelta(days=1)
        if current.weekday() < 5 and current not in holidays:
            added += 1
    return current


def classify_ratio(ratio_pct: float, rules: dict[str, Any]) -> str:
    if ratio_pct < _threshold(rules, "emergency_pct"):
        return "EMERGENCY"
    if ratio_pct < _threshold(rules, "maintenance_pct"):
        return "SHORTFALL"
    if ratio_pct < _threshold(rules, "watch_pct"):
        return "WATCH"
    return "SAFE"


def price_drop_to(stock_value: float, cash: float, debt: float, threshold_pct: float) -> float | None:
    """보유 주식이 함께 몇 % 떨어지면 담보비율이 threshold에 닿는지. 이미 아래면 0."""
    if stock_value <= 0:
        return None
    drop = 1 - (threshold_pct / 100 * debt - cash) / stock_value
    return round(max(0.0, min(drop, 1.0)) * 100, 1)


def restore_amounts(collateral: float, debt: float, target_pct: float) -> dict[str, float]:
    """target_pct 회복에 필요한 금액. 입금은 담보에 더해지고, 상환은 융자금을 줄인다(이자·수수료 제외)."""
    target = target_pct / 100
    return {
        "deposit_krw": round(max(0.0, target * debt - collateral)),
        "or_repay_krw": round(max(0.0, debt - collateral / target)),
    }


def evaluate_grace(rules: dict[str, Any], ratio_pct: float, shortfall_round: int | None,
                   liquidation_date: date) -> dict[str, Any] | None:
    for grace in rules.get("temporary_grace", []):
        start, end = date.fromisoformat(grace["effective_from"]), date.fromisoformat(grace["effective_to"])
        base = {"id": grace["id"], "period": f"{start}~{end}", "source": grace["source"], "caveat": grace["caveat"]}
        if not start <= liquidation_date <= end:
            continue
        in_band = grace["min_ratio_pct"] <= ratio_pct < grace["max_ratio_pct"]
        if not in_band:
            return {**base, "status": "NOT_ELIGIBLE",
                    "reason": f"담보비율 {ratio_pct:.1f}%는 유예 구간({grace['min_ratio_pct']}~{grace['max_ratio_pct']}% 미만) 밖"}
        if shortfall_round is None:
            return {**base, "status": "NEEDS_ROUND",
                    "reason": f"담보부족 {grace['shortfall_round']}회차라면 1회 유예 가능. 앱에서 담보부족 회차를 확인하세요",
                    "condition": f"반대매매 당일 {grace['check_time']}까지 {grace['min_ratio_pct']}% 이상 유지"}
        if shortfall_round != grace["shortfall_round"]:
            return {**base, "status": "NOT_ELIGIBLE",
                    "reason": f"담보부족 {shortfall_round}회차는 대상 아님 ({grace['shortfall_round']}회차만 유예)"}
        return {**base, "status": "ELIGIBLE",
                "reason": f"담보부족 {shortfall_round}회차 · {ratio_pct:.1f}% → 반대매매 {grace['grace_count']}회 유예 대상",
                "condition": f"반대매매 당일 {grace['check_time']}까지 {grace['min_ratio_pct']}% 이상 유지, 연속 유예 불가"}
    return None


def _misconception(rules: dict[str, Any], believed: float | None) -> str | None:
    maintenance, emergency = _threshold(rules, "maintenance_pct"), _threshold(rules, "emergency_pct")
    if believed is None or believed >= maintenance:
        return None
    role = "긴급 반대매매 기준" if believed == emergency else "유지 기준보다 낮은 값"
    return (f"{believed:g}%는 안전 기준이 아닙니다({role}). 담보비율이 {maintenance:g}% 미만이면 이미 담보부족이며, "
            f"D+1까지 {maintenance:g}%로 채우지 않으면 D+2에 반대매매됩니다. "
            f"{emergency:g}% 미만이면 당일 {maintenance:g}%까지 채워야 하고 아니면 D+1에 반대매매됩니다.")


def assess_account(account: MarginAccount, rules: dict[str, Any], *, believed_safe_pct: float | None = None) -> dict[str, Any]:
    ratio = account.ratio_pct
    status = classify_ratio(ratio, rules)
    maintenance, emergency, watch = (_threshold(rules, k) for k in ("maintenance_pct", "emergency_pct", "watch_pct"))
    sources = ["CREDIT_GUIDE", "ASSUMPTION"]
    explanation = [f"담보비율 {ratio:.1f}% — {STATUS_LABEL[status]}. 평가 기준: {rules['valuation']['price_basis']}."]
    warnings: list[str] = []
    timeline = None
    grace = None

    if status in ("SHORTFALL", "EMERGENCY"):
        # 120% 미만이 된 날이 있으면, 이후 일부 입금으로 120%를 넘겨도 그날 140% 회복 의무가 남는다(긴급 일정).
        emergency_clock = status == "EMERGENCY" or (
            account.emergency_date is not None and account.emergency_date <= account.as_of
        )
        if emergency_clock:
            start = account.emergency_date or account.as_of
            deadline = start
            liquidation = add_business_days(start, rules["emergency"]["liquidation_business_days"], account.holidays)
            explanation.append(f"{deadline}(D) 안에 {maintenance:g}% 이상으로 채우지 않으면 {liquidation}(D+1)에 반대매매됩니다.")
            if status == "SHORTFALL":
                explanation.append(
                    f"{start}에 {emergency:g}% 미만이었으므로 지금 {ratio:.1f}%로 {emergency:g}%를 넘긴 것만으로는 부족합니다. "
                    f"당일 {maintenance:g}%까지 채워야 D+1 반대매매를 피할 수 있습니다(회사 안내 문구 기준 해석)."
                )
        else:
            start = account.shortfall_date or account.as_of
            deadline = add_business_days(start, rules["shortfall"]["deposit_deadline_business_days"], account.holidays)
            liquidation = add_business_days(start, rules["shortfall"]["liquidation_business_days"], account.holidays)
            explanation.append(f"{deadline}(D+1)까지 {maintenance:g}% 이상으로 채우지 않으면 {liquidation}(D+2)에 반대매매됩니다.")
        timeline = {
            "clock": "EMERGENCY" if emergency_clock else "SHORTFALL",
            "shortfall_date": start.isoformat(), "deposit_deadline": deadline.isoformat(),
            "liquidation_date": liquidation.isoformat(),
            "note": "주말과 입력한 holidays만 제외. 실제 영업일·마감 시각은 앱 안내를 따르세요.",
        }
        grace = evaluate_grace(rules, ratio, account.shortfall_round, liquidation)
        if grace:
            sources.append(grace["source"])
            explanation.append(f"한시 유예({grace['period']}): {grace['reason']}.")
            warnings.append(grace["caveat"])
        haircut = rules["liquidation_haircut"]
        warnings.append(haircut["text"] + f" (A·B {haircut['by_grade']['A']:.0%}, C·D·E {haircut['by_grade']['C']:.0%})")
    elif status == "WATCH":
        explanation.append(f"{maintenance:g}%까지 여유가 작습니다. 전일 종가 기준으로 평가되므로 하루 급락에도 담보부족이 될 수 있습니다.")

    restore = restore_amounts(account.collateral, account.debt, maintenance)
    if restore["deposit_krw"] > 0:
        explanation.append(
            f"{maintenance:g}% 회복에 필요한 금액(계산값): 현금 입금 {restore['deposit_krw']:,.0f}원 "
            f"또는 신용융자 상환 {restore['or_repay_krw']:,.0f}원. 이자·수수료와 당일 시세 변동은 제외했습니다."
        )
    correction = _misconception(rules, believed_safe_pct)
    if correction:
        warnings.insert(0, correction)

    return {
        "kind": "account_assessment",
        "rules_version": rules["version"],
        "as_of": account.as_of.isoformat(),
        "inputs": {
            "stock_value_krw": round(account.stock_value), "cash_krw": round(account.cash),
            "credit_loan_krw": round(account.credit_loan), "accrued_interest_krw": round(account.accrued_interest),
            "shortfall_round": account.shortfall_round,
            "emergency_date": account.emergency_date.isoformat() if account.emergency_date else None,
        },
        "collateral_ratio_pct": round(ratio, 1),
        "status": status,
        "status_label": STATUS_LABEL[status],
        "thresholds_pct": {"watch": watch, "maintenance": maintenance, "emergency": emergency},
        "price_drop_to_pct": {
            "maintenance": price_drop_to(account.stock_value, account.cash, account.debt, maintenance),
            "emergency": price_drop_to(account.stock_value, account.cash, account.debt, emergency),
        },
        "to_restore_maintenance": restore,
        "timeline": timeline,
        "grace": grace,
        "warnings": warnings,
        "explanation": explanation,
        "assumptions": [rules["formula"]["text"], "보유 종목이 같은 비율로 움직인다고 가정한 하락률입니다."],
        "sources": _source_list(rules, sources),
    }


def pre_trade_check(rules: dict[str, Any], *, amount: float | None = None, grade: str | None = None,
                    account: MarginAccount | None = None) -> dict[str, Any]:
    """신용 매수 직후의 담보비율과 담보부족·긴급 구간까지의 하락률."""
    table = rules["margin_rate_by_grade"]
    grade_key = (grade or "").upper() or None
    assumed_grade = grade_key is None
    grade_key = grade_key or table["default_grade"]
    rate = table["rates"].get(grade_key)
    maintenance, emergency = _threshold(rules, "maintenance_pct"), _threshold(rules, "emergency_pct")
    base = {
        "kind": "pre_trade",
        "rules_version": rules["version"],
        "grade": grade_key,
        "grade_assumed": assumed_grade,
        "reason": "CREDIT_RISK_ACKNOWLEDGEMENT_REQUIRED",
        "decision_hint": "REQUIRE_CLARIFICATION",
        "sources": _source_list(rules, ["CREDIT_GUIDE", "ASSUMPTION"]),
    }
    if rate is None:
        question = f"{grade_key}군 종목은 신용 매수가 불가합니다. 현금 매수로 바꾸시겠어요?"
        return {**base, "status": "NOT_ALLOWED", "acknowledgement_question": question, "explanation": [question],
                "warnings": [], "assumptions": []}

    warnings: list[str] = []
    if account is not None and amount:
        own = rate * amount
        cash_used = min(own, account.cash)
        if own > account.cash:
            warnings.append(
                f"보증금 {own:,.0f}원 중 예수금 {account.cash:,.0f}원만 현금으로 내고, 나머지 {own - cash_used:,.0f}원은 "
                "대용으로 채워 그만큼 융자금이 늘어난다고 보수적으로 계산했습니다."
            )
        stock, cash = account.stock_value + amount, account.cash - cash_used
        debt = account.debt + amount - cash_used
        scope = "기존 계좌 포함"
    else:
        stock, cash, debt = 1.0, 0.0, 1 - rate  # 금액과 무관한 비율 계산
        scope = "이번 신용 매수분만"
    ratio = (stock + cash) / debt * 100
    drop_m = price_drop_to(stock, cash, debt, maintenance)
    drop_e = price_drop_to(stock, cash, debt, emergency)
    status = classify_ratio(ratio, rules)
    if status in ("SHORTFALL", "EMERGENCY"):
        question = (
            f"이 신용 매수를 하면 담보비율이 약 {ratio:.1f}%로 매수 즉시 {STATUS_LABEL[status]} 구간에 들어갑니다({scope}). "
            f"{maintenance:g}%를 회복하지 못하면 반대매매 대상이 됩니다. 금액을 줄이거나 현금 매수로 바꾸시겠어요?"
        )
    else:
        question = (
            f"신용으로 매수하면 담보비율이 약 {ratio:.1f}%에서 시작합니다({scope}, 보증금률 {rate:.0%}). "
            f"주가가 {drop_m:.1f}% 떨어지면 담보부족({maintenance:g}% 미만, 미납 시 D+2 반대매매), "
            f"{drop_e:.1f}% 떨어지면 긴급 구간({emergency:g}% 미만, 당일 미회복 시 D+1 반대매매)입니다. "
            "이 위험과 추가 입금 계획을 확인하셨나요?"
        )
    explanation = [question]
    if assumed_grade:
        warnings.append(f"종목군을 몰라 {grade_key}군 보증금률 {rate:.0%}로 계산했습니다. D군(50%)·E군(신용 불가)은 결과가 다릅니다.")
    if not table.get("verified", True):
        warnings.append(table["text"])
    return {
        **base,
        "status": status,
        "scope": scope,
        "amount_krw": amount,
        "margin_rate": rate,
        "collateral_ratio_pct": round(ratio, 1),
        "price_drop_to_pct": {"maintenance": drop_m, "emergency": drop_e},
        "acknowledgement_question": question,
        "explanation": explanation,
        "warnings": warnings,
        "assumptions": [
            rules["formula"]["text"],
            (f"보증금(보증금률 {rate:.0%})을 현금으로 내고 나머지를 융자받는다고 가정했습니다. 보증금을 대용(보유 주식)으로 채우면 "
             "융자금이 커져 담보비율이 더 낮게 시작하고 반대매매 구간에 더 빨리 닿습니다."),
        ],
    }


def build_alert_rule(rules: dict[str, Any], threshold_pct: float, *, account: MarginAccount | None = None,
                     believed_safe_pct: float | None = None) -> dict[str, Any]:
    maintenance, emergency, watch = (_threshold(rules, k) for k in ("maintenance_pct", "emergency_pct", "watch_pct"))
    warnings: list[str] = []
    if threshold_pct <= emergency:
        warnings.append(f"{threshold_pct:g}% 기준이면 알림이 올 때 이미 긴급 구간(D+1 반대매매)입니다. {watch:g}% 이상을 권장합니다.")
    elif threshold_pct <= maintenance:
        warnings.append(f"{threshold_pct:g}% 기준이면 알림이 올 때 이미 담보부족(미납 시 D+2 반대매매)입니다. "
                        f"{maintenance:g}%보다 높게(예: {watch:g}%) 설정하세요.")
    correction = _misconception(rules, believed_safe_pct)
    if correction:
        warnings.insert(0, correction)
    rule = {
        "type": "collateral_ratio_below",
        "threshold_pct": threshold_pct,
        "action": "notify_only",
        "execution_mode": "notify_only",
        "cooldown": {"mode": "once_per_day"},
        "evaluation_basis": f"{rules['valuation']['price_basis']} 기준 담보비율",
    }
    result: dict[str, Any] = {
        "kind": "collateral_alert",
        "rules_version": rules["version"],
        "rule": rule,
        "warnings": warnings,
        "sources": _source_list(rules, ["CREDIT_GUIDE"]),
    }
    if account is None:
        result.update(decision="WAIT", reason="ACCOUNT_SNAPSHOT_REQUIRED",
                      explanation=[(f"담보비율이 {threshold_pct:g}% 아래로 내려가면 알리는 룰입니다(주문 없음). "
                                    "계좌 스냅샷(--account)을 연결하면 현재 상태를 평가합니다.")])
        return result
    assessment = assess_account(account, rules)
    triggered = assessment["collateral_ratio_pct"] < threshold_pct
    result.update(
        decision="NOTIFY" if triggered else "WAIT",
        reason="COLLATERAL_RATIO_BELOW_THRESHOLD" if triggered else "COLLATERAL_RATIO_ABOVE_THRESHOLD",
        explanation=[(f"현재 담보비율 {assessment['collateral_ratio_pct']:.1f}% "
                      f"{'<' if triggered else '≥'} 알림 기준 {threshold_pct:g}%."), *assessment["explanation"][1:]],
        assessment=assessment,
    )
    return result


def explain_rules(rules: dict[str, Any], *, believed_safe_pct: float | None = None, as_of: date | None = None) -> dict[str, Any]:
    maintenance = _threshold(rules, "maintenance_pct")
    lines = [
        f"담보유지비율은 {maintenance:g}%입니다. 평가는 {rules['valuation']['price_basis']} 기준입니다.",
        rules["shortfall"]["text"] + ".",
        rules["emergency"]["text"] + ".",
    ]
    sources = ["CREDIT_GUIDE"]
    today = as_of or _today()
    for grace in rules.get("temporary_grace", []):
        if date.fromisoformat(grace["effective_from"]) <= today <= date.fromisoformat(grace["effective_to"]):
            lines.append(f"한시 유예({grace['effective_from']}~{grace['effective_to']}): {grace['text']}.")
            sources.append(grace["source"])
    warnings = []
    correction = _misconception(rules, believed_safe_pct)
    if correction:
        warnings.append(correction)
    return {"kind": "rule_explanation", "rules_version": rules["version"], "explanation": lines,
            "warnings": warnings, "sources": _source_list(rules, sources)}


# ── 출력 ────────────────────────────────────────────────────


def render_margin_markdown(result: dict[str, Any], *, heading: str = "#") -> list[str]:
    titles = {
        "account_assessment": "신용거래 담보 점검",
        "pre_trade": "신용 매수 사전 점검",
        "collateral_alert": "담보비율 알림 룰",
        "rule_explanation": "반대매매 기준 안내",
    }
    lines = [f"{heading} {titles.get(result['kind'], '신용거래 위험 점검')}", ""]
    if "collateral_ratio_pct" in result:
        status = result.get("status_label") or STATUS_LABEL.get(result.get("status", ""), result.get("status", ""))
        lines.append(f"- 담보비율: **{result['collateral_ratio_pct']:.1f}%** ({status})")
    drops = result.get("price_drop_to_pct")
    if drops and drops.get("maintenance") is not None:
        def _room(value: float) -> str:
            return "이미 기준 아래" if value <= 0 else f"{value:.1f}% 하락 시"
        lines.append(f"- 주가 하락 여유: 담보부족(140% 미만) {_room(drops['maintenance'])} · "
                     f"긴급(120% 미만) {_room(drops['emergency'])}")
    if result.get("decision"):
        lines.append(f"- 결정: `{result['decision']}` / `{result.get('reason', '')}`")
    if result.get("rule"):
        rule = result["rule"]
        lines.append(f"- 룰: 담보비율 {rule['threshold_pct']:g}% 미만이면 알림 (`{rule['execution_mode']}`, 하루 1회)")
    if result.get("timeline"):
        t = result["timeline"]
        clock = "긴급(120% 미만) 일정" if t.get("clock") == "EMERGENCY" else "담보부족 일정"
        lines.append(f"- {clock}: 발생 {t['shortfall_date']} → 140% 회복 기한 {t['deposit_deadline']} → "
                     f"미회복 시 반대매매 {t['liquidation_date']}")
    restore = result.get("to_restore_maintenance")
    if restore and restore.get("deposit_krw"):
        lines.append(f"- 140% 회복: 입금 {restore['deposit_krw']:,.0f}원 또는 상환 {restore['or_repay_krw']:,.0f}원")
    if result.get("grace"):
        grace = result["grace"]
        condition = f" (조건: {grace['condition']})" if grace.get("condition") else ""
        lines.append(f"- 한시 유예: `{grace['status']}` — {grace['reason']}{condition}")
    lines.append("")
    for line in result.get("explanation", []):
        lines.append(f"> {line}")
    if result.get("explanation"):
        lines.append("")
    for warning in result.get("warnings", []):
        lines.append(f"- ⚠ {warning}")
    for assumption in result.get("assumptions", []):
        lines.append(f"- 가정: {assumption}")
    lines.append("")
    lines.append("출처: " + " · ".join(
        f"[{s['title']}]({s['url']})" if s.get("url") else s["title"] for s in result.get("sources", [])
    ))
    lines.append(f"(규칙 버전 `{result.get('rules_version')}` — 실제 계좌의 담보비율과 일정은 앱 표시가 우선합니다. 투자 권유가 아닙니다.)")
    lines.append("")
    return lines
