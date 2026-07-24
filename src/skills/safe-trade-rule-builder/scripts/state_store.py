"""Thin wrapper that delegates to the canonical runtime module."""
from __future__ import annotations

from runtime_bridge import load_runtime_module

_MOD = load_runtime_module("state_store")

StateStore = _MOD.StateStore
DuplicateStateRecordError = _MOD.DuplicateStateRecordError
InMemoryStateStore = _MOD.InMemoryStateStore
FileStateStore = _MOD.FileStateStore
DynamoDBStateStore = _MOD.DynamoDBStateStore
now_seconds = _MOD.now_seconds
