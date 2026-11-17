"""주문 라우팅: SOR 적용 시간에는 SOR로, 그 외에는 KRX로 보낸다."""
from datetime import time

SOR_START = time(9, 0)  # mhg: SOR_START
# SOR(최선집행) 적용 종료 시각 — 2026-09-14 애프터마켓 개장으로 20:00까지 연장
SOR_END = time(20, 0)  # mhg: SOR_END


def route_order(at):
    t = at.time()
    if SOR_START <= t < SOR_END:
        return "SOR"
    return "KRX"
