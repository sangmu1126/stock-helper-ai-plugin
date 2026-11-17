from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_RUNTIME_DIR = Path(__file__).resolve().parent
_CACHE: dict[str, tuple[float, ConfigSnapshot]] = {}


@dataclass(frozen=True)
class ConfigSnapshot:
    kind: str
    data: dict[str, Any]
    source: str
    version: str
    loaded_at_epoch_seconds: int
    fallback_used: bool
    error: str | None = None

    def metadata(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "source": self.source,
            "version": self.version,
            "loaded_at_epoch_seconds": self.loaded_at_epoch_seconds,
            "fallback_used": self.fallback_used,
            "error": self.error,
        }


def load_config(
    *,
    kind: str,
    default_data: dict[str, Any],
    local_filename: str | None = None,
    env_path_name: str | None = None,
) -> ConfigSnapshot:
    """Load runtime policy config from a local JSON file with a TTL cache.

    The file named by ``env_path_name`` (if set) is read first, then the packaged
    local JSON, then the packaged default. Editing the file is picked up after the
    TTL expires, so policies can be hot-reloaded without restarting.
    """
    ttl_seconds = _int_env("SAFE_TRADE_CONFIG_TTL_SECONDS", 60)
    cache_key = f"{kind}:{os.getenv(env_path_name or '', '')}"
    cached = _CACHE.get(cache_key)
    now = time.time()
    if ttl_seconds > 0 and cached and cached[0] > now:
        return cached[1]

    snapshot = _load_local_or_default(kind, default_data, local_filename, env_path_name, fallback_error=None)
    if ttl_seconds > 0:
        _CACHE[cache_key] = (now + ttl_seconds, snapshot)
    return snapshot


def _load_local_or_default(
    kind: str,
    default_data: dict[str, Any],
    local_filename: str | None,
    env_path_name: str | None,
    fallback_error: str | None,
) -> ConfigSnapshot:
    path = _local_path(local_filename, env_path_name)
    if path is not None and path.exists():
        try:
            return _snapshot(kind, _load_json_file(path), f"local:{path.name}", fallback_used=bool(fallback_error), error=fallback_error)
        except (OSError, json.JSONDecodeError) as exc:
            fallback_error = f"{fallback_error}; {exc}" if fallback_error else str(exc)
    return _snapshot(kind, default_data.copy(), "default:packaged", fallback_used=bool(fallback_error), error=fallback_error)


def _local_path(local_filename: str | None, env_path_name: str | None) -> Path | None:
    if env_path_name and os.getenv(env_path_name):
        return Path(str(os.getenv(env_path_name))).expanduser()
    if local_filename:
        return _RUNTIME_DIR / local_filename
    return None


def _load_json_file(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        loaded = json.load(handle)
    if not isinstance(loaded, dict):
        raise TypeError(f"Config must be a JSON object: {path}")
    return loaded


def _snapshot(
    kind: str,
    data: dict[str, Any],
    source: str,
    *,
    fallback_used: bool,
    error: str | None = None,
) -> ConfigSnapshot:
    return ConfigSnapshot(
        kind=kind,
        data=data,
        source=source,
        version=str(data.get("version", "unknown")),
        loaded_at_epoch_seconds=int(time.time()),
        fallback_used=fallback_used,
        error=error,
    )


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default
