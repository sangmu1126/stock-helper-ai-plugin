"""Thin wrapper that delegates to the canonical runtime module."""
from __future__ import annotations

from runtime_bridge import load_runtime_module

_MOD = load_runtime_module("decision_log_store")

InMemoryDecisionLogStore = _MOD.InMemoryDecisionLogStore
DynamoDBDecisionLogStore = _MOD.DynamoDBDecisionLogStore
FileDecisionLogStore = _MOD.FileDecisionLogStore
