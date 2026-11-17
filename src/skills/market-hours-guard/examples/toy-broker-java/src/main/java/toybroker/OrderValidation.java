package toybroker;

import java.time.OffsetDateTime;
import java.time.format.DateTimeFormatter;

/** 주문 접수 검증. */
public final class OrderValidation {
    // 주문 접수 컷오프
    static final String ORDER_CUTOFF = "15:30";

    private OrderValidation() {
    }

    public static boolean isAfterCutoff(OffsetDateTime at) {
        return at.format(DateTimeFormatter.ofPattern("HH:mm")).compareTo(ORDER_CUTOFF) >= 0;
    }
}
