from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "src" / "skills" / "safe-trade-rule-builder" / "scripts"
FIXTURES = ROOT / "tests" / "fixtures" / "rule_json"
sys.path.insert(0, str(SCRIPTS))

from policy_engine import evaluate_policy
from rule_json import parse_rule_payload


@pytest.mark.parametrize("fixture_path", sorted(FIXTURES.glob("*.json")), ids=lambda path: path.stem)
def test_rule_json_fixtures_normalize_validate_and_policy(fixture_path: Path) -> None:
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    rule = parse_rule_payload(fixture["payload"], fixture["intent"])
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
    assert parts["parser"]["source"] == "codex"


SKILL = ROOT / "src" / "skills" / "safe-trade-rule-builder"


def _cli(*args, stdin: str | None = None):
    import os
    import subprocess

    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "SAFE_TRADE_METRICS_LOG": "0"}
    env.pop("PYTHONPATH", None)
    return subprocess.run([sys.executable, str(SCRIPTS / "rule_builder.py"), *args], input=stdin, text=True,
                          encoding="utf-8", capture_output=True, env=env, check=False)


def test_shipped_example_validates() -> None:
    example = json.loads((SKILL / "references" / "rule_json_example.json").read_text(encoding="utf-8"))
    rule = parse_rule_payload(example, example["_sentence"])
    assert rule.parser.source == "codex"
    assert rule.time_window.only_before_close_minutes == 30


def test_cli_accepts_rule_json_on_stdin_and_reports_errors() -> None:
    example = (SKILL / "references" / "rule_json_example.json").read_text(encoding="utf-8")
    ok = _cli("--intent", json.loads(example)["_sentence"], "--rule-json", "-", "--format", "json", stdin=example)
    assert ok.returncode == 0, ok.stderr
    assert json.loads(ok.stdout)["parser"]["source"] == "codex"

    bad = _cli("--intent", "테슬라 알려줘", "--rule-json", "-", stdin='{"trigger": {"type": "moon_shot"}}')
    assert bad.returncode == 2 and "trigger.type" in bad.stderr

    schema = _cli("--print-rule-schema")
    assert schema.returncode == 0 and json.loads(schema.stdout)["title"] == "ParsedRule"
