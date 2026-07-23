from __future__ import annotations

from deterministic_parser import parse_deterministic
from llm_parser import parse_llm
from schema import ParsedRule


def parse_intent(intent: str, parser: str = "auto") -> ParsedRule:
    if parser == "deterministic":
        return parse_deterministic(intent)
    if parser == "llm":
        return parse_llm(intent)
    if parser != "auto":
        raise ValueError(f"Unsupported parser strategy: {parser}")
    try:
        return parse_llm(intent)
    except Exception as exc:  # noqa: BLE001 - product fallback path
        return parse_deterministic(
            intent,
            fallback_used=True,
            warning=f"LLM parser unavailable or invalid: {exc}",
        )
