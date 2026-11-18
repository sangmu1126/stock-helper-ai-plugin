from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "src/skills/safe-trade-rule-builder/scripts"
sys.path.insert(0, str(SCRIPTS))

from alert_watch import AlertStore, WindowsNotifier, check_once, evaluate, validated_rule, worker_lock
from builder import build_rule

NOW = int(datetime(2026, 11, 18, 15, 0, tzinfo=UTC).timestamp())  # 10:00 New York
INTENT = "Notify me when TSLA falls below 200 dollars"


def draft():
    return asdict(build_rule("테슬라가 200달러 아래로 내려가면 알려줘"))


def quote(now=NOW, **overrides):
    return {"symbol": "TSLA", "currency": "USD", "regular_market_price": 190.0,
            "previous_close": 210.0, "market_state": "REGULAR", "timestamp": now,
            "health": {"ok": True}, **overrides}


@pytest.fixture
def store(tmp_path):
    value = AlertStore(tmp_path / "alerts.sqlite3")
    yield value
    value.close()


def run(store, notifier, data=None, now=NOW):
    provider = Mock()
    provider.get_quote.return_value = data or quote(now)
    return check_once(store, notifier, provider_factory=lambda _: provider, clock=lambda: now)


def test_register_revalidates_draft_and_persists(tmp_path):
    path = tmp_path / "alerts.sqlite3"
    first = AlertStore(path)
    rule_id = first.register(INTENT, draft(), "yfinance")
    assert first.register(INTENT, draft(), "yfinance") == rule_id
    assert len(first.rules()) == 1
    first.close()
    reopened = AlertStore(path)
    try:
        assert reopened.rules()[0]["id"] == rule_id
    finally:
        reopened.close()


@pytest.mark.parametrize("field,value", [
    ("action", "prepare_buy_order"), ("ambiguities", [{"field": "asset", "question": "Which?"}]),
    ("emotional_risk_flags", [{"flag": "urgency", "evidence": "now"}]),
    ("trigger", {"type": "price_cross_below", "price": float("nan"), "currency": "USD"}),
    ("trigger", {"type": "price_cross_below", "price": -1, "currency": "USD"}),
    ("time_window", {"expires": "today_only"}),
    ("time_window", {"requires_consecutive_days": 3}),
    ("cooldown", {"min_minutes_between_triggers": -1}),
    ("cancel_conditions", [{"type": "negative_news_requires_manual_review"}]),
])
def test_unsafe_or_unsupported_rules_cannot_register(field, value):
    data = draft()
    data[field] = value
    with pytest.raises(ValueError):
        validated_rule("TSLA price alert", data)


def test_supplied_allow_flag_is_not_trusted():
    data = draft()
    data["trigger"] = {"type": "needs_clarification"}
    data["policy_result"] = {"decision": "ALLOW"}
    with pytest.raises(ValueError):
        validated_rule(INTENT, data)


def test_notify_cooldown_restart_and_new_quote(store):
    rule_id = store.register(INTENT, draft(), "yfinance")
    notifier = Mock()
    assert run(store, notifier)[0]["status"] == "NOTIFY_ONLY"
    assert run(store, notifier, now=NOW + 60)[0]["reason"] == "COOLDOWN_ACTIVE"
    assert notifier.send.call_count == 1
    assert store.rules()[0]["id"] == rule_id
    assert run(store, notifier, now=NOW + 601)[0]["status"] == "NOTIFY_ONLY"
    assert notifier.send.call_count == 2
    assert len(store.events()) == 2
    assert all(event["status"] == "submitted" for event in store.events())


