# Production Checklist

- [x] External policy rule file.
- [x] External risk-limit file.
- [x] External prompt-security rule file.
- [x] Runtime config provider reading local JSON with path overrides.
- [x] Runtime config TTL cache and packaged fallback.
- [x] Decision log records policy, risk, and prompt-security config metadata.
- [x] Local runtime (`runtime_handler.handle_event`) uses the central decision engine.
- [x] Immutable decision-log shape.
- [x] Decision log store interface with in-memory (default) and local JSONL file stores.
- [x] State store interface with in-memory (default) and local JSON file stores for idempotency and cooldown.
- [x] Broker/account provider contracts.
- [x] Response schema version.
- [x] Error taxonomy.
- [x] Runtime observability trace and metrics (structured log on stderr).
- [x] Sensitive field redaction.
- [x] Demo events for allowed and stopped paths.
- [x] Runtime environment variable contract.
- [x] Operator runbook.
- [x] Runtime stop-level classification for hard stop, wait, clarify, confirm, and notify.
- [x] Idempotency keys include trigger status and quote timestamp.
- [x] Backtest output is explicitly marked as safety behavior review, not profit forecasting.
- [x] Duplicate decisions blocked across runs with the file state backend (tested).
- [x] No cloud SDK dependency in the plugin source (tested).

Still blocked without external access:

- KakaoPay Securities API integration.
- Broker credential handling for a real account connection.
- Continuous rule monitoring (scheduler, live quote feed, notification channel).
- Regulated manual-confirmation approval flow.
