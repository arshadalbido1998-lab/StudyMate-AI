import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv
from groq import AsyncGroq, Groq
from openai import AsyncOpenAI, OpenAI
from google import genai
from google.genai import errors, types
from services.mind_map_cancellation import (
    MindMapGenerationCancellation,
    MindMapGenerationCancelled,
)

load_dotenv()
logger = logging.getLogger(__name__)

AI_PROVIDER = os.getenv("AI_PROVIDER", "groq").strip().lower()

# Groq client
groq_api_key = os.getenv("GROQ_API_KEY")
groq_client = Groq(api_key=groq_api_key) if groq_api_key else None

# Gemini client remains available for later
gemini_api_key = os.getenv("GEMINI_API_KEY")
gemini_client = (
    genai.Client(api_key=gemini_api_key)
    if gemini_api_key
    else None
)

GROQ_MODEL = "openai/gpt-oss-120b"
GEMINI_MODEL = "gemini-3.8-flash"
GEMINI_MIND_MAP_MODEL = "gemini-3.6-flash"
OPENROUTER_MODEL = (
    os.getenv("OPENROUTER_MIND_MAP_MODEL", "openrouter/free").strip()
    or "openrouter/free"
)
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
openrouter_client = (
    OpenAI(api_key=openrouter_api_key, base_url=OPENROUTER_BASE_URL)
    if openrouter_api_key
    else None
)


@dataclass(frozen=True)
class ChatCompletionResult:
    content: str
    finish_reason: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None


