"""Thin wrapper that delegates to the canonical runtime module."""
from __future__ import annotations

from runtime_bridge import load_runtime_module

_MOD = load_runtime_module("decision_log")

stable_id = _MOD.stable_id
create_decision_log = _MOD.create_decision_log
DecisionLog = _MOD.DecisionLog
