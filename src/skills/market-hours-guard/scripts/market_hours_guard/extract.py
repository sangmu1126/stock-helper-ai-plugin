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
from dataclasses import dataclass, field
from datetime import time
from pathlib import Path

CODE_SUFFIXES = {
    ".py", ".java", ".kt", ".kts", ".scala", ".go", ".js", ".jsx", ".mjs", ".cjs",
    ".ts", ".tsx", ".cs", ".rb", ".swift", ".sql", ".sh",
}
CONFIG_SUFFIXES = {".yaml", ".yml", ".json", ".properties", ".toml", ".ini", ".cfg", ".conf", ".xml", ".env"}
DOC_SUFFIXES = {".md", ".txt", ".html", ".rst"}
# CSV는 API 명세·설정 표(설명 문장, 라벨 붙은 행)일 수도, 시세·체결 기록(시각이 값인 행 수천 개)일 수도 있다.
# 실제 저장소 평가에서 한국투자 API 명세 data.csv의 폐지 안내 3곳을 놓쳐서 검사 대상에 넣었다.
# 기록 데이터의 시각은 규칙이 아니므로 건너뛰되, 건너뛴 수와 파일 이름을 보고서에 남긴다.
DATA_SUFFIXES = {".csv"}
CSV_SERIES_ROWS = 50  # 칸 전체가 시각인 행이 이보다 많으면 시계열 열(기록 데이터)로 본다
CELL_EDGES = ",;\t\"'"
LETTER_RE = re.compile(r"[A-Za-z가-힣]")
SNIPPET_CHARS = 200
SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", ".venv", "venv", "__pycache__", "dist", "build",
    "target", ".gradle", ".idea", ".mypy_cache", ".pytest_cache", ".ruff_cache", "mhg-output",
}
# IDE(Eclipse·VS Code Java·IntelliJ)의 컴파일 결과 폴더. 설정 파일 사본이 들어 있어 중복 판정이 생긴다.
# 스크립트를 두는 bin/도 흔하므로 .class 파일이 있을 때만 건너뛴다.
COMPILED_OUTPUT_DIRS = {"bin", "out"}
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
# 숫자 문자열("153000")은 그 앞에 시각 이름이 있을 때만 시각으로 본다. 종목코드("005930")·필드 번호('1223')·
# 연월('202606')을 시각으로 읽지 않도록, 이름은 단어 단위로 보고 날짜 이름(dt, date ...)이면 뺀다.
COMPACT_HINT_WORDS = frozenset({"time", "hour", "hhmm", "hhmmss", "hms", "tm", "open", "close", "start", "end", "cutoff"})
NAME_BOUNDARY_RE = re.compile(r"[,(\[{;]")
COMPACT_HINT_KO_RE = re.compile(r"시각|시간|마감|개장")
COMPACT_DATE_WORDS = frozenset({"dt", "date", "ymd", "yyyymmdd", "yyyymm", "ym", "day", "month", "year"})
COMPACT_DATE_KO_RE = re.compile(r"일자|날짜|년월|연월")
# API 문서의 코드 목록("0:전체, 1:5미만, 4:10~20, 5:20일전")에 나오는 'N:숫자'는 시각이 아니다.
UNIT_AFTER_RE = re.compile(r"(?:일|주|만|천|원|초|개|년|배|회|억|%|미만|이상|이하|초과|분전|틱|위|호가|건)")
RANGE_TO_NUMBER_RE = re.compile(r"\s*~\s*\d+(?![\d:])")
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
    large_files: list[str] = field(default_factory=list)  # 크기 제한으로 읽지 않은 파일 (보고서에 표시)
    csv_data_values: int = 0  # CSV에서 기록 데이터 값으로 보고 건너뛴 시각 수 (보고서에 표시)
    csv_data_files: list[str] = field(default_factory=list)


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


def _code_list_item(m: re.Match, line: str) -> bool:
    """'N:숫자' 뒤에 단위(일·만·미만…)나 '~숫자'가 오면 코드 목록 항목이다(예: 4:10~20, 2:10미만, 5:20일전).

    '분'은 실제 시각에도 붙으므로("08:45분 경") 자릿수를 맞추지 않았거나(5:15분) 앞뒤 숫자가 같을 때(10:10분)만 코드로 본다.
    """
    rest = line[m.end():]
    if UNIT_AFTER_RE.match(rest) or RANGE_TO_NUMBER_RE.match(rest):
        return True
    start = m.start()
    if start >= 2 and line[start - 1] == "[" and (line[start - 2].isalnum() or line[start - 2] in "_])"):
        return True  # 슬라이스: row[9:21], rf1[11:40]
    hour, minute = m.group(1), m.group(2)
    return rest.startswith("분") and (len(hour) == 1 or hour == minute)


def _compact_named_as_time(prefix: str) -> bool:
    """숫자 문자열 바로 앞의 이름(같은 줄, 쉼표·괄호 뒤)이 시각 이름이고 날짜 이름이 아닌지."""
    near = NAME_BOUNDARY_RE.split(prefix)[-1]
    words = tokenize(near)
    if words & COMPACT_DATE_WORDS or COMPACT_DATE_KO_RE.search(near):
        return False
    return bool(words & COMPACT_HINT_WORDS or COMPACT_HINT_KO_RE.search(near))


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
        if _code_list_item(m, line):
            continue
        add(m.start(), m.end(), "literal", m.group(0), time(int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)))
    for m in COMPACT_RE.finditer(line):
        if not _compact_named_as_time(line[:m.start()]):
            continue
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


