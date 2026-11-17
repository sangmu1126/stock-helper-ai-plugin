package toybroker;

import java.time.LocalTime;
import java.time.OffsetDateTime;

/** 주문 라우팅: SOR 적용 시간에는 SOR로, 그 외에는 KRX로 보낸다. */
public final class OrderRouter {
    static final LocalTime SOR_START = LocalTime.of(9, 0);
    // SOR(최선집행) 적용 종료 시각
    static final LocalTime SOR_END = LocalTime.of(15, 30);

    private OrderRouter() {
    }

    public static String routeOrder(OffsetDateTime at) {
        LocalTime t = at.toLocalTime();
        return !t.isBefore(SOR_START) && t.isBefore(SOR_END) ? "SOR" : "KRX";
    }
}
