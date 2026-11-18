---
name: safe-trade-rule-builder
description: Build and validate safe trading-rule drafts, and register persistent local price alerts with Windows desktop notifications. Use for "테슬라 200달러 아래면 알려줘", price monitoring, 알림 등록/감시/중지, rule JSON, or pre-trade safety checks. Also use for credit/margin trading (신용, 빚투, 담보비율, 반대매매): forced-liquidation deadlines and required deposits. Price monitoring requires a running local worker; never submit live orders or claim an alert is active from a draft alone.
---

# Safe Trade Rule Builder

Use this skill to design the decision process, not to predict a correct trade. The output must help the user understand the rule, its missing assumptions, and the stop conditions before any order is considered.

## Safety Position

- Do not recommend a specific stock, target price, or guaranteed outcome.
- Do not produce code that sends a live order by default.
- Default to `manual_confirm` execution mode unless the user explicitly asks for a simulation-only automation flow.
- Convert emotional or vague phrases into bounded, testable conditions.
- Include reasons to wait or revise the rule, not only reasons to proceed.
- Treat unstable market data, stale prices, broker API failures, exchange delays, and missing risk limits as hard stops.

## Persuasion Workflow

1. Restate the user's intent in plain language.
2. Separate emotion from rule: identify revenge trading, fear of missing out, loss recovery, all-in language, or urgency.
3. Convert the intent into mechanical fields: asset, trigger, action, amount limit, time window, cooldown, and confirmation mode.
4. Add safety checks: market status, quote freshness, broker health, duplicate order prevention, max daily loss, max order amount, volatility spike, and circuit breaker state.
5. Produce a decision narrative with three branches: proceed to manual confirmation, wait, or reject the rule.
6. If the user requests live market context, use `--with-market-data` to fetch quote data through the configured provider and evaluate whether the trigger is currently met.
7. If the user asks for backtesting or rule safety validation, use `--backtest` to fetch historical bars and simulate how often the trigger would have fired.
8. Show how the local runtime (`src/runtime/runtime_handler.py`, `handle_event(event)`) evaluates the rule and returns a structured decision without live execution. Everything runs on the user's machine; no cloud account is needed.
9. End with user-facing questions that resolve missing assumptions.

## Parsed Rule Dimensions

Extract these fields when present. If a field is missing or ambiguous, keep the rule inactive and ask a blocking question.

- Asset: company name or direct ticker such as `035720`, `035720.KS`, `086520.KQ`, or a US ticker such as `TSLA`. The offline parser knows common Korean and US names (`scripts/asset_catalog.py`, e.g. SK하이닉스, 네이버, 에코프로, 테슬라, 애플); otherwise ask for the 6-digit code or ticker.
- Action: prepare buy, prepare sell, notify only, or block order.
- Price reference: previous close, current price, average purchase price, fixed KRW price, recent high, or moving average.
- Trigger: percent drop/rise, price cross above/below, recent-high drawdown, moving-average break, or volatility move. Price levels carry a currency: KRW for Korean stocks ("4만원 아래로"), USD for US stocks ("200달러 아래로", "$180 넘으면"). When you write rule JSON for a US stock price level, set `trigger.currency` to `USD`; a KRW price against a USD quote is stopped as `TRIGGER_CURRENCY_MISMATCH`.
- Order size: KRW amount, shares, position fraction, or portfolio/position percent.
- Time window: `market_session` (`regular`, or `after_hours` for the KRX after-market 16:00–20:00 since 2026-09-14), exclude opening minutes, exclude morning, close-only window, today-only, this-week-only, consecutive-day requirement.
- Cooldown: one-per-day, N-day wait, or N-minute wait.
- Cancel conditions: stale quote, negative news review, volume spike review, provider/broker instability, or daily drop threshold.
- Execution mode: notify only or manual confirmation. Never default to live order submission.
- Emotional risk: revenge trading, FOMO, all-in wording, urgency, or loss-recovery wording.

## Turning the Sentence into a Rule (no external AI API)

You (Codex) understand the user's sentence; the scripts do not call any external AI API.

