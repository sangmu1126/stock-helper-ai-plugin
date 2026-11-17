"""주문 접수 검증."""

# 정규장 주문 접수 컷오프 (검토 결과: SOR이 아니라 KRX 정규장 마감 기준)
ORDER_CUTOFF = "15:30"  # mhg: KRX_REGULAR_CLOSE


def is_after_cutoff(at):
    return at.strftime("%H:%M") >= ORDER_CUTOFF