class StructuredOutputUnsupportedError(RuntimeError):
    """Groq rejected the response-format feature/schema for this request."""

    def __init__(self, message: str, *, status_code: int | None = None, api_code: str | None = None, api_message: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.api_code = api_code
        self.api_message = api_message


class GroqCompletionOutputTruncatedError(RuntimeError):
    """Groq rejected an incomplete structured completion before returning a choice."""

    def __init__(self, message: str, *, status_code: int | None, api_code: str | None, api_message: str | None, output_chars: int, missing_properties: tuple[str, ...]):
        super().__init__(message)
        self.status_code = status_code
        self.api_code = api_code
        self.api_message = api_message
        self.output_chars = output_chars
        self.missing_properties = missing_properties


class OpenRouterStructuredOutputUnsupportedError(RuntimeError):
    """OpenRouter's selected model does not accept the requested JSON format."""


async def _create_cancellable_openrouter_completion(
    cancellation: MindMapGenerationCancellation,
    request: dict,
):
    if cancellation.async_openrouter_client is None:
        cancellation.async_openrouter_client = AsyncOpenAI(
            api_key=openrouter_api_key,
            base_url=OPENROUTER_BASE_URL,
        )
    return await cancellation.async_openrouter_client.chat.completions.create(**request)


def _openrouter_chat_completion(
    prompt: str,
    max_tokens: int | None = None,
    response_format: dict | None = None,
    request_stage: str = "api",
    retry_number: int = 0,
    chunk_size: int | None = None,
    cancellation: MindMapGenerationCancellation | None = None,
) -> ChatCompletionResult:
    """Call OpenRouter for mind-map work and normalize its OpenAI-compatible reply."""
    if openrouter_api_key is None:
        raise RuntimeError("OPENROUTER_API_KEY is missing. Check the backend .env file.")

    request = {
        "model": OPENROUTER_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
    }
    if max_tokens is not None:
        request["max_tokens"] = max_tokens
    if response_format is not None:
        request["response_format"] = response_format
        if response_format.get("type") == "json_schema":
            request["extra_body"] = {"provider": {"require_parameters": True}}

    if cancellation is not None:
        cancellation.check()
    started = time.perf_counter()
    try:
        response = (
            cancellation.run_async(
                _create_cancellable_openrouter_completion(cancellation, request)
            )
            if cancellation is not None
            else openrouter_client.chat.completions.create(**request)
        )
    except MindMapGenerationCancelled:
        logger.info(
            "Mind map OpenRouter request cancelled: model=%s stage=%s.",
            OPENROUTER_MODEL,
            request_stage,
        )
        raise
    except Exception as error:
        status_code = getattr(error, "status_code", None)
        body = getattr(error, "body", None)
        detail = body.get("error", body) if isinstance(body, dict) else {}
        code = detail.get("code") if isinstance(detail, dict) else None
        message = detail.get("message") if isinstance(detail, dict) else None
        markers = (str(code or "") + " " + str(message or "")).lower()
        if (
            response_format is not None
            and status_code in (400, 422)
            and any(term in markers for term in (
                "response_format", "json_schema", "structured output",
                "unsupported_parameter", "no endpoints support",
            ))
        ):
            raise OpenRouterStructuredOutputUnsupportedError(
                "OpenRouter's selected model rejected structured output."
            ) from error
        logger.warning(
            "Mind map OpenRouter request failed: model=%s stage=%s status=%s "
            "error_type=%s duration_ms=%.1f.",
            OPENROUTER_MODEL,
            request_stage,
            status_code if status_code is not None else "unavailable",
            type(error).__name__,
            (time.perf_counter() - started) * 1000,
        )
        raise RuntimeError(
            "OpenRouter could not generate a mind map response. Please try again later."
        ) from None

    choice = response.choices[0]
    usage = getattr(response, "usage", None)
    content = choice.message.content or ""
    if not isinstance(content, str):
        raise RuntimeError("OpenRouter returned a non-text mind map response.")
    logger.info(
        "OpenRouter mind map request completed: model=%s stage=%s mode=%s retry=%d "
        "duration_ms=%.1f prompt_tokens=%s completion_tokens=%s.",
        OPENROUTER_MODEL,
        request_stage,
        (response_format or {}).get("type", "none"),
        retry_number,
        (time.perf_counter() - started) * 1000,
        getattr(usage, "prompt_tokens", "unknown"),
        getattr(usage, "completion_tokens", "unknown"),
    )
    return ChatCompletionResult(
        content=content,
        finish_reason=getattr(choice, "finish_reason", None),
        prompt_tokens=getattr(usage, "prompt_tokens", None),
        completion_tokens=getattr(usage, "completion_tokens", None),
        total_tokens=getattr(usage, "total_tokens", None),
    )


class GeminiStructuredOutputUnsupportedError(RuntimeError):
    """Gemini rejected structured output for a mind-map request."""


class GeminiRateLimitError(RuntimeError):
    """Gemini rejected a Mind Map request because its quota/rate limit was hit."""

    def __init__(self, message: str, *, quota_exhausted: bool, retry_after: float | None):
        super().__init__(message)
        self.quota_exhausted = quota_exhausted
        self.retry_after = retry_after


def _gemini_rate_limit_details(error: Exception) -> tuple[bool, float | None]:
    """Classify 429s and extract provider retry hints without logging payloads."""
    message = str(getattr(error, "message", "") or str(error)).lower()
    status = str(getattr(error, "status", "") or "").lower()
    details = getattr(error, "details", None)
    markers = [message, status]
    retry_values: list[object] = []

    def visit(value: object) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {"message", "status", "reason", "quotaMetric", "quota_metric"} and isinstance(child, str):
                    markers.append(child.lower())
                    markers.append(key.lower())
                if key in {"retryDelay", "retry_delay"}:
                    retry_values.append(child)
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(details)
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", None)
    retry_after = None
    if headers is not None:
        try:
            retry_after = headers.get("Retry-After") or headers.get("retry-after")
        except AttributeError:
            pass
    if retry_after is None and retry_values:
        retry_after = retry_values[0]
    parsed_retry_after = None
    if isinstance(retry_after, (int, float)):
        parsed_retry_after = max(0.0, float(retry_after))
    elif isinstance(retry_after, str):
        import re
        from datetime import datetime, timezone
        from email.utils import parsedate_to_datetime

        match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*s\s*", retry_after, re.IGNORECASE)
        try:
            parsed_retry_after = max(0.0, float(match.group(1) if match else retry_after))
        except ValueError:
            try:
                retry_time = parsedate_to_datetime(retry_after)
                parsed_retry_after = max(
                    0.0,
                    (retry_time - datetime.now(timezone.utc)).total_seconds(),
                )
            except (TypeError, ValueError, OverflowError):
                parsed_retry_after = None

    combined = " ".join(markers)
    temporary_window = any(marker in combined for marker in (
        "per minute", "per second", "requestsperminute", "tokensperminute",
        "requests_per_minute", "tokens_per_minute", "perminute", "persecond",
        "rpm", "tpm",
    ))
    quota_exhausted = not temporary_window and any(marker in combined for marker in (
        "quota exceeded", "quota has been exceeded", "daily limit", "per day", "perday",
        "billing", "check your plan", "limit: 0", "quota",
    ))
    return quota_exhausted, parsed_retry_after


class GeminiRateLimitError(RuntimeError):
    """Gemini rejected a Mind Map request because its quota/rate limit was hit."""

    def __init__(self, message: str, *, quota_exhausted: bool, retry_after: float | None):
        super().__init__(message)
        self.quota_exhausted = quota_exhausted
        self.retry_after = retry_after


def _gemini_rate_limit_details(error: Exception) -> tuple[bool, float | None]:
    """Classify 429s and extract provider retry hints without logging payloads."""
    message = str(getattr(error, "message", "") or "").lower()
    status = str(getattr(error, "status", "") or "").lower()
    details = getattr(error, "details", None)
    markers = [message, status]
    if isinstance(details, (dict, list)):
        def visit(value: object) -> None:
            if isinstance(value, dict):
                for key, child in value.items():
                    if key in {"message", "status", "reason", "quotaMetric", "quota_metric"} and isinstance(child, str):
                        markers.append(child.lower())
                    if key in {"retryDelay", "retry_delay"}:
                        retry_values.append(child)
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)

        retry_values: list[object] = []
        visit(details)
    else:
        retry_values = []

    response = getattr(error, "response", None)
    headers = getattr(response, "headers", None)
    retry_after = None
    if headers is not None:
        try:
            retry_after = headers.get("Retry-After") or headers.get("retry-after")
        except AttributeError:
            pass
    if retry_after is None and retry_values:
        retry_after = retry_values[0]
    parsed_retry_after = None
    if isinstance(retry_after, (int, float)):
        parsed_retry_after = max(0.0, float(retry_after))
    elif isinstance(retry_after, str):
        import re

        match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*s\s*", retry_after, re.IGNORECASE)
        try:
            parsed_retry_after = max(0.0, float(match.group(1) if match else retry_after))
        except ValueError:
            parsed_retry_after = None

    combined = " ".join(markers)
    quota_exhausted = any(marker in combined for marker in (
        "quota exceeded", "quota has been exceeded", "daily limit", "per day",
        "billing", "check your plan", "quota_metric", "limit: 0",
    ))
    return quota_exhausted, parsed_retry_after