@pytest.mark.parametrize("changes,reason", [
    ({"currency": "KRW"}, "TRIGGER_CURRENCY_MISMATCH"),
    ({"currency": None}, "MISSING_QUOTE_CURRENCY"),
    ({"timestamp": NOW - 16, "age_seconds": 0}, "STALE_QUOTE"),
    ({"timestamp": NOW + 6}, "INVALID_QUOTE_TIMESTAMP"),  # beyond the 5-second clock-skew allowance
    ({"timestamp": 0}, "INVALID_QUOTE_TIMESTAMP"),
    ({"timestamp": None}, "INVALID_QUOTE_TIMESTAMP"),
    ({"symbol": "AAPL"}, "QUOTE_SYMBOL_MISMATCH"),
    ({"health": {"ok": False}}, "MARKET_DATA_HEALTHCHECK_FAILED"),
    ({"market_state": "CLOSED"}, "MARKET_NOT_OPEN"),
    ({"regular_market_price": float("inf")}, "INVALID_QUOTE_PRICE"),
    ({"previous_close": float("nan")}, "INVALID_QUOTE_FIELD"),
])
def test_bad_quotes_never_notify(store, changes, reason):
    store.register(INTENT, draft(), "yfinance")
    notifier = Mock()
    assert run(store, notifier, quote(**changes))[0]["reason"] == reason
    notifier.send.assert_not_called()
    assert store.events() == []


@pytest.mark.parametrize("at,reason", [
    (datetime(2026, 11, 18, 1, tzinfo=UTC), "OUTSIDE_SESSION"),
    (datetime(2026, 11, 26, 15, tzinfo=UTC), "MARKET_HOLIDAY"),
    (datetime(2026, 11, 21, 15, tzinfo=UTC), "OUTSIDE_SESSION"),
    (datetime(2026, 11, 27, 19, tzinfo=UTC), "OUTSIDE_SESSION"),
])
def test_calendar_checked_even_for_plain_regular_session(at, reason):
    now = int(at.timestamp())
    rule = validated_rule(INTENT, draft())
    assert evaluate(rule, quote(now), now)["reason"] == reason


def test_price_not_met_does_not_notify(store):
    store.register(INTENT, draft(), "yfinance")
    notifier = Mock()
    assert run(store, notifier, quote(regular_market_price=205))[0]["status"] == "WAIT"
    notifier.send.assert_not_called()


def test_pause_resume_remove(store):
    rule_id = store.register(INTENT, draft(), "yfinance")
    notifier = Mock()
    store.set_enabled(rule_id, False)
    assert run(store, notifier) == []
    store.set_enabled(rule_id, True)
    assert run(store, notifier)[0]["status"] == "NOTIFY_ONLY"
    store.remove(rule_id)
    assert store.rules() == []
    assert len(store.events()) == 1


def test_notification_error_is_recorded_and_retry_waits_for_fresh_quote(store):
    store.register(INTENT, draft(), "yfinance")
    notifier = Mock()
    notifier.send.side_effect = OSError("desktop unavailable")
    assert run(store, notifier)[0]["reason"] == "NOTIFICATION_FAILED"
    assert store.rules()[0]["last_notified"] is None
    assert store.events()[0]["status"] == "failed"
    notifier.send.side_effect = None
    assert run(store, notifier, now=NOW + 1)[0]["reason"] == "NOTIFICATION_RETRY_BACKOFF"
    assert run(store, notifier, now=NOW + 61)[0]["status"] == "NOTIFY_ONLY"


def test_same_quote_not_sent_twice_even_after_failed_delivery(store):
    store.register(INTENT, draft(), "yfinance")
    notifier = Mock()
    notifier.send.side_effect = RuntimeError("failed")
    run(store, notifier)
    # Fast polling / an adjusted clock must not reuse the same quote event.
    with store.db:
        store.db.execute("UPDATE rules SET last_attempt=NULL")
    assert run(store, notifier)[0]["reason"] == "QUOTE_ALREADY_PROCESSED"
    assert notifier.send.call_count == 1


def test_provider_failure_is_fail_closed(store):
    store.register(INTENT, draft(), "yfinance")
    notifier = Mock()
    provider = Mock()
    provider.get_quote.side_effect = TimeoutError("provider timeout")
    result = check_once(store, notifier, provider_factory=lambda _: provider, clock=lambda: NOW)
    assert result[0]["reason"] == "ALERT_EVALUATION_FAILED"
    notifier.send.assert_not_called()