1. Write the rule as JSON that follows the `ParsedRule` schema. Print the schema with `python scripts/rule_builder.py --print-rule-schema`; an example is in `references/rule_json_example.json`.
2. Do not guess. If the asset, amount, trigger, or action is unclear, leave it out and add an item to `ambiguities` with the question to ask.
3. Run `python scripts/rule_builder.py --intent "<the user's original sentence>" --rule-json -` and pass the JSON on stdin (or a file path instead of `-`). Always pass the original sentence: it is checked for prompt injection, and its explicit wording ("매수 후보", "매도 후보", "알려줘") overrides your JSON.
4. Exit code 2 means the JSON did not match the schema. Read the message, fix the JSON, and run again.
5. Without `--rule-json`, the offline parser (`--parser deterministic`, the default) handles common patterns. Use it for quick checks or when you cannot build the JSON.

## Persistent Price Alerts (Windows, local worker)

Price alerts are implemented in `scripts/alert_watch.py`. Do not answer a price-alert request only by saying that monitoring is unavailable. Distinguish a **draft**, **registered rule**, **running watcher**, and **notification submitted to Windows**. No live orders are supported.

1. Build the rule as above and use `rule_builder.py --save-draft <workspace>/rule-output/draft.json` to save the full JSON. Show the symbol, currency, inclusive threshold (the existing price-cross evaluator uses <= / >=), session, cooldown, quote source, and cancel conditions. A 60-second minimum polling/retry interval and 60-second minimum cooldown apply. Defaults are not user-confirmed choices.
2. Before registering or starting continuous monitoring, obtain explicit confirmation of these values and explain that quotes come from Yahoo via yfinance (may be delayed or unavailable), not KakaoPay Securities. The local PC must be awake, connected, and the worker must stay running. A draft-only request must not start a worker.
   **Known limitation — say it before registering a real-quote alert:** the watcher never notifies from a quote older than 15 seconds. Yahoo's KRX quotes are delayed by 20 minutes and it has no KRX after-market quotes, so a Korean-stock alert with the yfinance provider will most likely stay at `STOP / STALE_QUOTE` and never notify, even when the price condition is met. US stocks during the US regular session are different: measured on 2026-11-18, yfinance quotes for TSLA/AAPL/NVDA were 0–2 seconds old (Yahoo labels them "Nasdaq Real Time Price" although `exchangeDataDelayedBy` says 15), and a real-quote TSLA alert was submitted to Windows. This was a five-minute measurement and can change if Yahoo changes its feed. Outside the US regular session the quote time stays at the last regular close, so no alert fires. The limit is intentional (a stale price can mislead), not a bug to work around: do not relax it, and do not present `demo-fixture` notifications as real. Korean-stock alerts would need a real-time provider.
3. After confirmation, register with the command below. `--draft` accepts the complete rule-builder output or ParsedRule JSON; the code revalidates it and does not trust supplied ALLOW flags. `--confirm` means the user reviewed the settings. The DB path must be in the user's workspace, never in the installed plugin cache.

```powershell
python <skill>/scripts/alert_watch.py --db <workspace>/rule-output/alerts.sqlite3 add --draft <workspace>/rule-output/draft.json --intent "테슬라가 200달러 아래로 내려가면 알려줘" --confirm
```

4. Install Windows dependencies with `python -m pip install -r <plugin-root>/requirements.txt`. Run `alert_watch.py setup-notifications` once: this registers only the current user's app identifier/display name, never changes notification preferences or security policy. Use `test-notification` to submit a clearly labeled Windows test toast if the user requests a channel test. OS notification settings / Do Not Disturb may hide it; submission success does not prove the user saw it. Native delivery uses the Windows-Toasts library / Windows SDK, not PowerShell shell interpolation.
5. Start `run --interval 60` in a dedicated local terminal that stays open. If the agent environment cannot keep a process alive after the turn, give the exact terminal command rather than claiming it is running. Never install login tasks/services or bypass sandbox restrictions. Use `run --once` only as a one-cycle check, not as continuous monitoring.

```powershell
python <skill>/scripts/alert_watch.py --db <workspace>/rule-output/alerts.sqlite3 run --interval 60
python <skill>/scripts/alert_watch.py --db <workspace>/rule-output/alerts.sqlite3 status
python <skill>/scripts/alert_watch.py --db <workspace>/rule-output/alerts.sqlite3 list
python <skill>/scripts/alert_watch.py --db <workspace>/rule-output/alerts.sqlite3 events
python <skill>/scripts/alert_watch.py --db <workspace>/rule-output/alerts.sqlite3 pause <rule-id>
python <skill>/scripts/alert_watch.py --db <workspace>/rule-output/alerts.sqlite3 resume <rule-id>
python <skill>/scripts/alert_watch.py --db <workspace>/rule-output/alerts.sqlite3 remove <rule-id>
```

