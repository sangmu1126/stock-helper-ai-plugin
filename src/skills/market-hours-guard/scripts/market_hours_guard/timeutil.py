"""시각 파싱과 시간대 변환 (표준 라이브러리만 사용)."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, time, timedelta, timezone, tzinfo

_HHMM = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)(?::([0-5]\d))?$")


def parse_time(text: str) -> time:
    """'HH:MM' 또는 'HH:MM:SS'를 time으로 바꾼다."""
    match = _HHMM.match(str(text).strip())
    if not match:
        raise ValueError(f"시각 형식이 아닙니다: {text!r} (HH:MM 또는 HH:MM:SS)")
    return time(int(match.group(1)), int(match.group(2)), int(match.group(3) or 0))


def fmt_time(value: time) -> str:
    return value.strftime("%H:%M:%S" if value.second else "%H:%M")


def shift(value: time, minutes: int) -> time:
    """하루 안에서 분 단위로 이동한다 (자정을 넘으면 순환)."""
    moved = datetime.combine(date(2000, 1, 3), value) + timedelta(minutes=minutes)
    return moved.time()


def _nth_sunday(year: int, month: int, n: int) -> date:
    first = date(year, month, 1)
    first_sunday = first + timedelta(days=(6 - first.weekday()) % 7)
    return first_sunday + timedelta(weeks=n - 1)


class _USEastern(tzinfo):
    """tzdata가 없을 때만 쓰는 미국 동부 시간 (2007년 이후 서머타임 규칙)."""

    def _is_dst(self, dt: datetime | None) -> bool:
        if dt is None:
            return False
        start = datetime.combine(_nth_sunday(dt.year, 3, 2), time(2))
        end = datetime.combine(_nth_sunday(dt.year, 11, 1), time(2))
        return start <= dt.replace(tzinfo=None) < end

    def utcoffset(self, dt: datetime | None) -> timedelta:
        return timedelta(hours=-4) if self._is_dst(dt) else timedelta(hours=-5)

    def dst(self, dt: datetime | None) -> timedelta:
        return timedelta(hours=1) if self._is_dst(dt) else timedelta(0)

    def tzname(self, dt: datetime | None) -> str:
        return "EDT" if self._is_dst(dt) else "EST"


_FALLBACK: dict[str, tzinfo] = {
    "Asia/Seoul": timezone(timedelta(hours=9), "KST"),
    "America/New_York": _USEastern(),
    "UTC": UTC,
}


def get_tz(name: str) -> tzinfo:
    """IANA 시간대를 돌려준다. tzdata가 없으면 주요 시간대만 내장 규칙으로 대체한다."""
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(name)
    except (ImportError, KeyError, ValueError, OSError):  # 시간대 데이터 없음 (예: tzdata 미설치 Windows)
        fallback = _FALLBACK.get(name)
        if fallback is None:
            raise ValueError(f"시간대를 찾을 수 없습니다: {name} (tzdata 설치 필요)") from None
        return fallback


def is_weekday(day: date) -> bool:
    return day.weekday() < 5
