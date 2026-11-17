#!/usr/bin/env python3
"""신용거래 반대매매 가드 CLI.

    python margin_check.py assess    --account account.json [--believed 120]
    python margin_check.py pre-trade [--amount 1000000] [--grade A] [--account account.json]
    python margin_check.py alert     --threshold 150 [--account account.json]
    python margin_check.py explain   [--believed 120] [--as-of 2026-11-18]

종료 코드: 0 정상 · 1 담보부족/긴급(assess) 또는 알림 발생(alert) · 2 입력 오류
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from margin_guard import (
    MarginInputError,
    assess_account,
    build_alert_rule,
    explain_rules,
    load_account,
    load_margin_rules,
    pre_trade_check,
    render_margin_markdown,
)


def _emit(result: dict, fmt: str) -> None:
    if fmt == "markdown":
        print("\n".join(render_margin_markdown(result)))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser(description="신용거래 반대매매 가드")
    parser.add_argument("--rules", type=Path, help="margin_rules.json 경로 (기본: config/margin_rules.json)")
    parser.add_argument("--format", choices=["json", "markdown"], default="markdown")
    sub = parser.add_subparsers(dest="command", required=True)

    assess = sub.add_parser("assess", help="계좌 담보비율·기한·필요 금액·유예 판정")
    assess.add_argument("--account", type=Path, required=True)
    assess.add_argument("--believed", type=float, help="고객이 안전하다고 믿는 담보비율(오해 교정용)")

    pre = sub.add_parser("pre-trade", help="신용 매수 직후 담보비율과 하락 여유")
    pre.add_argument("--amount", type=float)
    pre.add_argument("--grade", help="종목군 A~E (모르면 생략)")
    pre.add_argument("--account", type=Path)

    alert = sub.add_parser("alert", help="담보비율 알림 룰 생성·평가")
    alert.add_argument("--threshold", type=float, required=True)
    alert.add_argument("--account", type=Path)

    explain = sub.add_parser("explain", help="반대매매 기준 설명")
    explain.add_argument("--believed", type=float)
    explain.add_argument("--as-of", type=date.fromisoformat)

    args = parser.parse_args(argv)
    try:
        rules = load_margin_rules(args.rules)
        account = load_account(args.account) if getattr(args, "account", None) else None
        if args.command == "assess":
            result = assess_account(account, rules, believed_safe_pct=args.believed)
            code = 1 if result["status"] in ("SHORTFALL", "EMERGENCY") else 0
        elif args.command == "pre-trade":
            result = pre_trade_check(rules, amount=args.amount, grade=args.grade, account=account)
            code = 0
        elif args.command == "alert":
            result = build_alert_rule(rules, args.threshold, account=account)
            code = 1 if result["decision"] == "NOTIFY" else 0
        else:
            result = explain_rules(rules, believed_safe_pct=args.believed, as_of=args.as_of)
            code = 0
    except (MarginInputError, FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"입력 오류: {exc}", file=sys.stderr)
        return 2
    _emit(result, args.format)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
