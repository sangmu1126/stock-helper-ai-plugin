"""가상의 사내 담보비율 계산 모듈 — 공식 규칙에 맞춘 버전(시연용, 실제 회사 코드 아님)."""
from datetime import date, timedelta

MAINTENANCE_RATIO = 140
EMERGENCY_RATIO = 120
WATCH_RATIO = 150
GRACE_FROM, GRACE_TO = date(2026, 11, 9), date(2027, 2, 5)
# 한국거래소 휴장일 공지(2026-11-18 조회) 중 시연 기간분. 실제 서비스는 거래소 달력을 받아 쓴다.
KRX_HOLIDAYS = {date(2026, 12, 25), date(2026, 12, 31), date(2027, 1, 1)}


def classify(ratio):
    if ratio < EMERGENCY_RATIO:
        return "EMERGENCY"
    if ratio < MAINTENANCE_RATIO:
        return "SHORTFALL"
    if ratio < WATCH_RATIO:
        return "WATCH"
    return "SAFE"


def _add_business_days(start, days):
    current, added = start, 0
    while added < days:
        current += timedelta(days=1)
        if current.weekday() < 5 and current not in KRX_HOLIDAYS:
            added += 1
    return current


def liquidation_day(clock, start):
    return _add_business_days(start, 2 if clock == "SHORTFALL" else 1)


def grace(ratio, shortfall_round, liquidation):
    if not GRACE_FROM <= liquidation <= GRACE_TO:
        return "NOT_ACTIVE"
    if not 130 <= ratio < 140:
        return "NOT_ELIGIBLE"
    if shortfall_round is None:
        return "NEEDS_ROUND"
    return "ELIGIBLE" if shortfall_round == 2 else "NOT_ELIGIBLE"
