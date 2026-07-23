# Safe Trade Runtime Runbook

## Normal Decision Path

1. Confirm `policy_rules.json` and `risk_limits.json` versions.
2. Check Lambda response `schema_version`.
3. Read `decision`, `reasons`, `errors`, and `next_step`.
4. For `MANUAL_CONFIRM`, show the confirmation checklist before any broker workflow.

## Stop Handling

- `BROKER_HEALTHCHECK_FAILED`: keep the rule disabled and check broker status.
- `BROKER_LATENCY_LIMIT_EXCEEDED`: retry later; do not ask for manual order confirmation.
- `QUOTE_TOO_OLD` or `MISSING_QUOTE_TIMESTAMP`: refresh quote data.
- `STALE_QUOTE`, `INVALID_NEGATIVE_QUOTE_TIMESTAMP`, `QUOTE_TIMESTAMP_IN_FUTURE`: treat as hard stops and refresh the quote provider.
- `DAILY_LOSS_LIMIT_REACHED`: block the rule for the day.
- `ORDER_AMOUNT_LIMIT_EXCEEDED`: ask the user to lower the maximum amount.
- `DUPLICATE_ORDER_BLOCKED`: inspect the idempotency key and cooldown state.

## Audit Handling

- Store `decision_log` in an append-only sink.
- For AWS deployments, set `SAFE_TRADE_DECISION_LOG_BACKEND=dynamodb` and `SAFE_TRADE_DECISION_LOG_TABLE=<table-name>`.
- Do not store API keys, tokens, raw account identifiers, or passwords.
- Keep `user_id_hash`, `rule_id`, `idempotency_key`, policy version, and risk-limit version for traceability.
- Confirm that `stop_level` is shown separately from `decision` so users see whether the issue is waitable, clarifiable, or a hard stop.

## State Store Handling

- For local tests, keep `SAFE_TRADE_STATE_BACKEND=memory`.
- For AWS deployments, set `SAFE_TRADE_STATE_BACKEND=dynamodb` and `SAFE_TRADE_STATE_TABLE=<table-name>`.
- Idempotency records use `pk=IDEMPOTENCY#<key>` with `ConditionExpression=attribute_not_exists(pk)`.
- Cooldown records use `pk=RULE#<rule_id>` and consistent reads.
- Transient state rows include `ttl_epoch_seconds`.

## AWS Deployment Blockers

- DynamoDB adapters are implemented, but still need concurrent load testing against real AWS tables.
- IAM policies must be narrowed to the exact state and audit tables.
- Broker/account APIs require approved credentials and network access.
- Live order submission must stay disabled until a separate regulated confirmation flow exists.
