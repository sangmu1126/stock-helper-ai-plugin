"""저장소에서 시각 표현과 그 문맥을 추출한다 (정적 텍스트 분석).

찾는 형태:
  literal       "15:30", '09:00:00', 주석·문자열 속 16:00~20:00
  call          time(15, 30), datetime.time(hour=9, minute=0), LocalTime.of(20, 0)
  cron          "35 15 * * 1-5", "0 35 15 * * MON-FRI"
  compact       "153000", "0900" (같은 줄에 시각 관련 이름이 있을 때만)
  hour_compare  now.hour >= 16, getHour() < 20
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import time
from pathlib import Path

CODE_SUFFIXES = {
    ".py", ".java", ".kt", ".kts", ".scala", ".go", ".js", ".jsx", ".mjs", ".cjs",
    ".ts", ".tsx", ".cs", ".rb", ".swift", ".sql", ".sh",
}
CONFIG_SUFFIXES = {".yaml", ".yml", ".json", ".properties", ".toml", ".ini", ".cfg", ".conf", ".xml", ".env"}
DOC_SUFFIXES = {".md", ".txt", ".html", ".rst"}
SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", ".venv", "venv", "__pycache__", "dist", "build",
    "target", ".gradle", ".idea", ".mypy_cache", ".pytest_cache", ".ruff_cache", "mhg-output",
}
GENERATED_MARKER = "mhg:generated"
MAX_BYTES = 1_000_000

LITERAL_RE = re.compile(r"(?<![A-Za-z0-9_:.])([01]?\d|2[0-3]):([0-5]\d)(?::([0-5]\d))?(?![\d:])")
# 특정 시점을 가리키는 타임스탬프(규칙이 아님)는 통째로 제외한다: 2026-11-18T15:30:00+09:00
TIMESTAMP_RE = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?")
CALL_RE = re.compile(
    r"\b(?:LocalTime\.of|(?:datetime\.|dt\.)?time|dtime)\(\s*(?:hour\s*=\s*)?(\d{1,2})\s*,"
    r"\s*(?:minute\s*=\s*)?(\d{1,2})(?:\s*,\s*(?:second\s*=\s*)?(\d{1,2}))?\s*[,)]"
)
COMPACT_RE = re.compile(r"""(["'])(\d{4}|\d{6})\1""")
COMPACT_HINT_RE = re.compile(r"time|hhmm|hms|open|close|start|end|cutoff|시각|시간|마감|개장", re.IGNORECASE)
CRON_RE = re.compile(r"""(["'])\s*((?:[^\s"']+\s+){4,6}[^\s"']+)\s*\1""")
CRON_FIELD_RE = re.compile(r"^[\d*/,\-?LW#A-Za-z]+$")
NUM_LIST_RE = re.compile(r"^\d{1,2}(?:,\d{1,2})*$")
HOUR_CMP_RE = re.compile(r"\b(?:hour|hours|getHour\(\)|get_hour\(\))\s*(?:>=|<=|==|<|>)\s*(\d{1,2})\b")
ANNOTATION_RE = re.compile(r"mhg:\s*([^\n]*)")

SCOPE_RE = re.compile(r"^\s*(?:export\s+)?(?:async\s+)?(?:def|class|fun|function|func)\s+([A-Za-z_]\w*)")
JAVA_METHOD_RE = re.compile(r"^\s*(?:public|private|protected)\b[^=;]*?\b([A-Za-z_]\w*)\s*\(")
YAML_KEY_RE = re.compile(r"""^\s*-?\s*["']?([\w.\-가-힣]+)["']?\s*:\s*(?:[{\[]\s*)?(?:#.*)?$""")

_CAMEL_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_WORD_RE = re.compile(r"[A-Za-z]+|[가-힣]+")


def tokenize(text: str) -> frozenset[str]:
    """식별자를 소문자 단어로 쪼갠다. US_OPEN_KST → us, open, kst / isUsOpen → is, us, open."""
    return frozenset(w.lower() for w in _WORD_RE.findall(_CAMEL_RE.sub(" ", text)))


@dataclass(frozen=True)
class Occurrence:
    path: str
    line: int
    col: int
    kind: str
    raw: str
    time: time
    snippet: str
    context: str
    tokens: frozenset[str]
    annotations: tuple[str, ...]
    index_on_line: int
    count_on_line: int


@dataclass
class FileStats:
    files_scanned: int = 0
    skipped_large: int = 0
    skipped_generated: int = 0


def _valid(h: int, m: int, s: int = 0) -> bool:
    return 0 <= h <= 23 and 0 <= m <= 59 and 0 <= s <= 59


def _cron_times(expr: str) -> list[time]:
    fields = expr.split()
    if not 5 <= len(fields) <= 7 or not all(CRON_FIELD_RE.match(f) for f in fields):
        return []
    minute, hour, rest = (fields[0], fields[1], fields[2:]) if len(fields) == 5 else (fields[1], fields[2], fields[3:])
    if not any("*" in f or "?" in f for f in rest):
        return []
    if not (NUM_LIST_RE.match(minute) and NUM_LIST_RE.match(hour)):
        return []
    return [time(int(h), int(m)) for h in hour.split(",") for m in minute.split(",") if _valid(int(h), int(m))]


def find_times(line: str) -> list[tuple[int, str, str, time]]:
    """한 줄에서 (열, 종류, 원문, 시각) 목록을 찾는다. 같은 위치를 두 번 세지 않는다."""
    found: list[tuple[int, str, str, time]] = []
    taken: list[tuple[int, int]] = []

    def add(start: int, end: int, kind: str, raw: str, value: time) -> None:
        if any(start < e and s < end for s, e in taken):
            return
        taken.append((start, end))
        found.append((start + 1, kind, raw, value))

    taken.extend((m.start(), m.end()) for m in TIMESTAMP_RE.finditer(line))
    for m in CRON_RE.finditer(line):
        for value in _cron_times(m.group(2)):
            add(m.start(2), m.end(2), "cron", m.group(2), value)
    for m in CALL_RE.finditer(line):
        h, mi, s = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
        if _valid(h, mi, s):
            add(m.start(), m.end(), "call", m.group(0).rstrip(",) "), time(h, mi, s))
    for m in LITERAL_RE.finditer(line):
        add(m.start(), m.end(), "literal", m.group(0), time(int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)))
    if COMPACT_HINT_RE.search(line):
        for m in COMPACT_RE.finditer(line):
            digits = m.group(2)
            h, mi, s = int(digits[:2]), int(digits[2:4]), int(digits[4:6] or 0)
            if _valid(h, mi, s):
                add(m.start(2), m.end(2), "compact", digits, time(h, mi, s))
    for m in HOUR_CMP_RE.finditer(line):
        h = int(m.group(1))
        if _valid(h, 0):
            add(m.start(), m.end(), "hour_compare", m.group(0), time(h, 0))
    found.sort(key=lambda item: item[0])
    return found


