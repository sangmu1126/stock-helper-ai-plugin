"""Thin wrapper that delegates to the canonical runtime module."""
from __future__ import annotations

from runtime_bridge import load_runtime_module

_MOD = load_runtime_module("decision_engine")

DecisionResult = _MOD.DecisionResult
DecisionEngine = _MOD.DecisionEngine
cooldown_to_seconds = _MOD.cooldown_to_seconds
normalize_reasons = _MOD.normalize_reasons
make_idempotency_key = _MOD.make_idempotency_key
