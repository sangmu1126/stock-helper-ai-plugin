package toybroker;

import java.time.OffsetDateTime;
import java.util.HashMap;
import java.util.Map;
import java.util.Set;
import java.util.function.Function;

/** mhg 경계 테스트 어댑터 — 기준표 probe를 이 저장소의 메서드에 연결한다. */
final class MhgAdapter {
    static final Set<String> SKIP = Set.of();
    static final Map<String, Function<OffsetDateTime, Object>> PROBES = new HashMap<>();

    static {
        PROBES.put("krx_session", Session::krxSession);
        PROBES.put("sor_enabled", at -> OrderRouter.routeOrder(at).equals("SOR"));
        PROBES.put("us_regular_open", UsMarket::isUsRegularOpen);
    }

    private MhgAdapter() {
    }
}
