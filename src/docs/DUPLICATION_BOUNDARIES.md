# Runtime and Skill Code Boundaries

## Single-sourced modules

The skill CLI reuses these runtime implementations through `scripts/runtime_bridge.py`:

- `runtime/confirmation.py`
- `runtime/policy_engine.py`

This avoids maintaining duplicate safety checklist and policy decision logic.

Prompt injection patterns intentionally remain as Python constants in both surfaces for now. The structures expose pattern ids, severities, and reason codes so they can move to AWS AppConfig, SSM Parameter Store, or another audited policy source later without changing downstream decision logs.

## Intentionally separate modules

The following files still exist in both `runtime/` and `skills/.../scripts/` because they serve different surfaces:

- `evaluation.py`: Lambda event evaluation versus richer skill/backtest support
- `decision_engine.py`: Lambda idempotency flow versus local drafting helpers
- `state_store.py`: Lambda memory/DynamoDB runtime versus local file-state test helpers
- `decision_log*.py`: Lambda audit shape versus local file/in-memory drafting support
- `providers.py`: Lambda event providers versus local market-data provider helpers

Do not merge these until a shared package is introduced and both Lambda packaging and Codex skill execution import from that package.