def test_synthetic_quotes_cannot_masquerade_as_live(store):
    store.register(INTENT, draft(), "yfinance")
    notifier = Mock()
    result = run(store, notifier, quote(health={"ok": True, "demo": True}))
    assert result[0]["reason"] == "SYNTHETIC_QUOTE_IN_LIVE_MODE"
    notifier.send.assert_not_called()


def test_demo_notifications_are_labeled(store):
    store.register(INTENT, draft(), "demo-fixture")
    notifier = Mock()
    run(store, notifier, quote(health={"ok": True, "demo": True}))
    assert notifier.send.call_args.args[0].startswith("[DEMO]")


def test_pc_clock_a_few_seconds_behind_does_not_block_a_fresh_quote(store):
    """A quote stamped 3 s after the PC clock was rejected as 'from the future' before."""
    store.register(INTENT, draft(), "yfinance")
    notifier = Mock()
    assert run(store, notifier, quote(timestamp=NOW + 3))[0]["status"] == "NOTIFY_ONLY"
    notifier.send.assert_called_once()


@pytest.mark.parametrize("ahead,valid", [(3, True), (60, False)])
def test_yfinance_allows_small_clock_skew_only(monkeypatch, ahead, valid):
    import time

    import market_data
    ticker = SimpleNamespace(
        info={"regularMarketTime": int(time.time()) + ahead, "currency": "USD", "marketState": "REGULAR"},
        fast_info=SimpleNamespace(last_price=190, previous_close=210),
    )
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=lambda _: ticker))
    monkeypatch.setattr(market_data, "_history_indicators", lambda *args, **kwargs: (None, None))
    result = market_data.YFinanceMarketDataProvider().get_quote("TSLA")
    assert result.health["ok"] is valid
    assert ("INVALID_QUOTE_TIMESTAMP" in result.health["errors"]) is not valid
    assert result.age_seconds == 0


def test_notification_shows_quote_time_in_market_time_zone(store):
    """Real-flow check showed the toast body as raw epoch seconds ("Quote: 1794987149")."""
    store.register(INTENT, draft(), "yfinance")
    notifier = Mock()
    run(store, notifier, quote())
    message = notifier.send.call_args.args[1]
    assert "quote time 2026-11-18 10:00:00 EST" in message and str(NOW) not in message


def test_worker_lock_blocks_a_second_process(tmp_path):
    path = tmp_path / "alerts.sqlite3"
    code = "from pathlib import Path; from alert_watch import worker_lock; import sys\nwith worker_lock(Path(sys.argv[1])): pass"
    with worker_lock(path):
        result = subprocess.run([sys.executable, "-c", code, str(path)], cwd=SCRIPTS, capture_output=True)
    assert result.returncode != 0
    with worker_lock(path):
        pass


def test_cli_requires_explicit_registration_confirmation(tmp_path):
    data = tmp_path / "draft.json"
    data.write_text(json.dumps(draft()), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "alert_watch.py"), "--db", str(tmp_path / "db.sqlite3"),
         "add", "--intent", INTENT, "--draft", str(data)], capture_output=True,
    )
    assert result.returncode == 2
    assert not (tmp_path / "db.sqlite3").exists()


