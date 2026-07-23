from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_RUNTIME_DIR = Path(__file__).resolve().parent
_CACHE: dict[str, tuple[float, "ConfigSnapshot"]] = {}


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
    """Load runtime policy config with local fallback and TTL cache.

    Production can set SAFE_TRADE_CONFIG_BACKEND to `ssm` or `appconfig`.
    The packaged local JSON remains the deterministic fallback for judging,
    local testing, and provider outages.
    """
    ttl_seconds = _int_env("SAFE_TRADE_CONFIG_TTL_SECONDS", 60)
    cache_key = ":".join(
        [
            kind,
            os.getenv("SAFE_TRADE_CONFIG_BACKEND", "local"),
            os.getenv(env_path_name or "", ""),
            os.getenv(_env_name(kind, "SSM_PARAMETER"), ""),
            os.getenv(_env_name(kind, "APPCONFIG_PROFILE"), ""),
        ]
    )
    cached = _CACHE.get(cache_key)
    now = time.time()
    if ttl_seconds > 0 and cached and cached[0] > now:
        return cached[1]

    snapshot = _load_uncached(
        kind=kind,
        default_data=default_data,
        local_filename=local_filename,
        env_path_name=env_path_name,
    )
    if ttl_seconds > 0:
        _CACHE[cache_key] = (now + ttl_seconds, snapshot)
    return snapshot


def _load_uncached(
    *,
    kind: str,
    default_data: dict[str, Any],
    local_filename: str | None,
    env_path_name: str | None,
) -> ConfigSnapshot:
    backend = os.getenv("SAFE_TRADE_CONFIG_BACKEND", "local").strip().lower()
    if backend == "ssm":
        parameter_name = os.getenv(_env_name(kind, "SSM_PARAMETER"))
        if parameter_name:
            try:
                return _snapshot(kind, _load_from_ssm(parameter_name), f"ssm:{parameter_name}", fallback_used=False)
            except Exception as exc:  # noqa: BLE001 - config provider must fail closed to fallback
                return _load_local_or_default(kind, default_data, local_filename, env_path_name, fallback_error=str(exc))
    if backend == "appconfig":
        try:
            return _snapshot(kind, _load_from_appconfig(kind), "appconfig", fallback_used=False)
        except Exception as exc:  # noqa: BLE001 - config provider must fail closed to fallback
            return _load_local_or_default(kind, default_data, local_filename, env_path_name, fallback_error=str(exc))
    return _load_local_or_default(kind, default_data, local_filename, env_path_name, fallback_error=None)


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
        raise ValueError(f"Config must be a JSON object: {path}")
    return loaded


def _load_from_ssm(parameter_name: str) -> dict[str, Any]:
    import boto3  # type: ignore[import-not-found]

    client = boto3.client("ssm")
    response = client.get_parameter(Name=parameter_name, WithDecryption=True)
    value = response["Parameter"]["Value"]
    loaded = json.loads(value)
    if not isinstance(loaded, dict):
        raise ValueError(f"SSM config must be a JSON object: {parameter_name}")
    return loaded


_APPCONFIG_TOKEN_CACHE: dict[str, str] = {}


def _load_from_appconfig(kind: str) -> dict[str, Any]:
    import boto3  # type: ignore[import-not-found]

    application = _required_env("SAFE_TRADE_APPCONFIG_APPLICATION")
    environment = _required_env("SAFE_TRADE_APPCONFIG_ENVIRONMENT")
    profile = os.getenv(_env_name(kind, "APPCONFIG_PROFILE")) or _required_env("SAFE_TRADE_APPCONFIG_PROFILE")
    cache_key = f"{application}:{environment}:{profile}"
    client = boto3.client("appconfigdata")

    token = _APPCONFIG_TOKEN_CACHE.get(cache_key)
    if not token:
        session = client.start_configuration_session(
            ApplicationIdentifier=application,
            EnvironmentIdentifier=environment,
            ConfigurationProfileIdentifier=profile,
        )
        token = session["InitialConfigurationToken"]

    response = client.get_latest_configuration(ConfigurationToken=token)
    _APPCONFIG_TOKEN_CACHE[cache_key] = response["NextPollConfigurationToken"]
    payload = response["Configuration"].read()
    loaded = json.loads(payload.decode("utf-8") or "{}")
    if not isinstance(loaded, dict):
        raise ValueError(f"AppConfig payload must be a JSON object: {profile}")
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


def _env_name(kind: str, suffix: str) -> str:
    normalized = kind.upper().replace("-", "_")
    return f"SAFE_TRADE_{normalized}_{suffix}"


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default
