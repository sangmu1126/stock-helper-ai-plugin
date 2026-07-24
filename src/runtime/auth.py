"""API Key validation middleware."""
from __future__ import annotations

import os
from typing import Any

import error_taxonomy as _ERRORS
import response_schema as _RESPONSE


def validate_api_key(event: dict[str, Any]) -> dict[str, Any] | None:
    """Validate x-api-key header.
    
    Returns a 403 response dict if validation fails, otherwise None.
    """
    headers = event.get("headers", {})
    api_key = headers.get("x-api-key") or headers.get("X-Api-Key")
    
    expected_key = os.environ.get("SAFE_TRADE_API_KEY")
    # If no expected key is configured, we assume API Gateway handles it entirely
    if expected_key and api_key != expected_key:
        import json
        body = _RESPONSE.envelope({
            "decision": "STOP",
            "reasons": ["UNAUTHORIZED"],
            "errors": _ERRORS.describe_reasons(["UNAUTHORIZED"]),
            "stop_level": "critical",
            "user_action": "Invalid API Key.",
        })
        return {
            "statusCode": 403,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(body, ensure_ascii=False),
        }
    return None
