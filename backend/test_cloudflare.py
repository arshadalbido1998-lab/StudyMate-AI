"""Standalone connectivity check for Cloudflare Workers AI.

Run from the backend directory with:
    .\.venv\Scripts\python.exe .\test_cloudflare.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import dotenv_values


BACKEND_DIR = Path(__file__).resolve().parent
ENV_PATH = BACKEND_DIR / ".env"
MODEL = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
TIMEOUT_SECONDS = 60
EXPECTED = {"status": "success", "message": "Cloudflare connected"}


def _redact(value: str, secrets: tuple[str, ...]) -> str:
    for secret in secrets:
        if secret:
            value = value.replace(secret, "[REDACTED]")
    return value


def main() -> int:
    print(f"Model: {MODEL}")
    if not ENV_PATH.is_file():
        print("HTTP status: unavailable")
        print("Failure: backend .env file not found.")
        return 2

    env = dotenv_values(ENV_PATH)
    account_id = (env.get("CLOUDFLARE_ACCOUNT_ID") or "").strip()
    api_token = (env.get("CLOUDFLARE_API_TOKEN") or "").strip()
    if not account_id or not api_token:
        print("HTTP status: unavailable")
        print("Failure: CLOUDFLARE_ACCOUNT_ID or CLOUDFLARE_API_TOKEN is missing from .env.")
        return 2

    prompt = (
        'Return a JSON object containing exactly these values: '
        '{"status":"success","message":"Cloudflare connected"}.'
    )
    schema = {
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["success"]},
            "message": {"type": "string", "enum": ["Cloudflare connected"]},
        },
        "required": ["status", "message"],
        "additionalProperties": False,
    }
    payload = {
        "prompt": prompt,
        "response_format": {"type": "json_schema", "json_schema": schema},
    }
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{MODEL}"
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    secrets = (account_id, api_token)
    http_status: int | None = None

    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            http_status = response.status
            raw_body = response.read().decode("utf-8", errors="replace")
    except HTTPError as error:
        http_status = error.code
        raw_body = error.read().decode("utf-8", errors="replace")
        print(f"HTTP status: {http_status}")
        print("Failure: Cloudflare returned an HTTP error.")
        _print_error_details(raw_body, secrets)
        return 1
    except URLError as error:
        print("HTTP status: unavailable")
        reason = getattr(error, "reason", "connection error")
        print(f"Failure: connection error ({_redact(str(reason), secrets)}).")
        return 1
    except TimeoutError:
        print("HTTP status: unavailable")
        print(f"Failure: request timed out after {TIMEOUT_SECONDS} seconds.")
        return 1
    except Exception as error:
        print("HTTP status: unavailable")
        print(f"Failure: unexpected error ({_redact(type(error).__name__, secrets)}).")
        return 1

    print(f"HTTP status: {http_status}")
    try:
        body = json.loads(raw_body)
    except json.JSONDecodeError:
        print("Failure: Cloudflare returned a non-JSON response.")
        print(f"Error details: {_redact(raw_body[:1000], secrets)}")
        return 1

    if not isinstance(body, dict) or body.get("success") is not True:
        print("Failure: Cloudflare API reported an unsuccessful result.")
        _print_error_details(raw_body, secrets)
        return 1

    result = body.get("result")
    returned = result.get("response") if isinstance(result, dict) else result
    print("Returned response:")
    print(_redact(json.dumps(returned, ensure_ascii=False, indent=2), secrets))

    parsed = returned
    if isinstance(returned, str):
        try:
            parsed = json.loads(returned)
        except json.JSONDecodeError:
            parsed = None
    if http_status is not None and 200 <= http_status < 300 and parsed == EXPECTED:
        print("Success: Cloudflare Workers AI returned the expected JSON.")
        return 0

    print("Failure: response did not match the expected JSON values.")
    return 1


def _print_error_details(raw_body: str, secrets: tuple[str, ...]) -> None:
    try:
        body = json.loads(raw_body)
    except json.JSONDecodeError:
        details = raw_body[:1000]
    else:
        errors = body.get("errors") if isinstance(body, dict) else None
        details = json.dumps(errors if errors else body, ensure_ascii=False)
    details = _redact(details, secrets)
    if details:
        print(f"Error details: {details[:1000]}")


if __name__ == "__main__":
    raise SystemExit(main())
