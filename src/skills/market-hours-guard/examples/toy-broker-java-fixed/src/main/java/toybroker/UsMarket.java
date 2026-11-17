package toybroker;

import java.time.DayOfWeek;
import java.time.LocalTime;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

/** 미국 정규장 개장 여부 — 뉴욕 시간으로 판정해 서머타임을 자동 반영한다. */
public final class UsMarket {
    static final ZoneId NEW_YORK = ZoneId.of("America/New_York");
    static final LocalTime US_OPEN = LocalTime.of(9, 30); // mhg: US_REGULAR_OPEN
    static final LocalTime US_CLOSE = LocalTime.of(16, 0); // mhg: US_REGULAR_CLOSE

    private UsMarket() {
    }

    public static boolean isUsRegularOpen(OffsetDateTime at) {
        ZonedDateTime local = at.atZoneSameInstant(NEW_YORK);
        LocalTime t = local.toLocalTime();
        boolean weekday = local.getDayOfWeek().compareTo(DayOfWeek.SATURDAY) < 0;
        return weekday && !t.isBefore(US_OPEN) && t.isBefore(US_CLOSE);
    }
}
