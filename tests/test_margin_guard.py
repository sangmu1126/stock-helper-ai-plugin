"""신용거래 반대매매 가드 테스트.

규칙 값은 카카오페이증권 공식 안내(140%·120%·D+1/D+2)와 2026-11-06 한시 유예 공지에서 왔다.
계좌는 모두 가상 데이터다.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "src" / "skills" / "safe-trade-rule-builder"
SCRIPTS = SKILL / "scripts"
EXAMPLES = SKILL / "examples" / "margin"
sys.path.insert(0, str(SCRIPTS))

from margin_guard import (
    add_business_days,
    assess_account,
    build_alert_rule,
    classify_ratio,
    detect_margin_intent,
    explain_rules,
    load_account,
    load_margin_rules,
    parse_account,
    pre_trade_check,
)

RULES = load_margin_rules()


def account(ratio_stock: float, *, loan: float = 100_000_000, cash: float = 0, **extra):
    return parse_account({
        "as_of": "2026-11-18", "credit_loan": loan, "cash": cash,
        "holdings": [{"name": "가상", "quantity": 1, "prev_close": ratio_stock}], **extra,
    })


def test_every_rule_has_a_known_source():
    sources = RULES["sources"]
    assert {"CREDIT_GUIDE", "GRACE_NOTICE"} <= set(sources)
    assert RULES["thresholds"]["maintenance_pct"]["value"] == 140
    assert RULES["thresholds"]["emergency_pct"]["value"] == 120


@pytest.mark.parametrize("ratio, status", [
    (150.0, "SAFE"), (149.9, "WATCH"), (140.0, "WATCH"),   # 140%는 '140% 미만'이 아니다
    (139.9, "SHORTFALL"), (120.0, "SHORTFALL"), (119.9, "EMERGENCY"),
])
def test_status_boundaries(ratio, status):
    assert classify_ratio(ratio, RULES) == status


def test_misguided_case_before_deposit_needs_140_today():
    result = assess_account(load_account(EXAMPLES / "misguided_before_deposit.json"), RULES, believed_safe_pct=120)
    assert result["collateral_ratio_pct"] == 112.0 and result["status"] == "EMERGENCY"
    assert result["to_restore_maintenance"] == {"deposit_krw": 140_000_000, "or_repay_krw": 100_000_000}
    assert result["timeline"]["clock"] == "EMERGENCY"
    assert result["timeline"]["liquidation_date"] == "2026-11-19"          # D+1
    assert "120%는 안전 기준이 아닙니다" in result["warnings"][0]


def test_misguided_case_after_partial_deposit_is_still_d_plus_1():
    """120%를 넘겨도 그날 120% 미만이었다면 당일 140% 회복 의무가 남는다 (보도된 오안내의 핵심)."""
    result = assess_account(load_account(EXAMPLES / "misguided_after_deposit.json"), RULES)
    assert result["collateral_ratio_pct"] == 127.2 and result["status"] == "SHORTFALL"
    assert result["timeline"]["clock"] == "EMERGENCY"
    assert result["timeline"]["liquidation_date"] == "2026-11-19"
    assert result["to_restore_maintenance"]["deposit_krw"] == 64_000_000
    assert any("120%를 넘긴 것만으로는 부족" in line for line in result["explanation"])


def test_plain_shortfall_uses_d_plus_2():
    result = assess_account(account(135_000_000, shortfall_date="2026-11-20"), RULES)  # 금요일
    assert result["timeline"]["clock"] == "SHORTFALL"
    assert result["timeline"]["deposit_deadline"] == "2026-11-23"   # 주말 건너뜀
    assert result["timeline"]["liquidation_date"] == "2026-11-24"


def test_business_days_skip_weekends_and_holidays():
    assert add_business_days(date(2026, 11, 20), 1) == date(2026, 11, 23)
    assert add_business_days(date(2026, 11, 20), 1, frozenset({date(2026, 11, 23)})) == date(2026, 11, 24)


@pytest.mark.parametrize("extra, ratio_stock, status", [
    ({"shortfall_round": 2, "shortfall_date": "2026-11-17"}, 135_000_000, "ELIGIBLE"),
    ({"shortfall_round": 1, "shortfall_date": "2026-11-17"}, 135_000_000, "NOT_ELIGIBLE"),
    ({"shortfall_date": "2026-11-17"}, 135_000_000, "NEEDS_ROUND"),
    ({"shortfall_round": 2, "shortfall_date": "2026-11-17"}, 125_000_000, "NOT_ELIGIBLE"),  # 130% 미만
])
def test_temporary_grace(extra, ratio_stock, status):
    result = assess_account(account(ratio_stock, **extra), RULES)
    assert result["grace"]["status"] == status
    assert "자동 현금상환" in " ".join(result["warnings"])


def test_grace_not_applied_outside_period():
    result = assess_account(parse_account({
        "as_of": "2027-03-02", "credit_loan": 100_000_000, "shortfall_round": 2,
        "holdings": [{"name": "가상", "quantity": 1, "prev_close": 135_000_000}],
    }), RULES)
    assert result["grace"] is None


def test_restore_amounts_actually_restore_140():
    acc = account(130_000_000, cash=2_000_000)
    restore = assess_account(acc, RULES)["to_restore_maintenance"]
    assert (acc.collateral + restore["deposit_krw"]) / acc.debt == pytest.approx(1.40, abs=1e-6)
    assert acc.collateral / (acc.debt - restore["or_repay_krw"]) == pytest.approx(1.40, abs=1e-6)


def test_pre_trade_without_account_is_amount_independent():
    result = pre_trade_check(RULES)
    assert result["collateral_ratio_pct"] == 181.8
    assert result["price_drop_to_pct"] == {"maintenance": 23.0, "emergency": 34.0}
    assert result["grade_assumed"] and result["decision_hint"] == "REQUIRE_CLARIFICATION"


def test_pre_trade_with_account_can_start_in_shortfall():
    result = pre_trade_check(RULES, amount=20_000_000, account=load_account(EXAMPLES / "watch.json"))
    assert result["collateral_ratio_pct"] == 139.1 and result["status"] == "SHORTFALL"
    assert "매수 즉시" in result["acknowledgement_question"]


def test_pre_trade_grade_e_not_allowed():
    assert pre_trade_check(RULES, grade="E")["status"] == "NOT_ALLOWED"


def test_alert_rule_warns_when_threshold_too_low_and_evaluates_account():
    assert "이미 담보부족" in build_alert_rule(RULES, 140)["warnings"][0]
    assert "긴급 구간" in build_alert_rule(RULES, 120)["warnings"][0]
    watch = load_account(EXAMPLES / "watch.json")
    assert build_alert_rule(RULES, 150, account=watch)["decision"] == "NOTIFY"
    assert build_alert_rule(RULES, 140, account=watch)["decision"] == "WAIT"


def test_explain_mentions_grace_only_inside_period():
    inside = explain_rules(RULES, as_of=date(2026, 11, 18))
    outside = explain_rules(RULES, as_of=date(2027, 3, 2))
    assert any("한시 유예" in line for line in inside["explanation"])
    assert not any("한시 유예" in line for line in outside["explanation"])


@pytest.mark.parametrize("intent, kind, threshold, believed", [
    ("담보비율 150% 아래로 내려가면 알려줘", "collateral_alert", 150.0, None),
    ("담보비율이 145%보다 낮아지면 알림 줘", "collateral_alert", 145.0, None),
    ("삼성전자 3% 떨어지면 신용으로 100만원어치 매수", "credit_buy", None, None),
    ("빚투로 카카오 사줘", "credit_buy", None, None),
    ("담보비율 120%만 맞추면 반대매매 안 되지?", "rule_question", None, 120.0),
    ("신용카드로 결제한 돈으로 매수", None, None, None),
    ("카카오가 3% 떨어지면 10만원만 매수 후보로 알려줘", None, None, None),
])
def test_detect_margin_intent(intent, kind, threshold, believed):
    detected = detect_margin_intent(intent)
    assert (detected.kind, detected.threshold_pct, detected.believed_safe_pct) == (kind, threshold, believed)


def test_invalid_account_rejected():
    from margin_guard import MarginInputError

    with pytest.raises(MarginInputError):
        parse_account({"credit_loan": 0, "holdings": []})
    with pytest.raises(MarginInputError):
        parse_account({"credit_loan": 1, "holdings": [{"quantity": 1, "prev_close": -5}]})


# ── 기존 룰 빌더와의 통합 ──────────────────────────────────


def test_credit_buy_requires_clarification_through_existing_policy():
    from builder import build_rule

    draft = build_rule("삼성전자가 전일 종가보다 3% 떨어지면 신용으로 100만원어치 매수 후보로 알려줘",
                       parser_strategy="deterministic")
    assert draft.decision_result["decision"] == "REQUIRE_CLARIFICATION"
    assert draft.margin_guard["collateral_ratio_pct"] == 181.8
    assert draft.guardrails["credit_risk"]["acknowledgement_required"] is True
    assert any(a["field"] == "credit_risk" for a in draft.ambiguities)


def test_cash_buy_is_unchanged():
    from builder import build_rule

    draft = build_rule("카카오가 3% 떨어지면 10만원만 매수 후보로 알려줘", parser_strategy="deterministic")
    assert draft.margin_guard is None
    assert "credit_risk" not in draft.guardrails
    assert draft.decision_result["decision"] == "WAIT"


def test_report_includes_margin_section():
    from builder import build_rule
    from report_renderer import render_markdown_report

    draft = build_rule("삼성전자가 3% 떨어지면 신용으로 100만원어치 매수", parser_strategy="deterministic")
    report = render_markdown_report(draft, locale="ko")
    assert "## 2-1. 신용 매수 사전 점검" in report and "23.0% 하락 시" in report


def _cli(*args):
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    env.pop("PYTHONPATH", None)  # README 예시처럼 PYTHONPATH 없이 실행돼야 한다
    return subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True,
                          encoding="utf-8", env=env, check=False)


def test_rule_builder_routes_collateral_alert_instead_of_price_rule():
    proc = _cli(SCRIPTS / "rule_builder.py", "--intent", "담보비율 150% 아래로 내려가면 알려줘",
                "--parser", "deterministic", "--account", EXAMPLES / "watch.json")
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["kind"] == "collateral_alert" and result["decision"] == "NOTIFY"


def test_margin_check_cli_exit_codes():
    assert _cli(SCRIPTS / "margin_check.py", "assess", "--account", EXAMPLES / "watch.json").returncode == 0
    assert _cli(SCRIPTS / "margin_check.py", "assess", "--account", EXAMPLES / "shortfall_round2.json").returncode == 1
    bad = _cli(SCRIPTS / "margin_check.py", "assess", "--account", EXAMPLES / "missing.json")
    assert bad.returncode == 2


def test_timeline_skips_krx_holidays():
    """연말: 12/30(수) 담보부족 → D+1 납부 기한은 1/4(월), D+2 반대매매는 1/5(화). 12/31 연말휴장일·1/1 신정 제외."""
    result = assess_account(account(135_000_000, shortfall_date="2026-12-30", as_of="2026-12-30"), RULES)
    timeline = result["timeline"]
    assert (timeline["deposit_deadline"], timeline["liquidation_date"]) == ("2027-01-04", "2027-01-05")
    assert timeline["skipped_holidays"] == ["2026-12-31", "2027-01-01"]
    assert any("휴장일 2026-12-31, 2027-01-01" in line for line in result["explanation"])
    assert "KRX_HOLIDAYS" in {s["id"] for s in result["sources"]}


def test_timeline_beyond_holiday_calendar_warns():
    result = assess_account(account(115_000_000, as_of="2027-12-30"), RULES)  # 긴급 → D+1, 12/31 휴장 → 2028-01-03
    assert result["timeline"]["liquidation_date"] == "2028-01-03"
    assert any("2027-12-31까지만 확인" in w for w in result["warnings"])
