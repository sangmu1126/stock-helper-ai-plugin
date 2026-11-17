"""주문 라우팅: SOR 적용 시간에는 SOR로, 그 외에는 KRX로 보낸다."""
from datetime import time

SOR_START = time(9, 0)
# SOR(최선집행) 적용 종료 시각
SOR_END = time(15, 30)


def route_order(at):
    t = at.time()
    if SOR_START <= t < SOR_END:
        return "SOR"
    return "KRX"
