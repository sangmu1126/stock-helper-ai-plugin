"""Persist notify-only rules and poll quotes while this local process is running."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sqlite3
import sys
import time
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from threading import Event
from typing import Any
from zoneinfo import ZoneInfo

from builder import build_rule, safe_lookback_days
from evaluation import evaluate_trigger
from market_data import get_provider
from schema import ParsedRule
from session_window import allowed_market_states, evaluate_time_window, load_sessions, market_for_symbol

DEFAULT_DB = Path("rule-output/alerts.sqlite3")
NOTIFICATION_APP_ID = "AXHackathon.SafeTrade.PriceAlerts"
SUPPORTED_TRIGGERS = {
    "price_cross_below", "price_cross_above", "price_drop_percent", "price_rise_percent",
    "recent_high_drop_percent", "moving_average_breakdown", "volatility_move_percent",
}


def encode(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def validated_rule(intent: str, payload: dict[str, Any]) -> dict[str, Any]:
    # Accept either a ParsedRule input or the full rule_builder.py JSON output.
    fields = {key: value for key, value in payload.items() if key in ParsedRule.model_fields}
    draft = asdict(build_rule(intent, rule_payload=fields))
    if draft["action"] != "notify_only" or draft["execution_mode"] != "notify_only":
        raise ValueError("Only notify_only rules may be registered; orders are never supported.")
    if draft["ambiguities"] or draft["emotional_risk_flags"] or draft["parser"].get("warnings"):
        raise ValueError("Resolve ambiguities, emotional flags, and parser warnings before registration.")
    if draft["policy_result"]["decision"] != "ALLOW":
        raise ValueError("The policy did not allow this rule.")
    if draft["asset"]["symbol"] in {"", "UNKNOWN"}:
        raise ValueError("A known symbol is required.")
    if draft["trigger"]["type"] not in SUPPORTED_TRIGGERS:
        raise ValueError("This trigger cannot be monitored.")
    trigger = draft["trigger"]
    if trigger["type"].startswith("price_cross"):
        positive_number(trigger.get("price"), "trigger.price")
        if not trigger.get("currency"):
            raise ValueError("An explicit trigger currency is required.")
    elif trigger["type"] != "moving_average_breakdown":
        positive_number(trigger.get("percent"), "trigger.percent")
    if trigger["type"] in {"price_drop_percent", "price_rise_percent"}:
        if trigger.get("reference") != "previous_close":
            raise ValueError("Percent alerts currently require previous_close.")
    if draft["time_window"].get("expires") or draft["time_window"].get("requires_consecutive_days"):
        raise ValueError("Expiry and consecutive-day alerts are not supported by this watcher.")
    if any(item["type"] != "quote_stale" for item in draft["cancel_conditions"]):
        raise ValueError("Manual-review/news/volume cancel conditions cannot be monitored automatically.")
    for key, value in draft["cooldown"].items():
        if value is not None and (not math.isfinite(float(value)) or value < 0):
            raise ValueError(f"Invalid cooldown: {key}")
    return {key: draft[key] for key in ParsedRule.model_fields}


def positive_number(value: Any, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{label} must be a finite positive number.")


class AlertStore:
    def __init__(self, path: Path):
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS rules (
                id TEXT PRIMARY KEY, intent TEXT NOT NULL, payload TEXT NOT NULL,
                provider TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
                created_at INTEGER NOT NULL, last_checked INTEGER,
                last_result TEXT, last_attempt INTEGER, last_notified INTEGER
            );
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY, rule_id TEXT NOT NULL, quote_timestamp INTEGER NOT NULL,
                attempted_at INTEGER NOT NULL, status TEXT NOT NULL, message TEXT NOT NULL,
                detail TEXT, UNIQUE(rule_id, quote_timestamp)
            );
        """)

    def close(self) -> None:
        self.db.close()

    def register(self, intent: str, payload: dict[str, Any], provider: str) -> str:
        if provider not in {"yfinance", "demo-fixture"}:
            raise ValueError("Use yfinance, or explicitly selected demo-fixture (synthetic data).")
        rule = validated_rule(intent, payload)
        semantic = {key: rule[key] for key in ("asset", "trigger", "action", "time_window", "cooldown", "cancel_conditions")}
        rule_id = hashlib.sha256(encode([semantic, provider]).encode()).hexdigest()[:20]
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO rules(id,intent,payload,provider,created_at) VALUES(?,?,?,?,?)",
                (rule_id, intent, encode(rule), provider, int(time.time())),
            )
        return rule_id

    def rules(self, *, active: bool = False) -> list[dict[str, Any]]:
        query = "SELECT * FROM rules" + (" WHERE enabled=1" if active else "") + " ORDER BY created_at,id"
        return [dict(row) for row in self.db.execute(query)]

    def set_enabled(self, rule_id: str, enabled: bool) -> None:
        with self.db:
            cursor = self.db.execute("UPDATE rules SET enabled=? WHERE id=?", (int(enabled), rule_id))
            if not cursor.rowcount:
                raise ValueError("Unknown rule id.")

    def remove(self, rule_id: str) -> None:
        with self.db:
            self.db.execute("DELETE FROM rules WHERE id=?", (rule_id,))

    def events(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self.db.execute("SELECT * FROM notifications ORDER BY id DESC LIMIT 100")]


