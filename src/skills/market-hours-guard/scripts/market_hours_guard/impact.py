"""기준표 변경 영향 미리보기: 현재 기준표와 새 기준표로 같은 저장소를 스캔해, 판정이 바뀌는 곳을 보여준다.

제도 변경 공지가 나왔을 때 기준표를 확정하기 전에 "몇 곳이 STALE·MISMATCH로 바뀌는가"를 먼저 본다.
코드는 바꾸지 않는다. 새 기준표에서 실패 조건(--fail-on) 상태가 새로 생기면 종료 코드 1.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .calendar_model import Boundary, Calendar
from .classify import Finding
from .scan import ScanResult, scan_repo
from .timeutil import fmt_time


@dataclass
class Change:
    path: str
    line: int
    found: str
    before: Finding | None
    after: Finding | None

    @property
    def transition(self) -> str:
        def label(f: Finding | None, with_boundary: bool) -> str:
            if f is None:
                return "-"
            return f"{f.status}({f.boundary})" if with_boundary and f.boundary else f.status

        same_status = bool(self.before and self.after and self.before.status == self.after.status)
        return f"{label(self.before, same_status)} → {label(self.after, same_status)}"


def _key(f: Finding) -> tuple[str, int, int, str]:
    return (f.path, f.line, f.col, f.raw)


def calendar_diff(old: Calendar, new: Calendar) -> list[str]:
    """기준 ID 단위로 값·상태가 달라진 것을 사람이 읽는 문장으로."""
    def desc(b: Boundary) -> str:
        tz = "" if b.tz == old.local_tz else f" {b.tz}"
        return f"{fmt_time(b.time)}{tz}" + (" (폐기)" if b.retired else "")

    before = {b.id: b for b in old.boundaries}
    after = {b.id: b for b in new.boundaries}
    lines = []
    for bid in sorted(before.keys() | after.keys()):
        a, b = before.get(bid), after.get(bid)
        if a is None:
            lines.append(f"추가: {bid} {desc(b)} — {b.meaning}")
        elif b is None:
            lines.append(f"삭제: {bid} {desc(a)}")
        elif (a.time, a.tz, a.retired, a.replaced_by) != (b.time, b.tz, b.retired, b.replaced_by):
            lines.append(f"변경: {bid} {desc(a)} → {desc(b)}")
    return lines


def compare(old_result: ScanResult, new_result: ScanResult) -> list[Change]:
    before = {_key(f): f for f in old_result.findings}
    after = {_key(f): f for f in new_result.findings}
    changes = []
    for key in sorted(before.keys() | after.keys()):
        a, b = before.get(key), after.get(key)
        if a and b and (a.status, a.boundary) == (b.status, b.boundary):
            continue
        sample = b or a
        changes.append(Change(path=sample.path, line=sample.line, found=sample.found, before=a, after=b))
    return changes


def run_impact(repo: Path, old: Calendar, new: Calendar, include_docs: bool = False,
               exclude: tuple[Path, ...] = ()) -> tuple[list[str], list[Change], ScanResult]:
    old_result = scan_repo(repo, old, include_docs=include_docs, exclude=exclude)
    new_result = scan_repo(repo, new, include_docs=include_docs, exclude=exclude)
    return calendar_diff(old, new), compare(old_result, new_result), new_result


def new_failures(changes: list[Change], fail_on: set[str]) -> list[Change]:
    return [c for c in changes if c.after and c.after.status in fail_on
            and not (c.before and c.before.status in fail_on)]


def render_impact(repo: Path, old: Calendar, new: Calendar, diff: list[str], changes: list[Change],
                  fail_on: set[str]) -> str:
    failing = new_failures(changes, fail_on)
    out = [
        "# 기준표 변경 영향 미리보기",
        "",
        f"- 대상 저장소: `{repo.name}`",
        f"- 현재 기준표: {old.name} ({old.digest}) → 새 기준표: {new.name} ({new.digest})",
        f"- 판정이 바뀌는 곳 {len(changes)}개 · 그중 새로 실패 조건({', '.join(sorted(fail_on))})이 되는 곳 {len(failing)}개",
        "",
        "## 기준표에서 바뀐 것",
        "",
        *([f"- {line}" for line in diff] or ["- 없음"]),
        "",
        "## 판정이 바뀌는 곳",
        "",
    ]
    if not changes:
        out.append("없음. 새 기준표를 적용해도 이 저장소의 판정은 그대로입니다.")
    else:
        out += ["| 위치 | 값 | 변화 | 새 판정 이유 |", "| --- | --- | --- | --- |"]
        for c in changes:
            reason = (c.after.reason if c.after else "새 기준표에서는 거래시간 표현으로 보지 않음").replace("|", "\\|")
            out.append(f"| `{c.path}:{c.line}` | {c.found} | {c.transition} | {reason} |")
    out += ["", "코드는 바꾸지 않았습니다. 새 기준표를 승인한 뒤 `scan`으로 확인하고 고치세요.", ""]
    return "\n".join(out)


def to_json(diff: list[str], changes: list[Change]) -> dict[str, Any]:
    def brief(f: Finding | None) -> dict[str, Any] | None:
        return None if f is None else {"status": f.status, "boundary": f.boundary, "expected": f.expected,
                                       "reason": f.reason}
    return {
        "calendar_changes": diff,
        "changes": [{"path": c.path, "line": c.line, "found": c.found, "before": brief(c.before),
                     "after": brief(c.after)} for c in changes],
    }
