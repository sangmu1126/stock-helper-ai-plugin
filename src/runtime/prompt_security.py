from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from config_provider import ConfigSnapshot, load_config


@dataclass(frozen=True)
class PromptSecurityPattern:
    id: str
    pattern: str
    severity: str
    reason: str
    enabled: bool = True


PROMPT_SECURITY_VERSION = "prompt-security.safe-trade.v1"
DEFAULT_PROMPT_SECURITY_CONFIG: dict[str, Any] = {
    "version": PROMPT_SECURITY_VERSION,
    "patterns": [
        {"id": "ignore_previous_instructions_ko", "pattern": r"이전\s*지시\s*무시", "severity": "high", "reason": "PROMPT_INJECTION_DETECTED", "enabled": True},
        {"id": "ignore_prior_instructions_ko", "pattern": r"앞(?:선|의)?\s*지시\s*무시", "severity": "high", "reason": "PROMPT_INJECTION_DETECTED", "enabled": True},
        {"id": "system_prompt_request_ko", "pattern": r"시스템\s*프롬프트", "severity": "high", "reason": "PROMPT_INJECTION_DETECTED", "enabled": True},
        {"id": "developer_instruction_bypass_ko", "pattern": r"개발자\s*지시\s*무시", "severity": "high", "reason": "PROMPT_INJECTION_DETECTED", "enabled": True},
        {"id": "ignore_previous_instructions_en", "pattern": r"ignore\s+(?:all\s+)?previous", "severity": "high", "reason": "PROMPT_INJECTION_DETECTED", "enabled": True},
        {"id": "ignore_system_instructions_en", "pattern": r"ignore\s+(?:the\s+)?(?:system|developer)\s+instructions?", "severity": "high", "reason": "PROMPT_INJECTION_DETECTED", "enabled": True},
        {"id": "disregard_previous_en", "pattern": r"disregard\s+(?:all\s+)?previous", "severity": "high", "reason": "PROMPT_INJECTION_DETECTED", "enabled": True},
        {"id": "reveal_system_prompt_en", "pattern": r"reveal\s+(?:the\s+)?(?:system\s+)?prompt", "severity": "high", "reason": "PROMPT_INJECTION_DETECTED", "enabled": True},
        {"id": "auto_order_request_ko", "pattern": r"자동\s*주문\s*해", "severity": "high", "reason": "LIVE_ORDER_PROMPT_BLOCKED", "enabled": True},
        {"id": "automatic_order_request_ko", "pattern": r"자동으로\s*주문", "severity": "high", "reason": "LIVE_ORDER_PROMPT_BLOCKED", "enabled": True},
        {"id": "immediate_order_request_ko", "pattern": r"바로\s*주문", "severity": "high", "reason": "LIVE_ORDER_PROMPT_BLOCKED", "enabled": True},
        {"id": "live_order_request_ko", "pattern": r"실주문", "severity": "high", "reason": "LIVE_ORDER_PROMPT_BLOCKED", "enabled": True},
        {"id": "live_order_request_en", "pattern": r"live\s*order", "severity": "high", "reason": "LIVE_ORDER_PROMPT_BLOCKED", "enabled": True},
        {"id": "place_order_request_en", "pattern": r"place\s+(?:the\s+)?order", "severity": "high", "reason": "LIVE_ORDER_PROMPT_BLOCKED", "enabled": True},
    ],
}


@dataclass(frozen=True)
class PromptSecurityResult:
    safe: bool
    matched_patterns: tuple[str, ...] = ()
    pattern_ids: tuple[str, ...] = ()
    severities: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    config_version: str = PROMPT_SECURITY_VERSION
    config_source: str = "default:packaged"
    config_fallback_used: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "safe": self.safe,
            "pattern_ids": list(self.pattern_ids),
            "severities": list(self.severities),
            "reasons": list(self.reasons),
            "config_version": self.config_version,
            "config_source": self.config_source,
            "config_fallback_used": self.config_fallback_used,
        }


def inspect_user_intent(intent: str, config_snapshot: ConfigSnapshot | None = None) -> PromptSecurityResult:
    snapshot = config_snapshot or load_prompt_security_config_snapshot()
    patterns = load_prompt_security_patterns(snapshot)
    normalized = " ".join(intent.strip().split()).lower()
    matches = tuple(item for item in patterns if item.enabled and re.search(item.pattern, normalized, re.IGNORECASE))
    return PromptSecurityResult(
        safe=not matches,
        matched_patterns=tuple(item.pattern for item in matches),
        pattern_ids=tuple(item.id for item in matches),
        severities=tuple(item.severity for item in matches),
        reasons=tuple(dict.fromkeys(item.reason for item in matches)),
        config_version=snapshot.version,
        config_source=snapshot.source,
        config_fallback_used=snapshot.fallback_used,
    )


def load_prompt_security_config_snapshot(config: dict[str, Any] | None = None) -> ConfigSnapshot:
    if config is not None:
        merged = DEFAULT_PROMPT_SECURITY_CONFIG.copy()
        merged.update(config)
        return ConfigSnapshot(
            kind="prompt-security",
            data=merged,
            source="in_memory",
            version=str(merged.get("version", PROMPT_SECURITY_VERSION)),
            loaded_at_epoch_seconds=0,
            fallback_used=False,
        )
    snapshot = load_config(
        kind="prompt-security",
        default_data=DEFAULT_PROMPT_SECURITY_CONFIG,
        local_filename="prompt_security_rules.json",
        env_path_name="SAFE_TRADE_PROMPT_SECURITY_CONFIG_PATH",
    )
    merged = DEFAULT_PROMPT_SECURITY_CONFIG.copy()
    merged.update(snapshot.data)
    return ConfigSnapshot(
        kind=snapshot.kind,
        data=merged,
        source=snapshot.source,
        version=str(merged.get("version", PROMPT_SECURITY_VERSION)),
        loaded_at_epoch_seconds=snapshot.loaded_at_epoch_seconds,
        fallback_used=snapshot.fallback_used,
        error=snapshot.error,
    )


def load_prompt_security_patterns(snapshot: ConfigSnapshot | None = None) -> tuple[PromptSecurityPattern, ...]:
    active_snapshot = snapshot or load_prompt_security_config_snapshot()
    patterns = active_snapshot.data.get("patterns", DEFAULT_PROMPT_SECURITY_CONFIG["patterns"])
    loaded: list[PromptSecurityPattern] = []
    for item in patterns:
        if not isinstance(item, dict):
            continue
        pattern = str(item.get("pattern", ""))
        try:
            re.compile(pattern)
        except re.error:
            continue
        loaded.append(
            PromptSecurityPattern(
                id=str(item.get("id", "unknown_pattern")),
                pattern=pattern,
                severity=str(item.get("severity", "medium")),
                reason=str(item.get("reason", "PROMPT_INJECTION_DETECTED")),
                enabled=bool(item.get("enabled", True)),
            )
        )
    if loaded:
        return tuple(loaded)
    return tuple(load_prompt_security_patterns(load_prompt_security_config_snapshot(DEFAULT_PROMPT_SECURITY_CONFIG)))
