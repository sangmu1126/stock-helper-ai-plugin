# Runtime Lambda

`lambda_handler.py` is a deployable AWS Lambda-style runtime for evaluating a generated trading rule before any order is submitted.

Runtime decision flow:

1. Load external policy rules from `policy_rules.json`.
2. Normalize broker health and account-limit inputs through provider contracts.
3. Fail closed on broker, exchange, quote freshness, account limit, duplicate-order, and unsupported action checks.
4. Evaluate the trigger in `evaluation.py`.
5. Combine policy, trigger status, idempotency, and cooldown in `decision_engine.py`.
6. Emit an immutable decision log shape and a confirmation checklist.

It returns:

- `STOP` when a health check or safety guardrail fails
- `WAIT` when the trigger condition is not met yet
- `NOTIFY_ONLY` when a notify-only rule matched and the user should be informed without order preparation
- `MANUAL_CONFIRM` when the rule is eligible to be shown to the user for manual confirmation
- `REQUIRE_CLARIFICATION` or `BLOCK` when policy prevents activation

It never submits live orders.

Deployment files:

- `lambda_handler.py`
- `evaluation.py`
- `policy_engine.py`
- `policy_rules.json`
- `decision_engine.py`
- `state_store.py`
- `decision_log.py`
- `decision_log_store.py`
- `confirmation.py`
- `providers.py`
- `requirements.txt`

AWS Lambda handler:

```text
lambda_handler.lambda_handler
```

Minimal runtime zip example:

```powershell
Compress-Archive -Path src\runtime\*.py,src\runtime\policy_rules.json -DestinationPath runtime-deploy.zip -Force
```

Local smoke test:

```powershell
python -X utf8 -c "import json, importlib.util; spec=importlib.util.spec_from_file_location('lh','src/runtime/lambda_handler.py'); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); event=json.load(open('src/runtime/sample_event.json', encoding='utf-8')); print(m.lambda_handler(event, None))"
```

DynamoDB backend mode:

```powershell
$env:SAFE_TRADE_STATE_BACKEND="dynamodb"
$env:SAFE_TRADE_STATE_TABLE="<state-table-name>"
$env:SAFE_TRADE_DECISION_LOG_BACKEND="dynamodb"
$env:SAFE_TRADE_DECISION_LOG_TABLE="<decision-log-table-name>"
```

State rows use `pk=IDEMPOTENCY#...` or `pk=RULE#...`. Decision-log rows use `decision_id` as the primary key.

SAM deploy with DynamoDB backends:

```powershell
sam deploy --template-file .aws-sam\build\template.yaml `
  --stack-name safe-trade-rule-builder-integration `
  --region ap-northeast-2 `
  --capabilities CAPABILITY_IAM CAPABILITY_AUTO_EXPAND `
  --resolve-s3 `
  --parameter-overrides StateBackend=dynamodb DecisionLogBackend=dynamodb `
  --no-confirm-changeset `
  --no-fail-on-empty-changeset
```

Production blockers before live trading:

- Set `SAFE_TRADE_STATE_BACKEND=dynamodb` to use `DynamoDBStateStore` with conditional writes for idempotency and consistent reads for cooldown.
- Include quote timestamp and trigger status in idempotency keys, and add TTL to all transient state rows.
- Set `SAFE_TRADE_DECISION_LOG_BACKEND=dynamodb` to use `DynamoDBDecisionLogStore` with immutable `decision_id` conditional writes.
- Implement `KakaoPaySecuritiesBrokerProvider` and `KakaoPaySecuritiesAccountProvider` after approved API credentials and network access are available.
- Keep broker order submission outside this Lambda until a separate authenticated manual-confirmation workflow is approved.
