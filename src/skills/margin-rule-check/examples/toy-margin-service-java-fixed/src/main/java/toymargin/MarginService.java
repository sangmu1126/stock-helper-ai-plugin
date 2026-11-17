package toymargin;

import java.time.DayOfWeek;
import java.time.LocalDate;
import java.util.Set;

/** 가상의 사내 담보비율 계산 모듈 — 공식 규칙에 맞춘 버전(시연용, 실제 회사 코드 아님). */
public final class MarginService {
    static final double MAINTENANCE_RATIO = 140;
    static final double EMERGENCY_RATIO = 120;
    static final double WATCH_RATIO = 150;
    static final LocalDate GRACE_FROM = LocalDate.of(2026, 11, 9);
    static final LocalDate GRACE_TO = LocalDate.of(2027, 2, 5);

    // 한국거래소 휴장일 공지(2026-11-18 조회) 중 시연 기간분. 실제 서비스는 거래소 달력을 받아 쓴다.
    static final Set<LocalDate> KRX_HOLIDAYS = Set.of(
            LocalDate.of(2026, 12, 25), LocalDate.of(2026, 12, 31), LocalDate.of(2027, 1, 1));

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
            if (current.getDayOfWeek().compareTo(DayOfWeek.SATURDAY) < 0 && !KRX_HOLIDAYS.contains(current)) {
                added++;
            }
        }
        return current;
    }

    public static LocalDate liquidationDay(String clock, LocalDate start) {
        return addBusinessDays(start, "SHORTFALL".equals(clock) ? 2 : 1);
    }

    public static String grace(double ratio, Integer shortfallRound, LocalDate liquidation) {
        if (liquidation.isBefore(GRACE_FROM) || liquidation.isAfter(GRACE_TO)) {
            return "NOT_ACTIVE";
        }
        if (ratio < 130 || ratio >= 140) {
            return "NOT_ELIGIBLE";
        }
        if (shortfallRound == null) {
            return "NEEDS_ROUND";
        }
        return shortfallRound == 2 ? "ELIGIBLE" : "NOT_ELIGIBLE";
    }
}
