"""경계 테스트를 JUnit 5 테스트로 만든다 (Java·Kotlin 저장소용).

pytest 출력과 같은 케이스(build_cases)를 쓴다. 케이스는 테스트 클래스 안에 그대로 들어가므로
JSON 라이브러리가 필요 없고, junit-jupiter(params 포함)만 있으면 된다.
생성 파일은 ASCII만 쓴다(한글은 \\uXXXX). 컴파일러 기본 인코딩이 UTF-8이 아닌 환경에서도 깨지지 않게 하기 위해서다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .calendar_model import Calendar
from .testgen import CASES_NAME, build_cases

TEST_CLASS = "MarketHoursBoundaryTest"
ADAPTER_CLASS = "MhgAdapter"


def java_string(value: Any) -> str:
    """Java 문자열 리터럴. 따옴표·역슬래시·제어 문자·비ASCII 문자를 이스케이프한다."""
    text = value if isinstance(value, str) else expect_text(value)
    out = []
    for ch in text:
        if ch in '"\\':
            out.append("\\" + ch)
        elif ch == "\n":
            out.append("\\n")
        elif 32 <= ord(ch) < 127:
            out.append(ch)
        else:
            out.extend(f"\\u{unit:04x}" for unit in _utf16_units(ch))
    return '"' + "".join(out) + '"'


def _utf16_units(ch: str) -> list[int]:
    data = ch.encode("utf-16-be")
    return [int.from_bytes(data[i:i + 2], "big") for i in range(0, len(data), 2)]


def expect_text(value: Any) -> str:
    """기대값을 Java의 String.valueOf(...) 결과와 같은 문자열로 바꾼다 (true/false, 숫자, 문자열)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _package_line(package: str | None) -> str:
    return f"package {package};\n\n" if package else ""


def render_test(cal: Calendar, cases: list[dict], package: str | None) -> str:
    rows = ",\n".join(
        "            Arguments.of(" + ", ".join(java_string(c[k]) for k in ("id", "probe", "at", "expect", "why", "probe_time"))
        + ")"
        for c in cases
    )
    not_connected = java_string("가 연결되지 않았습니다")
    skipped = java_string(": 어댑터에서 제외됨")
    expected = java_string(" | 기대 ")
    return f'''// mhg:generated - do not edit. Regenerate with: mhg.py gen-tests --format junit
// Calendar: {java_string(cal.name)} ({cal.digest}), {len(cases)} cases
{_package_line(package)}import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assumptions.assumeFalse;

import java.time.OffsetDateTime;
import java.util.function.Function;
import java.util.stream.Stream;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

class {TEST_CLASS} {{

    static Stream<Arguments> cases() {{
        return Stream.of(
{rows}
        );
    }}

    @ParameterizedTest(name = "{{0}}")
    @MethodSource("cases")
    void boundary(String id, String probe, String at, String expect, String why, String probeTime) {{
        assumeFalse({ADAPTER_CLASS}.SKIP.contains(probe), probe + {skipped});
        Function<OffsetDateTime, Object> fn = {ADAPTER_CLASS}.PROBES.get(probe);
        assertNotNull(fn, "{ADAPTER_CLASS}.PROBES[" + probe + "]" + {not_connected});
        Object actual = fn.apply(OffsetDateTime.parse(at));
        assertEquals(expect, String.valueOf(actual), why + " | " + at + " (" + probeTime + ")" + {expected} + expect);
    }}
}}
'''


def render_adapter(cal: Calendar, package: str | None) -> str:
    entries = "\n".join(
        f"        // {p.id}: expected values like {json.dumps(expect_text(p.default))}\n"
        f'        PROBES.put("{p.id}", null);'
        for p in cal.probes
    )
    return f'''// mhg adapter - connect each calendar probe to a function in this repository.
// A function takes the case time (OffsetDateTime with the calendar's local offset) and returns a value
// whose String.valueOf(...) equals the calendar's expect value (for example "REGULAR" or "true").
// A probe left as null fails its tests. If the repository has no such behavior, add its id to SKIP
// and write the reason in a comment.
{_package_line(package)}import java.time.OffsetDateTime;
import java.util.HashMap;
import java.util.Map;
import java.util.Set;
import java.util.function.Function;

final class {ADAPTER_CLASS} {{
    static final Set<String> SKIP = Set.of();
    static final Map<String, Function<OffsetDateTime, Object>> PROBES = new HashMap<>();

    static {{
{entries}
    }}

    private {ADAPTER_CLASS}() {{
    }}
}}
'''


def write_junit_tests(cal: Calendar, out_dir: Path, package: str | None = None) -> dict[str, Any]:
    """JUnit 테스트와 케이스 JSON(참고용)을 쓰고, 어댑터가 없으면 미연결 초안을 만든다(기존 파일은 보존)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cases = build_cases(cal)
    payload = {
        "_generated": "mhg:generated",
        "calendar": {"name": cal.name, "digest": cal.digest},
        "probes": {p.id: p.description for p in cal.probes},
        "cases": cases,
    }
    (out_dir / CASES_NAME).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    test_file = out_dir / f"{TEST_CLASS}.java"
    test_file.write_text(render_test(cal, cases, package), encoding="ascii")
    adapter = out_dir / f"{ADAPTER_CLASS}.java"
    adapter_created = not adapter.exists()
    if adapter_created:
        adapter.write_text(render_adapter(cal, package), encoding="ascii")
    return {
        "cases": len(cases),
        "probes": [p.id for p in cal.probes],
        "files": [str(test_file), str(out_dir / CASES_NAME)],
        "adapter": str(adapter),
        "adapter_created": adapter_created,
    }
