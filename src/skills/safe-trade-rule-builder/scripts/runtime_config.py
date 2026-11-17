"""Thin wrapper that delegates to the canonical runtime config module."""
from __future__ import annotations

from runtime_bridge import load_runtime_module

_MOD = load_runtime_module("config")

RuntimeConfig = _MOD.RuntimeConfig
load_runtime_config = _MOD.load_runtime_config
