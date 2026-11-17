#!/usr/bin/env python3
"""사내용 신용거래 규칙 점검 — 상담 스크립트·안내 문구·앱 설정·계산 로직이 공식 규칙과 맞는지 확인한다.

    python margin_rule_check.py lint --repo <폴더> [--out mrc-output]
    python margin_rule_check.py gen-tests --out <폴더>/tests/margin_rules

규칙 값(140% 유지·120% 긴급·D+1/D+2·한시 유예)은 투자자용 스킬의 config/margin_rules.json 하나만 쓴다.
lint 종료 코드: 0 문제 없음 · 1 MISCONCEPTION/MISMATCH 있음 · 2 입력 오류. 외부 서비스에 접속하지 않는다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

_SKILLS_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_SKILLS_DIR / "safe-trade-rule-builder" / "scripts"))

from docx_text import DocxError, read_docx_text
from margin_guard import add_business_days, classify_ratio, evaluate_grace, exchange_holidays, load_margin_rules
from mrc_junit import write_junit_tests
from mrc_sarif import to_sarif

SUFFIXES = {".md", ".txt", ".html", ".json", ".yaml", ".yml", ".properties", ".toml", ".py", ".kt", ".java",
            ".ts", ".tsx", ".js", ".csv", ".docx"}
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", "mrc-output"}
GENERATED_MARKER = "mrc:generated"
COLLATERAL_WORDS = ("담보", "반대매매", "collateral", "margin", "신용", "유예", "liquidation", "maintenance", "grace")
ROLE_WORDS = {
    "grace": ("유예", "grace"),
    "emergency": ("긴급", "최소", "당일", "emergency", "minimum"),
    "maintenance": ("유지", "담보부족", "maintenance", "shortfall", "회복", "채워", "채우"),
    "watch": ("주의", "알림", "watch", "alert"),
}
ROLE_LABEL = {"maintenance": "담보유지비율", "emergency": "긴급(최소) 기준", "grace": "한시 유예 구간", "watch": "주의 알림 기준"}
PERCENT_RE = re.compile(r"(?<![\d.])(\d{2,3}(?:\.\d+)?)\s*%")
KEY_VALUE_RE = re.compile(r"(\b\w*(?:ratio|pct|percent)\w*)\s*[:=]\s*[\"']?(\d{2,3}(?:\.\d+)?)", re.IGNORECASE)
DEADLINE_RE = re.compile(r"D\s*\+\s*(\d)")
DAYS_KEY_RE = re.compile(r"(\b\w*(?:liquidation|deadline|deposit)\w*)\s*[:=]\s*[\"']?(\d)\b", re.IGNORECASE)
MISCONCEPTION_RE = re.compile(
    r"(\d{2,3}(?:\.\d+)?)\s*%\s*(?:만\s*)?(?:이상이면|이상만|넘(?:기|으)면|맞추면|유지하면|이면)"
    r"[^.\n]*(?:반대매매|청산)[^.\n]*(?:없|안\s*되|안\s*당|되지\s*않|피할)"
)
SAFE_CLAIM_RE = re.compile(r"(\d{2,3}(?:\.\d+)?)\s*%[^.\n]{0,20}(?:안전|괜찮)")
SEVERITY = {"MISCONCEPTION": "high", "MISMATCH": "high", "REVIEW": "low", "OK": "info"}


@dataclass
class Finding:
    id: str
    status: str
    severity: str
    path: str
    line: int
    kind: str
    found: str
    role: str | None
    expected: str | None
    message: str
    snippet: str


def _expected_values(rules: dict[str, Any]) -> dict[str, Any]:
    grace = rules["temporary_grace"][0] if rules.get("temporary_grace") else None
    return {
        "maintenance": float(rules["thresholds"]["maintenance_pct"]["value"]),
        "emergency": float(rules["thresholds"]["emergency_pct"]["value"]),
        "grace": (float(grace["min_ratio_pct"]), float(grace["max_ratio_pct"])) if grace else None,
        "deposit_days": int(rules["shortfall"]["deposit_deadline_business_days"]),
        "shortfall_liquidation_days": int(rules["shortfall"]["liquidation_business_days"]),
        "emergency_liquidation_days": int(rules["emergency"]["liquidation_business_days"]),
    }


def _roles_in(text: str) -> set[str]:
    lowered = text.lower()
    return {role for role, words in ROLE_WORDS.items() if any(word in lowered for word in words)}


def _value_ok(role: str, value: float, expected: dict[str, Any]) -> bool:
    if role in ("maintenance", "emergency"):
        return value == expected[role]
    if role == "grace":
        return expected["grace"] is not None and value in expected["grace"]
    if role == "watch":
        return value > expected["maintenance"]
    return False


def _expected_text(role: str, expected: dict[str, Any]) -> str:
    if role == "grace":
        low, high = expected["grace"]
        return f"{low:g}~{high:g}% 미만"
    if role == "watch":
        return f"{expected['maintenance']:g}% 초과"
    return f"{expected[role]:g}%"


def _finding(path: str, line_no: int, kind: str, status: str, found: str, role: str | None,
             expected_text: str | None, message: str, snippet: str) -> Finding:
    digest = hashlib.sha1(f"{path}:{line_no}:{kind}:{found}".encode()).hexdigest()[:10]
    return Finding(digest, status, SEVERITY[status], path, line_no, kind, found, role, expected_text, message,
                   snippet.strip()[:200])


def _check_ratio(path: str, line_no: int, line: str, value: float, roles: set[str], expected: dict[str, Any],
                 kind: str) -> Finding:
    found = f"{value:g}%"
    if not roles:
        return _finding(path, line_no, kind, "REVIEW", found, None, None,
                        "담보비율로 보이지만 어떤 기준인지(유지·긴급·유예·알림) 문맥에 없습니다. 의미를 확인하세요.", line)
    for role in roles:
        if _value_ok(role, value, expected):
            return _finding(path, line_no, kind, "OK", found, role, _expected_text(role, expected),
                            f"{ROLE_LABEL[role]}과 일치합니다.", line)
    role = sorted(roles, key=list(ROLE_WORDS).index)[0]
    return _finding(path, line_no, kind, "MISMATCH", found, role, _expected_text(role, expected),
                    f"{ROLE_LABEL[role]}은 {_expected_text(role, expected)}인데 {found}로 적혀 있습니다.", line)


def lint_text(path: str, text: str, rules: dict[str, Any]) -> list[Finding]:
    expected = _expected_values(rules)
    maintenance = expected["maintenance"]
    findings: list[Finding] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        lowered = line.lower()
        if "mrc: ignore" in lowered:
            continue
        about_margin = any(word in lowered for word in COLLATERAL_WORDS)
        key_values = [(m.group(1), float(m.group(2))) for m in KEY_VALUE_RE.finditer(line)]
        day_keys = [(m.group(1), int(m.group(2))) for m in DAYS_KEY_RE.finditer(line)]
        if not about_margin and not key_values and not day_keys:
            continue

        misconceived: set[float] = set()
        for regex in (MISCONCEPTION_RE, SAFE_CLAIM_RE):
            for match in regex.finditer(line):
                value = float(match.group(1))
                if about_margin and value < maintenance and value not in misconceived:
                    misconceived.add(value)
                    findings.append(_finding(
                        path, line_no, "statement", "MISCONCEPTION", f"{value:g}%", "maintenance",
                        f"{maintenance:g}%",
                        f"{value:g}%면 반대매매를 피할 수 있다는 안내는 틀립니다. {maintenance:g}% 미만이면 이미 담보부족이고, "
                        f"{expected['emergency']:g}%는 긴급 반대매매 기준입니다.", line))

        if about_margin:
            roles = _roles_in(line)
            for match in PERCENT_RE.finditer(line):
                value = float(match.group(1))
                if value in misconceived:
                    continue
                findings.append(_check_ratio(path, line_no, line, value, roles, expected, "percent"))
            allowed: set[int] = set()
            if any(word in lowered for word in ("납부", "입금", "추가 담보", "채우", "채워", "deposit")):
                allowed.add(expected["deposit_days"])
            if any(word in lowered for word in ("반대매매", "liquidation", "청산")):
                allowed.add(expected["shortfall_liquidation_days"])
                if "emergency" in _roles_in(line) or f"{expected['emergency']:g}%" in line:
                    allowed.add(expected["emergency_liquidation_days"])
            if allowed:
                for match in DEADLINE_RE.finditer(line):
                    days = int(match.group(1))
                    status = "OK" if days in allowed else "MISMATCH"
                    message = ("일정이 규칙과 맞습니다." if status == "OK" else
                               f"규칙상 이 문장의 일정은 {', '.join(f'D+{d}' for d in sorted(allowed))}인데 D+{days}로 적혀 있습니다.")
                    findings.append(_finding(path, line_no, "deadline", status, f"D+{days}", None,
                                             ", ".join(f"D+{d}" for d in sorted(allowed)), message, line))

        for key, value in key_values:
            key_roles = _roles_in(key) or (_roles_in(line) if about_margin else set())
            if not key_roles and not about_margin:
                continue
            findings.append(_check_ratio(path, line_no, line, value, key_roles, expected, f"config:{key}"))
        for key, days in day_keys:
            lowered_key = key.lower()
            if "deposit" in lowered_key or "deadline" in lowered_key:
                want = expected["deposit_days"]
            elif "emergency" in lowered_key:
                want = expected["emergency_liquidation_days"]
            else:
                want = expected["shortfall_liquidation_days"]
            status = "OK" if days == want else "MISMATCH"
            message = "일정이 규칙과 맞습니다." if status == "OK" else f"규칙상 {key}는 {want}영업일인데 {days}로 설정돼 있습니다."
            findings.append(_finding(path, line_no, f"config:{key}", status, str(days), None, str(want), message, line))
    return findings


def lint_repo(repo: Path, rules: dict[str, Any], exclude: tuple[Path, ...] = ()) -> list[Finding]:
    findings: list[Finding] = []
    excluded = {p.resolve() for p in exclude}
    for file in sorted(repo.rglob("*")):
        if not file.is_file() or file.suffix.lower() not in SUFFIXES:
            continue
        if any(part in SKIP_DIRS for part in file.relative_to(repo).parts) or any(
            parent.resolve() in excluded for parent in file.parents
        ):
            continue
        rel = file.relative_to(repo).as_posix()
        if file.suffix.lower() == ".docx":
            try:
                text = read_docx_text(file)
            except DocxError as exc:
                findings.append(_finding(rel, 0, "docx", "REVIEW", "", None, None,
                                         f"{exc} — 내용을 직접 확인하세요", ""))
                continue
        else:
            text = file.read_text(encoding="utf-8", errors="replace")
        if GENERATED_MARKER in text[:300]:
            continue
        findings.extend(lint_text(rel, text, rules))
    order = ["MISCONCEPTION", "MISMATCH", "REVIEW", "OK"]
    findings.sort(key=lambda f: (order.index(f.status), f.path, f.line))
    return findings


def render_report(repo: Path, findings: list[Finding], rules: dict[str, Any]) -> str:
    counts = {s: sum(1 for f in findings if f.status == s) for s in ("MISCONCEPTION", "MISMATCH", "REVIEW", "OK")}
    lines = [
        "# 신용거래 규칙 점검 결과",
        "",
        f"- 대상: `{repo.name}` · 규칙 `{rules['version']}`",
        "- " + " · ".join(f"{k} {v}" for k, v in counts.items()),
        "",
    ]
    if any(f.path.lower().endswith(".docx") for f in findings):
        lines[-1:-1] = ["- Word(.docx) 파일의 위치는 `파일:문단 번호`입니다."]
    for title, statuses in (("고쳐야 할 안내·설정", ("MISCONCEPTION", "MISMATCH")), ("확인 필요", ("REVIEW",))):
        items = [f for f in findings if f.status in statuses]
        lines += [f"## {title} ({len(items)})", ""]
        lines += [f"- **{f.status}** `{f.path}:{f.line}` {f.found} — {f.message}\n  > {f.snippet}" for f in items] or ["없음."]
        lines.append("")
    sources = " · ".join(f"[{s['title']}]({s['url']})" for s in rules["sources"].values() if s.get("url"))
    lines += ["## 기준", "", f"규칙 파일: `safe-trade-rule-builder/config/margin_rules.json` — {sources}", ""]
    return "\n".join(lines)


# ── 계산 로직 적합성 테스트 생성 ───────────────────────────

_TEST_TEMPLATE = '''# mrc:generated — 직접 수정하지 말고 margin_rule_check.py gen-tests로 다시 만드세요.
"""신용거래 규칙 경계 테스트. 규칙 버전: {version}"""

from __future__ import annotations

import datetime as _dt
import json
import pathlib

import pytest

import mrc_adapter

_CASES = json.loads(pathlib.Path(__file__).with_name("margin_rule_cases.json").read_text(encoding="utf-8"))["cases"]


def _call(name, *args):
    fn = getattr(mrc_adapter, name, None)
    if fn == "skip":
        pytest.skip(f"{{name}}: 어댑터에서 제외됨")
    if fn is None:
        pytest.fail(f"mrc_adapter.{{name}}가 연결되지 않았습니다")
    return fn(*args)


@pytest.mark.parametrize("case", _CASES, ids=[c["id"] for c in _CASES])
def test_margin_rule(case):
    args = case["args"]
    if case["kind"] == "classify":
        actual = _call("classify_ratio", args["ratio_pct"])
    elif case["kind"] == "liquidation":
        actual = _call("liquidation_date", args["clock"], _dt.date.fromisoformat(args["start"]))
        actual = actual.isoformat() if hasattr(actual, "isoformat") else actual
    else:
        actual = _call("grace_status", args["ratio_pct"], args["shortfall_round"],
                       _dt.date.fromisoformat(args["liquidation_date"]))
    assert actual == case["expect"], f"{{case['why']}} — 기대 {{case['expect']!r}}, 실제 {{actual!r}}"
'''

_ADAPTER_TEMPLATE = '''"""신용거래 규칙 테스트 어댑터 — 회사 계산 코드를 연결한다. None이면 실패, "skip"이면 제외.