Registering an identical rule again returns the same id; if that rule was paused it stays paused (`already_registered: true`, `enabled: false`), so tell the user to `resume` it. The `add` output also lists `warnings`: `KRX_QUOTES_DELAYED` means a KRX symbol on yfinance quotes, which will most likely never notify (see the known limitation above). The rule is still registered, so tell the user and offer `remove <rule-id>`. Removing an unknown id is an error. The watcher recomputes quote age from the source timestamp (15-second freshness limit; a timestamp up to 5 seconds ahead of the PC clock counts as fresh, further ahead is rejected), checks symbol/currency, policy, actual session/holidays/DST, and persists cooldown and notification attempts in SQLite. Provider/notification failures are recorded rather than claimed as successful delivery. A failed notification can be attempted again with a new fresh quote after 60 seconds. Pausing/deleting takes effect for subsequent checks; an in-flight delivery may already be submitted. Restarting the worker retains cooldown; stopping it or sleeping the PC stops monitoring. A crash between Windows submission and recording success can cause a duplicate after restart; exactly-once delivery is not promised.

Scope: price alerts only. Account/collateral snapshot monitoring, expiry/consecutive-day rules, news/volume/manual-review cancellation, mobile/email delivery, automatic startup, and a guaranteed real-time feed are not implemented. Unsupported conditions are rejected at registration, not silently ignored. `--provider demo-fixture` is explicitly synthetic and notifications are labeled `[DEMO]`; it must never be presented as live market data.

When explaining output, mention the parser state before the safety decision:

1. `parser.source` = `codex`: the rule is your JSON, validated against the schema.
2. `parser.source` = `deterministic`: the offline parser interpreted the sentence.
3. `parser.source` = `deterministic_fallback`: prompt injection was detected in the sentence, so your JSON was ignored and the offline parser was used. Treat the draft with extra caution.
4. If `parser.warnings` is not empty, translate the warnings into plain language before discussing the rule.
5. If `ambiguities` is not empty, keep the rule inactive and ask the listed questions.

## Interpreting Script Output

Read the JSON in this order and explain it to the user in the same order:

1. `parser`, `ambiguities`: explain how the sentence was parsed, whether fallback was used, and which missing assumptions block activation.
2. `asset`, `trigger`, `action`, `execution_mode`: explain what mechanical rule was extracted from the user's sentence.
3. `emotional_risk_flags`: if any flags exist, say the rule should not be activated yet. Explain the exact phrase that triggered the flag and ask the user to rewrite the rule in calmer, bounded terms.
4. `market_data.health`: if `ok` is false, stop. Explain that the data provider failed or returned incomplete data, so the rule cannot be evaluated safely.
5. `trigger_evaluation`: treat `STOP` as a hard stop, `WAIT` as "condition not met or not enough support to act", and `MATCHED` as "eligible for manual confirmation only". If `trigger_evaluation.time_window` is present, the rule's time conditions (장 초반 제외, 오전 제외, 장 마감 N분 전) were checked in the stock's own market time (KRX = Asia/Seoul, US = America/New_York, so US DST is handled). A `TIME_WINDOW_*` reason means the price condition may be met but the time condition is not; explain `time_window.message` and the local time. "N일 연속" conditions cannot be verified from one quote and are held as `WAIT`. Sessions and special days come from `src/runtime/market_sessions.json` (shared with the local runtime): on exchange special days such as the 2026-11-19 suneung day the regular session is 10:00–16:30 and the after-market 17:00–20:00, NYSE early-close days end at 13:00, and a session the exchange has not announced for a special day returns `SESSION_SCHEDULE_UNCONFIRMED`. On an exchange holiday the rule waits with `MARKET_HOLIDAY` (say which holiday); after the published holiday calendar (2027-12-31) it waits with `HOLIDAY_CALENDAR_UNCONFIRMED`. KRX has no pre-market session configured, and US after-hours is not configured; such rules wait with `SESSION_NOT_AVAILABLE`.
6. `policy_result`: explain whether policy allowed the rule, required clarification, or blocked it. Policy decisions override trigger matches.
7. `decision_result`: explain the final orchestrated decision. Treat `BLOCK` and `REQUIRE_CLARIFICATION` as non-activation outcomes.
8. `decision_log`: mention that the decision is auditable through `decision_id`, `rule_id`, policy version, parser version, and market snapshot. Do not expose private user identifiers.
9. `confirmation_checklist`: before `MANUAL_CONFIRM` or `NOTIFY_ONLY`, show the checklist items the user must understand.
10. `backtest`: use this only as rule-safety evidence. Do not present it as profitability, expected return, or future prediction.
11. `backtest.safety_review.warnings`: translate every warning into a plain-language concern before discussing next steps.
12. `user_questions`: ask only the questions that block safe activation.

