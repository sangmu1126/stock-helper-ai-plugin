"""스캔 결과를 사람이 읽는 Markdown 보고서로 만든다."""

from __future__ import annotations

from .classify import STATUS_LABEL, STATUS_ORDER, Finding
from .scan import ScanResult


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _detail(n: int, f: Finding) -> list[str]:
    lines = [
        f"### {n}. {f.status} · `{f.path}:{f.line}`",
        "",
        f"```text\n{f.snippet}\n```",
        "",
        f"- 발견 값: `{f.found}` ({f.kind})",
        f"- 판단: {f.reason}",
    ]
    if f.expected:
        lines.append(f"- 기준값: `{f.expected}`" + (f" ({f.boundary})" if f.boundary else ""))
    if f.evidence:
        lines.append(f"- 문맥 근거: {', '.join(f.evidence[:6])}")
    if f.action:
        lines.append(f"- 조치: {f.action}")
    lines.append("")
    return lines


def _shown(files: list[str]) -> str:
    return ", ".join(f"`{p}`" for p in files[:5]) + (f" 외 {len(files) - 5}개" if len(files) > 5 else "")


def _skipped_line(result: ScanResult) -> list[str]:
    stats = result.stats
    out = []
    if stats.large_files:
        out.append(f"- **검사하지 않은 파일 {len(stats.large_files)}개** (1MB 초과): {_shown(stats.large_files)}"
                   " — 직접 확인하거나 나눠서 검사하세요")
    if stats.csv_data_values:
        out.append(f"- **CSV 기록 데이터로 보고 건너뛴 시각 {stats.csv_data_values}개** "
                   f"(파일 {len(stats.csv_data_files)}개: {_shown(stats.csv_data_files)}) — "
                   "숫자·시각만 있는 행과 시계열 시각 열입니다. 거래시간 규칙 표라면 직접 확인하세요")
    return out


def render_markdown(result: ScanResult) -> str:
    cal = result.calendar
    counts = result.counts()
    out = [
        "# 거래시간 변경 점검 결과",
        "",
        f"- 대상 저장소: `{result.repo.name}` · 검사 시각 {result.scanned_at}",
        (f"- 기준표: {cal.name} (`{cal.path.name}`, {cal.digest}"
         + (f", 기준일 {cal.basis_date}" if cal.basis_date else "") + ")"),
        (f"- 검사 파일 {result.stats.files_scanned}개 · 시각 표현 {result.occurrences}개 · "
         f"거래시간 문맥 {len(result.findings)}개 · 무관 {result.non_market}개 제외"),
        *_skipped_line(result),
        "",
        "| 상태 | 건수 | 의미 |",
        "| --- | ---: | --- |",
    ]
    out += [f"| {s} | {counts[s]} | {STATUS_LABEL[s]} |" for s in STATUS_ORDER]
    out.append("")

    groups = [
        ("우선 조치", ("MISMATCH", "STALE", "DST_RISK")),
        ("검토 필요", ("AMBIGUOUS", "UNMAPPED")),
    ]
    n = 0
    for title, statuses in groups:
        items = [f for f in result.findings if f.status in statuses]
        out += [f"## {title} ({len(items)})", ""]
        if not items:
            out += ["없음.", ""]
        for f in items:
            n += 1
            out += _detail(n, f)

    matches = [f for f in result.findings if f.status in ("MATCH", "IGNORED")]
    out += [f"## 현행 기준과 일치·제외 ({len(matches)})", ""]
    if matches:
        out += ["| 위치 | 값 | 기준 | 주석 확정 | 설명 |", "| --- | --- | --- | --- | --- |"]
        out += [
            f"| `{f.path}:{f.line}` | `{f.found}` | {f.boundary or '-'} | {'예' if f.reviewed else '아니오'} | {_cell(f.reason)} |"
            for f in matches
        ]
    else:
        out.append("없음.")
    out += [
        "",
        "## 이 검사가 보장하지 않는 것",
        "",
        "- 시스템 용량·성능, 거래소·SOR 제공사 등 외부 시스템 장애.",
        "- 기준표에 없는 규칙과 스캔 대상 확장자 밖의 파일(문서는 `--include-docs`로 포함).",
        "- 정적 패턴으로 드러나지 않는 시각 계산(분 단위 산술, DB에 저장된 값 등). 경계 테스트(`gen-tests`)로 동작을 함께 확인하세요.",
        "- 기준표 값 자체의 정확성. 기준표는 담당자가 출처와 함께 승인해야 합니다.",
        "",
    ]
    return "\n".join(out)
