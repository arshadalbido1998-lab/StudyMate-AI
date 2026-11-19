r"""Measure Mind Map stages for one PDF/TXT/MD without changing production code.

Offline mode only extracts and plans chunks:
    .\.venv\Scripts\python.exe .\benchmark_mind_map_pipeline.py .\sample.pdf

Opt-in live mode sends the selected document text to the configured Cloudflare
Workers AI account and measures provider, merge, validation, and total time:
    .\.venv\Scripts\python.exe .\benchmark_mind_map_pipeline.py .\sample.pdf --live

The script never prints document text or API credentials. Live mode can consume
Cloudflare Workers AI usage and should be used only when that is acceptable.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Any, Callable

from services import mind_map_service
from services.pdf_service import extract_text_from_pdf, extract_text_from_txt


def read_document(path: Path) -> tuple[str, float]:
    started = time.perf_counter()
    raw = path.read_bytes()
    if path.suffix.lower() == ".pdf":
        text = extract_text_from_pdf(raw)
    elif path.suffix.lower() in {".txt", ".md"}:
        text = extract_text_from_txt(raw)
    else:
        raise ValueError("Choose a PDF, TXT, or MD file.")
    return text, (time.perf_counter() - started) * 1000


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path, help="PDF, TXT, or MD file to measure")
    parser.add_argument(
        "--live",
        action="store_true",
        help="send the document to Cloudflare and measure real generation timings",
    )
    parser.add_argument("--language", default="English")
    args = parser.parse_args()

    if not args.file.is_file():
        parser.error("input file does not exist")
    try:
        document, extraction_ms = read_document(args.file)
        tokens = mind_map_service._token_count(document)
        chunk_started = time.perf_counter()
        chunks = mind_map_service._source_chunks(document, args.language)
        chunking_ms = (time.perf_counter() - chunk_started) * 1000
        direct_prompt = mind_map_service._make_prompt(
            document,
            args.language,
            partial=False,
            document_token_count=tokens,
        )
        try:
            mind_map_service._check_prompt_budget(direct_prompt)
            direct_fits = True
        except ValueError:
            direct_fits = False

        print(f"File type: {args.file.suffix.lower()}")
        print(f"Document characters: {len(document)}")
        print(f"Document tokens: {tokens}")
        print(f"Text extraction: {extraction_ms:.1f} ms")
        print(f"Chunk planning: {chunking_ms:.1f} ms")
        print(f"Planned source chunks: {len(chunks)}")
        print(f"Direct one-request prompt fits current budget: {direct_fits}")
        if not args.live:
            print("AI requests: 0 (offline mode)")
            print("Run again with --live to measure Cloudflare generation and merge timings.")
            return 0

        provider_calls: list[dict[str, Any]] = []
        validation_calls: list[float] = []
        original_provider = mind_map_service.cloudflare_mind_map_completion
        original_validator: Callable[..., Any] = mind_map_service.validate_mind_map

        def timed_provider(*provider_args: Any, **provider_kwargs: Any) -> Any:
            stage = provider_kwargs.get("request_stage", "unknown")
            call_started = time.perf_counter()
            result: Any = None
            try:
                result = original_provider(*provider_args, **provider_kwargs)
                return result
            finally:
                provider_calls.append({
                    "stage": stage,
                    "duration_ms": (time.perf_counter() - call_started) * 1000,
                    "truncated": getattr(result, "truncated", None),
                    "finish_reason": getattr(result, "finish_reason", None),
                    "completion_tokens": getattr(result, "completion_tokens", None),
                })

        def timed_validator(*validator_args: Any, **validator_kwargs: Any) -> Any:
            call_started = time.perf_counter()
            try:
                return original_validator(*validator_args, **validator_kwargs)
            finally:
                validation_calls.append((time.perf_counter() - call_started) * 1000)

        mind_map_service.cloudflare_mind_map_completion = timed_provider
        mind_map_service.validate_mind_map = timed_validator
        pipeline_started = time.perf_counter()
        generated_map: dict[str, Any] | None = None
        try:
            generated_map = mind_map_service.generate_mind_map(document, args.language)
        finally:
            total_ms = (time.perf_counter() - pipeline_started) * 1000
            mind_map_service.cloudflare_mind_map_completion = original_provider
            mind_map_service.validate_mind_map = original_validator

        provider_total = sum(call["duration_ms"] for call in provider_calls)
        merge_total = sum(
            call["duration_ms"] for call in provider_calls if call["stage"] == "merge"
        )
        print(f"Cloudflare requests: {len(provider_calls)} (sequential)")
        print(
            "Request counts: "
            + ", ".join(
                f"{stage}={sum(call['stage'] == stage for call in provider_calls)}"
                for stage in ("chunk", "merge", "repair")
            )
        )
        for index, call in enumerate(provider_calls, 1):
            print(
                f"  Request {index}: stage={call['stage']} "
                f"duration={call['duration_ms']:.1f} ms "
                f"truncated={call['truncated'] if call['truncated'] is not None else 'unknown'} "
                f"completion_tokens={call['completion_tokens'] if call['completion_tokens'] is not None else 'unknown'}"
            )
        confirmed_truncations = sum(call["truncated"] is True for call in provider_calls)
        print(f"Confirmed truncated responses: {confirmed_truncations}")
        print(f"Cloudflare time total: {provider_total:.1f} ms")
        print(f"Cloudflare merge request time: {merge_total:.1f} ms")
        print(
            "Local validation time total: "
            f"{sum(validation_calls):.1f} ms across {len(validation_calls)} validation(s)"
        )
        print(f"Generation pipeline total: {total_ms:.1f} ms")
        print(f"Other pipeline time (chunking/prompt handling/etc.): {max(0.0, total_ms - provider_total):.1f} ms")
        if generated_map is not None:
            main_topics = generated_map.get("main_topics", [])
            related_concepts = generated_map.get("related_concepts", [])
            node_count = 1 + sum(
                1 + len(topic.get("subtopics", [])) for topic in main_topics
            ) + len(related_concepts)
            map_text_parts: list[str] = []
            for node in [generated_map.get("central_topic", {}), *main_topics,
                         *(sub for topic in main_topics for sub in topic.get("subtopics", [])),
                         *related_concepts]:
                for field in ("label", "description", "relationship"):
                    value = node.get(field)
                    if isinstance(value, str):
                        map_text_parts.append(value.lower())
            map_text = " ".join(map_text_parts)
            important_terms = (
                "nucleus", "mitochondria", "membrane", "osmosis",
                "active transport", "atp", "cellular respiration",
                "photosynthesis", "dna", "transcription", "translation",
                "mitosis", "homeostasis",
            )
            retained_terms = sum(term in map_text for term in important_terms)
            print(f"Map structure: nodes={node_count} branches={len(main_topics)} cross_links={len(related_concepts)}")
            print(
                "Important concept coverage: "
                f"{retained_terms}/{len(important_terms)} expected concepts represented"
            )
        return 0
    except Exception as error:
        print(f"Benchmark failed: {type(error).__name__}: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
