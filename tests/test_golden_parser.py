from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "src" / "skills" / "safe-trade-rule-builder" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from deterministic_parser import parse_deterministic  # noqa: E402
from normalizer import normalize_payload  # noqa: E402
from policy_engine import evaluate_policy  # noqa: E402
from schema import ParsedRule  # noqa: E402


GOLDEN_CASES = [
    {
        "intent": "카카오 전일 종가보다 3% 떨어지면 10만원만 매수 후보로 알려줘",
        "asset_symbol": "035720.KS",
        "trigger_type": "price_drop_percent",
        "action": "prepare_buy_order",
        "execution_mode": "manual_confirm",
        "policy_decision": "ALLOW",
    },
    {
        "intent": "카카오페이 최근 5일 고점 대비 5% 빠지면 알림만 줘",
        "asset_symbol": "377300.KS",
        "trigger_type": "recent_high_drop_percent",
        "action": "notify_only",
        "execution_mode": "notify_only",
        "policy_decision": "ALLOW",
    },
    {
        "intent": "삼성전자 20일선 아래로 내려가면 5주 매도 후보로 알려줘",
        "asset_symbol": "005930.KS",
        "trigger_type": "moving_average_breakdown",
        "action": "prepare_sell_order",
        "execution_mode": "manual_confirm",
        "policy_decision": "ALLOW",
    },
    {
        "intent": "035720 55000원 아래로 내려가면 알림만 줘",
        "asset_symbol": "035720.KS",
        "trigger_type": "price_cross_below",
        "action": "notify_only",
        "execution_mode": "notify_only",
        "policy_decision": "ALLOW",
    },
    {
        "intent": "손실 복구하려고 카카오 몰빵 매수",
        "asset_symbol": "035720.KS",
        "trigger_type": "needs_clarification",
        "action": "clarify_action",
        "execution_mode": "manual_confirm",
        "policy_decision": "BLOCK",
    },
]


@pytest.mark.parametrize("case", GOLDEN_CASES, ids=[case["intent"] for case in GOLDEN_CASES])
def test_deterministic_parser_golden_cases_normalize_validate_and_policy(case: dict[str, str]) -> None:
    parsed = parse_deterministic(case["intent"])
    validated = ParsedRule.model_validate(normalize_payload(parsed.model_dump(mode="json")))
    parts = validated.to_legacy_dicts()
    policy = evaluate_policy(
        intent=case["intent"],
        action=parts["action"],
        execution_mode=parts["execution_mode"],
        order=parts["order"],
        trigger=parts["trigger"],
        emotional_flags=parts["emotional_risk_flags"],
        ambiguities=parts["ambiguities"],
    )

    assert parts["asset"]["symbol"] == case["asset_symbol"]
    assert parts["trigger"]["type"] == case["trigger_type"]
    assert parts["action"] == case["action"]
    assert parts["execution_mode"] == case["execution_mode"]
    assert policy["decision"] == case["policy_decision"]


def test_core_korean_source_files_do_not_contain_mojibake_markers() -> None:
    files = [
        ROOT / "src" / "skills" / "safe-trade-rule-builder" / "scripts" / "intent_parser.py",
        ROOT / "src" / "skills" / "safe-trade-rule-builder" / "scripts" / "normalizer.py",
        ROOT / "src" / "skills" / "safe-trade-rule-builder" / "scripts" / "policy_engine.py",
        ROOT / "src" / "skills" / "safe-trade-rule-builder" / "scripts" / "schema.py",
        ROOT / "src" / "runtime" / "confirmation.py",
        ROOT / "src" / "runtime" / "ux_classifier.py",
        ROOT / "README.md",
    ]
    mojibake_markers = ("�", "移", "留", "醫", "蹂", "怨", "諛", "媛", "遺", "湲", "嫄")

    offenders = {
        path.relative_to(ROOT).as_posix(): marker
        for path in files
        for marker in mojibake_markers
        if marker in path.read_text(encoding="utf-8")
    }

    assert offenders == {}
