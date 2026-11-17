"""미국 정규장 개장 여부 (한국시간 기준)."""
from datetime import time

# 미국 정규장 (한국시간)
US_OPEN_KST = time(22, 30)
US_CLOSE_KST = time(5, 0)


def is_us_regular_open(at):
    t = at.time()
    return t >= US_OPEN_KST or t < US_CLOSE_KST