@pytest.mark.parametrize("setting_name", ["ENABLED", "FIRST_REGISTRATION", "DISABLED_FOR_USER", "NATIVE_FAILURE"])
def test_windows_notifier_passes_text_as_data(monkeypatch, setting_name):
    import alert_watch
    monkeypatch.setattr(alert_watch.os, "name", "nt")
    toaster, toast = Mock(), SimpleNamespace()

    class NativeNotifier:
        @property
        def setting(self):
            if setting_name == "FIRST_REGISTRATION":
                error = OSError("No settings record yet")
                error.winerror = 1168
                raise error
            return SimpleNamespace(name="ENABLED" if setting_name == "NATIVE_FAILURE" else setting_name)

    toaster.toastNotifier = NativeNotifier()
    constructor = Mock(return_value=toaster)
    monkeypatch.setitem(sys.modules, "windows_toasts", SimpleNamespace(
        InteractableWindowsToaster=constructor, Toast=lambda: toast,
    ))
    registry = Mock()
    registry.OpenKey.return_value.__enter__ = Mock()
    registry.OpenKey.return_value.__exit__ = Mock()
    monkeypatch.setitem(sys.modules, "winreg", registry)
    monkeypatch.setattr(alert_watch, "Event", Mock)
    text = "$(Write-Output not-executable)"
    if setting_name == "DISABLED_FOR_USER":
        with pytest.raises(RuntimeError, match="disabled"):
            WindowsNotifier().send("TEST", text)
        toaster.show_toast.assert_not_called()
        return
    if setting_name == "NATIVE_FAILURE":
        toaster.show_toast.side_effect = lambda item: item.on_failed("OS rejected toast")
        with pytest.raises(RuntimeError, match="rejected"):
            WindowsNotifier().send("TEST", text)
        return
    receipt = WindowsNotifier().send("TEST", text)
    assert not receipt["display_confirmed"]
    assert toast.text_fields == ["TEST", text]
    toaster.show_toast.assert_called_once_with(toast)
    assert constructor.call_args.kwargs["notifierAUMID"] == alert_watch.NOTIFICATION_APP_ID


@pytest.mark.parametrize("timestamp", [None, "not-a-timestamp", 0])
def test_yfinance_does_not_invent_a_fresh_source_timestamp(monkeypatch, timestamp):
    import market_data
    ticker = SimpleNamespace(
        info={"regularMarketTime": timestamp, "currency": "USD", "marketState": "REGULAR"},
        fast_info=SimpleNamespace(last_price=190, previous_close=210),
    )
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=lambda _: ticker))
    monkeypatch.setattr(market_data, "_history_indicators", lambda *args, **kwargs: (None, None))
    result = market_data.YFinanceMarketDataProvider().get_quote("TSLA")
    assert result.timestamp == 0
    assert not result.health["ok"]
    assert "INVALID_QUOTE_TIMESTAMP" in result.health["errors"]


def test_cli_save_register_list_pause_and_once(tmp_path):
    path = tmp_path / "draft.json"
    db = tmp_path / "alerts.sqlite3"
    created = subprocess.run(
        [sys.executable, "-X", "utf8", str(SCRIPTS / "rule_builder.py"),
         "--intent", "테슬라가 200달러 아래로 내려가면 알려줘", "--save-draft", str(path)],
        capture_output=True,
    )
    assert created.returncode == 0
    assert json.loads(path.read_text(encoding="utf-8"))["action"] == "notify_only"

    def raw(*args):
        return subprocess.run(
            [sys.executable, "-X", "utf8", str(SCRIPTS / "alert_watch.py"), "--db", str(db), *args],
            capture_output=True, text=True, encoding="utf-8",
        )

    def cli(*args):
        value = raw(*args)
        assert value.returncode == 0, value.stderr
        return value.stdout

    add = ("add", "--draft", str(path), "--intent", INTENT, "--confirm")
    saved = json.loads(cli(*add))
    assert saved["monitoring_started"] is False
    assert (saved["already_registered"], saved["enabled"]) == (False, True)
    assert saved["warnings"] == []
    assert json.loads(cli("status"))["monitoring_running"] is False
    assert len(json.loads(cli("list"))) == 1
    cli("pause", saved["registered_rule_id"])
    # A paused registry runs without any quote request or native notification.
    assert cli("run", "--once").splitlines()[-1] == "[]"
    # Registering the same rule again keeps the explicit pause and says so.
    again = raw(*add)
    assert again.returncode == 0
    assert json.loads(again.stdout) | {"db": None} == saved | {"already_registered": True, "enabled": False, "db": None}
    assert "stays paused" in again.stderr and f"resume {saved['registered_rule_id']}" in again.stderr
    cli("remove", saved["registered_rule_id"])
    assert json.loads(cli("list")) == []
    # Removing an unknown id is an error, not a silent "removed".
    missing = raw("remove", saved["registered_rule_id"])
    assert missing.returncode == 2 and "Unknown rule id" in missing.stderr