def _snippet(line: str, col: int) -> str:
    """긴 줄(CSV 한 행, 한 줄짜리 JSON)은 첫 200자가 아니라 발견 위치 주변을 보여 준다."""
    text = line.strip()
    if len(text) <= SNIPPET_CHARS:
        return text
    center = col - 1 - (len(line) - len(line.lstrip()))
    start = max(0, min(center - SNIPPET_CHARS // 2, len(text) - SNIPPET_CHARS))
    end = start + SNIPPET_CHARS
    return ("…" if start else "") + text[start:end] + ("…" if end < len(text) else "")


def _whole_cell(line: str, col: int, raw: str) -> bool:
    before = line[:col - 1].rstrip(" ")
    after = line[col - 1 + len(raw):].lstrip(" ")
    return (not before or before[-1] in CELL_EDGES) and (not after or after[0] in CELL_EDGES)


def csv_data_values(lines: list[str], per_line: dict[int, list]) -> set[tuple[int, int]]:
    """CSV에서 규칙이 아니라 기록 데이터로 볼 시각의 (줄 번호, 줄 안 순번).

    - 글자 없이 숫자·날짜·시각만 있는 행: `2026-11-18,09:01,71000,...` (분봉·체결 기록)
    - 칸 전체가 시각인 행이 CSV_SERIES_ROWS개를 넘는 파일의 그런 칸: 종목명이 붙은 시세 기록의 시각 열
    설명 문장 속 시각과 라벨이 붙은 작은 표(`KRX,regular,09:00,15:30`)는 그대로 검사한다.
    """
    wordless = {(i, n) for i, hits in per_line.items() if hits and not LETTER_RE.search(lines[i])
                for n in range(len(hits))}
    cells = {(i, n) for i, hits in per_line.items() for n, (col, _, raw, _) in enumerate(hits)
             if _whole_cell(lines[i], col, raw)}
    series = len({i for i, _ in cells}) > CSV_SERIES_ROWS
    return wordless | (cells if series else set())


def extract_file(path: Path, rel: str, stats: FileStats | None = None) -> list[Occurrence]:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    path_words = " ".join(Path(rel).with_suffix("").parts)
    per_line = {i: find_times(line) for i, line in enumerate(lines)}
    is_csv = path.suffix.lower() in DATA_SUFFIXES
    data_values = csv_data_values(lines, per_line) if is_csv else set()
    if data_values and stats is not None:
        stats.csv_data_values += len(data_values)
        stats.csv_data_files.append(rel)
    # CSV는 열 이름(첫 행)이 각 행의 문맥이다: market,session,open,close
    column_names = [lines[0]] if is_csv and lines else []

    occurrences: list[Occurrence] = []
    for i, hits in per_line.items():
        if not hits:
            continue
        line = lines[i]
        annotations = _annotation_items(line)
        if not annotations and i > 0 and not per_line.get(i - 1):
            annotations = _annotation_items(lines[i - 1])
        previous = [lines[j] for j in range(max(0, i - 2), i)]
        context_raw = " ".join([*column_names, *previous, line, *_headers(lines, i), path_words])
        tokens = tokenize(context_raw)
        context = context_raw.lower()
        for n, (col, kind, raw, value) in enumerate(hits):
            if (i, n) in data_values:
                continue
            occurrences.append(Occurrence(
                path=rel, line=i + 1, col=col, kind=kind, raw=raw, time=value,
                snippet=_snippet(line, col), context=context, tokens=tokens,
                annotations=annotations, index_on_line=n, count_on_line=len(hits),
            ))
    return occurrences


def _wanted(name: str, suffixes: set[str]) -> bool:
    if name == ".env" or name.startswith(".env."):
        return ".env" in suffixes
    return Path(name).suffix.lower() in suffixes


def compiled_output_dir(path: Path) -> bool:
    if path.name not in COMPILED_OUTPUT_DIRS:
        return False
    return any(name.endswith(".class") for _, _, files in os.walk(path) for name in files)


def iter_files(root: Path, include_docs: bool = False, exclude: tuple[Path, ...] = ()):
    suffixes = CODE_SUFFIXES | CONFIG_SUFFIXES | DATA_SUFFIXES | (DOC_SUFFIXES if include_docs else set())
    excluded = tuple(p.resolve() for p in exclude)
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        dirnames[:] = sorted(
            d for d in dirnames
            if d not in SKIP_DIRS and (current / d).resolve() not in excluded
            and not compiled_output_dir(current / d)
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
            stats.large_files.append(file.relative_to(root).as_posix())
            continue
        with file.open(encoding="utf-8", errors="replace") as handle:
            head = "".join(handle.readline() for _ in range(5))
        if GENERATED_MARKER in head:
            stats.skipped_generated += 1
            continue
        stats.files_scanned += 1
        occurrences.extend(extract_file(file, file.relative_to(root).as_posix(), stats))
    return occurrences, stats
