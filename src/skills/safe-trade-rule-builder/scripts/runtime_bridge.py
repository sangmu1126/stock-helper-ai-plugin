from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def load_runtime_module(name: str) -> ModuleType:
    runtime_root = _runtime_root()
    if str(runtime_root) not in sys.path:
        sys.path.insert(0, str(runtime_root))
    runtime_path = runtime_root / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_safe_trade_runtime_shared_{name}", runtime_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Runtime module could not be loaded: {name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _runtime_root() -> Path:
    return Path(__file__).resolve().parents[3] / "runtime"
