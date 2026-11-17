"""승인된 거래시간 기준표(TOML) 모델과 검증.

기준표는 사람이 승인한 '정답'이다. 이 모듈은 값을 추측하거나 만들어내지 않고,
형식·출처·참조 관계만 검증한다.
"""

from __future__ import annotations

import hashlib
import itertools
import tomllib
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

from .timeutil import fmt_time, get_tz, is_weekday, parse_time

# 거래시간 문맥을 판단하는 기본 어휘. 기준표 [scan].context_keywords와 각 경계의 keywords가 더해진다.
DEFAULT_CONTEXT_KEYWORDS: tuple[str, ...] = (
    "market", "session", "trading", "trade", "order", "sor", "krx", "nxt", "kospi", "kosdaq",
    "nyse", "nasdaq", "us", "usa", "auction", "premarket", "aftermarket", "regular", "cutoff",
    "halt", "settlement",
    "거래", "주문", "체결", "호가", "정규장", "시간외", "프리마켓", "애프터마켓", "동시호가",
    "마감", "개장", "장전", "장후", "미국", "해외", "정산",
)


class CalendarError(ValueError):
    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("기준표 오류:\n" + "\n".join(f"- {p}" for p in problems))


@dataclass(frozen=True)
class Boundary:
    """의미가 붙은 하나의 경계 시각. retired=True면 더 이상 쓰면 안 되는 과거 값이다."""

    id: str
    time: time
    tz: str
    market: str
    meaning: str
    keywords: tuple[str, ...]
    source: str
    retired: bool = False
    replaced_by: str | None = None
    retired_on: date | None = None
    effective_from: date | None = None
    # 특수일 값처럼 흔한 시각과 겹치는 기준: 문맥에 이 기준의 키워드가 있을 때만 MATCH로 본다.
    requires_keyword: bool = False

    @property
    def label(self) -> str:
        return f"{self.id} {fmt_time(self.time)}"


@dataclass(frozen=True)
class Window:
    start: time
    end: time
    expect: Any
    source: str
    effective_from: date | None = None
    effective_to: date | None = None
    dates: tuple[date, ...] = ()          # 이 날짜에만 적용 (특수일 일정)
    exclude_dates: tuple[date, ...] = ()  # 이 날짜에는 적용 안 함 (특수일에 바뀌는 평소 일정)

    def applies(self, day: date) -> bool:
        started = self.effective_from is None or day >= self.effective_from
        not_ended = self.effective_to is None or day <= self.effective_to
        listed = not self.dates or day in self.dates
        return started and not_ended and listed and day not in self.exclude_dates


@dataclass(frozen=True)
class SpecialDay:
    """거래소가 거래시간을 바꾼 날(예: 수능일). confirmed_until 이후는 공지가 없어 경계 테스트에서 뺀다."""

    date: date
    name: str
    source: str
    confirmed_until: time | None = None


@dataclass(frozen=True)
class HolidayCalendar:
    """거래소가 공지한 휴장일. confirmed_through 이후 날짜는 휴장 여부를 알 수 없다."""

    market: str
    source: str
    confirmed_through: date
    days: dict[date, str]


@dataclass(frozen=True)
class Probe:
    """경계 테스트 대상 동작. 시각을 넣으면 기대값(expect)이 나와야 한다."""

    id: str
    description: str
    tz: str
    default: Any
    windows: tuple[Window, ...]
    sample_dates: tuple[date, ...]
    market: str | None = None  # 휴장일 달력을 적용할 시장 (없으면 휴장일을 보지 않음)


