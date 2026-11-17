from __future__ import annotations

from deterministic_parser import parse_deterministic
from schema import ParsedRule

SUPPORTED_PARSERS = ("deterministic",)


def parse_intent(intent: str, parser: str = "deterministic") -> ParsedRule:
    """문장을 오프라인 파서로 해석한다.

    Codex 안에서는 Codex가 룰 JSON을 직접 만들어 `rule_json.parse_rule_payload`로 넘기는 경로를 쓴다.
    외부 AI API는 호출하지 않는다.
    """
    if parser not in SUPPORTED_PARSERS:
        raise ValueError(f"Unsupported parser strategy: {parser} (supported: {', '.join(SUPPORTED_PARSERS)})")
    return parse_deterministic(intent)
