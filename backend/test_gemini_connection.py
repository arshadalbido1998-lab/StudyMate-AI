"""Minimal, standalone Gemini API connectivity check.

Run from the backend directory with:
    .\.venv\Scripts\python.exe .\test_gemini_connection.py

Reads GEMINI_API_KEY from this directory's .env and never prints the key,
request prompt, or generated response text.
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx
from dotenv import dotenv_values
from google import genai
from google.genai import errors, types


BACKEND_DIR = Path(__file__).resolve().parent
ENV_PATH = BACKEND_DIR / ".env"
GEMINI_MODEL = "gemini-3.6-flash"
TEST_PROMPT = "Reply with exactly OK."
REQUEST_TIMEOUT_MS = 30_000


def main() -> int:
    print("Loading Gemini API key from the backend .env file...", flush=True)
    if not ENV_PATH.is_file():
        print("Failure: backend .env file not found.", file=sys.stderr, flush=True)
        return 2

    api_key = (dotenv_values(ENV_PATH).get("GEMINI_API_KEY") or "").strip()
    if not api_key or api_key.lower().startswith(("your_", "replace", "put_")):
        print("Failure: GEMINI_API_KEY is missing or a placeholder.", file=sys.stderr, flush=True)
        return 2
    print("API key loaded (value hidden).", flush=True)

    client = None
    try:
        print(
            f"Connecting to {GEMINI_MODEL} with a {REQUEST_TIMEOUT_MS // 1000}-second request timeout...",
            flush=True,
        )
        client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS),
        )
        print("Sending test request...", flush=True)
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=TEST_PROMPT,
        )
        if not isinstance(getattr(response, "text", None), str) or not response.text.strip():
            print(f"Failure: {GEMINI_MODEL} returned no text response.", file=sys.stderr, flush=True)
            return 1
        print(f"Success: {GEMINI_MODEL} returned a text response.", flush=True)
        return 0
    except httpx.TimeoutException:
        print("Failure: Gemini request timed out after the configured 30-second HTTP timeout.", file=sys.stderr, flush=True)
        return 1
    except httpx.TransportError as error:
        print(
            f"Failure: Gemini connection error ({type(error).__name__}). Details withheld.",
            file=sys.stderr,
            flush=True,
        )
        return 1
    except errors.APIError as error:
        status_code = getattr(error, "code", None)
        status = str(getattr(error, "status", "")).upper()
        message = str(getattr(error, "message", "")).lower()
        is_auth_error = (
            status_code in (401, 403)
            or status in {"UNAUTHENTICATED", "PERMISSION_DENIED"}
            or "api_key_invalid" in message
            or "api key not valid" in message
        )
        if is_auth_error:
            print(
                "Failure: Gemini authentication was rejected. Check the key's validity and API access; details withheld.",
                file=sys.stderr,
                flush=True,
            )
        else:
            suffix = f" (HTTP {status_code})" if isinstance(status_code, int) else ""
            print(
                f"Failure: Gemini API error{suffix}. Details withheld.",
                file=sys.stderr,
                flush=True,
            )
        return 1
    except Exception as error:
        # SDK and transport exception messages may contain request details.
        print(
            f"Failure: unexpected Gemini test error ({type(error).__name__}). Details withheld.",
            file=sys.stderr,
            flush=True,
        )
        return 1
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
