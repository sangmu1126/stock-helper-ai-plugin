# Local Runtime

`runtime_handler.py` evaluates a generated trading rule before any order is considered. It runs entirely on the local machine with the Python standard library; no cloud account or external storage is needed.

Entry point:

```text
runtime_handler.handle_event(event) -> decision object
```

Runtime decision flow:

1. Load policy rules from `policy_rules.json` (or a local override path).
2. Normalize broker health and account-limit inputs through provider contracts.
3. Fail closed on broker, exchange, quote freshness, account limit, duplicate-order, and unsupported action checks.
4. Evaluate the trigger in `evaluation.py`, then the rule's session and time window in `market_sessions.py`.
5. Combine policy, trigger status, idempotency, and cooldown in `decision_engine.py`.
6. Append each evaluation's immutable decision log and return a confirmation checklist.

It returns:

- `STOP` when a health check or safety guardrail fails, or when the runtime itself fails (fail closed)
- `WAIT` when the trigger condition is not met yet, or a duplicate decision is blocked
- `NOTIFY_ONLY` when a notify-only rule matched and the user should be informed without order preparation
- `MANUAL_CONFIRM` when the rule is eligible to be shown to the user for manual confirmation
- `REQUIRE_CLARIFICATION` or `BLOCK` when policy prevents activation

It never submits live orders.

Files:

- `runtime_handler.py`, `evaluation.py`, `event_context.py`, `providers.py`
- `policy_engine.py`, `policy_rules.json`, `risk_controls.py`, `risk_limits.json`, `prompt_security.py`, `prompt_security_rules.json`, `config_provider.py`
- `decision_engine.py`, `decision_log.py`, `confirmation.py`, `ux_classifier.py`, `error_taxonomy.py`, `response_schema.py`, `redaction.py`, `observability.py`
- `config.py`, `store_factory.py`, `state_store.py`, `decision_log_store.py`
- `market_sessions.py`, `market_sessions.json` (shared with the investor skill)

Smoke test:

```powershell
python -X utf8 -c "import json, sys; sys.path.insert(0, 'src/runtime'); import runtime_handler as h; event=json.load(open('src/runtime/sample_event.json', encoding='utf-8')); print(h.handle_event(event)['decision'])"
```

## Sessions and time windows

`rule.time_window` in the event may set `market_session` (`regular` or `after_hours`) and conditions such as `only_before_close_minutes`, `exclude_open_minutes`, `exclude_morning`, or `requires_consecutive_days`. They are checked in the stock's market local time (KRX = Asia/Seoul, US = America/New_York, so US DST is handled). A MATCHED trigger that fails the window becomes `WAIT` with a `TIME_WINDOW_*` reason.

`market_sessions.json` holds the session hours with sources: KRX regular 09:00–15:30, KRX after-market 16:00–20:00 (from 2026-09-14), US regular 09:30–16:00 ET, exchange holidays, and exchange special days. On 2026-11-19 (suneung day) the KRX regular session is 10:00–16:30 and the after-market 17:00–20:00; on NYSE early-close days the US regular session ends at 13:00. A session the exchange has not announced for a special day returns `SESSION_SCHEDULE_UNCONFIRMED`.

Holidays come from the KRX holiday list and the NYSE calendar (2026–2027, `confirmed_through: 2027-12-31`). A time-window rule on a holiday waits with `MARKET_HOLIDAY`; a date after `confirmed_through` waits with `HOLIDAY_CALENDAR_UNCONFIRMED` until the calendar is updated. The credit guard uses the same KRX list for its business-day count. The exchange-status check also follows the session (after-hours rules accept `POST`/`AFTER_HOURS`).

Price-level triggers carry a currency. A trigger in KRW evaluated against a USD quote (or the reverse) stops with `TRIGGER_CURRENCY_MISMATCH`.

## Stores

| Setting | Behavior |
| --- | --- |
| default (`memory`) | A fresh in-memory store per call. For tests and demos. |
| `SAFE_TRADE_STATE_BACKEND=file`, `SAFE_TRADE_STATE_FILE=<path.json>` | Idempotency keys and cooldowns persist in a local JSON file, so a repeated decision is blocked across runs. The key and cooldown are written in one atomic file replace. |
| `SAFE_TRADE_DECISION_LOG_BACKEND=file`, `SAFE_TRADE_DECISION_LOG_FILE=<path.jsonl>` | Decision logs are appended to a local JSONL file. |

Any other backend value is rejected, and the evaluation returns `STOP`. A failed audit write also returns `STOP` through the handler's error boundary.

`query_user_decisions` accepts the original user ID and hashes it for lookup; logs store only `user_id_hash`.

Metrics are written as one JSON line to stderr (set `SAFE_TRADE_METRICS_LOG=0` to turn them off), so the decision output on stdout stays clean.

## Before any live use

- Implement `KakaoPaySecuritiesBrokerProvider` and `KakaoPaySecuritiesAccountProvider` after approved API credentials and network access are available.
- Continuous monitoring of rules (scheduler, live quote feed, notification channel) is not part of this runtime.
- The file stores are for a single machine; concurrent writers to the same file are not supported.
- Keep broker order submission outside this runtime until a separate authenticated manual-confirmation workflow is approved.
