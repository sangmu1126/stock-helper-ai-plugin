"""미국 정규장 개장 여부 — 뉴욕 시간으로 판정해 서머타임을 자동 반영한다."""
from datetime import time
from zoneinfo import ZoneInfo

NEW_YORK = ZoneInfo("America/New_York")
US_OPEN = time(9, 30)  # mhg: US_REGULAR_OPEN
US_CLOSE = time(16, 0)  # mhg: US_REGULAR_CLOSE


def is_us_regular_open(at):
    local = at.astimezone(NEW_YORK)
    return local.weekday() < 5 and US_OPEN <= local.time() < US_CLOSE
