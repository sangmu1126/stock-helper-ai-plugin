"""주문 접수 검증."""

# 주문 접수 컷오프
ORDER_CUTOFF = "15:30"


def is_after_cutoff(at):
    return at.strftime("%H:%M") >= ORDER_CUTOFF
