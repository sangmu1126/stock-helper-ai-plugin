package toybroker;

import java.time.OffsetDateTime;
import java.time.format.DateTimeFormatter;

/** 주문 접수 검증. */
public final class OrderValidation {
    // 정규장 주문 접수 컷오프 (검토 결과: SOR이 아니라 KRX 정규장 마감 기준)
    static final String ORDER_CUTOFF = "15:30"; // mhg: KRX_REGULAR_CLOSE

    private OrderValidation() {
    }

    public static boolean isAfterCutoff(OffsetDateTime at) {
        return at.format(DateTimeFormatter.ofPattern("HH:mm")).compareTo(ORDER_CUTOFF) >= 0;
    }
}