classify_ratio(ratio_pct: float) -> "SAFE" | "WATCH" | "SHORTFALL" | "EMERGENCY"
liquidation_date(clock: "SHORTFALL" | "EMERGENCY", start: date) -> date   # 주말·한국거래소 휴장일 제외 영업일 기준
grace_status(ratio_pct: float, shortfall_round: int | None, liquidation: date)
    -> "ELIGIBLE" | "NOT_ELIGIBLE" | "NEEDS_ROUND" | "NOT_ACTIVE"
"""

classify_ratio = None
liquidation_date = None
grace_status = None
'''


def build_cases(rules: dict[str, Any]) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    expected = _expected_values(rules)
    for ratio in (150, 149.9, 140, 139.9, 130, 129.9, 120, 119.9):
        cases.append({"id": f"classify-{ratio:g}", "kind": "classify", "args": {"ratio_pct": ratio},
                      "expect": classify_ratio(ratio, rules), "why": f"담보비율 {ratio:g}% 상태"})
    holidays, _ = exchange_holidays()
    # 수요일, 금요일(주말), 성탄절 전날(12/25 휴장), 연말(12/31 연말휴장일·1/1 신정)
    starts = (date(2026, 11, 18), date(2026, 11, 20), date(2026, 12, 24), date(2026, 12, 30))
    for clock, days in (("SHORTFALL", expected["shortfall_liquidation_days"]),
                        ("EMERGENCY", expected["emergency_liquidation_days"])):
        for start in starts:
            end = add_business_days(start, days, holidays)
            skipped = sorted(d.isoformat() for d in holidays if start < d <= end and d.weekday() < 5)
            cases.append({"id": f"liquidation-{clock.lower()}-{start}", "kind": "liquidation",
                          "args": {"clock": clock, "start": start.isoformat()},
                          "expect": end.isoformat(),
                          "why": f"{clock} 발생 {start} → D+{days} 반대매매"
                                 + (f" (휴장일 {', '.join(skipped)} 제외)" if skipped else "")})
    for ratio, round_, liquidation in ((135, 2, date(2026, 11, 19)), (135, 1, date(2026, 11, 19)),
                                       (125, 2, date(2026, 11, 19)), (135, None, date(2026, 11, 19)),
                                       (135, 2, date(2027, 3, 2))):
        grace = evaluate_grace(rules, ratio, round_, liquidation)
        cases.append({"id": f"grace-{ratio}-{round_}-{liquidation}", "kind": "grace",
                      "args": {"ratio_pct": ratio, "shortfall_round": round_, "liquidation_date": liquidation.isoformat()},
                      "expect": grace["status"] if grace else "NOT_ACTIVE",
                      "why": f"한시 유예: {ratio}%, 담보부족 {round_}회차, 반대매매 {liquidation}"})
    return cases


def write_tests(rules: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    cases = build_cases(rules)
    (out_dir / "margin_rule_cases.json").write_text(json.dumps(
        {"_generated": GENERATED_MARKER, "rules_version": rules["version"], "cases": cases},
        ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out_dir / "test_margin_rules_generated.py").write_text(_TEST_TEMPLATE.format(version=rules["version"]),
                                                            encoding="utf-8")
    adapter = out_dir / "mrc_adapter.py"
    created = not adapter.exists()
    if created:
        adapter.write_text(_ADAPTER_TEMPLATE, encoding="utf-8")
    return {"cases": len(cases), "adapter": str(adapter), "adapter_created": created}


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser(description="사내용 신용거래 규칙 점검")
    sub = parser.add_subparsers(dest="command", required=True)
    lint = sub.add_parser("lint", help="안내 문구·상담 스크립트·설정의 담보비율·일정 점검")
    lint.add_argument("--repo", required=True)
    lint.add_argument("--out", default="mrc-output")
    lint.add_argument("--sarif", help="SARIF 2.1.0 파일로도 저장 (GitHub code scanning 업로드용)")
    lint.add_argument("--sarif-base", default=".", help="SARIF 파일 경로의 기준 폴더 (기본: 현재 폴더 = 저장소 루트)")
    gen = sub.add_parser("gen-tests", help="계산 로직용 경계 테스트 생성")
    gen.add_argument("--out", required=True)
    gen.add_argument("--format", choices=["pytest", "junit"], default="pytest",
                     help="pytest(기본) 또는 junit(Java·Kotlin 계산 코드, JUnit 5)")
    gen.add_argument("--java-package", help="junit: 생성할 클래스의 패키지 (예: com.example.margin)")
    args = parser.parse_args(argv)
    rules = load_margin_rules()

    if args.command == "gen-tests":
        if args.format == "junit":
            info = write_junit_tests(build_cases(rules), rules["version"], Path(args.out), package=args.java_package)
        else:
            info = write_tests(rules, Path(args.out))
        state = "새로 만듦 — 회사 계산 함수를 연결하세요" if info["adapter_created"] else "기존 파일 유지"
        print(f"[mrc] 경계 테스트 {info['cases']}건 생성({args.format}) · 어댑터 {info['adapter']} ({state})")
        return 0

    repo = Path(args.repo)
    if not repo.is_dir():
        print(f"폴더가 없습니다: {repo}", file=sys.stderr)
        return 2
    out = Path(args.out)
    findings = lint_repo(repo, rules, exclude=(out,))
    out.mkdir(parents=True, exist_ok=True)
    (out / "findings.json").write_text(json.dumps({"rules_version": rules["version"],
                                                   "findings": [asdict(f) for f in findings]},
                                                  ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "report.md").write_text(render_report(repo, findings, rules), encoding="utf-8")
    if args.sarif:
        sarif = Path(args.sarif)
        sarif.parent.mkdir(parents=True, exist_ok=True)
        sarif.write_text(json.dumps(to_sarif(findings, repo, rules["version"], Path(args.sarif_base)),
                                    ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    bad = [f for f in findings if f.status in ("MISCONCEPTION", "MISMATCH")]
    review = [f for f in findings if f.status == "REVIEW"]
    print(f"[mrc] {repo.name}: 고칠 것 {len(bad)} · 확인 필요 {len(review)} · 일치 {len(findings) - len(bad) - len(review)}")
    for f in bad + review:
        print(f"  {f.status:<13} {f.path}:{f.line}  {f.found}  {f.message}")
    print(f"[mrc] 보고서: {out / 'report.md'}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
