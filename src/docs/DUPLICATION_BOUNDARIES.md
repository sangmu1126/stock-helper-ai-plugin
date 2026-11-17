# Runtime and Skill Code Boundaries

## Single-sourced modules

The skill CLI reuses these runtime implementations through `scripts/runtime_bridge.py`:

- `runtime/confirmation.py`
- `runtime/policy_engine.py`

This avoids maintaining duplicate safety checklist and policy decision logic.

Prompt injection patterns intentionally remain as Python constants in both surfaces for now. The structures expose pattern ids, severities, and reason codes so they can move to a separate audited policy file later without changing downstream decision logs.

## Intentionally separate modules

The following files still exist in both `runtime/` and `skills/.../scripts/` because they serve different surfaces:

- `evaluation.py`: runtime event evaluation versus richer skill/backtest support
- `providers.py`: runtime event providers versus local market-data provider helpers

`decision_engine.py`, `decision_log*.py`, `state_store.py`, `runtime_config.py`, and `session_window.py` in `scripts/` are thin wrappers that load the runtime implementation through `runtime_bridge.py`. Session hours and special days live only in `runtime/market_sessions.json`.

The in-house `margin-rule-check` skill imports `margin_guard.py` and `config/margin_rules.json` from the investor skill, so both skills share one rule file.

Do not merge the remaining pairs until a shared package is introduced and both the runtime and Codex skill execution import from that package.