async def _create_cancellable_gemini_completion(
    cancellation: MindMapGenerationCancellation,
    request: dict,
):
    if cancellation.gemini_sdk_client is None:
        if gemini_api_key is None:
            raise RuntimeError("GEMINI_API_KEY is missing. Check the backend .env file.")
        cancellation.gemini_sdk_client = genai.Client(api_key=gemini_api_key)
    return await cancellation.gemini_sdk_client.aio.models.generate_content(**request)


def _gemini_compatible_json_schema(schema: object) -> object:
    """Remove strict OpenAPI-only keywords while preserving the JSON contract."""
    if isinstance(schema, dict):
        return {
            key: _gemini_compatible_json_schema(value)
            for key, value in schema.items()
            if key != "additionalProperties"
        }
    if isinstance(schema, list):
        return [_gemini_compatible_json_schema(value) for value in schema]
    return schema


def _gemini_mind_map_completion(
    prompt: str,
    max_tokens: int | None = None,
    response_format: dict | None = None,
    request_stage: str = "api",
    retry_number: int = 0,
    chunk_size: int | None = None,
    cancellation: MindMapGenerationCancellation | None = None,
) -> ChatCompletionResult:
    """Generate Mind Map JSON directly through Google Gemini."""
    if gemini_api_key is None:
        raise RuntimeError("GEMINI_API_KEY is missing. Check the backend .env file.")

    config: dict = {"temperature": 0.3}
    if max_tokens is not None:
        config["max_output_tokens"] = max_tokens
    response_type = (response_format or {}).get("type")
    if response_type in {"json_schema", "json_object"}:
        config["response_mime_type"] = "application/json"
    if response_type == "json_schema":
        schema = (response_format.get("json_schema") or {}).get("schema")
        schema = _gemini_compatible_json_schema(schema)
        config_fields = getattr(types.GenerateContentConfig, "model_fields", {})
        if "response_json_schema" in config_fields:
            config["response_json_schema"] = schema
        else:  # Compatibility with older SDKs pinned in deployment environments.
            config["response_schema"] = schema

    request = {
        "model": GEMINI_MIND_MAP_MODEL,
        "contents": prompt,
        "config": types.GenerateContentConfig(**config),
    }
    started = time.perf_counter()
    response = None
    for attempt in range(2):
        try:
            if cancellation is not None:
                cancellation.check()
                response = cancellation.run_async(
                    _create_cancellable_gemini_completion(cancellation, request)
                )
            else:
                if gemini_client is None:
                    raise RuntimeError("GEMINI_API_KEY is missing. Check the backend .env file.")
                response = gemini_client.models.generate_content(**request)
            break
        except MindMapGenerationCancelled:
            logger.info(
                "Mind map Gemini request cancelled: model=%s stage=%s.",
                GEMINI_MIND_MAP_MODEL,
                request_stage,
            )
            raise
        except Exception as error:
            status_code = getattr(error, "code", None)
            status = getattr(error, "status_code", None)
            if not isinstance(status_code, int) and isinstance(status, int):
                status_code = status
            error_message = str(getattr(error, "message", "") or "").lower()
            error_markers = (str(getattr(error, "status", "")) + " " + error_message).lower()
            if (
                response_type == "json_schema"
                and status_code in (400, 422)
                and any(term in error_markers for term in (
                    "response_schema", "response_json_schema", "json_schema", "structured output", "schema",
                ))
            ):
                raise GeminiStructuredOutputUnsupportedError(
                    "Gemini rejected the Mind Map JSON schema configuration."
                ) from None
            if status_code == 429:
                quota_exhausted, retry_after = _gemini_rate_limit_details(error)
                if quota_exhausted:
                    raise GeminiRateLimitError(
                        "Gemini quota is exhausted for this project or model. Check the Google AI Studio quota and billing settings before retrying.",
                        quota_exhausted=True,
                        retry_after=retry_after,
                    ) from None
                wait_seconds = retry_after if retry_after is not None else 2.0
                if attempt == 0:
                    logger.warning(
                        "Gemini temporarily rate limited a Mind Map request: "
                        "stage=%s retry_after_seconds=%.1f; retrying once.",
                        request_stage,
                        wait_seconds,
                    )
                    if cancellation is None:
                        time.sleep(wait_seconds)
                    else:
                        cancellation.wait(wait_seconds)
                    continue
                raise GeminiRateLimitError(
                    f"Gemini is temporarily rate limiting Mind Map requests. Wait {max(1, round(wait_seconds))} seconds, then retry.",
                    quota_exhausted=False,
                    retry_after=retry_after,
                ) from None
            logger.warning(
                "Mind map Gemini request failed: model=%s stage=%s status=%s "
                "error_type=%s duration_ms=%.1f.",
                GEMINI_MIND_MAP_MODEL,
                request_stage,
                status_code if status_code is not None else "unavailable",
                type(error).__name__,
                (time.perf_counter() - started) * 1000,
            )
            raise RuntimeError(
                "Gemini could not generate a mind map response. Please try again later."
            ) from None

    if response is None:
        raise RuntimeError("Gemini returned no Mind Map response. Please retry.")

    candidates = getattr(response, "candidates", None) or []
    candidate = candidates[0] if candidates else None
    raw_finish_reason = getattr(candidate, "finish_reason", None)
    finish_name = (
        getattr(raw_finish_reason, "name", None)
        or getattr(raw_finish_reason, "value", None)
        or str(raw_finish_reason or "")
    )
    finish_name = str(finish_name).split(".")[-1].upper()
    finish_reason = (
        "length" if finish_name in {"MAX_TOKENS", "MAX_OUTPUT_TOKENS"}
        else "stop" if finish_name == "STOP"
        else finish_name.lower() or None
    )
    usage = getattr(response, "usage_metadata", None)
    completion_tokens = getattr(usage, "candidates_token_count", None)
    at_output_limit = bool(
        max_tokens is not None
        and isinstance(completion_tokens, int)
        and completion_tokens >= max_tokens
    )
    if at_output_limit and finish_reason in {None, "stop"}:
        finish_reason = "length"
    prompt_feedback = getattr(response, "prompt_feedback", None)
    raw_block_reason = getattr(prompt_feedback, "block_reason", None)
    block_reason = (
        getattr(raw_block_reason, "name", None)
        or getattr(raw_block_reason, "value", None)
        or str(raw_block_reason or "")
    )
    block_reason = str(block_reason).split(".")[-1].upper() or "NONE"
    safety_ratings = getattr(candidate, "safety_ratings", None) or []
    safety_categories = []
    for rating in safety_ratings:
        category = getattr(rating, "category", None)
        category = getattr(category, "name", None) or getattr(category, "value", None) or category
        if category:
            safety_categories.append(str(category).split(".")[-1])
    try:
        content = getattr(response, "text", None) or ""
    except (AttributeError, ValueError):
        content = ""
    if not isinstance(content, str):
        content = ""

    logger.info(
        "Mind map Gemini request completed: model=%s stage=%s mode=%s "
        "finish_reason=%s at_output_limit=%s prompt_block_reason=%s safety_categories=%s "
        "prompt_tokens=%s completion_tokens=%s retry=%d chunk_size=%s "
        "response_chars=%d duration_ms=%.1f.",
        GEMINI_MIND_MAP_MODEL,
        request_stage,
        response_type or "none",
        finish_reason or "unknown",
        at_output_limit,
        block_reason,
        ",".join(safety_categories) or "none",
        getattr(usage, "prompt_token_count", "unknown"),
        completion_tokens if completion_tokens is not None else "unknown",
        retry_number,
        chunk_size if chunk_size is not None else "n/a",
        len(content),
        (time.perf_counter() - started) * 1000,
    )
    if block_reason not in {"NONE", "BLOCK_REASON_UNSPECIFIED"} or finish_reason in {
        "safety", "recitation", "blocklist", "prohibited_content"
    }:
        raise RuntimeError(
            "Gemini blocked the Mind Map response. Review the uploaded document and retry with study material that does not trigger provider safety filters."
        )
    if not content.strip():
        raise RuntimeError(
            "Gemini returned no usable Mind Map content. Retry the generation; no incomplete map was accepted."
        )
    return ChatCompletionResult(
        content=content,
        finish_reason=finish_reason,
        prompt_tokens=getattr(usage, "prompt_token_count", None),
        completion_tokens=getattr(usage, "candidates_token_count", None),
        total_tokens=getattr(usage, "total_token_count", None),
    )


