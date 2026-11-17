package toybroker;

import java.time.LocalDate;
import java.time.LocalTime;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;
import java.util.Set;

/** KRX 세션 판정 — 휴장일, 정규장, 애프터마켓(2026-09-14~), 수능일 같은 특수일 시각을 구분한다. */
public final class Session {
    static final LocalTime REGULAR_OPEN = LocalTime.of(9, 0); // mhg: KRX_REGULAR_OPEN
    static final LocalTime REGULAR_CLOSE = LocalTime.of(15, 30); // mhg: KRX_REGULAR_CLOSE
    static final LocalTime AFTER_OPEN = LocalTime.of(16, 0); // mhg: KRX_AFTER_OPEN
    static final LocalTime AFTER_CLOSE = LocalTime.of(20, 0); // mhg: KRX_AFTER_CLOSE

    record Window(String state, LocalTime open, LocalTime close) {
    }

    static final List<Window> USUAL = List.of(
            new Window("REGULAR", REGULAR_OPEN, REGULAR_CLOSE),
            new Window("AFTER", AFTER_OPEN, AFTER_CLOSE));

    // 거래소가 거래시간을 바꾼 특수일: 그날은 평소 시각 대신 이 시각을 쓴다.
    static final Map<LocalDate, List<Window>> SPECIAL_HOURS = Map.of(
            LocalDate.of(2026, 11, 19), List.of(
                    new Window("REGULAR", LocalTime.of(10, 0), LocalTime.of(16, 30)), // mhg: KRX_REGULAR_OPEN_CSAT_2026, KRX_REGULAR_CLOSE_CSAT_2026
                    new Window("AFTER", LocalTime.of(17, 0), LocalTime.of(20, 0)))); // mhg: KRX_AFTER_OPEN_CSAT_2026, KRX_AFTER_CLOSE

    // 한국거래소 휴장일 공지(2026-11-18 조회) 중 시연 기간분. 실제 시스템은 거래소 달력을 받아 쓴다.
    static final Set<LocalDate> KRX_HOLIDAYS = Set.of(
            LocalDate.of(2026, 12, 25), LocalDate.of(2026, 12, 31), LocalDate.of(2027, 1, 1));

    private Session() {
    }

    public static String krxSession(OffsetDateTime at) {
        LocalDate day = at.toLocalDate();
        LocalTime t = at.toLocalTime();
        if (KRX_HOLIDAYS.contains(day)) {
            return "CLOSED";
        }
        for (Window w : SPECIAL_HOURS.getOrDefault(day, USUAL)) {
            if (!t.isBefore(w.open()) && t.isBefore(w.close())) {
                return w.state();
            }
        }
        return "CLOSED";
    }
}
