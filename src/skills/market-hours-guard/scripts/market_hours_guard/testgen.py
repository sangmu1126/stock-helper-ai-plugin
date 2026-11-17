"""기준표의 probe 정의에서 경계 시각 테스트를 생성한다.

각 구간 [start, end)의 경계마다 '1초 전'과 '정각'을 만들고, 기준표로 기대값을 계산한다.
외국 시간대 probe(예: 미국 정규장)는 표본 날짜마다 현지(한국) 시각으로 환산하므로
서머타임 전환 전후의 차이가 테스트에 그대로 드러난다.
특수일(수능일 등)에는 그날의 구간과 함께 빠진 평소 경계를, 휴장일에는 평소 경계 전부를 검사한다.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .calendar_model import Calendar, Probe, Window
from .timeutil import fmt_time, get_tz

ADAPTER_NAME = "mhg_adapter.py"
CASES_NAME = "market_hours_cases.json"
TEST_NAME = "test_market_hours_generated.py"

_TEST_TEMPLATE = '''# mhg:generated — 직접 수정하지 말고 `mhg.py gen-tests`로 다시 만드세요.
"""거래시간 경계 테스트. 기준표: {name} ({digest})"""

from __future__ import annotations

import datetime as _dt
import json
import pathlib

import pytest

import mhg_adapter

_CASES = json.loads(
    pathlib.Path(__file__).with_name("{cases}").read_text(encoding="utf-8")
)["cases"]


@pytest.mark.parametrize("case", _CASES, ids=[c["id"] for c in _CASES])
def test_market_hours_boundary(case):
    fn = mhg_adapter.PROBES.get(case["probe"])
    if fn == "skip":
        pytest.skip(f"{{case['probe']}}: 어댑터에서 제외됨")
    if fn is None:
        pytest.fail(f"mhg_adapter.PROBES['{{case['probe']}}']가 연결되지 않았습니다")
    at = _dt.datetime.fromisoformat(case["at"])
    actual = fn(at)
    assert actual == case["expect"], (
        f"{{case['why']}} | 시각 {{case['at']}} ({{case['probe_time']}}) | "
        f"기대 {{case['expect']!r}}, 실제 {{actual!r}}"
    )
'''

_ADAPTER_TEMPLATE = '''"""mhg 경계 테스트 어댑터 — 기준표의 probe를 이 저장소의 실제 함수에 연결한다.

각 값은 한국시간 aware datetime 하나를 받아 기준표 probe의 expect와 같은 형식을 돌려주는 함수다.
연결할 함수가 없으면 "skip"으로 두고, 이유를 주석으로 남긴다. None이면 테스트가 실패한다.
"""

PROBES = {{
{entries}
}}
'''


def _expected(windows: list[Window], probe: Probe, local_time) -> tuple[Any, str]:
    for w in windows:
        if w.start <= local_time < w.end:
            return w.expect, f"{fmt_time(w.start)}~{fmt_time(w.end)} 구간"
    return probe.default, "구간 밖"


def build_cases(cal: Calendar) -> list[dict]:
    local_tz = get_tz(cal.local_tz)
    cases: list[dict] = []
    for probe in cal.probes:
        probe_tz = get_tz(probe.tz)
        for day in probe.sample_dates:
            windows = sorted((w for w in probe.windows if w.applies(day)), key=lambda w: w.start)
            special = cal.special_day(day)
            holiday = cal.holiday(probe.market, day)
            # 특수일에 적용이 빠진 평소 구간의 경계도 검사한다(예: 수능일 09:00에는 아직 정규장이 아님).
            moved = [w for w in probe.windows if day in w.exclude_dates]
            if holiday:  # 휴장일에는 평소 구간이 모두 빠진다. 평소 경계 시각에 전부 default여야 한다.
                windows, moved = [], windows
            points: dict[datetime, str] = {}
            for w, suffix in [(w, "") for w in windows] + [(w, " (평소 경계)") for w in moved]:
                for edge, edge_name in ((w.start, "시작"), (w.end, "종료")):
                    at = datetime.combine(day, edge, tzinfo=probe_tz)
                    span = f"{fmt_time(w.start)}~{fmt_time(w.end)}{suffix}"
                    points.setdefault(at - timedelta(seconds=1), f"{span} {edge_name} 1초 전")
                    points.setdefault(at, f"{span} {edge_name} 정각")
            cutoff = special.confirmed_until if special else None
            for at in sorted(points):
                if cutoff and at.astimezone(local_tz).time() >= cutoff:
                    continue  # 거래소가 공지하지 않은 시간대는 기대값을 정할 수 없어 뺀다
                local_in_probe = at.astimezone(probe_tz)
                expect, where = _expected(windows, probe, local_in_probe.time())
                local = at.astimezone(local_tz)
                cases.append({
                    "id": f"{probe.id}@{local.strftime('%Y%m%d-%H%M%S')}",
                    "probe": probe.id,
                    "at": local.isoformat(),
                    "probe_time": f"{local_in_probe.strftime('%Y-%m-%d %H:%M:%S')} {local_in_probe.tzname()}",
                    "expect": expect,
                    "why": (f"[{special.name}] " if special else "") + (f"[휴장일 {holiday}] " if holiday else "")
                           + f"{probe.description or probe.id}: {points[at]} → {where}",
                })
    return cases


def write_tests(cal: Calendar, out_dir: Path, adapter_hint: dict[str, str] | None = None) -> dict[str, Any]:
    """테스트·케이스 파일을 쓰고, 어댑터가 없으면 미연결 상태의 초안을 만든다(기존 파일은 보존)."""
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
    (out_dir / TEST_NAME).write_text(
        _TEST_TEMPLATE.format(name=cal.name, digest=cal.digest, cases=CASES_NAME), encoding="utf-8"
    )
    adapter = out_dir / ADAPTER_NAME
    adapter_created = False
    if not adapter.exists():
        hint = adapter_hint or {}
        entries = "\n".join(
            f"    # {p.description or p.id} (기대값 예: {p.default!r})\n"
            f"    {p.id!r}: {hint.get(p.id, 'None')},"
            for p in cal.probes
        )
        adapter.write_text(_ADAPTER_TEMPLATE.format(entries=entries), encoding="utf-8")
        adapter_created = True
    return {
        "cases": len(cases),
        "probes": [p.id for p in cal.probes],
        "files": [str(out_dir / TEST_NAME), str(out_dir / CASES_NAME)],
        "adapter": str(adapter),
        "adapter_created": adapter_created,
    }