def _groq_error_details(error: Exception) -> tuple[str | None, str | None, str]:
    """Extract safe error metadata and inspect, but never return, generated text."""
    body = getattr(error, "body", None)
    if isinstance(body, dict):
        detail = body.get("error", body)
        if isinstance(detail, dict):
            message = detail.get("message")
            code = detail.get("code")
            failed_generation = detail.get("failed_generation")
            failed_generation = failed_generation if isinstance(failed_generation, str) else ""
            return (
                message[:500] if isinstance(message, str) else None,
                code[:100] if isinstance(code, str) else None,
                failed_generation,
            )
    return None, None, ""


def _missing_mind_map_fields(failed_generation: str) -> tuple[str, ...]:
    import re

    present = set(re.findall(r'"(central_topic|main_topics|related_concepts)"\s*:', failed_generation))
    return tuple(field for field in ("central_topic", "main_topics", "related_concepts") if field not in present)


async def _create_cancellable_groq_completion(
    cancellation: MindMapGenerationCancellation,
    request: dict,
):
    if cancellation.async_groq_client is None:
        cancellation.async_groq_client = AsyncGroq(api_key=groq_api_key)
    return await cancellation.async_groq_client.chat.completions.create(**request)


def _groq_chat_completion(
    prompt: str,
    max_tokens: int | None = None,
    response_format: dict | None = None,
    request_stage: str = "api",
    retry_number: int = 0,
    chunk_size: int | None = None,
    cancellation: MindMapGenerationCancellation | None = None,
) -> ChatCompletionResult:
    if groq_client is None:
        raise RuntimeError("GROQ_API_KEY is missing. Check the backend .env file.")

    request = {
        "model": GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
    }
    if max_tokens is not None:
        request["max_completion_tokens"] = max_tokens
    if response_format is not None:
        request["response_format"] = response_format

    for attempt in range(3):
        if cancellation is not None:
            cancellation.check()
        request_started = time.perf_counter()
        try:
            response = (
                cancellation.run_async(
                    _create_cancellable_groq_completion(cancellation, request)
                )
                if cancellation is not None
                else groq_client.chat.completions.create(**request)
            )
            duration_ms = (time.perf_counter() - request_started) * 1000
            choice = response.choices[0]
            usage = getattr(response, "usage", None)
            content = choice.message.content or ""
            logger.info(
                "Groq request completed: stage=%s mode=%s retry=%d "
                "duration_ms=%.1f prompt_tokens=%s completion_tokens=%s.",
                request_stage,
                (response_format or {}).get("type", "none"),
                retry_number + attempt,
                duration_ms,
                getattr(usage, "prompt_tokens", "unknown"),
                getattr(usage, "completion_tokens", "unknown"),
            )
            return ChatCompletionResult(
                content=content,
                finish_reason=getattr(choice, "finish_reason", None),
                prompt_tokens=getattr(usage, "prompt_tokens", None),
                completion_tokens=getattr(usage, "completion_tokens", None),
                total_tokens=getattr(usage, "total_tokens", None),
            )
        except MindMapGenerationCancelled:
            logger.info(
                "Groq request cancelled: stage=%s mode=%s duration_ms=%.1f.",
                request_stage,
                (response_format or {}).get("type", "none"),
                (time.perf_counter() - request_started) * 1000,
            )
            raise
        except Exception as error:
            logger.info(
                "Groq request failed: stage=%s mode=%s retry=%d duration_ms=%.1f.",
                request_stage,
                (response_format or {}).get("type", "none"),
                retry_number + attempt,
                (time.perf_counter() - request_started) * 1000,
            )
            status_code = getattr(error, "status_code", None)
            error_text = str(error).lower()
            api_message, api_code, failed_generation = _groq_error_details(error)
            missing_properties = _missing_mind_map_fields(failed_generation)
            incomplete_json = False
            if failed_generation:
                try:
                    json.loads(failed_generation)
                except (json.JSONDecodeError, TypeError):
                    incomplete_json = True
            if (
                response_format is not None
                and status_code in (400, 422)
                and api_code == "json_validate_failed"
                and (
                    "truncat" in (api_message or "").lower()
                    or incomplete_json
                    or (failed_generation and "related_concepts" in missing_properties)
                )
            ):
                raise GroqCompletionOutputTruncatedError(
                    "Groq rejected an incomplete structured completion.",
                    status_code=status_code,
                    api_code=api_code,
                    api_message=api_message,
                    output_chars=len(failed_generation),
                    missing_properties=missing_properties,
                ) from error
            is_structured_rejection = any(
                marker in error_text
                for marker in ("response_format", "json_schema", "structured output", "schema")
            ) or api_code == "json_validate_failed"
            if response_format is not None and status_code in (400, 422) and is_structured_rejection:
                raise StructuredOutputUnsupportedError(
                    "Groq rejected the structured output format.",
                    status_code=status_code,
                    api_code=api_code,
                    api_message=api_message,
                ) from error
            token_limit_error = any(
                marker in error_text
                for marker in (
                    "tokens per minute", "token per minute", "tpm", "requested tokens",
                    "context_length_exceeded", "maximum context", "prompt is too long",
                )
            )
            if status_code == 429 and token_limit_error:
                raise RuntimeError(
                    "The mind map request exceeded Groq's token limit. "
                    "Please retry; the document will be split into smaller sections."
                ) from error
            if status_code == 429 and attempt < 2:
                retry_after = getattr(getattr(error, "response", None), "headers", {}).get("retry-after")
                try:
                    wait_seconds = max(2 ** (attempt + 1), float(retry_after) if retry_after is not None else 0)
                except (TypeError, ValueError):
                    wait_seconds = 2 ** (attempt + 1)
                if request_stage == "api" and chunk_size is None and retry_number == 0:
                    logger.warning(
                        "Groq rate limited a request; retrying in %s seconds.",
                        wait_seconds,
                    )
                else:
                    logger.warning(
                        "Groq rate limited a request: stage=%s mode=%s "
                        "max_completion_tokens=%s retry=%d chunk_size=%s backoff_seconds=%s.",
                        request_stage,
                        (response_format or {}).get("type", "none"),
                        max_tokens if max_tokens is not None else "provider-default",
                        retry_number + attempt + 1,
                        chunk_size if chunk_size is not None else "n/a",
                        wait_seconds,
                    )
                if cancellation is None:
                    time.sleep(wait_seconds)
                else:
                    cancellation.wait(wait_seconds)
                continue
            if status_code == 429:
                raise RuntimeError("Groq is temporarily rate-limiting requests. Please try again shortly.") from error
            if status_code in (400, 413):
                raise RuntimeError("Groq rejected the request size. Please retry with a smaller document.") from error
            logger.error("Groq request failed (status %s).", status_code)
            raise RuntimeError("Groq could not generate a response. Please try again later.") from error
    raise RuntimeError("Groq could not generate a response.")


