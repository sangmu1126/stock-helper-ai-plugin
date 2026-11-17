from datetime import date, time

REGULAR_OPEN = time(9, 0)  # mhg: KRX_REGULAR_OPEN
REGULAR_CLOSE = time(15, 30)  # mhg: KRX_REGULAR_CLOSE
AFTER_OPEN = time(16, 0)  # mhg: KRX_AFTER_OPEN
AFTER_CLOSE = time(20, 0)  # mhg: KRX_AFTER_CLOSE

# 거래소가 정규장 시간을 바꾼 특수일. 그날의 다른 세션 시간은 공지되지 않았으므로 정규장 외에는 CLOSED.
SPECIAL_REGULAR = {
    date(2026, 11, 19): (time(10, 0), time(16, 30)),  # mhg: KRX_REGULAR_OPEN_CSAT_2026, KRX_REGULAR_CLOSE_CSAT_2026
}


def krx_session(at):
    """KRX 세션 판정 — 정규장, 애프터마켓(2026-09-14~), 수능일 같은 특수일 정규장을 구분한다."""
    t = at.time()
    special = SPECIAL_REGULAR.get(at.date())
    open_, close = special or (REGULAR_OPEN, REGULAR_CLOSE)
    if open_ <= t < close:
        return "REGULAR"
    if special is None and AFTER_OPEN <= t < AFTER_CLOSE:
        return "AFTER"
    return "CLOSED"
