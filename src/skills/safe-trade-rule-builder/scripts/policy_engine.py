from __future__ import annotations

import json
from pathlib import Path

from runtime_bridge import load_runtime_module

_POLICY = load_runtime_module("policy_engine")

POLICY_VERSION = _POLICY.POLICY_VERSION
DEFAULT_POLICY_CONFIG = _POLICY.DEFAULT_POLICY_CONFIG
PolicyResult = _POLICY.PolicyResult
PolicyEngine = _POLICY.PolicyEngine


def evaluate_policy(**kwargs):
    return PolicyEngine().evaluate(**kwargs).to_dict()


def load_policy_config(policy_path: Path | None = None):
    if policy_path is None:
        return _POLICY.load_policy_config()
    if not policy_path.exists():
        return DEFAULT_POLICY_CONFIG.copy()
    try:
        with policy_path.open("r", encoding="utf-8") as handle:
            loaded = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return DEFAULT_POLICY_CONFIG.copy()
    config = DEFAULT_POLICY_CONFIG.copy()
    config.update(loaded)
    return config
