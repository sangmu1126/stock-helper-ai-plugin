#!/usr/bin/env python3
"""CLI for generating safe trading-rule drafts evaluated by the local runtime."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from builder import build_rule
from margin_guard import (
    assess_account,
    build_alert_rule,
    detect_margin_intent,
    explain_rules,
    load_account,
    load_margin_rules,
    render_margin_markdown,
)
from report_renderer import render_markdown_report
from rule_json import RuleJsonError, rule_json_schema


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--intent", help="Natural-language trade intent (required unless --print-rule-schema).")
    parser.add_argument(
        "--provider",
        default="yfinance",
        choices=["demo-fixture", "yfinance", "kakaopay-securities"],
        help="Market data provider adapter.",
    )
    parser.add_argument(
        "--parser",
        default="deterministic",
        choices=["deterministic"],
        help="Offline parser used when no --rule-json is given.",
    )
    parser.add_argument(
        "--rule-json",
        help="Rule JSON written by Codex from the user's sentence (file path, or - for stdin). "
        "Validated against the ParsedRule schema; see --print-rule-schema.",
    )
    parser.add_argument(
        "--print-rule-schema",
        action="store_true",
        help="Print the ParsedRule JSON schema that --rule-json must follow, then exit.",
    )
    parser.add_argument(
        "--with-market-data",
        action="store_true",
        help="Fetch quote data and evaluate the trigger against the quote.",
    )
    parser.add_argument(
        "--backtest",
        action="store_true",
        help="Fetch historical data and simulate how often the rule would have triggered.",
    )
    parser.add_argument(
        "--backtest-period",
        default="6mo",
        help="History period for provider-backed backtest, for example 1mo, 6mo, 1y.",
    )
    parser.add_argument(
        "--backtest-interval",
        default="1d",
        help="History interval for provider-backed backtest, for example 1d or 1wk.",
    )
    parser.add_argument(
        "--format",
        default="json",
        choices=["json", "markdown"],
        help="Output format.",
    )
    parser.add_argument(
        "--locale",
        default="ko",
        choices=["ko", "en"],
        help="Markdown report language.",
    )
    parser.add_argument(
        "--account",
        type=Path,
        help="Credit account snapshot JSON for margin (반대매매) checks.",
    )
    parser.add_argument("--save-draft", type=Path, help="Save the full JSON draft for review and alert registration.")
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    if args.print_rule_schema:
        print(json.dumps(rule_json_schema(), ensure_ascii=False, indent=2))
        return 0
    if not args.intent:
        parser.error("--intent is required")
    rule_payload = None
    if args.rule_json:
        try:
            raw = sys.stdin.read() if args.rule_json == "-" else Path(args.rule_json).read_text(encoding="utf-8")
            rule_payload = json.loads(raw)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"rule JSON could not be read: {exc}", file=sys.stderr)
            return 2
    account = load_account(args.account) if args.account else None

    # 담보비율 알림·반대매매 질문은 종목 룰이 아니므로 신용거래 가드로 보낸다.
    margin_intent = detect_margin_intent(args.intent)
    if margin_intent.kind in {"collateral_alert", "rule_question"}:
        if args.save_draft:
            parser.error("--save-draft is for price rules; account monitoring is not supported.")
        rules = load_margin_rules()
        if margin_intent.kind == "collateral_alert":
            result = build_alert_rule(
                rules, margin_intent.threshold_pct, account=account,
                believed_safe_pct=margin_intent.believed_safe_pct,
            )
        else:
            result = explain_rules(rules, believed_safe_pct=margin_intent.believed_safe_pct)
            if account is not None:
                result["assessment"] = assess_account(account, rules, believed_safe_pct=margin_intent.believed_safe_pct)
        if args.format == "markdown":
            lines = render_margin_markdown(result)
            if result.get("assessment") and result["kind"] == "rule_explanation":
                lines += render_margin_markdown(result["assessment"], heading="##")
            print("\n".join(lines))
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    try:
        draft = build_rule(
            args.intent,
            provider_name=args.provider,
            with_market_data=args.with_market_data,
            backtest=args.backtest,
            backtest_period=args.backtest_period,
            backtest_interval=args.backtest_interval,
            parser_strategy=args.parser,
            margin_account=account,
            rule_payload=rule_payload,
        )
    except RuleJsonError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.save_draft:
        args.save_draft.parent.mkdir(parents=True, exist_ok=True)
        args.save_draft.write_text(json.dumps(asdict(draft), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.format == "markdown":
        print(render_markdown_report(draft, locale=args.locale))
    else:
        print(json.dumps(asdict(draft), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
