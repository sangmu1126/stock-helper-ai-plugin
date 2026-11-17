from datetime import time

REGULAR_OPEN = time(9, 0)  # mhg: KRX_REGULAR_OPEN
REGULAR_CLOSE = time(15, 30)  # mhg: KRX_REGULAR_CLOSE
AFTER_OPEN = time(16, 0)  # mhg: KRX_AFTER_OPEN
AFTER_CLOSE = time(20, 0)  # mhg: KRX_AFTER_CLOSE


def krx_session(at):
    """KRX 세션 판정 — 정규장과 애프터마켓(2026-09-14~)을 구분한다."""
    t = at.time()
    if REGULAR_OPEN <= t < REGULAR_CLOSE:
        return "REGULAR"
    if AFTER_OPEN <= t < AFTER_CLOSE:
        return "AFTER"
    return "CLOSED"