@contextmanager
def worker_lock(path: Path):
    """An OS lock is released on exit/crash, unlike a stale PID file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(path.suffix + ".lock").open("a+b") as handle:
        handle.seek(0)
        handle.write(b"0")
        handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise ValueError("Another watcher is already using this database.") from exc
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


class WindowsNotifier:
    def send(self, title: str, message: str) -> dict[str, Any]:
        if os.name != "nt":
            raise RuntimeError("Desktop notifications currently require Windows.")
        try:
            from windows_toasts import InteractableWindowsToaster, Toast
        except ImportError as exc:
            raise RuntimeError("Install Windows dependencies with: python -m pip install windows-toasts") from exc
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, f"SOFTWARE\\Classes\\AppUserModelId\\{NOTIFICATION_APP_ID}"):
                pass
        except FileNotFoundError as exc:
            raise RuntimeError("Run alert_watch.py setup-notifications once to register the notification app.") from exc
        toaster = InteractableWindowsToaster("Safe Trade Price Alerts", notifierAUMID=NOTIFICATION_APP_ID)
        setting_name = "UNAVAILABLE"
        try:
            setting_name = toaster.toastNotifier.setting.name
        except OSError as exc:
            # Windows can lack a settings record until a new app sends its first toast.
            if getattr(exc, "winerror", None) not in {1168, -2147023728}:
                raise
        if setting_name not in {"ENABLED", "UNAVAILABLE"}:
            raise RuntimeError(f"Windows notifications are disabled: {setting_name}")
        notification = Toast()
        notification.text_fields = [title[:120], message[:500]]
        failures, failed = [], Event()

        def on_failed(event):
            failures.append(str(event))
            failed.set()

        notification.on_failed = on_failed
        toaster.show_toast(notification)
        failed.wait(1)
        if failures:
            raise RuntimeError(f"Windows rejected the notification: {failures[0]}")
        return {"backend": "windows-toasts", "notification_setting": setting_name, "display_confirmed": False}


def setup_notifications() -> None:
    if os.name != "nt":
        raise RuntimeError("Notification app registration requires Windows.")
    import winreg
    # App identity only; do not change notification preferences or security policy.
    key_path = f"SOFTWARE\\Classes\\AppUserModelId\\{NOTIFICATION_APP_ID}"
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key_path) as key:
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, "Safe Trade Price Alerts")


def evaluate(rule: dict[str, Any], quote: dict[str, Any], now: int) -> dict[str, Any]:
    symbol = rule["asset"]["symbol"]
    if quote.get("symbol") != symbol:
        return {"status": "STOP", "reason": "QUOTE_SYMBOL_MISMATCH"}
    timestamp = quote.get("timestamp")
    if isinstance(timestamp, bool) or not isinstance(timestamp, int) or timestamp <= 0 or timestamp > now:
        return {"status": "STOP", "reason": "INVALID_QUOTE_TIMESTAMP"}
    price = quote.get("regular_market_price")
    try:
        positive_number(price, "quote.price")
    except ValueError:
        return {"status": "STOP", "reason": "INVALID_QUOTE_PRICE"}
    if not quote.get("currency"):
        return {"status": "STOP", "reason": "MISSING_QUOTE_CURRENCY"}
    for key in ("previous_close", "day_high", "recent_high", "moving_average", "move_percent"):
        value = quote.get(key)
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value)
            or (key != "move_percent" and value <= 0)
        ):
            return {"status": "STOP", "reason": "INVALID_QUOTE_FIELD", "field": key}
    quote = {**quote, "age_seconds": now - timestamp}
    result = evaluate_trigger(rule["trigger"], quote, allowed_states=allowed_market_states(rule["time_window"]))
    if result["status"] != "MATCHED":
        return result
    # Unlike draft-only evaluation, regular-session alerts always check the calendar.
    window = evaluate_time_window(rule["time_window"], symbol, datetime.fromtimestamp(now, UTC))
    if window["status"] != "OK":
        return {"status": "WAIT", "reason": window["reason"], "time_window": window}
    return result


def quote_time_text(symbol: str, timestamp: int) -> str:
    """Show the source quote time in the market's own time zone instead of raw epoch seconds."""
    sessions = load_sessions()
    zone = ZoneInfo(sessions["markets"][market_for_symbol(symbol, sessions)]["tz"])
    return datetime.fromtimestamp(timestamp, zone).strftime("%Y-%m-%d %H:%M:%S %Z")


