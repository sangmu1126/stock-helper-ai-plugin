# Runtime Config Hotloading

The runtime separates policy-style configuration from decision code while keeping packaged local fallback for reproducible judging and offline tests.

## Hotload Targets

- `policy`: investment-advice blocking patterns, emotional-risk policy actions, clarification behavior.
- `risk`: max daily loss, max order amount, broker latency limit, live-order disable flags.
- `prompt-security`: prompt injection and live-order request patterns.

Core schemas, enum values, decision states, and validation code remain in code because changing them at runtime can break compatibility and auditability.

## Sources

Default source:

- `src/runtime/policy_rules.json`
- `src/runtime/risk_limits.json`
- `src/runtime/prompt_security_rules.json`

Runtime override sources:

- Local file path: `SAFE_TRADE_POLICY_CONFIG_PATH`, `SAFE_TRADE_RISK_LIMITS_PATH`, `SAFE_TRADE_PROMPT_SECURITY_CONFIG_PATH`
- AWS SSM Parameter Store: `SAFE_TRADE_POLICY_SSM_PARAMETER`, `SAFE_TRADE_RISK_SSM_PARAMETER`, `SAFE_TRADE_PROMPT_SECURITY_SSM_PARAMETER`
- AWS AppConfig: `SAFE_TRADE_CONFIG_BACKEND=appconfig` with application, environment, and profile identifiers

## Fallback Rules

- If the selected provider fails, the runtime falls back to packaged local config.
- If the selected JSON is malformed, the runtime falls back to packaged defaults.
- Config is cached with `SAFE_TRADE_CONFIG_TTL_SECONDS` to avoid external provider calls on every Lambda invoke.

## Audit Metadata

Each decision log records:

- config version
- config source
- fallback usage
- prompt-security pattern ids and reasons when matched

This keeps hotloaded decisions explainable even when the code package did not change.
