"""Cloudflare Workers AI client used exclusively for Mind Map requests."""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

from services.mind_map_cancellation import (
    MindMapGenerationCancellation,
    MindMapGenerationCancelled,
)

logger = logging.getLogger(__name__)
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

CLOUDFLARE_MODEL = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
CLOUDFLARE_TIMEOUT_SECONDS = 60.0
cloudflare_account_id = (os.getenv("CLOUDFLARE_ACCOUNT_ID") or "").strip()
cloudflare_api_token = (os.getenv("CLOUDFLARE_API_TOKEN") or "").strip()


@dataclass(frozen=True)
class CloudflareCompletionResult:
    content: str
    finish_reason: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    truncated: bool = False


class CloudflareRateLimitError(RuntimeError):
    """Cloudflare returned HTTP 429; callers should not automatically retry."""

    def __init__(self, message: str, *, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class CloudflareProviderError(RuntimeError):
    """A safe, user-facing Cloudflare provider failure."""


async def _post_cancellable(
    cancellation: MindMapGenerationCancellation,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
) -> httpx.Response:
    if cancellation.async_cloudflare_client is None:
        cancellation.async_cloudflare_client = httpx.AsyncClient(
            timeout=httpx.Timeout(CLOUDFLARE_TIMEOUT_SECONDS)
        )
    response = await cancellation.async_cloudflare_client.post(
        url, headers=headers, json=payload
    )
    return response


def _safe_retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return max(0.0, min(float(value), 3600.0))
    except (TypeError, ValueError):
        return None


def _reported_finish_reason(result: dict[str, Any]) -> str | None:
    """Return a provider finish reason when the REST response includes one."""
    value = result.get("finish_reason", result.get("stop_reason"))
    return value.strip().lower() if isinstance(value, str) and value.strip() else None


def _usage_token_count(usage: dict[str, Any], field: str) -> int | None:
    """Normalize documented numeric token usage without inventing missing data."""
    value = usage.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value < 0 or not float(value).is_integer():
        return None
    return int(value)


def _safe_provider_message(response: httpx.Response) -> str:
    """Extract a brief provider explanation without echoing response secrets."""
    try:
        body = response.json()
    except (ValueError, json.JSONDecodeError):
        body = None
    messages: list[str] = []
    if isinstance(body, dict):
        errors = body.get("errors")
        if isinstance(errors, list):
            for item in errors[:3]:
                if isinstance(item, dict):
                    message = item.get("message")
                    if isinstance(message, str):
                        messages.append(message)
        if not messages and isinstance(body.get("error"), dict):
            message = body["error"].get("message")
            if isinstance(message, str):
                messages.append(message)
    combined = " ".join(messages)
    for secret in (cloudflare_api_token, cloudflare_account_id):
        if secret:
            combined = combined.replace(secret, "[REDACTED]")
    combined = " ".join(combined.split())[:400]
    return combined or f"HTTP {response.status_code} provider error"


def cloudflare_mind_map_completion(
    prompt: str,
    max_tokens: int | None = None,
    response_format: dict | None = None,
    request_stage: str = "chunk",
    retry_number: int = 0,
    chunk_size: int | None = None,
    cancellation: MindMapGenerationCancellation | None = None,
) -> CloudflareCompletionResult:
    """Make one sequential Workers AI request with strict JSON Schema output."""
    if not cloudflare_account_id or not cloudflare_api_token:
        raise CloudflareProviderError(
            "CLOUDFLARE_ACCOUNT_ID or CLOUDFLARE_API_TOKEN is missing from the backend .env file."
        )
    if cancellation is not None:
        cancellation.check()

    schema = None
    if response_format is not None:
        schema = response_format.get("json_schema", {}).get("schema")
    payload: dict[str, Any] = {"prompt": prompt}
    if max_tokens is not None:
        # Keep the existing output bound; this also caps billed generation size.
        payload["max_tokens"] = max_tokens
    if schema is not None:
        # Workers AI JSON Mode accepts the JSON Schema directly in this property.
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": schema,
        }

    url = (
        "https://api.cloudflare.com/client/v4/accounts/"
        f"{cloudflare_account_id}/ai/run/{CLOUDFLARE_MODEL}"
    )
    headers = {
        "Authorization": f"Bearer {cloudflare_api_token}",
        "Content-Type": "application/json",
    }
    started = time.perf_counter()
    try:
        if cancellation is not None:
            response = cancellation.run_async(
                _post_cancellable(cancellation, url, headers, payload)
            )
        else:
            response = httpx.post(
                url,
                headers=headers,
                json=payload,
                timeout=CLOUDFLARE_TIMEOUT_SECONDS,
            )
    except MindMapGenerationCancelled:
        logger.info("Mind map Cloudflare request cancelled: stage=%s.", request_stage)
        raise
    except httpx.TimeoutException:
        raise CloudflareProviderError(
            "Cloudflare Workers AI did not respond within 60 seconds. Please try again later."
        ) from None
    except httpx.RequestError as error:
        logger.warning(
            "Mind map Cloudflare transport failed: stage=%s error_type=%s duration_ms=%.1f.",
            request_stage,
            type(error).__name__,
            (time.perf_counter() - started) * 1000,
        )
        raise CloudflareProviderError(
            "Cloudflare Workers AI could not be reached. Please try again later."
        ) from None

    if response.status_code == 429:
        retry_after = _safe_retry_after(response.headers.get("Retry-After"))
        logger.warning("Mind map Cloudflare rate limited: stage=%s.", request_stage)
        raise CloudflareRateLimitError(
            "Cloudflare Workers AI is rate limiting Mind Map requests. Please wait before trying again.",
            retry_after=retry_after,
        )
    if not response.is_success:
        detail = _safe_provider_message(response)
        logger.warning(
            "Mind map Cloudflare request failed: stage=%s status=%d detail=%s.",
            request_stage,
            response.status_code,
            detail,
        )
        raise CloudflareProviderError(
            f"Cloudflare Workers AI returned HTTP {response.status_code}: {detail}"
        )
    try:
        body = response.json()
    except (ValueError, json.JSONDecodeError):
        raise CloudflareProviderError(
            "Cloudflare Workers AI returned a non-JSON API response."
        ) from None
    if not isinstance(body, dict) or body.get("success") is not True:
        raise CloudflareProviderError(
            f"Cloudflare Workers AI reported an unsuccessful result: {_safe_provider_message(response)}"
        )
    result = body.get("result")
    content = result.get("response") if isinstance(result, dict) else None
    if isinstance(content, (dict, list)):
        content = json.dumps(content, ensure_ascii=False)
    if not isinstance(content, str) or not content.strip():
        raise CloudflareProviderError("Cloudflare Workers AI returned no usable Mind Map content.")
    usage = result.get("usage", {}) if isinstance(result, dict) else {}
    usage = usage if isinstance(usage, dict) else {}
    finish_reason = _reported_finish_reason(result) if isinstance(result, dict) else None
    completion_tokens = _usage_token_count(usage, "completion_tokens")
    # The REST schema documents usage counts but not finish_reason. Reaching the
    # exact requested output-token ceiling is the available provider-side signal
    # that generation was stopped by max_tokens. Missing usage stays unknown.
    explicit_length_stop = finish_reason in {
        "length",
        "max_tokens",
        "max_output_tokens",
        "token_limit",
        "token_limit_reached",
    }
    reached_output_ceiling = (
        max_tokens is not None
        and completion_tokens is not None
        and completion_tokens >= max_tokens
    )
    truncated = explicit_length_stop or (
        finish_reason is None and reached_output_ceiling
    )
    prompt_tokens = _usage_token_count(usage, "prompt_tokens")
    total_tokens = _usage_token_count(usage, "total_tokens")
    logger.info(
        "Mind map Cloudflare request completed: model=%s stage=%s mode=json_schema "
        "retry=%d chunk_size=%s prompt_tokens=%s completion_tokens=%s "
        "finish_reason=%s truncated=%s duration_ms=%.1f.",
        CLOUDFLARE_MODEL,
        request_stage,
        retry_number,
        chunk_size if chunk_size is not None else "n/a",
        prompt_tokens if prompt_tokens is not None else "unknown",
        completion_tokens if completion_tokens is not None else "unknown",
        finish_reason or "unknown",
        truncated,
        (time.perf_counter() - started) * 1000,
    )
    return CloudflareCompletionResult(
        content=content,
        finish_reason=finish_reason,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        truncated=truncated,
    )
