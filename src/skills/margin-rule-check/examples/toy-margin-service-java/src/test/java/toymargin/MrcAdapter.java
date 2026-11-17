package toymargin;

import java.time.LocalDate;
import java.util.Set;
import java.util.function.BiFunction;
import java.util.function.Function;

/** 신용거래 규칙 테스트 어댑터 — 이 저장소의 계산 메서드를 연결한다. */
final class MrcAdapter {
    interface GraceStatus {
        String apply(double ratioPct, Integer shortfallRound, LocalDate liquidationDate);
    }

    static final Set<String> SKIP = Set.of();
    static final Function<Double, String> classifyRatio = MarginService::classify;
    static final BiFunction<String, LocalDate, LocalDate> liquidationDate = MarginService::liquidationDay;
    static final GraceStatus graceStatus = MarginService::grace;

    private MrcAdapter() {
    }
}
