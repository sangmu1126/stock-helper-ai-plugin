from __future__ import annotations

from runtime_bridge import load_runtime_module


_CONFIRMATION = load_runtime_module("confirmation")

CONFIRMATION_SCHEMA_VERSION = _CONFIRMATION.CONFIRMATION_SCHEMA_VERSION
ChecklistItem = _CONFIRMATION.ChecklistItem
ConfirmationChecklist = _CONFIRMATION.ConfirmationChecklist
build_confirmation_checklist = _CONFIRMATION.build_confirmation_checklist