@dataclass(frozen=True)
class Calendar:
    path: Path
    name: str
    local_tz: str
    basis_date: date | None
    boundaries: tuple[Boundary, ...]
    probes: tuple[Probe, ...]
    context_keywords: tuple[str, ...]
    sources: dict[str, str]
    digest: str
    special_days: tuple[SpecialDay, ...] = ()
    holidays: dict[str, HolidayCalendar] | None = None

    def special_day(self, day: date) -> SpecialDay | None:
        return next((s for s in self.special_days if s.date == day), None)

    def holiday(self, market: str | None, day: date) -> str | None:
        """그 시장의 휴장일이면 이름, 아니면 None."""
        calendar = (self.holidays or {}).get(market or "")
        return calendar.days.get(day) if calendar else None

    @property
    def active(self) -> tuple[Boundary, ...]:
        return tuple(b for b in self.boundaries if not b.retired)

    @property
    def retired(self) -> tuple[Boundary, ...]:
        return tuple(b for b in self.boundaries if b.retired)

    def get(self, boundary_id: str) -> Boundary | None:
        for boundary in self.boundaries:
            if boundary.id == boundary_id:
                return boundary
        return None

    def local_equivalents(self, boundary: Boundary) -> dict[str, time]:
        """외국 시간대 경계를 기준 연도의 겨울·여름 날짜로 현지(한국) 시각에 환산한다.

        예: 미국 정규장 09:30 America/New_York → {"EST": 23:30, "EDT": 22:30}
        """
        if boundary.tz == self.local_tz:
            return {self.local_tz: boundary.time}
        year = (self.basis_date or datetime.now().astimezone().date()).year
        source_tz, local_tz = get_tz(boundary.tz), get_tz(self.local_tz)
        result: dict[str, time] = {}
        for ref in (date(year, 1, 15), date(year, 7, 15)):
            src = datetime.combine(ref, boundary.time, tzinfo=source_tz)
            result[src.tzname() or ref.isoformat()] = src.astimezone(local_tz).time()
        return result


def _as_date(value: Any, where: str, problems: list[str]) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        problems.append(f"{where}: 날짜 형식이 아닙니다 ({value!r})")
        return None


def _date_list(values: Any, where: str, problems: list[str]) -> tuple[date, ...]:
    if values is None:
        return ()
    if not isinstance(values, list):
        problems.append(f"{where}: 날짜 목록이어야 합니다")
        return ()
    return tuple(d for d in (_as_date(v, where, problems) for v in values) if d is not None)


def _as_time(value: Any, where: str, problems: list[str]) -> time | None:
    if isinstance(value, time):
        return value.replace(tzinfo=None)
    try:
        return parse_time(str(value))
    except ValueError as exc:
        problems.append(f"{where}: {exc}")
        return None


def _check_tz(name: str, where: str, problems: list[str]) -> None:
    try:
        get_tz(name)
    except ValueError as exc:
        problems.append(f"{where}: {exc}")


def _check_source(item: dict, where: str, sources: dict[str, str], problems: list[str]) -> str:
    source = str(item.get("source", "")).strip()
    if not source:
        problems.append(f"{where}: source가 없습니다 (모든 값은 출처를 가져야 합니다)")
    elif source not in sources:
        problems.append(f"{where}: source '{source}'가 [sources]에 없습니다")
    return source


def _boundary(item: dict, retired: bool, local_tz: str, sources: dict[str, str],
              where: str, problems: list[str]) -> Boundary | None:
    before = len(problems)
    boundary_id = str(item.get("id", "")).strip()
    if not boundary_id or not boundary_id.replace("_", "").isalnum() or boundary_id[0].isdigit():
        problems.append(f"{where}: id는 영문·숫자·밑줄로 된 식별자여야 합니다 ({boundary_id!r})")
    at = _as_time(item.get("time"), f"{where}.time", problems)
    tz = str(item.get("tz", local_tz))
    _check_tz(tz, f"{where}.tz", problems)
    meaning = str(item.get("meaning", "")).strip()
    if not meaning:
        problems.append(f"{where}: meaning(의미 설명)이 없습니다")
    keywords = item.get("keywords")
    if not isinstance(keywords, list) or not keywords or not all(isinstance(k, str) and k.strip() for k in keywords):
        problems.append(f"{where}: keywords는 비어 있지 않은 문자열 목록이어야 합니다")
        keywords = []
    source = _check_source(item, where, sources, problems)
    replaced_by = item.get("replaced_by")
    if retired and not replaced_by:
        problems.append(f"{where}: retired 항목에는 replaced_by가 필요합니다")
    if len(problems) > before or at is None:
        return None
    return Boundary(
        id=boundary_id,
        time=at,
        tz=tz,
        market=str(item.get("market", "")),
        meaning=meaning,
        keywords=tuple(k.strip().lower() for k in keywords),
        source=source,
        retired=retired,
        replaced_by=str(replaced_by) if replaced_by else None,
        retired_on=_as_date(item.get("retired_on"), f"{where}.retired_on", problems),
        effective_from=_as_date(item.get("effective_from"), f"{where}.effective_from", problems),
        requires_keyword=bool(item.get("requires_keyword", False)),
    )


