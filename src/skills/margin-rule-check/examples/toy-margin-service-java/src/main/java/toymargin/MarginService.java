package toymargin;

import java.time.DayOfWeek;
import java.time.LocalDate;

/** 가상의 사내 담보비율 계산 모듈 — 공식 규칙과 어긋난 부분이 일부러 들어 있다(시연용, 실제 회사 코드 아님). */
public final class MarginService {
    static final double MAINTENANCE_RATIO = 130;
    static final double EMERGENCY_RATIO = 120;
    static final double WATCH_RATIO = 150;
    static final LocalDate GRACE_FROM = LocalDate.of(2026, 11, 9);
    static final LocalDate GRACE_TO = LocalDate.of(2027, 2, 5);

    private MarginService() {
    }

    public static String classify(double ratio) {
        if (ratio < EMERGENCY_RATIO) {
            return "EMERGENCY";
        }
        if (ratio < MAINTENANCE_RATIO) {
            return "SHORTFALL";
        }
        if (ratio < WATCH_RATIO) {
            return "WATCH";
        }
        return "SAFE";
    }

    static LocalDate addBusinessDays(LocalDate start, int days) {
        LocalDate current = start;
        int added = 0;
        while (added < days) {
            current = current.plusDays(1);
            if (current.getDayOfWeek().compareTo(DayOfWeek.SATURDAY) < 0) {
                added++;
            }
        }
        return current;
    }

    public static LocalDate liquidationDay(String clock, LocalDate start) {
        return addBusinessDays(start, "SHORTFALL".equals(clock) ? 3 : 1);
    }

    public static String grace(double ratio, Integer shortfallRound, LocalDate liquidation) {
        if (liquidation.isBefore(GRACE_FROM) || liquidation.isAfter(GRACE_TO)) {
            return "NOT_ACTIVE";
        }
        if (ratio < 130 || ratio >= 140) {
            return "NOT_ELIGIBLE";
        }
        return "ELIGIBLE";
    }
}