def _chat(prompt: str, max_tokens: int | None = None) -> str:
    """Send a prompt to the selected AI provider."""

    if AI_PROVIDER == "groq":
        return _groq_chat_completion(prompt, max_tokens).content

    elif AI_PROVIDER == "gemini":
        if gemini_client is None:
            raise RuntimeError(
                "GEMINI_API_KEY is missing. Check the backend .env file."
            )

        max_attempts = 3

        for attempt in range(max_attempts):
            try:
                request = {"model": GEMINI_MODEL, "contents": prompt}
                if max_tokens is not None:
                    request["config"] = {"max_output_tokens": max_tokens}
                response = gemini_client.models.generate_content(**request)
                return response.text or ""

            except errors.APIError as error:
                status_code = getattr(error, "code", None)

                if status_code not in (429, 500, 502, 503, 504):
                    raise

                if attempt == max_attempts - 1:
                    raise RuntimeError(
                        "The AI provider could not generate a response. Please try again later."
                    ) from error

                wait_seconds = 2 ** (attempt + 1)
                logger.warning(
                    "Gemini temporary error (%s); retrying in %s seconds.",
                    status_code,
                    wait_seconds,
                )
                time.sleep(wait_seconds)

    else:
        raise RuntimeError(
            f"Unsupported AI_PROVIDER: {AI_PROVIDER}. "
            "Choose 'groq' or 'gemini' in the .env file."
        )

    raise RuntimeError("The AI provider could not generate a response.")

