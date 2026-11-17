"""신용거래 규칙 경계 테스트를 JUnit 5 테스트로 만든다 (Java·Kotlin 계산 코드용).

pytest 출력과 같은 케이스를 쓴다. 케이스는 테스트 클래스 안에 그대로 들어가므로 JSON 라이브러리가 필요 없고,
junit-jupiter(params 포함)만 있으면 된다. 생성 파일은 ASCII만 쓴다(한글은 \\uXXXX).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

TEST_CLASS = "MarginRuleTest"
ADAPTER_CLASS = "MrcAdapter"
GENERATED_MARKER = "mrc:generated"


def java_string(text: str) -> str:
    out = []
    for ch in text:
        if ch in '"\\':
            out.append("\\" + ch)
        elif ch == "\n":
            out.append("\\n")
        elif 32 <= ord(ch) < 127:
            out.append(ch)
        else:
            data = ch.encode("utf-16-be")
            out.extend(f"\\u{int.from_bytes(data[i:i + 2], 'big'):04x}" for i in range(0, len(data), 2))
    return '"' + "".join(out) + '"'


def _double(value: float) -> str:
    return repr(float(value))


def _rows(cases: list[dict[str, Any]], kind: str) -> str:
    rows = []
    for c in (c for c in cases if c["kind"] == kind):
        a = c["args"]
        if kind == "classify":
            values = [java_string(c["id"]), _double(a["ratio_pct"])]
        elif kind == "liquidation":
            values = [java_string(c["id"]), java_string(a["clock"]), java_string(a["start"])]
        else:
            rnd = a["shortfall_round"]
            values = [java_string(c["id"]), _double(a["ratio_pct"]), "null" if rnd is None else f"Integer.valueOf({rnd})",
                      java_string(a["liquidation_date"])]
        values += [java_string(str(c["expect"])), java_string(c["why"])]
        rows.append("            Arguments.of(" + ", ".join(values) + ")")
    return ",\n".join(rows)


def render_test(cases: list[dict[str, Any]], version: str, package: str | None) -> str:
    pkg = f"package {package};\n\n" if package else ""
    missing = java_string("가 연결되지 않았습니다")
    expected = java_string(" — 기대 ")
    return f'''// {GENERATED_MARKER} - do not edit. Regenerate with: margin_rule_check.py gen-tests --format junit
// Margin rules version: {version}, {len(cases)} cases
{pkg}import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assumptions.assumeFalse;

import java.time.LocalDate;
import java.util.stream.Stream;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

class {TEST_CLASS} {{

    static Stream<Arguments> classifyCases() {{
        return Stream.of(
{_rows(cases, "classify")}
        );
    }}

    static Stream<Arguments> liquidationCases() {{
        return Stream.of(
{_rows(cases, "liquidation")}
        );
    }}

    static Stream<Arguments> graceCases() {{
        return Stream.of(
{_rows(cases, "grace")}
        );
    }}

    @ParameterizedTest(name = "{{0}}")
    @MethodSource("classifyCases")
    void classifyRatio(String id, double ratioPct, String expect, String why) {{
        assumeFalse({ADAPTER_CLASS}.SKIP.contains("classify_ratio"));
        assertNotNull({ADAPTER_CLASS}.classifyRatio, "{ADAPTER_CLASS}.classifyRatio" + {missing});
        assertEquals(expect, {ADAPTER_CLASS}.classifyRatio.apply(ratioPct), why + {expected} + expect);
    }}

    @ParameterizedTest(name = "{{0}}")
    @MethodSource("liquidationCases")
    void liquidationDate(String id, String clock, String start, String expect, String why) {{
        assumeFalse({ADAPTER_CLASS}.SKIP.contains("liquidation_date"));
        assertNotNull({ADAPTER_CLASS}.liquidationDate, "{ADAPTER_CLASS}.liquidationDate" + {missing});
        Object actual = {ADAPTER_CLASS}.liquidationDate.apply(clock, LocalDate.parse(start));
        assertEquals(expect, String.valueOf(actual), why + {expected} + expect);
    }}

    @ParameterizedTest(name = "{{0}}")
    @MethodSource("graceCases")
    void graceStatus(String id, double ratioPct, Integer shortfallRound, String liquidation, String expect, String why) {{
        assumeFalse({ADAPTER_CLASS}.SKIP.contains("grace_status"));
        assertNotNull({ADAPTER_CLASS}.graceStatus, "{ADAPTER_CLASS}.graceStatus" + {missing});
        assertEquals(expect, {ADAPTER_CLASS}.graceStatus.apply(ratioPct, shortfallRound, LocalDate.parse(liquidation)),
                why + {expected} + expect);
    }}
}}
'''


def render_adapter(package: str | None) -> str:
    pkg = f"package {package};\n\n" if package else ""
    return f'''// mrc adapter - connect the company's margin calculation methods. A null field fails its tests;
// put "classify_ratio", "liquidation_date" or "grace_status" in SKIP (with a reason) if the code has no such logic.
//   classifyRatio(ratioPct)              -> "SAFE" | "WATCH" | "SHORTFALL" | "EMERGENCY"
//   liquidationDate(clock, start)        -> date, counting business days (weekends and KRX holidays skipped);
//                                           clock is "SHORTFALL" or "EMERGENCY"
//   graceStatus(ratioPct, round, date)   -> "ELIGIBLE" | "NOT_ELIGIBLE" | "NEEDS_ROUND" | "NOT_ACTIVE"
{pkg}import java.time.LocalDate;
import java.util.Set;
import java.util.function.BiFunction;
import java.util.function.Function;

final class {ADAPTER_CLASS} {{
    interface GraceStatus {{
        String apply(double ratioPct, Integer shortfallRound, LocalDate liquidationDate);
    }}

    static final Set<String> SKIP = Set.of();
    static final Function<Double, String> classifyRatio = null;
    static final BiFunction<String, LocalDate, LocalDate> liquidationDate = null;
    static final GraceStatus graceStatus = null;

    private {ADAPTER_CLASS}() {{
    }}
}}
'''


def write_junit_tests(cases: list[dict[str, Any]], version: str, out_dir: Path,
                      package: str | None = None) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "margin_rule_cases.json").write_text(json.dumps(
        {"_generated": GENERATED_MARKER, "rules_version": version, "cases": cases},
        ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out_dir / f"{TEST_CLASS}.java").write_text(render_test(cases, version, package), encoding="ascii")
    adapter = out_dir / f"{ADAPTER_CLASS}.java"
    created = not adapter.exists()
    if created:
        adapter.write_text(render_adapter(package), encoding="ascii")
    return {"cases": len(cases), "adapter": str(adapter), "adapter_created": created}
