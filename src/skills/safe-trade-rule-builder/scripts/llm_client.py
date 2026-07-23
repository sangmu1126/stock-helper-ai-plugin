from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


DEFAULT_MODEL = os.getenv("SAFE_TRADE_RULE_LLM_MODEL", "gpt-4.1-mini")
DEFAULT_TIMEOUT_SECONDS = float(os.getenv("SAFE_TRADE_RULE_LLM_TIMEOUT_SECONDS", "20"))


class LLMUnavailable(RuntimeError):
    pass


def parse_with_openai(
    prompt: str,
    *,
    model: str = DEFAULT_MODEL,
    schema_model: type[Any] | None = None,
) -> dict[str, Any]:
    load_local_env()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise LLMUnavailable("OPENAI_API_KEY is not set")
    try:
        from openai import OpenAI  # type: ignore[import-not-found]
    except ImportError as exc:
        raise LLMUnavailable("openai package is not installed") from exc

    client = OpenAI(api_key=api_key, timeout=DEFAULT_TIMEOUT_SECONDS)
    if schema_model is not None and hasattr(client.responses, "parse"):
        response = client.responses.parse(
            model=model,
            input=prompt,
            text_format=schema_model,
        )
        return _coerce_parsed_response(response)

    response = client.responses.create(
        model=model,
        input=prompt,
        temperature=0,
    )
    text = getattr(response, "output_text", None)
    if not text:
        raise LLMUnavailable("OpenAI response did not include output_text")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMUnavailable(f"OpenAI response was not valid JSON: {exc}") from exc


def _coerce_parsed_response(response: Any) -> dict[str, Any]:
    parsed = getattr(response, "output_parsed", None)
    if parsed is None:
        raise LLMUnavailable("OpenAI structured response did not include output_parsed")
    if hasattr(parsed, "model_dump"):
        return parsed.model_dump(mode="json", exclude_none=True)
    if isinstance(parsed, dict):
        return parsed
    raise LLMUnavailable(f"Unsupported OpenAI structured response type: {type(parsed).__name__}")


def load_local_env() -> None:
    for path in _candidate_env_paths():
        if not path.exists():
            continue
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def _candidate_env_paths() -> tuple[Path, ...]:
    script_root = Path(__file__).resolve().parents[4]
    return (Path.cwd() / ".env", script_root / ".env")