@pytest.mark.parametrize(("symbol", "provider", "expected"), [
    ("035720.KS", "yfinance", ["KRX_QUOTES_DELAYED"]),
    ("247540.KQ", "yfinance", ["KRX_QUOTES_DELAYED"]),
    ("035720.KS", "demo-fixture", []),
    ("TSLA", "yfinance", []),
])
def test_registration_warns_only_where_quotes_are_known_to_be_delayed(symbol, provider, expected):
    from alert_watch import registration_warnings
    assert registration_warnings(symbol, provider) == expected


def test_cli_warns_when_a_krx_alert_on_yahoo_quotes_will_not_fire(tmp_path):
    rule = {"asset": {"symbol": "035720.KS", "name": "Kakao Corp"},
            "trigger": {"type": "price_drop_percent", "reference": "previous_close", "percent": 3},
            "action": "notify_only", "execution_mode": "notify_only", "time_window": {"market_session": "regular"},
            "cooldown": {"min_minutes_between_triggers": 10}, "cancel_conditions": [{"type": "quote_stale"}],
            "emotional_risk_flags": [], "ambiguities": []}
    path = tmp_path / "kakao.json"
    path.write_text(json.dumps(rule), encoding="utf-8")

    def add(provider):
        return subprocess.run(
            [sys.executable, "-X", "utf8", str(SCRIPTS / "alert_watch.py"), "--db", str(tmp_path / "alerts.sqlite3"),
             "add", "--draft", str(path), "--intent", "카카오가 3% 떨어지면 알려줘", "--provider", provider, "--confirm"],
            capture_output=True, text=True, encoding="utf-8",
        )

    real = add("yfinance")
    assert real.returncode == 0, real.stderr
    saved = json.loads(real.stdout)
    assert saved["warnings"] == ["KRX_QUOTES_DELAYED"]
    assert "STALE_QUOTE" in real.stderr and f"remove {saved['registered_rule_id']}" in real.stderr
    # Still registered: the warning explains, it does not silently drop the user's confirmed rule.
    store = AlertStore(tmp_path / "alerts.sqlite3")
    try:
        assert [row["id"] for row in store.rules()] == [saved["registered_rule_id"]]
    finally:
        store.close()
    demo = add("demo-fixture")
    assert demo.returncode == 0 and json.loads(demo.stdout)["warnings"] == [] and "STALE_QUOTE" not in demo.stderr


def test_run_repeats_until_interrupt_and_releases_lock(monkeypatch, tmp_path):
    import alert_watch
    db = tmp_path / "alerts.sqlite3"
    cycle = Mock(return_value=[])
    sleeper = Mock(side_effect=[None, KeyboardInterrupt])
    monkeypatch.setattr(alert_watch, "check_once", cycle)
    monkeypatch.setattr(alert_watch.time, "sleep", sleeper)
    monkeypatch.setattr(sys, "argv", ["alert_watch.py", "--db", str(db), "run", "--interval", "60"])
    assert alert_watch.main() == 0
    assert cycle.call_count == 2
    assert sleeper.call_args.args == (60,)
    with worker_lock(db):
        pass


def test_outside_session_does_not_request_quotes(store):
    store.register(INTENT, draft(), "yfinance")
    factory, notifier = Mock(), Mock()
    now = datetime(2026, 11, 18, 1, tzinfo=UTC).timestamp()
    result = check_once(store, notifier, provider_factory=factory, clock=lambda: now)
    assert result[0]["reason"] == "OUTSIDE_SESSION"
    factory.assert_not_called()
    notifier.send.assert_not_called()


def test_cooldown_survives_reopening_database(store):
    store.register(INTENT, draft(), "yfinance")
    notifier = Mock()
    run(store, notifier)
    reopened = AlertStore(store.path)
    try:
        assert run(reopened, notifier, now=NOW + 60)[0]["reason"] == "COOLDOWN_ACTIVE"
        assert notifier.send.call_count == 1
    finally:
        reopened.close()
