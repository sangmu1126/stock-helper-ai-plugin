"""API Key and Mock JWT validation middleware."""
from __future__ import annotations

import base64
import json
import os
from typing import Any

import error_taxonomy as _ERRORS
import response_schema as _RESPONSE


def validate_api_gateway_auth(event: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    """Validate auth and return (error_response, user_id).
    
    Returns (None, user_id) if validation succeeds.
    Returns (401/403 response dict, "anonymous") if validation fails.
    """
    headers = event.get("headers") or {}
    # 1. API Key check
    api_key = headers.get("x-api-key") or headers.get("X-Api-Key")
    expected_key = os.environ.get("SAFE_TRADE_API_KEY")
    if expected_key and api_key != expected_key:
        return _build_error(403, "UNAUTHORIZED", "Invalid API Key."), "anonymous"
        
    # 2. JWT Bearer token check (Mock implementation for hackathon)
    # We expect `Authorization: Bearer <base64_json_payload>`
    auth_header = headers.get("authorization") or headers.get("Authorization") or ""
    if not auth_header.lower().startswith("bearer "):
        return _build_error(401, "MISSING_AUTH_TOKEN", "Missing or invalid Authorization header."), "anonymous"
        
    token = auth_header[7:].strip()
    try:
        # Mock: token is just base64 encoded JSON payload (e.g. eyJzdWIiOiAidXNlcjEyMyJ9)
        # In production, use python-jose or jwt to decode and verify signature against JWKS
        padding = "=" * ((4 - len(token) % 4) % 4)
        decoded_bytes = base64.b64decode(token + padding)
        payload = json.loads(decoded_bytes)
        user_id = payload.get("sub")
        if not user_id:
            return _build_error(401, "INVALID_TOKEN", "Token missing 'sub' claim."), "anonymous"
        return None, str(user_id)
    except Exception:  # noqa: BLE001
        return _build_error(401, "INVALID_TOKEN", "Malformed token."), "anonymous"


def _build_error(status_code: int, reason: str, message: str) -> dict[str, Any]:
    body = _RESPONSE.envelope({
        "decision": "STOP",
        "reasons": [reason],
        "errors": _ERRORS.describe_reasons([reason]),
        "stop_level": "critical",
        "user_action": message,
    })
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, ensure_ascii=False),
    }