def summarize_content(
    text: str,
    mode: str = "medium",
    language: str = "english",
) -> str:
    """Generate a summary of the provided text."""

    lang_instruction = (
        "Respond in Malayalam."
        if language.lower() == "malayalam"
        else "Respond in English."
    )

    length_map = {
        "short": "Provide a concise summary in 3-5 bullet points.",
        "medium": (
            "Provide a detailed summary with 8-12 bullet points covering "
            "key concepts, definitions, and main ideas."
        ),
        "detailed": (
            "Provide a comprehensive summary with sections, bullet points, "
            "key concepts, important terms, formulas, and facts."
        ),
    }

    length_instruction = length_map.get(mode, length_map["medium"])

    prompt = f"""You are an expert study assistant. {lang_instruction}

Analyze the following study material and {length_instruction}

Format your response with:
- A title/topic line
- Key Concepts section
- Main Points as bullet points
- Quick Facts, if any

Study Material:
\"\"\"
{text}
\"\"\"
"""

    return _chat(prompt)


def answer_question(
    context: str,
    question: str,
    chat_history: list,
    language: str = "english",
) -> str:
    """Answer questions based on uploaded study material."""

    lang_instruction = (
        "Respond in Malayalam."
        if language.lower() == "malayalam"
        else "Respond in English."
    )

    history_text = ""

    if chat_history:
        history_text = "\n\nPrevious conversation:\n"

        for msg in chat_history[-6:]:
            history_text += (
                f"User: {msg['user']}\n"
                f"Assistant: {msg['assistant']}\n\n"
            )

    prompt = f"""You are a helpful study assistant. {lang_instruction}
Answer strictly based on the study material below.
If the answer is not found, say:
"I couldn't find information about this in your uploaded material."
Be encouraging and clear.

{history_text}

Study Material:
\"\"\"
{context}
\"\"\"

Student's Question: {question}

Provide a clear answer with supporting details and examples when relevant.
"""

    return _chat(prompt)


