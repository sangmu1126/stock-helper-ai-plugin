from __future__ import annotations

from pathlib import Path


def lambda_template() -> str:
    return runtime_file("lambda_handler.py")


def runtime_files() -> dict[str, str]:
    runtime_root = _runtime_root()
    return {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(runtime_root.iterdir())
        if path.is_file() and path.suffix in {".py", ".json", ".md", ".txt"}
    }


def runtime_file(filename: str) -> str:
    runtime_path = _runtime_root() / filename
    return runtime_path.read_text(encoding="utf-8")


def _runtime_root() -> Path:
    current = Path(__file__).resolve()
    plugin_root = current.parents[3]
    return plugin_root / "runtime"
