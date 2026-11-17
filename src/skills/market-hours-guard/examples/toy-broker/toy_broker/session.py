from datetime import time


def krx_session(at):
    """KRX 세션 판정 — 정규장 외에는 장 종료로 본다."""
    t = at.time()
    if time(9, 0) <= t < time(15, 30):
        return "REGULAR"
    return "CLOSED"
