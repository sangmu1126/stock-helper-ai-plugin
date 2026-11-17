---
name: safe-trade-rule-builder
description: Convert beginner investors' natural-language buy or sell intent into explainable, mechanical, serverless trading-rule drafts with risk guardrails. Use when the user asks to turn phrases like "buy Kakao if it falls 3%" into rule JSON, Lambda-style code, pre-trade health checks, circuit breakers, or a persuasion process that helps a novice understand whether to buy, sell, wait, or revise the rule without receiving direct investment advice. Also use for credit/margin trading (신용, 빚투, 담보비율, 반대매매): pre-trade forced-liquidation thresholds, collateral shortfall deadlines and required deposit, the 2026-11 temporary grace rule, and collateral-ratio alerts.
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
8. Generate serverless pseudocode or Lambda-style Python that evaluates the rule and returns a structured decision without live execution.
9. End with user-facing questions that resolve missing assumptions.

## Parsed Rule Dimensions

Extract these fields when present. If a field is missing or ambiguous, keep the rule inactive and ask a blocking question.

- Asset: company name or direct ticker such as `035720` or `035720.KS`.
- Action: prepare buy, prepare sell, notify only, or block order.
- Price reference: previous close, current price, average purchase price, fixed KRW price, recent high, or moving average.
- Trigger: percent drop/rise, price cross above/below, recent-high drawdown, moving-average break, or volatility move.
- Order size: KRW amount, shares, position fraction, or portfolio/position percent.
- Time window: regular session, exclude opening minutes, exclude morning, close-only window, today-only, this-week-only, consecutive-day requirement.
- Cooldown: one-per-day, N-day wait, or N-minute wait.
- Cancel conditions: stale quote, negative news review, volume spike review, provider/broker instability, or daily drop threshold.
- Execution mode: notify only or manual confirmation. Never default to live order submission.
- Emotional risk: revenge trading, FOMO, all-in wording, urgency, or loss-recovery wording.

## Parser Strategy

Default to `--parser auto` for production-like prototypes. The auto strategy tries the LLM parser first, validates the response with the Pydantic `ParsedRule` schema, normalizes provider-agnostic fields, then runs the safety validator. If the LLM path is unavailable because `OPENAI_API_KEY` or the OpenAI package is missing, auto falls back to the deterministic parser and records that fallback in `parser.source`, `parser.fallback_used`, and `parser.warnings`.

Use these parser modes intentionally:

- `auto`: preferred default. LLM-first extraction with deterministic fallback.
- `llm`: strict LLM extraction. Use when API access is configured and a failure should stop the run.
- `deterministic`: offline parser for reproducible demos, tests, and network-restricted judging.

When explaining output, always mention the parser state before the safety decision:

1. If `parser.source` is `llm`, explain that the rule was interpreted by schema-constrained LLM parsing and then validated.
2. If `parser.source` is `deterministic_fallback`, explain that the LLM parser was unavailable or failed, so the result is a conservative fallback draft that needs closer human review.
3. If `parser.warnings` is not empty, translate the warnings into plain language before discussing the rule.
4. If `ambiguities` is not empty, keep the rule inactive and ask the listed questions.

## Interpreting Script Output

Read the JSON in this order and explain it to the user in the same order:

1. `parser`, `ambiguities`: explain how the sentence was parsed, whether fallback was used, and which missing assumptions block activation.
2. `asset`, `trigger`, `action`, `execution_mode`: explain what mechanical rule was extracted from the user's sentence.
3. `emotional_risk_flags`: if any flags exist, say the rule should not be activated yet. Explain the exact phrase that triggered the flag and ask the user to rewrite the rule in calmer, bounded terms.
4. `market_data.health`: if `ok` is false, stop. Explain that the data provider failed or returned incomplete data, so the rule cannot be evaluated safely.
5. `trigger_evaluation`: treat `STOP` as a hard stop, `WAIT` as "condition not met or not enough support to act", and `MATCHED` as "eligible for manual confirmation only".
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

Account snapshot fields: `as_of`, `credit_loan`, `accrued_interest`, `cash`, `holdings[{name, quantity, prev_close, grade}]`, `shortfall_round`, `shortfall_date` (first day below 140%), `emergency_date` (day it fell below 120%), `holidays`. Example accounts under `examples/margin/` are synthetic.

## Script

For the default LLM-first parser with deterministic fallback, run:

```powershell
python src\skills\safe-trade-rule-builder\scripts\rule_builder.py --intent "카카오 3% 떨어지면 사줘" --parser auto
```

For a reproducible offline parser demo, run:

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
- serverless deployment shape
- deployable Lambda runtime reference at `src/runtime/lambda_handler.py`
- policy and decision orchestration outputs
- immutable decision-log preview
- confirmation checklist for user consent
- explanation prompts for the user

Runtime smoke test:

```powershell
python -X utf8 -c "import json, importlib.util; spec=importlib.util.spec_from_file_location('lh','src/runtime/lambda_handler.py'); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); event=json.load(open('src/runtime/sample_event.json', encoding='utf-8')); print(m.lambda_handler(event, None))"
```

The market-data adapter is intentionally isolated behind `MarketDataProvider.get_quote(symbol) -> MarketQuote` and `MarketDataProvider.get_history(symbol, period, interval)`. Replace the `yfinance` provider with `kakaopay-securities` when an approved KakaoPay Securities API is available.

Use the script output as a draft and refine it for the user's actual context.
