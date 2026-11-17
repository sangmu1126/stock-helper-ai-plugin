package toybroker;

import java.time.LocalTime;
import java.time.OffsetDateTime;

/** 미국 정규장 개장 여부 (한국시간 기준). */
public final class UsMarket {
    // 미국 정규장 (한국시간)
    static final LocalTime US_OPEN_KST = LocalTime.of(22, 30);
    static final LocalTime US_CLOSE_KST = LocalTime.of(5, 0);

    private UsMarket() {
    }

    public static boolean isUsRegularOpen(OffsetDateTime at) {
        LocalTime t = at.toLocalTime();
        return !t.isBefore(US_OPEN_KST) || t.isBefore(US_CLOSE_KST);
    }
}