def check_once(store: AlertStore, notifier: Any, *, provider_factory=get_provider, clock=time.time) -> list[dict[str, Any]]:
    results = []
    for saved in store.rules(active=True):
        rule_id, quote = saved["id"], None
        try:
            rule = validated_rule(saved["intent"], json.loads(saved["payload"]))
            window = evaluate_time_window(rule["time_window"], rule["asset"]["symbol"], datetime.fromtimestamp(clock(), UTC))
            if window["status"] != "OK":
                result = {"status": "WAIT", "reason": window["reason"], "time_window": window}
            else:
                raw = provider_factory(saved["provider"]).get_quote(
                    rule["asset"]["symbol"], lookback_days=safe_lookback_days(rule["trigger"]),
                )
                quote = raw if isinstance(raw, dict) else asdict(raw)
                if quote.get("health", {}).get("demo") and saved["provider"] != "demo-fixture":
                    result = {"status": "STOP", "reason": "SYNTHETIC_QUOTE_IN_LIVE_MODE"}
                else:
                    result = evaluate(rule, quote, int(clock()))
        except Exception as exc:  # noqa: BLE001 - one provider failure must not stop other rules
            result = {"status": "STOP", "reason": "ALERT_EVALUATION_FAILED", "detail": str(exc)}
        now = int(clock())
        event_id = None
        with store.db:
            current = store.db.execute("SELECT * FROM rules WHERE id=? AND enabled=1", (rule_id,)).fetchone()
            if current is None:
                continue
            if result["status"] == "MATCHED":
                cooldown = rule["cooldown"]
                seconds = max(
                    60, int((cooldown.get("min_minutes_between_triggers") or 0) * 60),
                    int((cooldown.get("min_days_between_triggers") or 0) * 86400),
                )
                if current["last_notified"] is not None and now - current["last_notified"] < seconds:
                    result = {"status": "WAIT", "reason": "COOLDOWN_ACTIVE"}
                elif current["last_attempt"] is not None and now - current["last_attempt"] < 60:
                    result = {"status": "WAIT", "reason": "NOTIFICATION_RETRY_BACKOFF"}
                else:
                    price, currency = quote["regular_market_price"], quote["currency"]
                    prefix = "[DEMO] " if saved["provider"] == "demo-fixture" else ""
                    title = f"{prefix}Safe Trade: {rule['asset']['symbol']}"
                    quoted_at = quote_time_text(rule["asset"]["symbol"], quote["timestamp"])
                    message = f"Condition matched: {price:g} {currency} (quote time {quoted_at}). No order submitted."
                    cursor = store.db.execute(
                        "INSERT OR IGNORE INTO notifications(rule_id,quote_timestamp,attempted_at,status,message) "
                        "VALUES(?,?,?,'submitting',?)", (rule_id, quote["timestamp"], now, message),
                    )
                    if cursor.rowcount:
                        event_id = cursor.lastrowid
                        store.db.execute("UPDATE rules SET last_attempt=? WHERE id=?", (now, rule_id))
                    else:
                        result = {"status": "WAIT", "reason": "QUOTE_ALREADY_PROCESSED"}
            store.db.execute("UPDATE rules SET last_checked=?,last_result=? WHERE id=?", (now, encode(result), rule_id))
        if event_id is not None:
            try:
                receipt = notifier.send(title, message)
            except Exception as exc:  # noqa: BLE001 - preserve failures for inspection and later fresh-quote retry
                result = {"status": "STOP", "reason": "NOTIFICATION_FAILED", "detail": str(exc)}
                with store.db:
                    store.db.execute("UPDATE notifications SET status='failed',detail=? WHERE id=?", (str(exc), event_id))
            else:
                result = {"status": "NOTIFY_ONLY", "reason": "SUBMITTED_TO_WINDOWS", "notification_id": event_id}
                if isinstance(receipt, dict):
                    result["receipt"] = receipt
                with store.db:
                    store.db.execute("UPDATE notifications SET status='submitted' WHERE id=?", (event_id,))
                    store.db.execute("UPDATE rules SET last_notified=? WHERE id=?", (int(clock()), rule_id))
            with store.db:
                store.db.execute("UPDATE rules SET last_result=? WHERE id=?", (encode(result), rule_id))
        results.append({"rule_id": rule_id, **result})
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    commands = parser.add_subparsers(dest="command", required=True)
    add = commands.add_parser("add", help="Persist an explicitly approved notify-only rule.")
    add.add_argument("--draft", type=Path, required=True)
    add.add_argument("--intent", required=True)
    add.add_argument("--provider", choices=["yfinance", "demo-fixture"], default="yfinance")
    add.add_argument("--confirm", action="store_true", help="Confirm symbol, threshold, session, cooldown and local storage.")
    commands.add_parser("list")
    commands.add_parser("events")
    commands.add_parser("status")
    for name in ("pause", "resume", "remove"):
        commands.add_parser(name).add_argument("id")
    run = commands.add_parser("run", help="Poll until Ctrl+C; stopping this process stops monitoring.")
    run.add_argument("--interval", type=int, default=60)
    run.add_argument("--once", action="store_true")
    commands.add_parser("test-notification", help="Send a clearly labeled test desktop notification, not a stock alert.")
    commands.add_parser("setup-notifications", help="Register this app's display name in the current user's notification registry.")
    args = parser.parse_args()
    if args.command == "add" and not args.confirm:
        parser.error("Review the draft, then pass --confirm to register it. Registration does not start monitoring.")
    if args.command == "run" and args.interval < 60:
        parser.error("--interval must be at least 60 seconds.")
    store = None
    try:
        if args.command == "setup-notifications":
            setup_notifications()
            print(encode({"registered_notification_app": NOTIFICATION_APP_ID}))
            return 0
        if args.command == "test-notification":
            receipt = WindowsNotifier().send("Safe Trade - TEST", "Test notification only. No stock condition was checked. No order submitted.")
            print(encode({"status": "submitted", **receipt}))
            return 0
        store = AlertStore(args.db)
        if args.command == "add":
            rule_id = store.register(args.intent, json.loads(args.draft.read_text(encoding="utf-8-sig")), args.provider)
            print(encode({"registered_rule_id": rule_id, "monitoring_started": False, "db": str(store.path)}))
        elif args.command == "list":
            print(encode(store.rules()))
        elif args.command == "events":
            print(encode(store.events()))
        elif args.command == "status":
            running = False
            try:
                with worker_lock(store.path):
                    pass
            except ValueError:
                running = True
            print(encode({"monitoring_running": running, "active_rules": len(store.rules(active=True)),
                          "db": str(store.path)}))
        elif args.command in {"pause", "resume"}:
            store.set_enabled(args.id, args.command == "resume")
            print(encode({"rule_id": args.id, "enabled": args.command == "resume"}))
        elif args.command == "remove":
            store.remove(args.id)
            print(encode({"removed": args.id, "notification_history_preserved": True}))
        elif args.command == "run":
            with worker_lock(store.path):
                print("Local watcher running; keep this process and PC awake. Ctrl+C stops it.", flush=True)
                while True:
                    print(encode(check_once(store, WindowsNotifier())), flush=True)
                    if args.once:
                        break
                    time.sleep(args.interval)
        return 0
    except KeyboardInterrupt:
        print("Monitoring stopped. Registered rules remain on disk.")
        return 0
    except (OSError, ValueError, RuntimeError, sqlite3.Error) as exc:
        print(f"Alert watcher error: {exc}", file=sys.stderr)
        return 2
    finally:
        if store is not None:
            store.close()


if __name__ == "__main__":
    raise SystemExit(main())
