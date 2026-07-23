#!/usr/bin/env python3
"""CLI for generating safe serverless trading-rule drafts."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from builder import build_rule
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
    args = parser.parse_args()
    draft = build_rule(
        args.intent,
        provider_name=args.provider,
        with_market_data=args.with_market_data,
        backtest=args.backtest,
        backtest_period=args.backtest_period,
        backtest_interval=args.backtest_interval,
        parser_strategy=args.parser,
    )
    if args.format == "markdown":
        print(render_markdown_report(draft, locale=args.locale))
    else:
        print(json.dumps(asdict(draft), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
