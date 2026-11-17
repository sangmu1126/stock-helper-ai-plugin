from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def load_runtime_module(name: str) -> ModuleType:
    runtime_root = _runtime_root()
    _ensure_runtime_on_path(runtime_root)
    runtime_path = runtime_root / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_safe_trade_runtime_shared_{name}", runtime_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Runtime module could not be loaded: {name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _ensure_runtime_on_path(runtime_root: Path) -> None:
    """Put src/runtime on sys.path *after* this scripts directory.

    Both directories contain modules with the same names (prompt_security, policy_engine, ...).
    Inserting runtime at position 0 made e.g. `from prompt_security import raise_if_unsafe`
    resolve to the runtime module and fail unless PYTHONPATH happened to order them correctly.
    """
    resolved = [Path(entry or ".").resolve() for entry in sys.path]
    if runtime_root in resolved:
        return
    scripts_dir = Path(__file__).resolve().parent
    insert_at = resolved.index(scripts_dir) + 1 if scripts_dir in resolved else len(sys.path)
    sys.path.insert(insert_at, str(runtime_root))


def _runtime_root() -> Path:
    return Path(__file__).resolve().parents[3] / "runtime"
