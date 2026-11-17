from __future__ import annotations

import re

from asset_catalog import find_asset

EMOTIONAL_PATTERNS = {
    "revenge_or_recovery": ["복구", "만회", "손실 메꾸", "본전"],
    "fomo": ["놓치", "급등", "지금 안 사면", "불타기"],
    "all_in": ["몰빵", "전부", "있는 돈 다", "풀매수"],
    "urgency": ["바로", "즉시", "무조건", "당장"],
}


def detect_asset(intent: str) -> dict[str, str]:
    return find_asset(intent) or {"symbol": "UNKNOWN", "name": "Unknown asset"}


def detect_percent(intent: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*%", intent)
    return float(match.group(1)) if match else None


def detect_action(intent: str) -> str:
    if any(word in intent for word in ["하지 말", "하지마", "매수하지 말", "매도하지 말"]):
        return "block_order"
    if any(word in intent for word in ["알려", "알림", "후보", "확인해"]):
        if any(word in intent for word in ["팔", "매도", "정리", "익절", "손절"]):
            return "prepare_sell_order"
        if any(word in intent for word in ["사", "매수", "담아", "진입"]):
            return "prepare_buy_order"
        return "notify_only"
    if any(word in intent for word in ["팔", "매도", "정리", "익절", "손절"]):
        return "prepare_sell_order"
    if any(word in intent for word in ["사", "매수", "담아", "진입"]):
        return "prepare_buy_order"
    if any(word in intent for word in ["멈춰", "중단"]):
        return "block_order"
    return "clarify_action"


def detect_trigger(intent: str) -> dict[str, object]:
    condition = detect_price_condition(intent)
    if condition is not None:
        direction, price, currency = condition
        return {"type": f"price_cross_{direction}", "price": price, "currency": currency}

    reference = detect_reference(intent)
    lookback = detect_lookback_days(intent)

    if any(word in intent for word in ["이동평균", "일선", "선 아래", "선 밑"]):
        return {
            "type": "moving_average_breakdown",
            "reference": "moving_average",
            "lookback_days": lookback or 20,
        }

    percent = detect_percent(intent)
    if percent is None:
        return {"type": "needs_clarification", "reason": "No numeric trigger was found."}

    if "고점" in intent and any(word in intent for word in ["대비", "보다"]):
        return {
            "type": "recent_high_drop_percent",
            "reference": "recent_high",
            "lookback_days": lookback or 20,
            "percent": percent,
        }
    if any(word in intent for word in ["변동성", "움직", "등락"]):
        return {
            "type": "volatility_move_percent",
            "reference": "intraday_or_daily_move",
            "percent": percent,
        }
    if any(word in intent for word in ["떨어", "하락", "빠지", "내려"]):
        return {
            "type": "price_drop_percent",
            "from": reference,
            "reference": reference,
            "percent": percent,
        }
    if any(word in intent for word in ["오르", "상승", "급등"]):
        return {
            "type": "price_rise_percent",
            "from": reference,
            "reference": reference,
            "percent": percent,
        }
    return {
        "type": "price_move_percent",
        "from": reference,
        "reference": reference,
        "percent": percent,
        "direction": "needs_clarification",
    }


def detect_reference(intent: str) -> str:
    if any(word in intent for word in ["평균 매수가", "평단", "내 매수가"]):
        return "average_purchase_price"
    if "현재가" in intent:
        return "current_price"
    if any(word in intent for word in ["전일 종가", "전날 종가", "어제 종가"]):
        return "previous_close"
    return "previous_close"


_KRW_PRICE_RE = re.compile(r"(?<![\d.,])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*(억|천만|백만|만)?\s*원")
_USD_PRICE_RE = re.compile(
    r"\$\s*(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)|(?<![\d.,])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*(?:달러|불|usd)", re.IGNORECASE
)
_PRICE_UNITS = {None: 1, "만": 10_000, "백만": 1_000_000, "천만": 10_000_000, "억": 100_000_000}
# 가격 바로 뒤(조사 허용)에 방향을 나타내는 말이 와야 가격 조건으로 본다: "4만원 아래로", "$180 넘으면", "200달러를 돌파하면"
_PRICE_BELOW_RE = re.compile(r"^\s*(?:을|를|이|가|선|대)?\s*(?:밑|아래|이하|미만|깨지|하회)")
_PRICE_ABOVE_RE = re.compile(r"^\s*(?:을|를|이|가|선|대)?\s*(?:위|넘|이상|초과|돌파|상회)")


def detect_price_condition(intent: str) -> tuple[str, float, str] | None:
    """("below"|"above", 가격, "KRW"|"USD"). 가격 바로 뒤에 방향을 나타내는 말이 있을 때만 가격 조건으로 본다."""
    candidates: list[tuple[int, float, str, int]] = []
    for match in _KRW_PRICE_RE.finditer(intent):
        number = float(match.group(1).replace(",", "")) * _PRICE_UNITS[match.group(2)]
        candidates.append((match.start(), number, "KRW", match.end()))
    for match in _USD_PRICE_RE.finditer(intent):
        number = float((match.group(1) or match.group(2)).replace(",", ""))
        candidates.append((match.start(), number, "USD", match.end()))
    for _, price, currency, end in sorted(candidates):
        rest = intent[end:]
        if _PRICE_BELOW_RE.match(rest):
            return ("below", price, currency)
        if _PRICE_ABOVE_RE.match(rest):
            return ("above", price, currency)
    return None


def detect_lookback_days(intent: str) -> int | None:
    match = re.search(r"최근\s*(\d+)\s*일", intent)
    if match:
        return int(match.group(1))
    match = re.search(r"(\d+)\s*일선", intent)
    if match:
        return int(match.group(1))
    return None


def detect_order(intent: str) -> dict[str, object]:
    shares = re.search(r"(\d+)\s*주", intent)
    if shares:
        return {"mode": "shares", "value": int(shares.group(1))}
    percent = re.search(r"(\d+(?:\.\d+)?)\s*%\s*(?:만|만큼|비중|수량|보유)", intent)
    if percent:
        return {"mode": "portfolio_or_position_percent", "value": float(percent.group(1))}
    if "절반" in intent or "반만" in intent:
        return {"mode": "position_fraction", "value": 0.5}
    amount = detect_amount_krw(intent)
    if amount is not None:
        return {"mode": "amount", "value": amount, "currency": "KRW"}
    return {"mode": "required_before_activation"}


_AMOUNT_RE = re.compile(r"(?<![\d.,])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*(억|천만|백만|만)?\s*원")
_AMOUNT_UNITS = {None: 1, "만": 10_000, "백만": 1_000_000, "천만": 10_000_000, "억": 100_000_000}
# 금액 뒤에 이런 말이 오면 주문 금액이 아니라 가격 조건이다: "4만원 아래로", "55000원 되면", "4만원에 사줘"
_PRICE_CONTEXT_RE = re.compile(r"^\s*(?:을|를|이|가)?\s*(?:아래|이하|미만|밑|위|이상|초과|넘|돌파|상회|하회|깨지|도달|되면|선|대|에\s)")


def detect_amount_krw(intent: str) -> float | None:
    """주문 금액(원). '10만원만', '50만원어치', '100만원 매수', '1,000,000원', '1억원'."""
    for match in _AMOUNT_RE.finditer(intent):
        if _PRICE_CONTEXT_RE.match(intent[match.end():]):
            continue
        number = float(match.group(1).replace(",", ""))
        return number * _AMOUNT_UNITS[match.group(2)]
    return None


def detect_time_window(intent: str) -> dict[str, object]:
    window: dict[str, object] = {"market_session": "regular"}
    lowered = intent.lower()
    if any(word in intent for word in ["애프터마켓", "시간외", "장후", "장 마감 후"]) or any(
        word in lowered for word in ["after-hours", "after hours", "aftermarket"]
    ):
        window["market_session"] = "after_hours"
    elif any(word in intent for word in ["프리마켓", "장전", "장 시작 전"]) or any(
        word in lowered for word in ["pre-market", "premarket"]
    ):
        window["market_session"] = "pre_market"
    if any(word in intent for word in ["장 시작 직후 제외", "장초반 제외", "장 초반 제외"]):
        window["exclude_open_minutes"] = 10
    if "오전" in intent and any(word in intent for word in ["하지 말", "제외"]):
        window["exclude_morning"] = True
    if "장 마감" in intent:
        minutes = re.search(r"장 마감\s*(\d+)\s*분", intent)
        window["only_before_close_minutes"] = int(minutes.group(1)) if minutes else 30
    if "오늘만" in intent:
        window["expires"] = "today"
    if "이번 주" in intent:
        window["expires"] = "this_week"
    if "3일 연속" in intent:
        window["requires_consecutive_days"] = 3
    return window


def detect_cooldown(intent: str) -> dict[str, object]:
    if "하루 한 번" in intent or "1일 1번" in intent:
        return {"min_days_between_triggers": 1}
    match = re.search(r"(\d+)\s*일\s*(?:쉬|쿨다운|기다)", intent)
    if match:
        return {"min_days_between_triggers": int(match.group(1))}
    match = re.search(r"(\d+)\s*분\s*(?:쉬|쿨다운|기다)", intent)
    if match:
        return {"min_minutes_between_triggers": int(match.group(1))}
    return {"min_minutes_between_triggers": 10}


def detect_cancel_conditions(intent: str) -> list[dict[str, object]]:
    conditions: list[dict[str, object]] = [{"type": "quote_stale"}]
    if "뉴스" in intent and any(word in intent for word in ["악재", "나쁘", "부정"]):
        conditions.append({"type": "negative_news_requires_manual_review"})
    if "거래량" in intent and any(word in intent for word in ["너무 많", "급증", "폭증"]):
        conditions.append({"type": "volume_spike_requires_manual_review"})
    percent = detect_percent(intent)
    if (
        percent is not None
        and any(word in intent for word in ["빠지", "하락", "떨어"])
        and any(word in intent for word in ["넘게", "이상"])
        and any(word in intent for word in ["하지 마", "하지 말", "멈춰", "중단"])
    ):
        conditions.append({"type": "daily_drop_exceeds_percent", "percent": percent})
    if any(word in intent for word in ["시세 지연", "지연되면", "서버 불안", "장애"]):
        conditions.append({"type": "provider_or_broker_unstable"})
    return conditions


def detect_execution_mode(intent: str) -> str:
    if any(word in intent for word in ["알림만", "알려줘", "후보로", "확인해줘"]):
        return "notify_only"
    if any(word in intent for word in ["자동 주문하지", "내가 확인", "확인하고"]):
        return "manual_confirm"
    return "manual_confirm"


def detect_emotional_flags(intent: str) -> list[dict[str, str]]:
    flags: list[dict[str, str]] = []
    for flag, words in EMOTIONAL_PATTERNS.items():
        for word in words:
            if word in intent:
                flags.append(
                    {
                        "flag": flag,
                        "evidence": word,
                        "response": "룰을 활성화하기 전에 감정이 가라앉은 상태에서 다시 확인해 주세요.",
                    }
                )
                break
    return flags
