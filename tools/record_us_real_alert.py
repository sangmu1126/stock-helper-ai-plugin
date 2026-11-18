"""Measure real Yahoo Finance quote age in the US regular session and run one real-quote alert (Windows only).

Run during the US regular session (09:30-16:00 New York time). The tool
1. samples TSLA, AAPL and NVDA through the plugin's own yfinance provider and records how old each quote is
   (the watcher only notifies from a quote at most 15 seconds old), and
2. registers one TSLA alert whose condition is certainly met (at or below 10,000 USD) in a fresh workspace and runs
   the watcher once against live quotes, so the real notification path is exercised.
The data is live, not demo-fixture; nothing here places orders. A screenshot of the notification corner is taken
only with --screenshot and must be reviewed before it is shared.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "src/skills/safe-trade-rule-builder/scripts"
KST = ZoneInfo("Asia/Seoul")
SYMBOLS = ("TSLA", "AAPL", "NVDA")
METADATA = ("quoteSourceName", "exchangeDataDelayedBy", "fullExchangeName")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "docs/media/us-real-alert")
    parser.add_argument("--rounds", type=int, default=10, help="quote samples per symbol")
    parser.add_argument("--gap", type=int, default=30, help="seconds between rounds")
    parser.add_argument("--screenshot", action="store_true", help="Capture the bottom-right notification corner.")
    args = parser.parse_args()
    if os.name != "nt":
        raise SystemExit("Windows only: the alert step submits a Windows notification.")
    sys.path.insert(0, str(SCRIPTS))
    from alert_watch import quote_time_text
    from market_data import get_provider
    from models import MAX_QUOTE_AGE_SECONDS
    from session_window import evaluate_time_window

    if evaluate_time_window({"market_session": "regular"}, "TSLA", datetime.now(UTC))["status"] != "OK":
        raise SystemExit("Run this during the US regular session (09:30-16:00 New York time).")
    import yfinance as yf

    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # physical pixels for the screenshot
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.txt"):
        old.unlink()
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    steps: list[dict] = []

    def stamp() -> str:
        return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST")

    # 1. quote age, measured the way the watcher sees it: after the quote has been fetched
    started = stamp()
    provider = get_provider("yfinance")
    metadata = {symbol: {key: yf.Ticker(symbol).info.get(key) for key in METADATA} for symbol in SYMBOLS}
    samples = []
    for round_no in range(1, args.rounds + 1):
        for symbol in SYMBOLS:
            quote = provider.get_quote(symbol, lookback_days=1)
            fetched = int(time.time())
            samples.append({
                "round": round_no, "symbol": symbol, "fetched_at": datetime.now(KST).strftime("%H:%M:%S"),
                "quote_time": quote_time_text(symbol, quote.timestamp) if quote.timestamp > 0 else None,
                "age_seconds": fetched - quote.timestamp, "market_state": quote.market_state,
                "price": quote.regular_market_price, "health_errors": quote.health.get("errors", []),
            })
        print(f"round {round_no}: " + ", ".join(f"{s['symbol']}={s['age_seconds']}s" for s in samples[-len(SYMBOLS):]),
              flush=True)
        if round_no < args.rounds:
            time.sleep(args.gap)
    ages = {}
    for symbol in SYMBOLS:
        values = [s["age_seconds"] for s in samples if s["symbol"] == symbol and not s["health_errors"]]
        ages[symbol] = {"min": min(values, default=None), "max": max(values, default=None), "count": len(values),
                        "within_limit": sum(value <= MAX_QUOTE_AGE_SECONDS for value in values),
                        "health_errors": sum(bool(s["health_errors"]) for s in samples if s["symbol"] == symbol)}
    fresh = all(a["count"] and a["within_limit"] == a["count"] for a in ages.values())
    steps.append({"step": "quotes", "check": f"모든 시세가 {MAX_QUOTE_AGE_SECONDS}초 이하", "expectation_met": fresh})

    rows = [f"| {s['round']} | {s['fetched_at']} | {s['symbol']} | {s['quote_time']} | {s['age_seconds']} | "
            f"{s['market_state']} | {s['price']} | {', '.join(s['health_errors']) or '-'} |" for s in samples]
    lines = [
        "# 미국 정규장 실제 시세 나이 (Yahoo Finance, yfinance)",
        "",
        "합성 데이터가 아닙니다. 플러그인의 yfinance 공급자(market_data.py)로 조회했습니다.",
        f"측정: {started} ~ {stamp()}, {args.rounds}회 x {args.gap}초 간격",
        f"시세 나이 = 조회가 끝난 시각 - 시세 시각(regularMarketTime). 감시는 {MAX_QUOTE_AGE_SECONDS}초 이하인 시세로만 알립니다.",
        "",
        "## Yahoo가 붙인 시세 정보",
        *(f"- {symbol}: " + ", ".join(f"{k}={json.dumps(v, ensure_ascii=False)}" for k, v in meta.items())
          for symbol, meta in metadata.items()),
        "",
        "## 표본",
        "| 회차 | 조회 시각(KST) | 종목 | 시세 시각(현지) | 시세 나이(초) | 장 상태 | 가격 | 헬스 오류 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
        *rows,
        "",
        "## 요약",
        *(f"- {symbol}: 최소 {a['min']}초, 최대 {a['max']}초, {MAX_QUOTE_AGE_SECONDS}초 이하 {a['within_limit']}/{a['count']}, "
          f"헬스 오류 {a['health_errors']}건" for symbol, a in ages.items()),
    ]
    (out / "quotes.txt").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    # 2. one real-quote alert in a fresh workspace
    shot = None
    cycle: list = []
    with tempfile.TemporaryDirectory(prefix="us-real-alert-") as directory:
        work = Path(directory)

        def clean(value: str) -> str:
            for path, label in ((work, "<fresh-workspace>"), (ROOT, "<repo>")):
                for form in (str(path), path.as_posix(), json.dumps(str(path))[1:-1]):
                    value = value.replace(form, label)
            profile = os.environ.get("USERPROFILE", "")
            for form in (profile, profile.replace("\\", "/"), json.dumps(profile)[1:-1]):
                if form:
                    value = value.replace(form, "<user>")
            return value

        def write(text: str) -> None:
            with (out / "alert.txt").open("a", encoding="utf-8", newline="\n") as handle:
                handle.write("\n".join(line.rstrip() for line in clean(text).splitlines()) + "\n\n")

        def run(label, command, *, contains=None):
            result = subprocess.run([sys.executable, *map(str, command)], cwd=work, env=env, capture_output=True,
                                    text=True, encoding="utf-8", errors="replace", timeout=120, check=False)
            passed = result.returncode == 0 and (contains is None or contains in result.stdout + result.stderr)
            write(f"## {label}\ntime: {stamp()}\n"
                  f"command: {subprocess.list2cmdline(['python', *map(str, command)])}\n"
                  f"exit_code: {result.returncode} expectation_met: {passed}\nSTDOUT\n{result.stdout}STDERR\n{result.stderr}")
            steps.append({"step": "alert", "check": label, "exit_code": result.returncode, "expectation_met": passed})
            print(f"alert | {label}: exit={result.returncode} ok={passed}", flush=True)
            return result

        intent = "테슬라가 10000달러 아래면 알려줘"
        rule = {  # the format Codex structures from the sentence (see SKILL.md); the script revalidates it
            "asset": {"symbol": "TSLA", "name": "Tesla"},
            "trigger": {"type": "price_cross_below", "price": 10000, "currency": "USD"},
            "action": "notify_only", "execution_mode": "notify_only",
            "time_window": {"market_session": "regular"},
            "cooldown": {"min_minutes_between_triggers": 10},
            "cancel_conditions": [{"type": "quote_stale"}], "emotional_risk_flags": [], "ambiguities": [],
        }
        (work / "rule.json").write_text(json.dumps(rule, ensure_ascii=False, indent=2), encoding="utf-8")
        write("# 실제 시세 알림 1회 (Yahoo Finance, yfinance)\n"
              "합성 데이터가 아니라서 알림 제목에 [DEMO]가 붙지 않습니다. 실주문은 하지 않습니다.\n"
              "실제 알림 경로를 확인하려고 조건은 반드시 맞도록 정했습니다(TSLA 10,000달러 이하).\n"
              "룰 JSON은 Codex가 문장을 구조화하는 형식으로 이 도구가 넣었습니다(그래서 리포트의 파서 표시가 codex).\n"
              f"사용자 문장: {intent}\n{json.dumps(rule, ensure_ascii=False, indent=2)}")
        watch = [SCRIPTS / "alert_watch.py", "--db", work / "rule-output/alerts.sqlite3"]
        run("rule_builder: 초안 저장과 리포트", [SCRIPTS / "rule_builder.py", "--intent", intent, "--rule-json", "rule.json",
                                         "--save-draft", "rule-output/draft.json", "--format", "markdown"],
            contains="알림 등록: 아직 미등록")
        run("실제 시세(yfinance)로 등록", [*watch, "add", "--draft", "rule-output/draft.json", "--intent", intent,
                                     "--provider", "yfinance", "--confirm"], contains='"monitoring_started": false')
        once = run("1회 평가(run --once)", [*watch, "run", "--once"], contains='"NOTIFY_ONLY"')
        cycle = next((json.loads(line) for line in once.stdout.splitlines() if line.startswith("[")), [])
        if args.screenshot and cycle and cycle[0].get("status") == "NOTIFY_ONLY":
            from PIL import ImageGrab

            time.sleep(1.5)
            user32 = ctypes.windll.user32
            width, height, scale = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1), user32.GetDpiForSystem() / 96
            shot = out / "notification.png"
            # only the notification and the taskbar clock; review the image before sharing it
            box = (width - int(390 * scale), height - int(200 * scale), width, height)
            ImageGrab.grab(bbox=box, include_layered_windows=True).save(shot)
        run("알림 이력(제출 기록, 실주문 없음)", [*watch, "events"], contains='"status": "submitted"')

    manifest = json.loads((ROOT / "src/.codex-plugin/plugin.json").read_text(encoding="utf-8"))
    dirty = subprocess.check_output(["git", "status", "--porcelain", "--", "src", "tools"], cwd=ROOT, text=True)
    summary = {
        "recorded_at": datetime.now(KST).isoformat(timespec="seconds"),
        "plugin_version": manifest["version"],
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "uncommitted_source_files": sorted(line[3:] for line in dirty.splitlines()),
        "python": platform.python_version(), "yfinance": yf.__version__, "os": f"{platform.system()} {platform.release()}",
        "data_source": "Yahoo Finance via yfinance: live quotes, not demo-fixture",
        "freshness_limit_seconds": MAX_QUOTE_AGE_SECONDS,
        "yahoo_metadata": metadata,
        "quote_age_seconds": ages,
        "alert_cycle": cycle,
        "notification": "submitted to Windows; 'submitted' is not proof that a person saw it",
        "screenshot": shot.name if shot else None,
        "orders": "none; the watcher is notify-only",
        "steps": steps,
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    failed = [s for s in steps if not s["expectation_met"]]
    print(f"{len(steps) - len(failed)}/{len(steps)} checks met -> {out}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