def generate_study_plan(
    subject: str,
    topics: str,
    exam_date: str,
    hours_per_day: int,
    language: str = "english",
) -> str:
    """Generate a personalized study plan using the actual available days."""

    from datetime import date, timedelta

    try:
        exam_day = date.fromisoformat(exam_date)
    except (ValueError, TypeError):
        raise ValueError("Please provide a valid exam date in YYYY-MM-DD format.")

    today = date.today()

    if exam_day < today:
        raise ValueError("The exam date cannot be in the past.")

    if not isinstance(hours_per_day, int) or isinstance(hours_per_day, bool):
        raise ValueError("Study hours must be a whole number.")

    if not 1 <= hours_per_day <= 16:
        raise ValueError("Study hours must be between 1 and 16 per day.")

    available_days = (exam_day - today).days

    lang_instruction = (
        "Respond in Malayalam."
        if language.lower() == "malayalam"
        else "Respond in English."
    )

    if available_days == 0:
        schedule_instruction = (
            "The exam is TODAY. Create a last-day revision plan only. "
            "Do not invent additional study days or dates."
        )
    else:
        study_start = today.isoformat()
        study_end = (exam_day - timedelta(days=1)).isoformat()

        schedule_instruction = f"""
Create a realistic day-by-day schedule using ONLY these dates:
- Start date: {study_start}
- Final study date: {study_end}
- Available study days: {available_days}

Do not include dates outside this range.
Do not invent a 28-day or 4-week schedule when fewer days are available.
Prioritize important topics, practice, and revision according to the time remaining.
"""

    prompt = f"""You are an expert academic planner. {lang_instruction}

Create a practical, personalized study plan based on the information below.

Current date: {today.isoformat()}
Exam date: {exam_day.isoformat()}
Subject: {subject}
Topics: {topics}
Available study time: {hours_per_day} hours per day
Days before the exam: {available_days}

DATE RULES:
{schedule_instruction}

Include:
- Daily topics and realistic time allocation.
- Use the student's provided topics as the main study syllabus.
- Do not introduce unrelated topics that the student did not provide.
- If a prerequisite is essential, briefly explain why it is needed.
- Include practice questions based on the provided topics.
- Include revision of previously studied topics.
- Prioritize the provided topics according to the available time.
- Include a short pre-exam checklist.

Keep the plan achievable. Never invent extra study days or dates.
"""

    return _chat(prompt)


