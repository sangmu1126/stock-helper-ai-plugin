# Production Checklist

- [x] External policy rule file.
- [x] External risk-limit file.
- [x] External prompt-security rule file.
- [x] Runtime config provider with local, SSM, and AppConfig source boundaries.
- [x] Runtime config TTL cache and packaged fallback.
- [x] Decision log records policy, risk, and prompt-security config metadata.
- [x] Lambda runtime uses the central decision engine.
- [x] Immutable decision-log shape.
- [x] Decision log store interface and DynamoDB adapter for immutable audit logs.
- [x] State store interface and DynamoDB adapter for idempotency and cooldown.
- [x] Broker/account provider contracts.
- [x] Response schema version.
- [x] Error taxonomy.
- [x] Runtime observability trace and metrics.
- [x] Sensitive field redaction.
- [x] AWS SAM scaffold.
- [x] Demo events for allowed and stopped paths.
- [x] Runtime environment variable contract.
- [x] Operator runbook.
- [x] Runtime stop-level classification for hard stop, wait, clarify, confirm, and notify.
- [x] Idempotency keys include trigger status and quote timestamp.
- [x] Backtest output is explicitly marked as safety behavior review, not profit forecasting.
- [x] SAM local container invoke validated for manual-confirm and broker-latency stop paths.
- [x] Real AWS stack deployed with DynamoDB backends.
- [x] Real Lambda invoke validated manual-confirm, duplicate-idempotency, and broker-latency stop paths.

Still blocked without external access:

- KakaoPay Securities API integration.
- Full AppConfig/SSM production rollout with IAM-scoped config resources.
- Secrets Manager broker credential integration.
- CloudWatch alarm deployment.
- Regulated manual-confirmation approval flow.