def _probe(item: dict, local_tz: str, sources: dict[str, str], where: str,
           problems: list[str]) -> Probe | None:
    before = len(problems)
    probe_id = str(item.get("id", "")).strip()
    if not probe_id:
        problems.append(f"{where}: id가 없습니다")
    tz = str(item.get("tz", local_tz))
    _check_tz(tz, f"{where}.tz", problems)
    if "default" not in item:
        problems.append(f"{where}: default(어느 구간에도 속하지 않을 때의 기대값)가 없습니다")
    windows: list[Window] = []
    raw_windows = item.get("window", [])
    if not raw_windows:
        problems.append(f"{where}: [[probe.window]]가 하나 이상 필요합니다")
    for i, raw in enumerate(raw_windows):
        w_where = f"{where}.window[{i}]"
        start = _as_time(raw.get("start"), f"{w_where}.start", problems)
        end = _as_time(raw.get("end"), f"{w_where}.end", problems)
        if "expect" not in raw:
            problems.append(f"{w_where}: expect가 없습니다")
        source = _check_source(raw, w_where, sources, problems)
        if start and end and not start < end:
            problems.append(f"{w_where}: start < end여야 합니다 (자정을 넘는 구간은 시간대를 바꿔 표현)")
        if start and end:
            windows.append(Window(
                start=start, end=end, expect=raw.get("expect"), source=source,
                effective_from=_as_date(raw.get("effective_from"), f"{w_where}.effective_from", problems),
                effective_to=_as_date(raw.get("effective_to"), f"{w_where}.effective_to", problems),
                dates=_date_list(raw.get("dates"), f"{w_where}.dates", problems),
                exclude_dates=_date_list(raw.get("exclude_dates"), f"{w_where}.exclude_dates", problems),
            ))
    sample_dates = [
        d for d in (_as_date(v, f"{where}.sample_dates", problems) for v in item.get("sample_dates", []))
        if d is not None
    ]
    if not sample_dates:
        problems.append(f"{where}: sample_dates(테스트할 거래일)가 필요합니다")
    for day in sample_dates:
        if not is_weekday(day):
            problems.append(f"{where}: {day}는 주말입니다 (거래일을 지정하세요)")
        active = sorted((w for w in windows if w.applies(day)), key=lambda w: w.start)
        for left, right in itertools.pairwise(active):
            if right.start < left.end:
                problems.append(f"{where}: {day}에 구간이 겹칩니다 ({fmt_time(left.start)}~{fmt_time(left.end)}, "
                                f"{fmt_time(right.start)}~{fmt_time(right.end)})")
    if len(problems) > before:
        return None
    return Probe(
        id=probe_id,
        description=str(item.get("description", "")),
        tz=tz,
        default=item.get("default"),
        windows=tuple(windows),
        sample_dates=tuple(sample_dates),
        market=str(item["market"]) if item.get("market") else None,
    )


def _holidays(data: dict, sources: dict[str, str], problems: list[str]) -> dict[str, HolidayCalendar]:
    result: dict[str, HolidayCalendar] = {}
    raw_all = data.get("holidays", {})
    if not isinstance(raw_all, dict):
        problems.append("[holidays.<시장>] 형식이어야 합니다")
        return result
    for market, raw in raw_all.items():
        where = f"holidays.{market}"
        source = _check_source(raw, where, sources, problems)
        through = _as_date(raw.get("confirmed_through"), f"{where}.confirmed_through", problems)
        if through is None:
            problems.append(f"{where}: confirmed_through(달력을 확인한 마지막 날짜)가 필요합니다")
        days: dict[date, str] = {}
        for key, name in (raw.get("days") or {}).items():
            day = _as_date(key, f"{where}.days", problems)
            if day is None:
                continue
            if not is_weekday(day):
                problems.append(f"{where}.days: {day}는 주말입니다 (주말은 적지 않습니다)")
            if through and day > through:
                problems.append(f"{where}.days: {day}가 confirmed_through({through}) 뒤입니다")
            days[day] = str(name)
        if through:
            result[str(market)] = HolidayCalendar(market=str(market), source=source, confirmed_through=through, days=days)
    return result