def generate_quiz(
    context: str,
    question_count: int,
    difficulty: str,
    language: str = "english",
    previous_questions: Optional[list[str]] = None,
) -> list[dict[str, object]]:
    """Generate and validate multiple-choice questions from study material."""
    if question_count not in (5, 10, 15):
        raise ValueError("Question count must be 5, 10, or 15.")
    if difficulty not in ("easy", "medium", "hard"):
        raise ValueError("Difficulty must be easy, medium, or hard.")
    if not context.strip():
        raise ValueError("The uploaded document has no usable study content.")

    previous_question_guidance = ""
    if previous_questions:
        previous_question_list = "\n".join(
            f"- {question}" for question in previous_questions
        )
        previous_question_guidance = f"""
Questions from the immediately previous quiz:
{previous_question_list}

Avoid repeating these questions or merely rephrasing them. Vary the concepts
and question focus while staying faithful to the study material. If the source
offers limited distinct content, prioritize accuracy over uniqueness.
"""

    prompt = f"""You are an expert study-quiz writer. Use ONLY the study material below.
Do not use outside knowledge or invent facts not supported by the material.
Write exactly {question_count} multiple-choice questions at {difficulty} difficulty.
Write all questions, options, and explanations in {language}.
{previous_question_guidance}

Return only a valid JSON object with this exact shape:
{{
  "questions": [
    {{
      "question": "Question text",
      "options": [
        {{"id": "A", "text": "Option text"}},
        {{"id": "B", "text": "Option text"}},
        {{"id": "C", "text": "Option text"}},
        {{"id": "D", "text": "Option text"}}
      ],
      "correct_option_id": "A",
      "explanation": "Why the correct option is supported by the material"
    }}
  ]
}}

Every question must have exactly four distinct options with IDs A, B, C, D
and exactly one correct option. Explanations must be grounded in the material.
Do not include markdown fences or any text outside the JSON object.

Study material:
\"\"\"
{context}
\"\"\"
"""

    response = _chat(prompt).strip()
    if response.startswith("```"):
        response = response.removeprefix("```json").removeprefix("```").strip()
        if response.endswith("```"):
            response = response[:-3].strip()

    try:
        payload = json.loads(response)
    except json.JSONDecodeError:
        start = response.find("{")
        end = response.rfind("}")
        if start < 0 or end <= start:
            raise ValueError(
                "The AI returned an invalid quiz. Please try generating it again."
            ) from None
        try:
            payload = json.loads(response[start : end + 1])
        except json.JSONDecodeError:
            raise ValueError(
                "The AI returned an invalid quiz. Please try generating it again."
            ) from None

    questions = payload.get("questions") if isinstance(payload, dict) else None
    if not isinstance(questions, list) or len(questions) != question_count:
        raise ValueError(
            "The AI returned an invalid quiz. Please try generating it again."
        )

    validated_questions: list[dict[str, object]] = []
    option_ids = {"A", "B", "C", "D"}
    for question in questions:
        if not isinstance(question, dict):
            raise ValueError(
                "The AI returned an invalid quiz. Please try generating it again."
            )

        prompt_text = question.get("question")
        explanation = question.get("explanation")
        options = question.get("options")
        correct_option_id = question.get("correct_option_id")
        if (
            not isinstance(prompt_text, str)
            or not prompt_text.strip()
            or not isinstance(explanation, str)
            or not explanation.strip()
            or not isinstance(options, list)
            or len(options) != 4
            or not isinstance(correct_option_id, str)
            or correct_option_id not in option_ids
        ):
            raise ValueError(
                "The AI returned an invalid quiz. Please try generating it again."
            )

        validated_options: list[dict[str, str]] = []
        for option in options:
            if (
                not isinstance(option, dict)
                or not isinstance(option.get("id"), str)
                or option["id"] not in option_ids
                or not isinstance(option.get("text"), str)
                or not option["text"].strip()
            ):
                raise ValueError(
                    "The AI returned an invalid quiz. Please try generating it again."
                )
            validated_options.append(
                {"id": option["id"], "text": option["text"].strip()}
            )

        if (
            {option["id"] for option in validated_options} != option_ids
            or len({option["text"].casefold() for option in validated_options}) != 4
        ):
            raise ValueError(
                "The AI returned an invalid quiz. Please try generating it again."
            )

        validated_questions.append(
            {
                "question": prompt_text.strip(),
                "options": validated_options,
                "correct_option_id": correct_option_id,
                "explanation": explanation.strip(),
            }
        )

    return validated_questions


def generate_flashcards(
    context: str,
    count: int = 10,
    language: str = "english",
) -> list[dict[str, str]]:
    """Generate study flashcards from uploaded material."""
    if count not in (5, 10, 15):
        raise ValueError("Flashcard count must be 5, 10, or 15.")
    if not context.strip():
        raise ValueError("The uploaded document has no usable study content.")

    prompt = f"""You are an expert study assistant. Use ONLY the study material below.
Create exactly {count} flashcards for revision. Write all text in {language}.
Each flashcard must have a concise front (question/term) and a clear back (answer/explanation).

Return only a valid JSON object with this exact shape:
{{
  "flashcards": [
    {{"front": "Front text", "back": "Back text"}}
  ]
}}

Do not include markdown fences or any text outside the JSON object.

Study material:
\"\"\"
{context}
\"\"\"
"""

    response = _chat(prompt).strip()
    if response.startswith("```"):
        response = response.removeprefix("```json").removeprefix("```").strip()
        if response.endswith("```"):
            response = response[:-3].strip()

    try:
        payload = json.loads(response)
    except json.JSONDecodeError:
        start = response.find("{")
        end = response.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("The AI returned invalid flashcards. Please try again.") from None
        try:
            payload = json.loads(response[start : end + 1])
        except json.JSONDecodeError:
            raise ValueError("The AI returned invalid flashcards. Please try again.") from None

    flashcards = payload.get("flashcards") if isinstance(payload, dict) else None
    if not isinstance(flashcards, list) or len(flashcards) != count:
        raise ValueError("The AI returned invalid flashcards. Please try again.")

    validated: list[dict[str, str]] = []
    for card in flashcards:
        if not isinstance(card, dict):
            raise ValueError("The AI returned invalid flashcards. Please try again.")
        front = card.get("front")
        back = card.get("back")
        if not isinstance(front, str) or not front.strip() or not isinstance(back, str) or not back.strip():
            raise ValueError("The AI returned invalid flashcards. Please try again.")
        validated.append({"front": front.strip(), "back": back.strip()})

    return validated


def general_answer(question, chat_history=None, language="english"):
    """Answer a general question without uploaded notes."""
    history = chat_history or []

    prompt = f"""
You are StudyMate AI, a helpful study assistant.
Answer the user's question clearly and accurately.
Use simple language and headings or bullet points when useful.
If the user asks for a table, provide a Markdown table.
Respond in {language}.

Conversation history:
{history}

User question:
{question}
"""
    return _chat(prompt)