Decision wording:

- `STOP`: "This rule should not proceed now because <reason>."
- `WAIT`: "The rule is defined, but the current or historical evidence does not justify even a manual confirmation step yet."
- `MATCHED`: "The mechanical condition appears to be met, but the next step is manual confirmation, not automatic order submission."
- `NOTIFY_ONLY`: "The condition appears to be met, but the system should only notify the user and must not prepare an order."
- `REQUIRE_CLARIFICATION`: "The rule cannot be activated until the user resolves the listed policy or parser questions."
- `BLOCK`: "The rule is blocked by policy and should not proceed."
- Emotional flag present: "Before any market check, this wording suggests emotional trading risk."

Backtest warning translations:

- `INSUFFICIENT_HISTORY_FOR_CONFIDENCE`: "There are too few historical bars to trust this rule's behavior."
- `NO_TRIGGER_EVENTS_FOUND`: "This rule did not trigger in the tested period, so it may be too narrow or untested."
- `TRIGGER_TOO_FREQUENT_FOR_BEGINNER_GUARDRAIL`: "This rule would have fired often, which can create overtrading risk for a beginner."
- `HIGH_VOLATILITY_PERIOD_INCLUDED`: "The tested period includes unusually large price moves, so the user should review whether the rule is reacting to stress rather than opportunity."

Recommended answer shape:

```text
1. Extracted rule
- Parser:
- Asset:
- Trigger:
- Action:
- Execution mode:

2. Safety status
- Emotion check:
- Market data health:
- Trigger evaluation:
- Backtest safety:

3. Interpretation
- What this means:
- Why this is not an investment recommendation:
- What would make the rule safer:

4. Next questions
- ...
```

Never say "buy", "sell", "profitable", "expected return", or "safe to execute" as a conclusion. Say "eligible for manual confirmation" only when all required checks pass.

## Credit Trading Guard (신용거래 반대매매 가드)

Why: KakaoPay Securities' credit lending grew 168.5% year over year, complaints rose 829% in H1 2026, and a reported case had a customer told "120% is enough" when the maintenance ratio is 140%. Customers need to know *when* and *how much* to deposit, and the rules (140% / 120% / D+1 / D+2 / temporary grace) are easy to get wrong.

Rules live only in `config/margin_rules.json`, each with a `source` (official credit guide, 2026-11-06 grace notice) or `ASSUMPTION`. Never state a threshold, deadline, or grace condition that is not in that file. Mention `rules_version` when answering.

Routing (automatic in `rule_builder.py`):

- Credit buy intent ("신용으로", "빚투", "미수" + buy) → normal rule plus `margin_guard` (pre-trade check). An acknowledgement question is added, so the decision becomes `REQUIRE_CLARIFICATION`. Explain the starting collateral ratio and the price drop that reaches 140% (shortfall) and 120% (emergency). If the result says the buy starts in shortfall, say so first.
- "담보비율 N% 아래로 내려가면 알려줘" → collateral alert rule (`notify_only`), not a price rule. If N ≤ 140, warn that the alert fires only after the account is already short.
- Questions about 담보비율/반대매매 → rule explanation. If the user believes a ratio below 140% is safe (e.g. "120%만 맞추면"), correct it first.
- With `--account <snapshot.json>`: assess the account.

Explaining an assessment, in this order:

1. Ratio and status (`SAFE` ≥150, `WATCH` 140–150, `SHORTFALL` <140, `EMERGENCY` <120).
2. Timeline. If `timeline.clock` is `EMERGENCY`, the customer must reach 140% **the same day**, even if the ratio is now above 120% after a partial deposit; otherwise liquidation is D+1.
3. Amount to restore 140%: cash deposit or loan repayment (repayment needs less money). These are arithmetic, not advice; exclude interest and fees.
4. Grace (`ELIGIBLE` / `NEEDS_ROUND` / `NOT_ELIGIBLE`) with its conditions (shortfall round 2, 130–140%, 08:00 check, once).
5. Warnings: automatic cash repayment may still run; liquidation sells with a 15–20% haircut, so more shares can be sold than the shortfall.
6. Always add: the app's displayed ratio and schedule take precedence; this is not investment advice.