def load_calendar(path: str | Path) -> Calendar:
    path = Path(path)
    raw_bytes = path.read_bytes()
    try:
        data = tomllib.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise CalendarError([f"TOML을 읽을 수 없습니다: {exc}"]) from exc

    problems: list[str] = []
    meta = data.get("meta", {})
    local_tz = str(meta.get("local_tz", "Asia/Seoul"))
    _check_tz(local_tz, "meta.local_tz", problems)
    sources = {str(k): str(v) for k, v in data.get("sources", {}).items()}

    boundaries: list[Boundary] = []
    for table, retired in (("boundary", False), ("retired", True)):
        for i, item in enumerate(data.get(table, [])):
            boundary = _boundary(item, retired, local_tz, sources, f"{table}[{i}]", problems)
            if boundary:
                boundaries.append(boundary)
    if not any(not b.retired for b in boundaries):
        problems.append("[[boundary]]가 하나 이상 필요합니다")

    seen: set[str] = set()
    for boundary in boundaries:
        if boundary.id in seen:
            problems.append(f"id 중복: {boundary.id}")
        seen.add(boundary.id)
    active_ids = {b.id for b in boundaries if not b.retired}
    for boundary in boundaries:
        if boundary.retired and boundary.replaced_by not in active_ids:
            problems.append(f"{boundary.id}: replaced_by '{boundary.replaced_by}'가 현행 [[boundary]]에 없습니다")

    probes = [
        p for p in (_probe(item, local_tz, sources, f"probe[{i}]", problems)
                    for i, item in enumerate(data.get("probe", [])))
        if p is not None
    ]
    probe_ids = [p.id for p in probes]
    for dup in {i for i in probe_ids if probe_ids.count(i) > 1}:
        problems.append(f"probe id 중복: {dup}")

    special_days: list[SpecialDay] = []
    for i, raw in enumerate(data.get("special_day", [])):
        where = f"special_day[{i}]"
        day = _as_date(raw.get("date"), f"{where}.date", problems)
        source = _check_source(raw, where, sources, problems)
        until = _as_time(raw["confirmed_until"], f"{where}.confirmed_until", problems) if raw.get("confirmed_until") else None
        if not str(raw.get("name", "")).strip():
            problems.append(f"{where}: name이 없습니다")
        if day:
            special_days.append(SpecialDay(date=day, name=str(raw.get("name", "")), source=source, confirmed_until=until))

    holidays = _holidays(data, sources, problems)
    for probe in probes:
        calendar = holidays.get(probe.market or "")
        if calendar is None:
            continue  # 휴장일 달력이 없는 시장은 주말만 본다
        for day in probe.sample_dates:
            if day > calendar.confirmed_through:
                problems.append(f"probe {probe.id}: {day}는 {probe.market} 휴장일 달력 확인 범위"
                                f"({calendar.confirmed_through}) 밖이라 기대값을 정할 수 없습니다")
            elif day in calendar.days and any(day in w.dates for w in probe.windows):
                problems.append(f"probe {probe.id}: {day}는 휴장일({calendar.days[day]})인데 그날 전용 구간이 있습니다")

    scan = data.get("scan", {})
    extra = scan.get("context_keywords", [])
    if not isinstance(extra, list) or not all(isinstance(k, str) for k in extra):
        problems.append("scan.context_keywords는 문자열 목록이어야 합니다")
        extra = []

    if problems:
        raise CalendarError(problems)

    return Calendar(
        path=path,
        name=str(meta.get("name", path.stem)),
        local_tz=local_tz,
        basis_date=_as_date(meta.get("basis_date"), "meta.basis_date", []),
        boundaries=tuple(boundaries),
        probes=tuple(probes),
        context_keywords=tuple(dict.fromkeys(
            [*DEFAULT_CONTEXT_KEYWORDS, *(k.lower() for k in extra),
             *(k for b in boundaries for k in b.keywords)]
        )),
        sources=sources,
        digest="sha256:" + hashlib.sha256(raw_bytes).hexdigest()[:16],
        special_days=tuple(special_days),
        holidays=holidays,
    )
