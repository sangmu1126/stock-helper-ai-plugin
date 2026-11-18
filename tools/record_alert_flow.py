"""Record the local price-alert flow end to end in a fresh workspace (Windows only).

draft -> settings check -> register -> watch -> Windows notification -> stop (Ctrl+C).

The flow uses the synthetic demo-fixture provider so that the condition can match; its notifications are
labelled [DEMO]. A separate step runs the same watcher once against Yahoo Finance (yfinance) and records why it
did or did not notify. Nothing here places orders. A desktop screenshot of the notification corner is taken
only with --screenshot and must be reviewed before it is shared.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import platform
import queue
import subprocess
import sys
import tempfile
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "src/skills/safe-trade-rule-builder/scripts"
KST = ZoneInfo("Asia/Seoul")
DEMO_SYMBOL = "035720.KS"
# Processes started from IDE/agent shells can inherit "ignore Ctrl+C"; a normal terminal does not. The watcher is
# started through this launcher so that it handles Ctrl+C the way it does in a terminal. alert_watch.py is unchanged.
WATCH_LAUNCHER = """
import ctypes, os, runpy, sys
ctypes.windll.kernel32.SetConsoleCtrlHandler(None, False)
script = sys.argv[1]
sys.argv = sys.argv[1:]
sys.path.insert(0, os.path.dirname(script))
runpy.run_path(script, run_name="__main__")
"""
STOP_HELPER = """
import ctypes, sys, time
k = ctypes.WinDLL("kernel32", use_last_error=True)
k.FreeConsole()
if not k.AttachConsole(int(sys.argv[1])):
    raise SystemExit(f"AttachConsole failed: {ctypes.get_last_error()}")
