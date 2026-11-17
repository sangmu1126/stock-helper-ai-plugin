"""추출한 시각 표현을 기준표와 대조해 상태를 판정한다.

판정 원칙
- 같은 숫자라도 의미가 다를 수 있다(15:30 = KRX 정규장 마감 / 과거 SOR 종료).
  그래서 숫자만으로 오류라고 하지 않고, 문맥 키워드 근거가 있을 때만 STALE로 본다.
- 근거가 부족하면 AMBIGUOUS로 남겨 사람이(또는 Codex가 코드를 읽고) 의미를 확정한다.
- `mhg: <ID>` 주석으로 의미가 확정된 줄은 기준표 값과 정확히 비교한다(MISMATCH 검출).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from .calendar_model import Boundary, Calendar
from .extract import Occurrence
from .timeutil import fmt_time, shift

STATUS_ORDER = ("MISMATCH", "STALE", "DST_RISK", "AMBIGUOUS", "UNMAPPED", "MATCH", "IGNORED")
SEVERITY = {
    "MISMATCH": "high", "STALE": "high", "DST_RISK": "high",
    "AMBIGUOUS": "medium", "UNMAPPED": "low", "MATCH": "info", "IGNORED": "info",
}
STATUS_LABEL = {
    "MISMATCH": "주석으로 지정한 기준과 값 불일치",
    "STALE": "폐기된 기준값 사용 의심 (변경 누락)",
    "DST_RISK": "미국 시각을 한국시각 고정값으로 사용 (서머타임 미반영)",
    "AMBIGUOUS": "현행·폐기 기준에 모두 해당 — 의미 확인 필요",
    "UNMAPPED": "거래시간 문맥이지만 기준표에 없는 값",
    "MATCH": "현행 기준과 일치",
    "IGNORED": "무관 표시됨 (mhg: ignore)",
}
SEASONAL_TOKENS = {"dst", "summer", "winter", "edt", "est", "daylight"}
SEASONAL_KO = ("서머타임", "썸머타임", "하절기", "동절기")
_ITEM_RE = re.compile(r"\s*([A-Za-z_]\w*)(?:\s*([+-])\s*(\d+)\s*([mh]))?")


@dataclass
class Finding:
    id: str
    status: str
    severity: str
    path: str
    line: int
    col: int
    kind: str
    found: str
    raw: str
    boundary: str | None
    expected: str | None
    reason: str
    action: str
    evidence: list[str] = field(default_factory=list)
    reviewed: bool = False
    snippet: str = ""


def keyword_hits(keywords: tuple[str, ...] | list[str], occ: Occurrence) -> list[str]:
    """영문 키워드는 토큰 일치(4자 이상이면 접두어 일치), 한글 키워드는 부분 문자열로 찾는다."""
    hits: list[str] = []
    for keyword in keywords:
        k = keyword.lower()
        if re.search(r"[가-힣]", k):
            if k in occ.context:
                hits.append(keyword)
        elif k in occ.tokens or (len(k) >= 4 and any(t.startswith(k) for t in occ.tokens)):
            hits.append(keyword)
    return hits


def _finding(occ: Occurrence, status: str, reason: str, action: str = "", boundary: Boundary | None = None,
             expected: str | None = None, evidence: list[str] | None = None, reviewed: bool = False) -> Finding:
    digest = hashlib.sha1(f"{occ.path}:{occ.line}:{occ.col}:{occ.raw}".encode()).hexdigest()[:10]
    return Finding(
        id=digest, status=status, severity=SEVERITY[status], path=occ.path, line=occ.line, col=occ.col,
        kind=occ.kind, found=fmt_time(occ.time), raw=occ.raw,
        boundary=boundary.id if boundary else None, expected=expected, reason=reason, action=action,
        evidence=evidence or [], reviewed=reviewed, snippet=occ.snippet,
    )


def _parse_item(item: str) -> tuple[str, int] | None:
    match = _ITEM_RE.match(item)
    if not match:
        return None
    ident = match.group(1)
    if ident.lower() == "ignore":
        return ("ignore", 0)
    offset = 0
    if match.group(2):
        amount = int(match.group(3)) * (60 if match.group(4) == "h" else 1)
        offset = amount if match.group(2) == "+" else -amount
    return (ident, offset)


def _expected_local(cal: Calendar, b: Boundary, offset: int) -> set:
    return {shift(t, offset) for t in cal.local_equivalents(b).values()}


def _pick_annotation(occ: Occurrence, cal: Calendar) -> tuple[str, int] | None:
    items = [p for p in (_parse_item(i) for i in occ.annotations) if p]
    if not items:
        return None
    if len(items) == 1:
        return items[0]
    if len(items) == occ.count_on_line:
        return items[occ.index_on_line]
    for ident, offset in items:  # 개수가 다르면 값이 맞는 주석을 찾는다
        b = cal.get(ident)
        if b and (shift(b.time, offset) == occ.time or occ.time in _expected_local(cal, b, offset)):
            return (ident, offset)
    return None


def _describe(ident: str, offset: int) -> str:
    if not offset:
        return ident
    sign = "+" if offset > 0 else "-"
    return f"{ident}{sign}{abs(offset)}m"


def _classify_annotated(occ: Occurrence, cal: Calendar, ident: str, offset: int) -> Finding:
    if ident == "ignore":
        return _finding(occ, "IGNORED", "mhg: ignore로 거래시간과 무관하다고 표시됨", reviewed=True)
    b = cal.get(ident)
    if b is None:
        return _finding(occ, "MISMATCH", f"주석의 기준 ID '{ident}'가 기준표에 없습니다",
                        "기준표의 ID로 고치거나, 새 기준이면 출처와 함께 기준표에 추가 승인을 받으세요.")
    if b.retired:
        new = cal.get(b.replaced_by or "")
        new_desc = f"{new.id} {fmt_time(new.time)}" if new else "(대체 기준 없음)"
        return _finding(occ, "STALE", f"주석이 폐기된 기준 {b.label}을 가리킵니다 (→ {new_desc})",
                        f"값을 {new_desc} 기준으로 바꾸고 주석을 `mhg: {_describe(new.id if new else '?', offset)}`로 갱신하세요.",
                        boundary=b, expected=fmt_time(shift(new.time, offset)) if new else None, reviewed=True)
    expected = shift(b.time, offset)
    label = _describe(b.id, offset)
    if occ.time == expected:
        return _finding(occ, "MATCH", f"{label} = {fmt_time(expected)} ({b.meaning})", boundary=b,
                        expected=fmt_time(expected), reviewed=True)
    if b.tz != cal.local_tz and occ.time in _expected_local(cal, b, offset):
        eq = cal.local_equivalents(b)
        seasons = ", ".join(f"{k} {fmt_time(shift(v, offset))}" for k, v in eq.items())
        return _finding(occ, "DST_RISK", f"{label}({b.tz})를 현지 고정 시각으로 썼습니다 — 계절에 따라 {seasons}",
                        f"{b.tz} 시간대로 변환해 {fmt_time(expected)}과 비교하세요.", boundary=b,
                        expected=fmt_time(expected), reviewed=True)
    return _finding(occ, "MISMATCH", f"주석 {label}의 현행 값은 {fmt_time(expected)}인데 코드 값은 {fmt_time(occ.time)}입니다",
                    f"기준표가 바뀌었다면 값을 {fmt_time(expected)}으로 수정하고, 의미가 다르면 주석을 고치세요.",
                    boundary=b, expected=fmt_time(expected), reviewed=True)


def classify(occ: Occurrence, cal: Calendar) -> Finding | None:
    """거래시간과 무관한 표현이면 None을 돌려준다."""
    picked = _pick_annotation(occ, cal)
    if picked:
        return _classify_annotated(occ, cal, *picked)

    market_hits = keyword_hits(cal.context_keywords, occ)
    if not market_hits:
        return None

    t = occ.time
    local = cal.local_tz
    # requires_keyword 기준(예: 수능일 10:00)은 그 기준의 단어가 문맥에 있을 때만 후보로 본다.
    same_value = [b for b in cal.active if b.time == t]
    active = [b for b in same_value
              if (b.tz == local and not b.requires_keyword) or keyword_hits(b.keywords, occ)]
    keyword_only = [b for b in same_value if b.tz == local and b.requires_keyword and b not in active]
    retired = [b for b in cal.retired if b.time == t]
    foreign_local: list[tuple[Boundary, str]] = [
        (b, season) for b in cal.active if b.tz != local and keyword_hits(b.keywords, occ)
        for season, value in cal.local_equivalents(b).items() if value == t
    ]
    scored_active = sorted(((b, keyword_hits(b.keywords, occ)) for b in active), key=lambda x: -len(x[1]))
    scored_retired = sorted(((b, keyword_hits(b.keywords, occ)) for b in retired), key=lambda x: -len(x[1]))
    best_a = len(scored_active[0][1]) if scored_active else 0
    best_r = len(scored_retired[0][1]) if scored_retired else 0

    if foreign_local and best_a == 0:
        b, season = foreign_local[0]
        eq = cal.local_equivalents(b)
        seasons = ", ".join(f"{k} {fmt_time(v)}" for k, v in eq.items())
        hits = keyword_hits(b.keywords, occ)
        seasonal = bool(SEASONAL_TOKENS & occ.tokens) or any(k in occ.context for k in SEASONAL_KO)
        if seasonal:
            return _finding(occ, "MATCH", f"{b.meaning}의 계절별 현지 고정값({season}) — 전환일 판정은 경계 테스트로 확인",
                            boundary=b, expected=fmt_time(eq[season]), evidence=hits)
        return _finding(
            occ, "DST_RISK",
            f"{b.meaning}({fmt_time(b.time)} {b.tz})을 한국시각 고정값 {fmt_time(t)}({season})로 썼습니다. "
            f"현지 시각은 계절마다 다릅니다: {seasons}",
            f"{b.tz} 기준 {fmt_time(b.time)}과 비교하도록 바꾸고 `mhg: {b.id}` 주석을 다세요.",
            boundary=b, expected=f"{fmt_time(b.time)} {b.tz}", evidence=hits,
        )

    if best_r > 0 and best_r > best_a:
        r, hits = scored_retired[0]
        new = cal.get(r.replaced_by or "")
        since = f", {r.retired_on} 변경" if r.retired_on else ""
        new_desc = f"{fmt_time(new.time)}({new.id})" if new else "(대체 기준 없음)"
        return _finding(
            occ, "STALE",
            f"{r.meaning} — 과거 값 {fmt_time(r.time)}이 {new_desc}로 바뀌었습니다{since}",
            f"이 값이 그 의미라면 {new_desc}로 바꾸고 `mhg: {new.id if new else '?'}` 주석을 다세요. "
            "의미가 다르면 해당 기준 ID로 주석을 다세요.",
            boundary=r, expected=fmt_time(new.time) if new else None, evidence=hits,
        )
    if best_a > 0 and best_a == best_r:
        a, r = scored_active[0][0], scored_retired[0][0]
        return _finding(occ, "AMBIGUOUS",
                        f"{fmt_time(t)}은 현행 {a.label}({a.meaning})과 폐기된 {r.label}({r.meaning})에 같은 수준으로 해당합니다",
                        f"코드 의미를 확인해 `mhg: {a.id}` 또는 대체 기준으로 수정하세요.",
                        evidence=scored_active[0][1] + scored_retired[0][1])
    if best_a > 0:
        a, hits = scored_active[0]
        return _finding(occ, "MATCH", f"{a.meaning}", boundary=a, expected=fmt_time(a.time), evidence=hits)
    if retired:
        r = retired[0]
        current = ", ".join(f"{b.label}({b.meaning})" for b in active) or "없음"
        return _finding(occ, "AMBIGUOUS",
                        f"{fmt_time(t)}은 폐기된 {r.label}({r.meaning})과 같은 값이지만 문맥 근거가 없습니다. 같은 값의 현행 기준: {current}",
                        "코드가 어떤 기준을 뜻하는지 확인해 `mhg: <ID>` 주석을 달고, 폐기된 의미라면 값을 바꾸세요.",
                        evidence=market_hits)
    if active:
        a = active[0]
        note = "" if len(active) == 1 else f" (같은 값의 기준 {len(active)}개: {', '.join(b.id for b in active)})"
        return _finding(occ, "MATCH", f"{a.meaning} — 의미 키워드 없음{note}",
                        "의미를 고정하려면 `mhg: <ID>` 주석을 다세요.", boundary=a, expected=fmt_time(a.time),
                        evidence=market_hits)
    if keyword_only:
        b = keyword_only[0]
        return _finding(occ, "UNMAPPED",
                        f"{b.label}({b.meaning})과 값은 같지만 그 문맥({', '.join(b.keywords[:3])})이 없어 기준값으로 보지 않았습니다",
                        f"그 기준이 맞다면 `mhg: {b.id}` 주석을 달고, 다른 시장·업무의 시각이면 `mhg: ignore`로 표시하세요.",
                        evidence=market_hits)
    return _finding(occ, "UNMAPPED", f"거래시간 문맥({', '.join(market_hits[:4])})이지만 기준표에 없는 시각입니다",
                    "다른 기준에서 파생된 값이면 `mhg: <ID>+5m`처럼, 무관하면 `mhg: ignore`로 표시하세요. "
                    "기준표에 빠진 기준이면 출처와 함께 추가 승인을 받으세요.",
                    evidence=market_hits)
