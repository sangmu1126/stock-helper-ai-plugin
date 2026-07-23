from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "src" / "skills" / "safe-trade-rule-builder" / "scripts"
FIXTURES = ROOT / "tests" / "fixtures" / "llm_outputs"
sys.path.insert(0, str(SCRIPTS))

from llm_parser import normalize_llm_payload  # noqa: E402
from policy_engine import evaluate_policy  # noqa: E402


@pytest.mark.parametrize("fixture_path", sorted(FIXTURES.glob("*.json")), ids=lambda path: path.stem)
def test_llm_output_fixtures_normalize_validate_and_policy(fixture_path: Path) -> None:
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    rule = normalize_llm_payload(
        fixture["payload"],
        fixture["intent"],
        structured_output_used=True,
    )
    parts = rule.to_legacy_dicts()
    policy = evaluate_policy(
        intent=fixture["intent"],
        action=parts["action"],
        execution_mode=parts["execution_mode"],
        order=parts["order"],
        trigger=parts["trigger"],
        emotional_flags=parts["emotional_risk_flags"],
        ambiguities=parts["ambiguities"],
    )
    expected = fixture["expected"]

    assert parts["asset"]["symbol"] == expected["asset_symbol"]
    assert parts["trigger"]["type"] == expected["trigger_type"]
    assert parts["action"] == expected["action"]
    assert parts["execution_mode"] == expected["execution_mode"]
    assert policy["decision"] == expected["policy_decision"]
    assert parts["parser"]["source"] == "llm"
    assert parts["parser"]["structured_output_used"] is True
