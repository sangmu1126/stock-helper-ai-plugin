"""점검 결과를 SARIF 2.1.0으로 내보낸다 (GitHub code scanning 업로드용).

MISCONCEPTION·MISMATCH는 error, REVIEW는 warning, OK는 넣지 않는다.
Word(.docx)는 줄 번호가 없으므로 위치에는 파일만 넣고 문단 번호는 메시지에 쓴다.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"
INFO_URI = "https://github.com/sangmu1126/stock-helper-ai-plugin"
RULES = {
    "MISCONCEPTION": ("error", "140% 미만 값으로 '반대매매 없음·안전'이라고 안내",
                      "140% 미만은 이미 담보부족이고 120%는 긴급 기준입니다. 규칙 파일의 사실대로 고치세요."),
    "MISMATCH": ("error", "유지·긴급·유예·알림 기준이나 D+N 일정이 규칙과 다름",
                 "규칙 파일(safe-trade-rule-builder/config/margin_rules.json)의 값으로 고치세요."),
    "REVIEW": ("warning", "담보비율로 보이지만 어떤 기준인지 문맥에 없음",
               "문맥을 읽고 판단하세요. 무관하면 같은 줄에 `mrc: ignore`를 다세요."),
}


def _uri(repo: Path, rel_path: str, base: Path | None) -> str:
    if base is not None:
        try:
            return (repo / rel_path).resolve().relative_to(base.resolve()).as_posix()
        except ValueError:
            pass
    return rel_path


def to_sarif(findings: list[Any], repo: Path, rules_version: str, base: Path | None = None) -> dict[str, Any]:
    ids = list(RULES)
    results = []
    for f in findings:
        if f.status not in RULES:
            continue
        docx = f.path.lower().endswith(".docx")
        where = f" (문단 {f.line})" if docx and f.line else ""
        expected = f", 기준 {f.expected}" if f.expected else ""
        location: dict[str, Any] = {"artifactLocation": {"uri": _uri(repo, f.path, base)}}
        if not docx and f.line:
            location["region"] = {"startLine": f.line}
        results.append({
            "ruleId": f.status,
            "ruleIndex": ids.index(f.status),
            "level": RULES[f.status][0],
            "message": {"text": f"{f.status}: {f.found}{expected}{where} — {f.message}"},
            "locations": [{"physicalLocation": location}],
            "partialFingerprints": {"mrcFindingId/v1": f.id},
        })
    return {
        "$schema": SCHEMA,
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": {
                "name": "margin-rule-check", "informationUri": INFO_URI,
                "rules": [{"id": rid, "name": rid.title(), "shortDescription": {"text": short},
                           "help": {"text": help_text}, "defaultConfiguration": {"level": level}}
                          for rid, (level, short, help_text) in RULES.items()],
            }},
            "automationDetails": {"id": "margin-rule-check/"},
            "properties": {"rulesVersion": rules_version},
            "results": results,
        }],
    }