def _annotation_items(line: str) -> tuple[str, ...]:
    match = ANNOTATION_RE.search(line)
    if not match or match.group(1).strip().startswith("generated"):
        return ()
    body = re.split(r"\*/|-->|\s#\s", match.group(1))[0]
    return tuple(item.strip() for item in body.split(",") if item.strip())


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" \t"))


def _headers(lines: list[str], idx: int, limit: int = 3, lookback: int = 80) -> list[str]:
    """현재 줄을 감싸는 함수·클래스 이름이나 YAML/JSON 상위 키를 들여쓰기 기준으로 모은다."""
    names: list[str] = []
    current = _indent(lines[idx])
    for j in range(idx - 1, max(-1, idx - lookback), -1):
        text = lines[j]
        if not text.strip():
            continue
        level = _indent(text)
        if level >= current:
            continue
        match = SCOPE_RE.match(text) or JAVA_METHOD_RE.match(text) or YAML_KEY_RE.match(text)
        if match:
            names.append(match.group(1))
            current = level
            if len(names) >= limit or level == 0:
                break
    return names


def extract_file(path: Path, rel: str) -> list[Occurrence]:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    path_words = " ".join(Path(rel).with_suffix("").parts)
    per_line = {i: find_times(line) for i, line in enumerate(lines)}

    occurrences: list[Occurrence] = []
    for i, hits in per_line.items():
        if not hits:
            continue
        line = lines[i]
        annotations = _annotation_items(line)
        if not annotations and i > 0 and not per_line.get(i - 1):
            annotations = _annotation_items(lines[i - 1])
        previous = [lines[j] for j in range(max(0, i - 2), i)]
        context_raw = " ".join([*previous, line, *_headers(lines, i), path_words])
        tokens = tokenize(context_raw)
        context = context_raw.lower()
        for n, (col, kind, raw, value) in enumerate(hits):
            occurrences.append(Occurrence(
                path=rel, line=i + 1, col=col, kind=kind, raw=raw, time=value,
                snippet=line.strip()[:200], context=context, tokens=tokens,
                annotations=annotations, index_on_line=n, count_on_line=len(hits),
            ))
    return occurrences


def _wanted(name: str, suffixes: set[str]) -> bool:
    if name == ".env" or name.startswith(".env."):
        return ".env" in suffixes
    return Path(name).suffix.lower() in suffixes


def iter_files(root: Path, include_docs: bool = False, exclude: tuple[Path, ...] = ()):
    suffixes = CODE_SUFFIXES | CONFIG_SUFFIXES | (DOC_SUFFIXES if include_docs else set())
    excluded = tuple(p.resolve() for p in exclude)
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        dirnames[:] = sorted(
            d for d in dirnames
            if d not in SKIP_DIRS and (current / d).resolve() not in excluded
        )
        for name in sorted(filenames):
            if _wanted(name, suffixes):
                yield current / name


def extract_repo(root: Path, include_docs: bool = False,
                 exclude: tuple[Path, ...] = ()) -> tuple[list[Occurrence], FileStats]:
    stats = FileStats()
    occurrences: list[Occurrence] = []
    for file in iter_files(root, include_docs, exclude):
        if file.stat().st_size > MAX_BYTES:
            stats.skipped_large += 1
            continue
        with file.open(encoding="utf-8", errors="replace") as handle:
            head = "".join(handle.readline() for _ in range(5))
        if GENERATED_MARKER in head:
            stats.skipped_generated += 1
            continue
        stats.files_scanned += 1
        occurrences.extend(extract_file(file, file.relative_to(root).as_posix()))
    return occurrences, stats