k.SetConsoleCtrlHandler(None, True)   # this helper ignores the Ctrl+C it sends
sent = k.GenerateConsoleCtrlEvent(0, 0)  # CTRL_C_EVENT to the watcher's console
time.sleep(1)
k.FreeConsole()
raise SystemExit(0 if sent else 1)
"""


def open_session() -> str:
    sys.path.insert(0, str(SCRIPTS))
    from session_window import evaluate_time_window

    now = datetime.now(UTC)
    for session in ("regular", "after_hours"):
        if evaluate_time_window({"market_session": session}, DEMO_SYMBOL, now)["status"] == "OK":
            return session
    raise SystemExit("Run this during a KRX regular session (09:00-15:30 KST) or after-market (16:00-20:00 KST).")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "docs/media/alert-flow")
    parser.add_argument("--screenshot", action="store_true", help="Capture the bottom-right notification corner.")
    args = parser.parse_args()
    if os.name != "nt":
        raise SystemExit("Windows only: the flow submits Windows notifications.")
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # physical pixels for the screenshot
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    session = open_session()
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    steps: list[dict] = []

    with tempfile.TemporaryDirectory(prefix="safe-trade-alert-") as directory:
        work = Path(directory)
        db, real_db = work / "rule-output/alerts.sqlite3", work / "rule-output/real.sqlite3"

        def clean(value: str) -> str:
            for path, label in ((work, "<fresh-workspace>"), (ROOT, "<repo>")):
                for form in (str(path), path.as_posix(), json.dumps(str(path))[1:-1]):
                    value = value.replace(form, label)
            profile = os.environ.get("USERPROFILE", "")
            for form in (profile, profile.replace("\\", "/"), json.dumps(profile)[1:-1]):
                if form:
                    value = value.replace(form, "<user>")
            return value

        def stamp() -> str:
            return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST")

        def write(step: str, text: str) -> None:
            with (out / f"{step}.txt").open("a", encoding="utf-8", newline="\n") as handle:
                handle.write("\n".join(line.rstrip() for line in clean(text).splitlines()) + "\n\n")

        def run(step, label, command, *, expected=0, contains=None):
            result = subprocess.run([sys.executable, *map(str, command)], cwd=work, env=env, capture_output=True,
                                    text=True, encoding="utf-8", errors="replace", timeout=120, check=False)
            passed = result.returncode == expected and (contains is None or contains in result.stdout + result.stderr)
            write(step, f"## {label}\ntime: {stamp()}\n"
                        f"command: {subprocess.list2cmdline(['python', *map(str, command)])}\n"
                        f"exit_code: {result.returncode} (expected {expected}) expectation_met: {passed}\n"
                        f"STDOUT\n{result.stdout}STDERR\n{result.stderr}")
            steps.append({"step": step, "check": label, "exit_code": result.returncode, "expectation_met": passed})
            print(f"{step} | {label}: exit={result.returncode} ok={passed}", flush=True)
            return result

        def note(step, label, passed, text):
            write(step, f"## {label}\ntime: {stamp()}\nexpectation_met: {passed}\n{text}")
            steps.append({"step": step, "check": label, "expectation_met": passed})
            print(f"{step} | {label}: ok={passed}", flush=True)

        for old in out.glob("*.txt"):
            old.unlink()
        watch = [SCRIPTS / "alert_watch.py", "--db", db]
        label = {"regular": "장중에", "after_hours": "애프터마켓에서"}[session]
        intent = f"카카오가 {label} 전일 종가보다 3% 떨어지면 알려줘. 10분에 한 번만."
        rule = {  # what Codex structures from the sentence (see SKILL.md); the script revalidates it
            "asset": {"symbol": DEMO_SYMBOL, "name": "Kakao Corp"},
            "trigger": {"type": "price_drop_percent", "reference": "previous_close", "percent": 3},
            "action": "notify_only", "execution_mode": "notify_only",
            "time_window": {"market_session": session},
            "cooldown": {"min_minutes_between_triggers": 10},
            "cancel_conditions": [{"type": "quote_stale"}], "emotional_risk_flags": [], "ambiguities": [],
        }
        (work / "rule.json").write_text(json.dumps(rule, ensure_ascii=False, indent=2), encoding="utf-8")
        write("01-draft", f"# 1. 초안\n사용자 문장: {intent}\nCodex가 구조화한 룰 JSON(rule.json):\n"
                          f"{json.dumps(rule, ensure_ascii=False, indent=2)}")
        run("01-draft", "rule_builder: 초안 저장과 리포트", [
            SCRIPTS / "rule_builder.py", "--intent", intent, "--rule-json", "rule.json",
            "--save-draft", "rule-output/draft.json", "--format", "markdown"], contains="알림 등록: 아직 미등록")

        draft = json.loads((work / "rule-output/draft.json").read_text(encoding="utf-8"))
        settings = {
            "종목": f"{draft['asset']['name']} ({draft['asset']['symbol']})", "조건": draft["trigger"],
            "행동": f"{draft['action']} / {draft['execution_mode']}", "세션": draft["time_window"],
            "쿨다운": draft["cooldown"], "취소 조건": draft["cancel_conditions"],
            "정책": draft["policy_result"]["decision"],
            "시세 출처": "demo-fixture (합성 데이터, 실제 시세 아님) - 알림 제목에 [DEMO] 표시",
        }
        write("02-confirm", "# 2. 조건 확인\n사용자에게 보여 주고 확인받는 값:\n"
                            + "\n".join(f"- {k}: {json.dumps(v, ensure_ascii=False)}" for k, v in settings.items()))
        run("02-confirm", "확인 없이 등록 시도는 거부", [*watch, "add", "--draft", "rule-output/draft.json",
                                                    "--intent", intent, "--provider", "demo-fixture"],
            expected=2, contains="--confirm")

        added = run("03-register", "확인 후 등록(감시는 아직 시작 안 함)", [
            *watch, "add", "--draft", "rule-output/draft.json", "--intent", intent,
            "--provider", "demo-fixture", "--confirm"], contains='"monitoring_started": false')
        rule_id = json.loads(added.stdout)["registered_rule_id"]
        run("03-register", "상태: 감시 프로세스 없음, 활성 룰 1개", [*watch, "status"],
            contains='"monitoring_running": false')
        run("03-register", "등록 목록", [*watch, "list"], contains=rule_id)

        # 4. watch: a hidden console of its own so that a real Ctrl+C can be delivered later
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 0
        watcher = subprocess.Popen([sys.executable, "-c", WATCH_LAUNCHER, *map(str, watch), "run", "--interval", "60"],
                                   cwd=work, env=env,
                                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, encoding="utf-8", errors="replace",
                                   creationflags=subprocess.CREATE_NEW_CONSOLE, startupinfo=startup)
        lines: queue.Queue[str] = queue.Queue()
        log: list[str] = []

        def pump():
            for line in watcher.stdout:
                entry = f"[{stamp()}] {line.rstrip()}"
                log.append(entry)
                lines.put(line.strip())

        threading.Thread(target=pump, daemon=True).start()
        write("04-watch", f"# 4. 감시\ntime: {stamp()}\ncommand: python alert_watch.py --db <db> run --interval 60\n"
                          "(감시 프로세스 출력은 이 파일 끝에 시각과 함께 붙는다)")

        def next_cycle(timeout: float) -> list:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                try:
                    line = lines.get(timeout=1)
                except queue.Empty:
                    continue
                if line.startswith("["):
                    return json.loads(line)
            raise SystemExit("watcher produced no cycle output in time")

        first = next_cycle(60)
        shot = None
        if args.screenshot and first and first[0].get("status") == "NOTIFY_ONLY":
            from PIL import ImageGrab

            time.sleep(2)
            user32 = ctypes.windll.user32
            width, height, scale = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1), user32.GetDpiForSystem() / 96
            shot = out / "notification.png"
            # only the notification and the taskbar clock; review the image before sharing it
            box = (width - int(390 * scale), height - int(200 * scale), width, height)
            ImageGrab.grab(bbox=box, include_layered_windows=True).save(shot)
        note("04-watch", "1회차: 조건 충족 -> Windows 알림 제출", bool(first) and first[0].get("status") == "NOTIFY_ONLY",
             json.dumps(first, ensure_ascii=False, indent=2))
        run("04-watch", "감시 중 상태", [*watch, "status"], contains='"monitoring_running": true')
        run("04-watch", "두 번째 감시 프로세스는 거부(같은 DB)", [*watch, "run", "--once"],
            expected=2, contains="Another watcher")
        second = next_cycle(90)
        note("04-watch", "2회차(60초 뒤): 쿨다운으로 재알림 안 함",
             bool(second) and second[0].get("reason") == "COOLDOWN_ACTIVE", json.dumps(second, ensure_ascii=False))

        run("05-notify", "알림 이력(제출 기록, 실주문 없음)", [*watch, "events"], contains='"status": "submitted"')

        helper = subprocess.run([sys.executable, "-c", STOP_HELPER, str(watcher.pid)], capture_output=True, text=True,
                                creationflags=subprocess.CREATE_NO_WINDOW, timeout=30, check=False)
        try:
            watcher.wait(timeout=30)
        except subprocess.TimeoutExpired:
            watcher.kill()
            watcher.wait(timeout=30)
        time.sleep(1)
        stderr = watcher.stderr.read()
        write("04-watch", "### 감시 프로세스 출력\n" + "\n".join(log) + (f"\nSTDERR\n{stderr}" if stderr else ""))
        stopped = watcher.returncode == 0 and any("Monitoring stopped" in line for line in log)
        note("06-stop", "Ctrl+C로 감시 종료", stopped,
             f"helper_exit: {helper.returncode} {helper.stderr.strip()}\nwatcher_exit: {watcher.returncode}\n"
             + "\n".join(log[-1:]))
        run("06-stop", "종료 후 상태", [*watch, "status"], contains='"monitoring_running": false')
        run("06-stop", "등록 룰은 남음", [*watch, "list"], contains=rule_id)
        run("06-stop", "룰 삭제", [*watch, "remove", rule_id], contains="notification_history_preserved")
        run("06-stop", "삭제 후 목록", [*watch, "list"], contains="[]")
        run("06-stop", "알림 이력은 보존", [*watch, "events"], contains=rule_id)

        # 7. real quotes: same rule against Yahoo Finance, one cycle only, plus the provider's own delay metadata
        real = [SCRIPTS / "alert_watch.py", "--db", real_db]
        write("07-real-quote", "# 7. 실제 시세(Yahoo Finance, yfinance) 1회 점검\n"
                               "합성 데이터가 아니다. 알림이 나가면 제목에 [DEMO]가 붙지 않는다.")
        probe = ("import json, time, yfinance as yf\n"
                 "for s in ('035720.KS', 'TSLA'):\n"
                 "    i = yf.Ticker(s).info\n"
                 "    print(json.dumps({'symbol': s, 'exchangeDataDelayedBy_min': i.get('exchangeDataDelayedBy'),\n"
                 "        'marketState': i.get('marketState'), 'currency': i.get('currency'),\n"
                 "        'regularMarketPrice': i.get('regularMarketPrice'),\n"
                 "        'quote_age_seconds': int(time.time()) - int(i.get('regularMarketTime') or 0)}))\n")
        run("07-real-quote", "Yahoo 시세 메타데이터(지연 분, 시세 나이)", ["-c", probe])
        run("07-real-quote", "같은 룰을 실제 시세로 등록", [*real, "add", "--draft", "rule-output/draft.json",
                                                 "--intent", intent, "--provider", "yfinance", "--confirm"])
        run("07-real-quote", "1회 평가(run --once)", [*real, "run", "--once"])
        tsla = "테슬라가 200달러 아래로 내려가면 알려줘"
        run("07-real-quote", "TSLA 200달러 이하 초안(오프라인 파서)",
            [SCRIPTS / "rule_builder.py", "--intent", tsla, "--save-draft", "rule-output/tsla.json",
             "--format", "markdown"])
        run("07-real-quote", "TSLA 실제 시세로 등록", [*real, "add", "--draft", "rule-output/tsla.json",
                                                "--intent", tsla, "--provider", "yfinance", "--confirm"])
        run("07-real-quote", "1회 평가(두 룰)", [*real, "run", "--once"])
        run("07-real-quote", "알림 이력", [*real, "events"])

    manifest = json.loads((ROOT / "src/.codex-plugin/plugin.json").read_text(encoding="utf-8"))
    dirty = subprocess.check_output(["git", "status", "--porcelain", "--", "src", "tools"], cwd=ROOT, text=True)
    summary = {
        "recorded_at": datetime.now(KST).isoformat(timespec="seconds"),
        "plugin_version": manifest["version"],
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "uncommitted_source_files": sorted(line[3:] for line in dirty.splitlines()),
        "python": platform.python_version(), "os": f"{platform.system()} {platform.release()}",
        "workspace": "fresh temporary folder with an empty alert database (same state as a new session)",
        "demo_session": session,
        "data_sources": {
            "01-06": "demo-fixture: built-in synthetic prices, not market data; notification titles start with [DEMO]",
            "07": "Yahoo Finance via yfinance: real quotes as delivered by the provider",
        },
        "notification": "real Windows notifications were submitted; 'submitted' is not proof that a person saw it",
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
