"""명령줄 진입점: check-calendar / scan / gen-tests."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .calendar_model import CalendarError, load_calendar
from .classify import STATUS_ORDER
from .junit import write_junit_tests
from .report import render_markdown
from .scan import scan_repo
from .testgen import write_tests

EXIT_OK, EXIT_FINDINGS, EXIT_INPUT = 0, 1, 2


def _utf8_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def _statuses(text: str) -> set[str]:
    values = {s.strip().upper() for s in text.split(",") if s.strip()}
    unknown = values - set(STATUS_ORDER)
    if unknown:
        raise argparse.ArgumentTypeError(f"알 수 없는 상태: {', '.join(sorted(unknown))}")
    return values


def _cmd_check(args) -> int:
    cal = load_calendar(args.calendar)
    print(f"기준표 정상: {cal.name} ({cal.digest})")
    print(f"- 현행 경계 {len(cal.active)}개, 폐기 경계 {len(cal.retired)}개, probe {len(cal.probes)}개")
    for b in cal.retired:
        new = cal.get(b.replaced_by or "")
        print(f"- 변경: {b.id} {b.time:%H:%M} → {new.id} {new.time:%H:%M}"
              + (f" ({b.retired_on})" if b.retired_on else ""))
    return EXIT_OK


def _cmd_scan(args) -> int:
    cal = load_calendar(args.calendar)
    repo = Path(args.repo)
    if not repo.is_dir():
        print(f"저장소 경로가 없습니다: {repo}", file=sys.stderr)
        return EXIT_INPUT
    out = Path(args.out)
    result = scan_repo(repo, cal, include_docs=args.include_docs, exclude=(out,))
    out.mkdir(parents=True, exist_ok=True)
    (out / "findings.json").write_text(
        json.dumps(result.to_json(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "report.md").write_text(render_markdown(result), encoding="utf-8")

    counts = result.counts()
    summary = " · ".join(f"{s} {counts[s]}" for s in STATUS_ORDER if counts[s])
    print(f"[mhg] {repo.name}: 파일 {result.stats.files_scanned}개, 거래시간 표현 {len(result.findings)}개"
          f" → {summary or '해당 없음'}")
    if result.stats.large_files:
        print(f"[mhg] 주의: 1MB를 넘어 검사하지 않은 파일 {len(result.stats.large_files)}개 — "
              + ", ".join(result.stats.large_files[:3]) + (" 외" if len(result.stats.large_files) > 3 else ""))
    for f in result.findings:
        if f.status in ("MATCH", "IGNORED") and not args.verbose:
            continue
        print(f"  {f.status:<9} {f.path}:{f.line}  {f.found}  {f.reason}")
    print(f"[mhg] 보고서: {out / 'report.md'}")
    failing = result.failing(args.fail_on)
    if failing:
        print(f"[mhg] 실패 조건({', '.join(sorted(args.fail_on))}) {len(failing)}건")
        return EXIT_FINDINGS
    return EXIT_OK


def _cmd_gen(args) -> int:
    cal = load_calendar(args.calendar)
    if args.format == "junit":
        info = write_junit_tests(cal, Path(args.out), package=args.java_package)
    else:
        info = write_tests(cal, Path(args.out))
    print(f"[mhg] 경계 테스트 {info['cases']}건 생성 ({args.format}, probe: {', '.join(info['probes'])})")
    for path in info["files"]:
        print(f"  - {path}")
    state = "새로 만듦 — PROBES를 저장소 함수에 연결하세요" if info["adapter_created"] else "기존 파일 유지"
    print(f"  - {info['adapter']} ({state})")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mhg", description="거래시간 변경 점검기 (Market Hours Guard)")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check-calendar", help="기준표 형식·출처·참조 검증")
    check.add_argument("--calendar", required=True)
    check.set_defaults(func=_cmd_check)

    scan = sub.add_parser("scan", help="저장소의 거래시간 표현을 기준표와 대조")
    scan.add_argument("--repo", required=True)
    scan.add_argument("--calendar", required=True)
    scan.add_argument("--out", default="mhg-output")
    scan.add_argument("--include-docs", action="store_true", help=".md/.txt/.html 문서도 검사")
    scan.add_argument("--fail-on", type=_statuses, default=_statuses("MISMATCH,STALE,DST_RISK"),
                      help="종료 코드 1로 실패시킬 상태 (기본: MISMATCH,STALE,DST_RISK)")
    scan.add_argument("--verbose", action="store_true", help="MATCH 항목도 출력")
    scan.set_defaults(func=_cmd_scan)

    gen = sub.add_parser("gen-tests", help="기준표 probe에서 경계 시각 테스트 생성")
    gen.add_argument("--calendar", required=True)
    gen.add_argument("--out", required=True, help="테스트를 쓸 디렉터리 (예: <repo>/tests/market_hours, <repo>/src/test/java/...)")
    gen.add_argument("--format", choices=["pytest", "junit"], default="pytest",
                     help="pytest(기본) 또는 junit(Java·Kotlin 저장소, JUnit 5)")
    gen.add_argument("--java-package", help="junit: 생성할 클래스의 패키지 (예: com.example.trading)")
    gen.set_defaults(func=_cmd_gen)
    return parser


def main(argv: list[str] | None = None) -> int:
    _utf8_stdout()
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except CalendarError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_INPUT
    except FileNotFoundError as exc:
        print(f"파일을 찾을 수 없습니다: {exc.filename}", file=sys.stderr)
        return EXIT_INPUT