Do not suggest which stock to sell or recommend taking or avoiding credit. Present the numbers and the deadlines.

```powershell
python src\skills\safe-trade-rule-builder\scripts\margin_check.py assess --account src\skills\safe-trade-rule-builder\examples\margin\misguided_after_deposit.json
python src\skills\safe-trade-rule-builder\scripts\margin_check.py pre-trade --amount 20000000 --account src\skills\safe-trade-rule-builder\examples\margin\watch.json
python src\skills\safe-trade-rule-builder\scripts\margin_check.py alert --threshold 150 --account src\skills\safe-trade-rule-builder\examples\margin\watch.json
python src\skills\safe-trade-rule-builder\scripts\rule_builder.py --intent "담보비율 120%만 맞추면 반대매매 안 되지?" --format markdown
```

Account snapshot fields: `as_of`, `credit_loan`, `accrued_interest`, `cash`, `holdings[{name, quantity, prev_close, grade}]`, `shortfall_round`, `shortfall_date` (first day below 140%), `emergency_date` (day it fell below 120%), `holidays` (extra non-business days; KRX holidays through 2027 are already applied, and `timeline.skipped_holidays` lists the ones skipped). Example accounts under `examples/margin/` are synthetic.

## Script

With rule JSON written by Codex (preferred inside Codex):

```powershell
Get-Content rule.json | python src\skills\safe-trade-rule-builder\scripts\rule_builder.py --intent "카카오 3% 떨어지면 10만원만 매수 후보로 알려줘" --rule-json -
```

With the offline parser only (default):

```powershell
python src\skills\safe-trade-rule-builder\scripts\rule_builder.py --intent "카카오 3% 떨어지면 사줘" --parser deterministic
```

For a user-facing markdown report:

```powershell
python src\skills\safe-trade-rule-builder\scripts\rule_builder.py --intent "카카오 3% 떨어지면 사줘" --format markdown --locale ko
```

With prototype market data from yfinance:

```powershell
python src\skills\safe-trade-rule-builder\scripts\rule_builder.py --intent "카카오 3% 떨어지면 사줘" --with-market-data --provider yfinance --format markdown
```

With historical backtesting from yfinance:

```powershell
python src\skills\safe-trade-rule-builder\scripts\rule_builder.py --intent "카카오 3% 떨어지면 사줘" --backtest --backtest-period 6mo --backtest-interval 1d --provider yfinance --format markdown
```

With built-in warning demo data:

```powershell
python src\skills\safe-trade-rule-builder\scripts\rule_builder.py --intent "카카오 3% 떨어지면 사줘" --backtest --provider demo-fixture --format markdown
```

Use `demo-fixture` only to demonstrate warning behavior without network access. It is synthetic data, not market data.

The script can emit JSON or a markdown report containing:

- normalized rule
- optional market quote from the selected provider
- enriched quote indicators such as recent high, moving average, and move percent when available
- trigger evaluation against the quote
- optional historical trigger simulation
- safety warnings such as no events, too many events, or high-volatility periods
- emotional-risk flags
- pre-trade health checks
- local runtime shape (`runtime_shape`)
- local runtime reference at `src/runtime/runtime_handler.py` (`handle_event(event)`)
- policy and decision orchestration outputs
- immutable decision-log preview
- confirmation checklist for user consent
- explanation prompts for the user

Runtime smoke test:

```powershell
python -X utf8 -c "import json, sys; sys.path.insert(0, 'src/runtime'); import runtime_handler as h; event=json.load(open('src/runtime/sample_event.json', encoding='utf-8')); print(h.handle_event(event)['decision'])"
```

The market-data adapter is intentionally isolated behind `MarketDataProvider.get_quote(symbol) -> MarketQuote` and `MarketDataProvider.get_history(symbol, period, interval)`. Replace the `yfinance` provider with `kakaopay-securities` when an approved KakaoPay Securities API is available.

Use the script output as a draft and refine it for the user's actual context.
