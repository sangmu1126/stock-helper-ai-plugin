"""Thin wrapper that delegates to the canonical runtime session module (runtime/market_sessions.py)."""
from __future__ import annotations

from runtime_bridge import load_runtime_module

_MOD = load_runtime_module("market_sessions")

CONSTRAINT_KEYS = _MOD.CONSTRAINT_KEYS
SESSIONS_PATH = _MOD.SESSIONS_PATH
allowed_market_states = _MOD.allowed_market_states
apply_time_window = _MOD.apply_time_window
day_status = _MOD.day_status
evaluate_time_window = _MOD.evaluate_time_window
market_holidays = _MOD.market_holidays
has_constraints = _MOD.has_constraints
load_sessions = _MOD.load_sessions
market_for_symbol = _MOD.market_for_symbol
session_hours = _MOD.session_hours
