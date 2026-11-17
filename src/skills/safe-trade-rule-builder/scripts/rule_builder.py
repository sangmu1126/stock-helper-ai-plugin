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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--intent", required=True, help="Natural-language trade intent.")
    parser.add_argument(
        "--provider",
        default="yfinance",
        choices=["demo-fixture", "yfinance", "kakaopay-securities"],
        help="Market data provider adapter.",
    )
    parser.add_argument(
        "--parser",
        default="auto",
        choices=["auto", "llm", "deterministic"],
        help="Parser strategy. auto uses LLM first and falls back to deterministic parsing.",
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
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    account = load_account(args.account) if args.account else None

    # 담보비율 알림·반대매매 질문은 종목 룰이 아니므로 신용거래 가드로 보낸다.
    margin_intent = detect_margin_intent(args.intent)
    if margin_intent.kind in {"collateral_alert", "rule_question"}:
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

    draft = build_rule(
        args.intent,
        provider_name=args.provider,
        with_market_data=args.with_market_data,
        backtest=args.backtest,
        backtest_period=args.backtest_period,
        backtest_interval=args.backtest_interval,
        parser_strategy=args.parser,
        margin_account=account,
    )
    if args.format == "markdown":
        print(render_markdown_report(draft, locale=args.locale))
    else:
        print(json.dumps(asdict(draft), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
