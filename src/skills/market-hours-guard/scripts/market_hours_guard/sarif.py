"""스캔 결과를 SARIF 2.1.0으로 내보낸다.

GitHub code scanning(`github/codeql-action/upload-sarif`)에 올리면 PR 화면의 해당 줄에 판정이 표시된다.
MATCH·IGNORED는 문제가 아니므로 넣지 않는다. 실패 조건(--fail-on) 상태는 error, AMBIGUOUS는 warning,
UNMAPPED는 note로 둔다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import __version__
from .classify import STATUS_LABEL
from .scan import ScanResult

SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"
INFO_URI = "https://github.com/sangmu1126/stock-helper-ai-plugin"
RULE_HELP = {
    "MISMATCH": "`mhg:` 주석으로 지정한 기준과 값이 다릅니다. 기준표가 바뀌었다면 값을 고치고, 의미가 다르면 주석을 고치세요.",
    "STALE": "폐기된 기준값으로 보입니다. 제도 변경이 반영되지 않았을 수 있습니다. 대체 기준 값으로 바꾸고 `mhg:` 주석을 다세요.",
    "DST_RISK": "외국 시장 시각을 한국시각 고정값으로 썼습니다. 서머타임 전환 때 틀립니다. 현지 시간대로 변환해 비교하세요.",
    "AMBIGUOUS": "현행 기준과 폐기된 기준에 모두 해당합니다. 코드 의미를 확인해 `mhg:` 주석으로 고정하세요.",
    "UNMAPPED": "거래시간 문맥이지만 기준표에 없는 값입니다. 파생 값이면 `mhg: <ID>+5m`, 무관하면 `mhg: ignore`로 표시하세요.",
}
REPORTED = tuple(RULE_HELP)


def _level(status: str, fail_on: set[str]) -> str:
    if status in fail_on:
        return "error"
    return "warning" if status in ("MISMATCH", "STALE", "DST_RISK", "AMBIGUOUS") else "note"


def artifact_uri(repo: Path, rel_path: str, base: Path | None) -> str:
    """base(기본: 현재 폴더) 기준 상대 경로. GitHub는 저장소 루트 기준 경로로 줄을 찾는다."""
    if base is not None:
        try:
            return (repo / rel_path).resolve().relative_to(base.resolve()).as_posix()
        except ValueError:
            pass
    return rel_path


def to_sarif(result: ScanResult, fail_on: set[str], base: Path | None = None) -> dict[str, Any]:
    rules = [{
        "id": status,
        "name": status.title().replace("_", ""),
        "shortDescription": {"text": STATUS_LABEL[status]},
        "help": {"text": RULE_HELP[status]},
        "defaultConfiguration": {"level": _level(status, fail_on)},
    } for status in REPORTED]
    index = {status: i for i, status in enumerate(REPORTED)}
    results = []
    for f in result.findings:
        if f.status not in index:
            continue
        expected = f" (기준 {f.expected}{', ' + f.boundary if f.boundary else ''})" if f.expected else ""
        results.append({
            "ruleId": f.status,
            "ruleIndex": index[f.status],
            "level": _level(f.status, fail_on),
            "message": {"text": f"{f.status}: {f.found}{expected} — {f.reason}"},
            "locations": [{"physicalLocation": {
                "artifactLocation": {"uri": artifact_uri(result.repo, f.path, base)},
                "region": {"startLine": f.line, "startColumn": max(f.col, 1)},
            }}],
            "partialFingerprints": {"mhgFindingId/v1": f.id},
        })
    return {
        "$schema": SCHEMA,
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": {"name": "market-hours-guard", "version": __version__,
                                "informationUri": INFO_URI, "rules": rules}},
            "automationDetails": {"id": "market-hours-guard/"},
            "properties": {"calendar": result.calendar.name, "calendarDigest": result.calendar.digest},
            "results": results,
        }],
    }
