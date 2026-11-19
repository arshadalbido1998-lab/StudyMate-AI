"""Sequential, non-production benchmark for OpenRouter mind-map models.

Run from the backend folder with the same Python environment as the app:
    python .\benchmark_openrouter_mind_map.py
    python .\benchmark_openrouter_mind_map.py --model dots-studio/dots-3-note-preview:free

This script reads OPENROUTER_API_KEY from the adjacent .env file, performs a
non-generation connectivity check, then sends at most three requests per model.
It does not change production settings or write benchmark output to disk.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import httpx
from dotenv import dotenv_values
from openai import APIConnectionError, APIError, APITimeoutError


BACKEND_DIR = Path(__file__).resolve().parent
ENV_PATH = BACKEND_DIR / ".env"
BASE_URL = "https://openrouter.ai/api/v1"
MODELS = (
    "particle-ai/particle-1:free",
    "baidu/ernie-5.5-flash-preview:free",
    "dots-studio/dots-3-note-preview:free",
)
TRIALS_PER_MODEL = 3
MAX_OUTPUT_TOKENS = 4_000
TEMPERATURE = 0.3
REQUEST_TIMEOUT_SECONDS = 90

SYNTHETIC_SOURCE = """Photosynthesis converts light energy into chemical energy in plants, algae, and some bacteria. Chlorophyll in chloroplasts absorbs light, especially red and blue wavelengths, while reflecting green light. During the light-dependent reactions, water molecules are split, releasing oxygen and producing ATP and NADPH. The Calvin cycle uses ATP and NADPH to fix carbon dioxide into glucose. Stomata regulate gas exchange: carbon dioxide enters and oxygen exits, while guard cells adjust stomatal opening in response to water availability. Light intensity, carbon dioxide concentration, and temperature affect the rate of photosynthesis. Photosynthesis stores energy in glucose and supports food webs; cellular respiration later releases usable energy from glucose."""


def _api_key_from_env() -> str:
    if not ENV_PATH.is_file():
        raise RuntimeError(f"Backend .env file not found: {ENV_PATH}")
    key = (dotenv_values(ENV_PATH).get("OPENROUTER_API_KEY") or "").strip()
    if not key or key.lower().startswith(("your_", "replace", "put_")):
        raise RuntimeError("OPENROUTER_API_KEY is missing or a placeholder in the backend .env file.")
    return key


def _connectivity_check(api_key: str) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{BASE_URL}/models",
        headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
        method="GET",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            latency_ms = round((time.perf_counter() - started) * 1000, 1)
            response.read(1)
            if not 200 <= response.status < 300:
                return {"ok": False, "http_status": response.status, "latency_ms": latency_ms}
            return {"ok": True, "http_status": response.status, "latency_ms": latency_ms}
    except urllib.error.HTTPError as error:
        return {
            "ok": False,
            "http_status": error.code,
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            "error": "OpenRouter rejected the connectivity check; verify the key and account access.",
        }
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        reason = getattr(error, "reason", error)
        return {
            "ok": False,
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            "error": f"Network connectivity check failed: {type(reason).__name__}: {reason}",
        }


def _production_validation(content: str) -> tuple[bool, str | None]:
    from services.mind_map_service import (
        _normalize_mind_map,
        _parse_json_response,
        validate_mind_map,
    )

    try:
        parsed = _parse_json_response(content)
        validate_mind_map(_normalize_mind_map(parsed))
        return True, None
    except (ValueError, TypeError, json.JSONDecodeError) as error:
        return False, f"{type(error).__name__}: {error}"


def _one_trial(client: Any, model: str, prompt: str) -> dict[str, Any]:
    from services.mind_map_service import mind_map_json_schema

    record: dict[str, Any] = {"model": model}
    started = time.perf_counter()
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=TEMPERATURE,
            max_tokens=MAX_OUTPUT_TOKENS,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "mind_map",
                    "strict": True,
                    "schema": mind_map_json_schema(),
                },
            },
            extra_body={"provider": {"require_parameters": True}},
        )
        record["latency_ms"] = round((time.perf_counter() - started) * 1000, 1)
        record["http_status"] = 200
        record["model_available"] = True
        record["returned_model_id"] = getattr(response, "model", None)
        choices = getattr(response, "choices", []) or []
        choice = choices[0] if choices else None
        record["finish_reason"] = getattr(choice, "finish_reason", None)
        record["truncated"] = record["finish_reason"] == "length"
        usage = getattr(response, "usage", None)
        record["token_usage"] = {
            "prompt_tokens": getattr(usage, "prompt_tokens", None),
            "completion_tokens": getattr(usage, "completion_tokens", None),
            "total_tokens": getattr(usage, "total_tokens", None),
        }
        message = getattr(choice, "message", None)
        content = getattr(message, "content", "") if message is not None else ""
        if not isinstance(content, str):
            content = ""
        try:
            json.loads(content)
            record["json_parse_success"] = True
        except (json.JSONDecodeError, TypeError):
            record["json_parse_success"] = False
        valid, validation_error = _production_validation(content)
        record["production_validation_success"] = valid
        return record
    except (httpx.TimeoutException, APITimeoutError):
        record["latency_ms"] = round((time.perf_counter() - started) * 1000, 1)
        record.update(error_category="timeout", rate_limited=False)
        return record
    except (httpx.ConnectError, httpx.NetworkError, APIConnectionError) as error:
        record["latency_ms"] = round((time.perf_counter() - started) * 1000, 1)
        record.update(error_category="connection_error", error_type=type(error).__name__, rate_limited=False)
        return record
    except APIError as error:
        record["latency_ms"] = round((time.perf_counter() - started) * 1000, 1)
        status = getattr(error, "status_code", None)
        record["http_status"] = status
        record["model_available"] = False if status == 404 else None
        record["error_category"] = "rate_limit" if status == 429 else "openai_api_error"
        record["error_type"] = type(error).__name__
        record["rate_limited"] = status == 429
        return record


def main() -> int:
    parser = argparse.ArgumentParser(description="Sequential OpenRouter mind-map model benchmark.")
    parser.add_argument(
        "--model",
        dest="models",
        action="append",
        choices=MODELS,
        help="Model ID to benchmark; repeat this option to select multiple models. Defaults to all models.",
    )
    args = parser.parse_args()
    selected_models = args.models or MODELS

    api_key = _api_key_from_env()
    connectivity = _connectivity_check(api_key)
    print("Connectivity check:")
    print(json.dumps(connectivity, indent=2))
    if not connectivity["ok"]:
        print("Benchmark stopped before model trials.")
        return 2

    # Ensure imports resolve from this backend folder when launched by full path.
    sys.path.insert(0, str(BACKEND_DIR))
    from openai import OpenAI
    from services.mind_map_service import _make_prompt

    prompt = _make_prompt(SYNTHETIC_SOURCE, "English", partial=False)
    client = OpenAI(api_key=api_key, base_url=BASE_URL, timeout=REQUEST_TIMEOUT_SECONDS, max_retries=0)
    results: list[dict[str, Any]] = []
    stop_for_rate_limit = False
    stop_for_auth = False
    interrupted = False

    try:
        for model in selected_models:
            for trial in range(1, TRIALS_PER_MODEL + 1):
                if stop_for_rate_limit or stop_for_auth:
                    break
                print(f"Starting trial {trial}/{TRIALS_PER_MODEL} for model {model}.", flush=True)
                trial_started = time.perf_counter()
                try:
                    result = _one_trial(client, model, prompt)
                except KeyboardInterrupt:
                    result = {
                        "model": model,
                        "trial": trial,
                        "latency_ms": round((time.perf_counter() - trial_started) * 1000, 1),
                        "error_category": "interrupted",
                    }
                    results.append(result)
                    print(f"Finished trial {trial}/{TRIALS_PER_MODEL} for model {model} (interrupted).", flush=True)
                    interrupted = True
                    break
                result["trial"] = trial
                results.append(result)
                print(f"Finished trial {trial}/{TRIALS_PER_MODEL} for model {model}.", flush=True)
                if result.get("rate_limited"):
                    stop_for_rate_limit = True
                    break
                if result.get("http_status") in (401, 403):
                    stop_for_auth = True
                    break
                if result.get("http_status") in (400, 404, 422):
                    # A repeated identical request cannot fix an unsupported model or format.
                    break
                if result.get("error_category") in {"timeout", "connection_error"}:
                    # Do not spend more trials on a model with a transport failure.
                    break
            if interrupted:
                break
    except KeyboardInterrupt:
        interrupted = True
        print("\nBenchmark interrupted by Ctrl+C; reporting completed trials.", flush=True)

    print("\nBenchmark results (request content and API key are omitted):")
    print(json.dumps({
        "prompt_source": "identical synthetic photosynthesis source for every model",
        "temperature": TEMPERATURE,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "trials_per_model": TRIALS_PER_MODEL,
        "models_selected": selected_models,
        "sequential": True,
        "stopped_for_rate_limit": stop_for_rate_limit,
        "stopped_for_network_error": False,
        "stopped_for_auth_error": stop_for_auth,
        "interrupted": interrupted,
        "results": results,
    }, indent=2))
    client.close()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        # Do not include arbitrary exception details that could contain credentials.
        print(f"Benchmark setup failed: {type(error).__name__}.", file=sys.stderr)
        raise SystemExit(1)
