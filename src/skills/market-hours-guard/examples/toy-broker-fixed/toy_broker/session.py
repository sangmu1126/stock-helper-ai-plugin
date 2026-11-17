from datetime import date, time

REGULAR_OPEN = time(9, 0)  # mhg: KRX_REGULAR_OPEN
REGULAR_CLOSE = time(15, 30)  # mhg: KRX_REGULAR_CLOSE
AFTER_OPEN = time(16, 0)  # mhg: KRX_AFTER_OPEN
AFTER_CLOSE = time(20, 0)  # mhg: KRX_AFTER_CLOSE

# 거래소가 거래시간을 바꾼 특수일: 그날은 평소 시각 대신 이 시각을 쓴다.
SPECIAL_HOURS = {
    date(2026, 11, 19): {
        "REGULAR": (time(10, 0), time(16, 30)),  # mhg: KRX_REGULAR_OPEN_CSAT_2026, KRX_REGULAR_CLOSE_CSAT_2026
        "AFTER": (time(17, 0), time(20, 0)),  # mhg: KRX_AFTER_OPEN_CSAT_2026, KRX_AFTER_CLOSE
    },
}

# 한국거래소 휴장일 공지(2026-11-18 조회) 중 시연 기간분. 실제 시스템은 거래소 달력을 받아 쓴다.
KRX_HOLIDAYS = {date(2026, 12, 25), date(2026, 12, 31), date(2027, 1, 1)}


def krx_session(at):
    """KRX 세션 판정 — 휴장일, 정규장, 애프터마켓(2026-09-14~), 수능일 같은 특수일 시각을 구분한다."""
    day, t = at.date(), at.time()
    if day in KRX_HOLIDAYS:
        return "CLOSED"
    hours = SPECIAL_HOURS.get(day, {"REGULAR": (REGULAR_OPEN, REGULAR_CLOSE), "AFTER": (AFTER_OPEN, AFTER_CLOSE)})
    for state, (open_, close) in hours.items():
        if open_ <= t < close:
            return state
    return "CLOSED"
