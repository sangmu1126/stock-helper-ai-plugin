package toybroker;

import java.time.LocalTime;
import java.time.OffsetDateTime;

/** KRX 세션 판정 — 정규장 외에는 장 종료로 본다. */
public final class Session {
    private Session() {
    }

    public static String krxSession(OffsetDateTime at) {
        LocalTime t = at.toLocalTime();
        if (!t.isBefore(LocalTime.of(9, 0)) && t.isBefore(LocalTime.of(15, 30))) {
            return "REGULAR";
        }
        return "CLOSED";
    }
}
