"""Document-grounded mind map generation and response validation."""

import asyncio
import hashlib
import json
import logging
import os
import re
import threading
import time
from copy import deepcopy
from typing import Any, Callable

import tiktoken

from services.cloudflare_service import (
    CLOUDFLARE_MODEL,
    CloudflareRateLimitError,
    cloudflare_mind_map_completion,
)
from services.mind_map_cancellation import (
    MindMapGenerationCancellation,
    MindMapGenerationCancelled,
)

logger = logging.getLogger(__name__)

MAX_MIND_MAP_SOURCE_CHARS = 768_000
MAX_MIND_MAP_REQUEST_TOKENS = 7_200
MAX_MIND_MAP_PROMPT_TOKENS = 3_200
MAX_MIND_MAP_OUTPUT_TOKENS = 4_000
MIND_MAP_SOURCE_CHUNK_TOKENS = 2_200
MIND_MAP_MEDIUM_DOCUMENT_MAX_TOKENS = MIND_MAP_SOURCE_CHUNK_TOKENS * 5
MAX_MIND_MAP_CHUNK_RETRIES = 4
MAX_MAIN_TOPICS = 8
MAX_SUBTOPICS_PER_TOPIC = 5
MAX_RELATED_CONCEPTS = 12
MAX_LABEL_LENGTH = 100
MAX_DESCRIPTION_LENGTH = 280
ProgressCallback = Callable[..., None]


def _chunk_concurrency() -> int:
    """Read a conservative worker limit, never exceeding the safe cap of 3."""
    raw = os.getenv("STUDYMATE_MIND_MAP_CONCURRENCY", "2").strip()
    try:
        configured = int(raw)
    except ValueError:
        logger.warning("Invalid mind map concurrency setting; using default 2.")
        return 2
    return max(1, min(3, configured))




class MindMapTooLargeError(ValueError):
    """The document exceeds the bounded amount of source text we can map."""


class MindMapTruncatedResponseError(ValueError):
    """The provider stopped before it completed a mind map response."""


class AmbiguousRelationshipReferenceError(ValueError):
    """A cross-link target ID names multiple hierarchy nodes."""


def mind_map_json_schema() -> dict[str, Any]:
    """Return the strict-output-compatible subset of the validated map contract."""

    def node_schema(properties: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": properties,
            "required": list(properties),
            "additionalProperties": False,
        }

    id_field = {"type": "string"}
    text_field = {"type": "string"}
    central = node_schema({"id": {"type": "string", "enum": ["central"]}, "label": text_field, "description": text_field})
    subtopic = node_schema({"id": id_field, "label": text_field, "description": text_field})
    topic = node_schema({
        "id": id_field,
        "label": text_field,
        "description": text_field,
        "subtopics": {"type": "array", "items": subtopic},
    })
    related = node_schema({
        "id": id_field,
        "label": text_field,
        "description": text_field,
        "related_to": {"type": "array", "items": text_field},
        "relationship": text_field,
    })
    return node_schema({
        "central_topic": central,
        "main_topics": {"type": "array", "items": topic},
        "related_concepts": {"type": "array", "items": related},
    })


def _tokenizer() -> tiktoken.Encoding:
    try:
        return tiktoken.get_encoding("o200k_base")
    except (ValueError, KeyError) as error:
        raise RuntimeError(
            "The mind map tokenizer is unavailable. Please contact support."
        ) from error


def _token_count(text: str) -> int:
    return len(_tokenizer().encode(text, disallowed_special=()))


def _check_prompt_budget(prompt: str) -> None:
    prompt_tokens = _token_count(prompt)
    if (
        prompt_tokens > MAX_MIND_MAP_PROMPT_TOKENS
        or prompt_tokens + MAX_MIND_MAP_OUTPUT_TOKENS > MAX_MIND_MAP_REQUEST_TOKENS
    ):
        raise ValueError(
            "The mind map request exceeded its safe token budget. "
            "Please try again or upload a smaller document."
        )


def _mind_map_size_profile(document_tokens: int) -> tuple[str, int, int, int]:
    """Return label, minimum branches, maximum branches and related-node cap."""
    if document_tokens <= MIND_MAP_SOURCE_CHUNK_TOKENS:
        return "short", 3, 4, MAX_RELATED_CONCEPTS
    if document_tokens <= MIND_MAP_MEDIUM_DOCUMENT_MAX_TOKENS:
        return "medium", 4, 6, MAX_RELATED_CONCEPTS
    return "long", 5, 7, MAX_RELATED_CONCEPTS


def _balanced_map_guidance(
    profile: tuple[str, int, int, int],
) -> str:
    document_size, min_topics, max_topics, max_related = profile
    return f"""Balanced sizing for this {document_size} document:
Use {min_topics} to {max_topics} main branches as scale guidance, not a quota;
include only distinct, source-supported topics. Add subtopics when they represent
important separate ideas; do not invent filler. Treat 15 to 25 total nodes as a
soft range, not a count to fill. Usually include 1 to 4 related-concept nodes;
add more only for important, non-duplicate cross-links, up to {max_related}.
For long documents, prioritize key themes and definitions without dropping a
distinct supported branch."""


def _call_mind_map(
    prompt: str,
    *,
    stage: str = "chunk",
    retry_number: int = 0,
    chunk_size: int | None = None,
    cancellation: MindMapGenerationCancellation | None = None,
) -> str:
    if cancellation is not None:
        cancellation.check()
    _check_prompt_budget(prompt)
    strict_format = {
        "type": "json_schema",
        "json_schema": {
            "name": "mind_map",
            "strict": True,
            "schema": mind_map_json_schema(),
        },
    }
    mode = "json_schema"
    logger.info(
        "Mind map provider selected: provider=Cloudflare Workers AI model=%s stage=%s.",
        CLOUDFLARE_MODEL,
        stage,
    )
    result = cloudflare_mind_map_completion(
        prompt,
        max_tokens=MAX_MIND_MAP_OUTPUT_TOKENS,
        response_format=strict_format,
        request_stage=stage,
        retry_number=retry_number,
        chunk_size=chunk_size,
        cancellation=cancellation,
    )

    logger.info(
        "Mind map provider metadata: provider=Cloudflare Workers AI model=%s stage=%s mode=%s max_tokens=%d "
        "finish_reason=%s prompt_tokens=%s completion_tokens=%s total_tokens=%s "
        "retry=%d chunk_size=%s response_chars=%d.",
        CLOUDFLARE_MODEL,
        stage,
        mode,
        MAX_MIND_MAP_OUTPUT_TOKENS,
        result.finish_reason or "unknown",
        result.prompt_tokens if result.prompt_tokens is not None else "unknown",
        result.completion_tokens if result.completion_tokens is not None else "unknown",
        result.total_tokens if result.total_tokens is not None else "unknown",
        retry_number,
        chunk_size if chunk_size is not None else "n/a",
        len(result.content),
    )
    if result.finish_reason == "length" or getattr(result, "truncated", False):
        raise MindMapTruncatedResponseError(
            "Cloudflare stopped before completing the mind map. The source will be split into smaller sections."
        )
    return result.content


def _parse_json_response(response: str) -> Any:
    text = response.strip()
    decoder = json.JSONDecoder()
    errors: list[json.JSONDecodeError] = []
    best_candidate: dict[str, Any] | None = None
    best_score = -1
    schema_key_groups = (
        {"central_topic", "centralTopic", "root"},
        {"main_topics", "mainTopics", "topics"},
        {"related_concepts", "relatedConcepts"},
    )
    for start, character in enumerate(text):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text, start)
        except json.JSONDecodeError as error:
            errors.append(error)
            continue
        if isinstance(value, dict):
            score = sum(bool(group.intersection(value)) for group in schema_key_groups)
            if score > best_score:
                best_candidate = value
                best_score = score
            if score == len(schema_key_groups):
                return value

    if best_candidate is not None and (best_score > 0 or not errors):
        return best_candidate

    if errors:
        error = errors[-1]
        raise ValueError(
            "The AI response contained incomplete or malformed JSON "
            f"(line {error.lineno}, column {error.colno})."
        ) from error
    raise ValueError("The AI response did not contain a JSON object.")


def _required_text(value: Any, field: str, path: str, limit: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{path}.{field} must be text.")
    text = value.strip()
    if not text or len(text) > limit:
        raise ValueError(f"{path}.{field} must contain 1 to {limit} characters.")
    return text


def validate_mind_map(
    payload: Any,
    *,
    max_main_topics: int = MAX_MAIN_TOPICS,
    max_subtopics_per_topic: int = MAX_SUBTOPICS_PER_TOPIC,
    max_related_concepts: int = MAX_RELATED_CONCEPTS,
) -> dict[str, Any]:
    """Validate and normalize the AI-produced hierarchy and cross-links."""
    if not isinstance(payload, dict):
        raise ValueError("The AI response must be a JSON object.")

    payload = _normalize_duplicate_node_ids(payload)

    central_value = payload.get("central_topic")
    if not isinstance(central_value, dict):
        raise ValueError("The mind map is missing its central topic.")
    central_topic = {
        "id": "central",
        "label": _required_text(
            central_value.get("label"), "label", "central_topic", MAX_LABEL_LENGTH
        ),
        "description": _required_text(
            central_value.get("description"),
            "description",
            "central_topic",
            MAX_DESCRIPTION_LENGTH,
        ),
    }

    raw_topics = payload.get("main_topics")
    if not isinstance(raw_topics, list) or not 1 <= len(raw_topics) <= max_main_topics:
        raise ValueError(f"main_topics must contain 1 to {max_main_topics} topics.")

    identifiers = {"central"}

    def parse_node(raw: Any, path: str) -> dict[str, str]:
        if not isinstance(raw, dict):
            raise ValueError(f"{path} must be an object.")
        node_id = raw.get("id")
        if (
            not isinstance(node_id, str)
            or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}", node_id)
        ):
            raise ValueError(f"{path}.id is invalid.")
        if node_id in identifiers:
            raise ValueError(f"{path}.id duplicates another node id.")
        identifiers.add(node_id)
        return {
            "id": node_id,
            "label": _required_text(raw.get("label"), "label", path, MAX_LABEL_LENGTH),
            "description": _required_text(
                raw.get("description"), "description", path, MAX_DESCRIPTION_LENGTH
            ),
        }

    main_topics: list[dict[str, Any]] = []
    for topic_index, raw_topic in enumerate(raw_topics, start=1):
        topic = parse_node(raw_topic, f"main_topics[{topic_index - 1}]")
        raw_subtopics = raw_topic.get("subtopics")
        if (
            not isinstance(raw_subtopics, list)
            or len(raw_subtopics) > max_subtopics_per_topic
        ):
            raise ValueError(
                f"main_topics[{topic_index - 1}].subtopics must contain at most "
                f"{max_subtopics_per_topic} subtopics."
            )
        topic["subtopics"] = [
            parse_node(subtopic, f"main_topics[{topic_index - 1}].subtopics[{index}]")
            for index, subtopic in enumerate(raw_subtopics)
        ]
        main_topics.append(topic)

    hierarchy_ids = set(identifiers)

    raw_related = payload.get("related_concepts")
    if (
        not isinstance(raw_related, list)
        or len(raw_related) > max_related_concepts
    ):
        raise ValueError(
            f"related_concepts must contain at most {max_related_concepts} concepts."
        )

    related_concepts: list[dict[str, Any]] = []
    for related_index, raw_concept in enumerate(raw_related):
        path = f"related_concepts[{related_index}]"
        concept = parse_node(raw_concept, path)
        raw_related_to = raw_concept.get("related_to")
        if not isinstance(raw_related_to, list) or len(raw_related_to) < 2:
            raise ValueError(
                f"{path}.related_to must connect at least two topic or subtopic nodes."
            )
        related_to: list[str] = []
        for target in raw_related_to:
            if not isinstance(target, str) or target not in hierarchy_ids:
                raise ValueError(f"{path}.related_to contains an unknown node id.")
            if target not in related_to:
                related_to.append(target)
        if len(related_to) < 2:
            raise ValueError(f"{path}.related_to must contain two distinct node ids.")
        if "central" in related_to:
            raise ValueError(f"{path}.related_to cannot reference the central topic.")
        concept["related_to"] = related_to
        concept["relationship"] = _required_text(
            raw_concept.get("relationship"),
            "relationship",
            path,
            MAX_DESCRIPTION_LENGTH,
        )
        related_concepts.append(concept)

    node_count = 1 + sum(
        1 + len(topic["subtopics"]) for topic in main_topics
    ) + len(related_concepts)
    if node_count > 64:
        raise ValueError("The generated mind map contains too many nodes.")

    return {
        "central_topic": central_topic,
        "main_topics": main_topics,
        "related_concepts": related_concepts,
    }


def _normalize_duplicate_node_ids(payload: dict[str, Any]) -> dict[str, Any]:
    """Give colliding node IDs deterministic positional suffixes.

    Cross-links can only target hierarchy nodes. If an original hierarchy ID is
    ambiguous, fail safely instead of guessing which node a relationship meant.
    """
    normalized = deepcopy(payload)
    raw_central = normalized.get("central_topic")
    hierarchy_nodes: list[tuple[str, dict[str, Any]]] = []
    if isinstance(raw_central, dict):
        raw_central["id"] = "central"
        hierarchy_nodes.append(("central_topic", raw_central))
    raw_topics = normalized.get("main_topics")
    if isinstance(raw_topics, list):
        for topic_index, topic in enumerate(raw_topics):
            if not isinstance(topic, dict):
                continue
            hierarchy_nodes.append((f"main_topics[{topic_index}]", topic))
            children = topic.get("subtopics")
            if isinstance(children, list):
                hierarchy_nodes.extend(
                    (f"main_topics[{topic_index}].subtopics[{child_index}]", child)
                    for child_index, child in enumerate(children)
                    if isinstance(child, dict)
                )

    original_ids: dict[str, list[str]] = {}
    for path, node in hierarchy_nodes:
        node_id = node.get("id")
        if isinstance(node_id, str):
            original_ids.setdefault(node_id, []).append(path)
    duplicate_hierarchy_ids = {
        node_id for node_id, paths in original_ids.items() if len(paths) > 1
    }

    nodes: list[tuple[str, dict[str, Any]]] = list(hierarchy_nodes)
    related = normalized.get("related_concepts")
    if isinstance(related, list):
        nodes.extend(
            (f"related_concepts[{index}]", concept)
            for index, concept in enumerate(related)
            if isinstance(concept, dict)
        )

    counts: dict[str, int] = {}
    for _, node in nodes:
        node_id = node.get("id")
        if isinstance(node_id, str):
            counts[node_id] = counts.get(node_id, 0) + 1
    used: set[str] = set()
    for path, node in nodes:
        node_id = node.get("id")
        if not isinstance(node_id, str):
            continue
        if node_id not in used:
            used.add(node_id)
            continue
        path_suffix = re.sub(r"[^a-zA-Z0-9]+", "-", path).strip("-")
        suffix = 2
        candidate = f"{node_id[:42]}-{path_suffix[:16]}-{suffix}"
        while candidate in used or counts.get(candidate, 0):
            suffix += 1
            candidate = f"{node_id[:42]}-{path_suffix[:16]}-{suffix}"
        node["id"] = candidate[:64]
        used.add(node["id"])

    if isinstance(related, list):
        for concept_index, concept in enumerate(related):
            if not isinstance(concept, dict):
                continue
            targets = concept.get("related_to")
            if isinstance(targets, list):
                for target in targets:
                    if target in duplicate_hierarchy_ids:
                        raise AmbiguousRelationshipReferenceError(
                            f"related_concepts[{concept_index}].related_to contains "
                            f"ambiguous node id '{target}'."
                        )
    return normalized


def _schema_instructions(max_topics: int, max_subtopics: int, max_related: int) -> str:
    return f"""Return exactly one JSON object matching this schema. All shown keys
are required, including empty arrays; do not rename, omit, or add fields:
{{
  "central_topic": {{"id": "central", "label": "...", "description": "..."}},
  "main_topics": [
    {{"id": "topic-1", "label": "...", "description": "...", "subtopics": [
      {{"id": "subtopic-1", "label": "...", "description": "..."}}
    ]}}
  ],
  "related_concepts": [
    {{"id": "related-1", "label": "...", "description": "...", "related_to": ["topic-1", "subtopic-1"], "relationship": "..."}}
  ]
}}

Use 1 to {max_topics} main topics, each with a "subtopics" array containing no
more than {max_subtopics} items, and a "related_concepts" array containing no more
than {max_related} items. All node IDs, including central_topic's "central", must
be unique across the entire graph. Every non-central node across main topics, all
subtopics, and related concepts must have a globally unique "id" (never reuse an
id in another branch) containing only letters, digits, underscores, or hyphens;
ids must start with a letter or digit. Each node requires non-empty string "label"
and "description" fields.
Each related concept also requires a non-empty "relationship" string and a
"related_to" array with at least two distinct ids of existing main topics or
subtopics (never "central"). Include a related concept only when the source
supports that connection. Use concise 2-5 word labels. Aim for one 6-14 word
description stating a useful definition, role, mechanism, or cause/effect with
key technical terms. Preserve source terminology; use a synonym to clarify, not
replace, an important term. Cover source-taught definitions, classifications,
processes, characteristics, causes/effects, and key relationships. Keep related
but distinct ideas separate; exclude incidental examples, repetitions, and
unsupported details. Do not repeat a label or another node's explanation. For
related concepts, the description defines the concept; the relationship states
its supported link in one sentence of at most 16 words. Shorten wording before
dropping an important branch, subtopic, or cross-link. Escape quotes, backslashes,
and line breaks inside JSON strings. Do not include markdown, code fences,
comments, or text outside the JSON object."""


def _copy_alias(
    item: dict[str, Any], canonical: str, aliases: tuple[str, ...]
) -> None:
    if canonical not in item:
        for alias in aliases:
            if alias in item:
                item[canonical] = item[alias]
                break


def _normalize_node(raw: Any, *, is_central: bool = False) -> Any:
    if not isinstance(raw, dict):
        return raw
    node = dict(raw)
    _copy_alias(node, "label", ("name", "title"))
    _copy_alias(node, "description", ("details", "summary"))
    if not is_central:
        _copy_alias(node, "id", ("node_id", "nodeId", "identifier"))
        _copy_alias(node, "subtopics", ("children",))
    return node


def _normalize_mind_map(payload: Any) -> Any:
    """Normalize unambiguous naming variants without inventing map content."""
    if not isinstance(payload, dict):
        return payload
    normalized = dict(payload)
    wrapped_map = normalized.get("mind_map")
    if isinstance(wrapped_map, dict) and "central_topic" not in normalized:
        normalized = dict(wrapped_map)
    _copy_alias(normalized, "central_topic", ("centralTopic", "root"))
    _copy_alias(normalized, "main_topics", ("mainTopics", "topics"))
    _copy_alias(normalized, "related_concepts", ("relatedConcepts",))

    normalized["central_topic"] = _normalize_node(
        normalized.get("central_topic"), is_central=True
    )
    raw_topics = normalized.get("main_topics")
    if isinstance(raw_topics, list):
        topics = []
        for raw_topic in raw_topics:
            topic = _normalize_node(raw_topic)
            if isinstance(topic, dict) and isinstance(topic.get("subtopics"), list):
                topic["subtopics"] = [
                    _normalize_node(subtopic) for subtopic in topic["subtopics"]
                ]
            topics.append(topic)
        normalized["main_topics"] = topics

    raw_related = normalized.get("related_concepts")
    if isinstance(raw_related, list):
        related_concepts = []
        for raw_concept in raw_related:
            concept = _normalize_node(raw_concept)
            if isinstance(concept, dict):
                _copy_alias(concept, "related_to", ("relatedTo", "connections"))
                _copy_alias(concept, "relationship", ("relation",))
            related_concepts.append(concept)
        normalized["related_concepts"] = related_concepts
    return normalized


def _response_shape(response: str) -> str:
    """Describe response keys and types only; never log generated text values."""
    try:
        payload = _parse_json_response(response)
    except ValueError:
        return "unparseable"
    if not isinstance(payload, dict):
        return type(payload).__name__

    parts = [f"top_keys={sorted(str(key) for key in payload)}"]
    for key in ("central_topic", "centralTopic", "root"):
        value = payload.get(key)
        if isinstance(value, dict):
            parts.append(f"{key}_keys={sorted(str(field) for field in value)}")
            break
    for key in ("main_topics", "mainTopics", "topics"):
        value = payload.get(key)
        if isinstance(value, list):
            parts.append(f"{key}_count={len(value)}")
            if value and isinstance(value[0], dict):
                parts.append(
                    f"first_topic_keys={sorted(str(field) for field in value[0])}"
                )
            break
    return "; ".join(parts)


def _make_repair_prompt(
    response: str,
    error: ValueError,
    *,
    partial: bool,
) -> str:
    limits = (4, 3, 4) if partial else (
        MAX_MAIN_TOPICS,
        MAX_SUBTOPICS_PER_TOPIC,
        MAX_RELATED_CONCEPTS,
    )
    prefix = f"""Repair the JSON mind map below using only its existing information.
Do not add facts, concepts, descriptions, or relationships. Fix only the reported
schema/format problems. Return exactly one JSON object and no surrounding text.

Validation error:
{error}

Required schema:
{_schema_instructions(*limits)}

Malformed response:"""
    excerpt = response
    while True:
        prompt = f"{prefix}\n{excerpt}"
        try:
            _check_prompt_budget(prompt)
            return prompt
        except ValueError:
            if len(excerpt) <= 256:
                raise
            keep = max(32, len(excerpt) // 4)
            excerpt = (
                f"{excerpt[:keep]}\n[response excerpt shortened]\n"
                f"{excerpt[-keep:]}"
            )


def _make_prompt(
    source: str,
    language: str,
    *,
    partial: bool,
    limits: tuple[int, int, int] | None = None,
    document_token_count: int | None = None,
) -> str:
    if partial:
        task = (
            "Map this excerpt for a later document-wide merge. Keep its distinct "
            "important concepts, definitions, and facts; combine repetitions."
        )
        max_topics, max_subtopics, max_related = limits or (4, 3, 4)
        size_guidance = (
            "Use only the distinct branches and subtopics needed to capture this "
            "excerpt's important information. Do not fill the available counts "
            "or omit an important concept just to meet a size target. Combine "
            "details only when they describe the same concept; keep distinct "
            "concepts as separate nodes."
        )
    else:
        task = (
            "Map the full study document: identify its central idea, major "
            "concepts, useful subtopics, and meaningful supported cross-links."
        )
        document_tokens = (
            document_token_count
            if document_token_count is not None
            else _token_count(source)
        )
        profile = _mind_map_size_profile(document_tokens)
        max_topics, max_subtopics, max_related = (
            limits
            or (profile[2], min(4, MAX_SUBTOPICS_PER_TOPIC), profile[3])
        )
        size_guidance = _balanced_map_guidance(profile)

    return f"""You are StudyMate AI, creating a source-grounded study mind map.
Use only information in the supplied material. Do not add outside knowledge,
assumptions, or unsupported relationships. Write all labels and descriptions in
{language}.

{task}

{_schema_instructions(max_topics, max_subtopics, max_related)}

{size_guidance}

Study material:
<source>
{source}
</source>"""


def _make_merge_prompt(
    maps: list[dict[str, Any]],
    language: str,
    *,
    partial: bool,
    compact: bool = False,
    document_token_count: int | None = None,
) -> str:
    size_guidance = ""
    if compact:
        limits = (2, 1, 2)
        task = (
            "Condense these maps for a later merge. Combine duplicates while "
            "preserving distinct supported topics, definitions, and cross-links."
        )
    elif partial:
        limits = (4, 3, 4)
        task = (
            "Merge these section maps. Combine duplicates; preserve distinct "
            "concepts and meaningful supported cross-branch relationships."
        )
    else:
        profile = _mind_map_size_profile(
            document_token_count
            if document_token_count is not None
            else MIND_MAP_SOURCE_CHUNK_TOKENS + 1
        )
        limits = (profile[2], min(4, MAX_SUBTOPICS_PER_TOPIC), profile[3])
        size_guidance = _balanced_map_guidance(profile)
        task = (
            "Build one coherent map from these section maps. Combine duplicates "
            "and preserve distinct important topics and supported relationships."
        )

    return f"""Merge only concepts supported by these section maps. Add no outside
facts. Write the result in {language}.

{task}

{_schema_instructions(*limits)}

{size_guidance}

Extracted topic maps:
<topic_maps>
{json.dumps(maps, ensure_ascii=False, separators=(",", ":"))}
</topic_maps>"""


def _source_chunks(
    source: str,
    language: str,
    chunk_size: int = MIND_MAP_SOURCE_CHUNK_TOKENS,
) -> list[str]:
    started = time.perf_counter()
    encoding = _tokenizer()
    token_ids = encoding.encode(source, disallowed_special=())
    chunks: list[str] = []
    seen_chunks: set[str] = set()
    dropped_empty = 0
    dropped_duplicate = 0
    base_prompt_tokens = _token_count(_make_prompt("", language, partial=True))
    source_token_budget = min(
        MAX_MIND_MAP_PROMPT_TOKENS - base_prompt_tokens,
        MAX_MIND_MAP_REQUEST_TOKENS - MAX_MIND_MAP_OUTPUT_TOKENS - base_prompt_tokens,
    )
    if source_token_budget < 1:
        raise ValueError("The mind map prompt leaves no room for document text.")
    source_token_budget = min(chunk_size, source_token_budget)
    start = 0

    while start < len(token_ids):
        end = min(start + source_token_budget, len(token_ids))
        while end > start:
            raw_chunk = b"".join(
                encoding.decode_single_token_bytes(token_id)
                for token_id in token_ids[start:end]
            )
            try:
                chunk = raw_chunk.decode("utf-8")
            except UnicodeDecodeError:
                end -= 1
                continue

            prompt_tokens = _token_count(_make_prompt(chunk, language, partial=True))
            prompt_limit = min(
                MAX_MIND_MAP_PROMPT_TOKENS,
                MAX_MIND_MAP_REQUEST_TOKENS - MAX_MIND_MAP_OUTPUT_TOKENS,
            )
            if prompt_tokens <= prompt_limit:
                cleaned = chunk.strip()
                if not cleaned:
                    dropped_empty += 1
                elif cleaned in seen_chunks:
                    dropped_duplicate += 1
                else:
                    chunks.append(cleaned)
                    seen_chunks.add(cleaned)
                start = end
                break
            overflow = prompt_tokens - prompt_limit
            end -= max(8, overflow + 8)
        else:
            raise ValueError(
                "A section of this document could not fit within the safe mind map "
                "token budget. Please try a different document."
            )

    logger.info(
        "Mind map source chunking completed: duration_ms=%.1f source_tokens=%d "
        "chunk_count=%d dropped_empty=%d dropped_duplicate=%d.",
        (time.perf_counter() - started) * 1000,
        len(token_ids),
        len(chunks),
        dropped_empty,
        dropped_duplicate,
    )
    return chunks


def _merge_batches(
    maps: list[dict[str, Any]],
    language: str,
    *,
    partial: bool,
) -> list[list[dict[str, Any]]]:
    batches: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for mind_map in maps:
        candidate = [*current, mind_map]
        prompt = _make_merge_prompt(candidate, language, partial=partial)
        try:
            _check_prompt_budget(prompt)
        except ValueError:
            if not current:
                raise ValueError(
                    "A generated mind map could not fit within the safe merge "
                    "token budget. Please retry."
                )
            batches.append(current)
            current = [mind_map]
            _check_prompt_budget(
                _make_merge_prompt(current, language, partial=partial)
            )
        else:
            current = candidate
    if current:
        batches.append(current)
    return batches


def _generate_validated(
    prompt: str,
    *,
    partial: bool = False,
    stage: str = "merge",
    retry_number: int = 0,
    chunk_size: int | None = None,
    progress_callback: ProgressCallback | None = None,
    cancellation: MindMapGenerationCancellation | None = None,
) -> dict[str, Any]:
    limits = (
        {
            "max_main_topics": 4,
            "max_subtopics_per_topic": 3,
            "max_related_concepts": 4,
        }
        if partial
        else {}
    )
    try:
        if cancellation is not None:
            cancellation.check()
        response = _call_mind_map(
            prompt,
            stage=stage,
            retry_number=retry_number,
            chunk_size=chunk_size,
            cancellation=cancellation,
        )
        if cancellation is not None:
            cancellation.check()
    except MindMapTruncatedResponseError:
        if stage == "merge" and retry_number < 1:
            concise_prompt = (
                f"{prompt}\n\nThe previous merge was truncated. Return a concise, "
                "complete graph; keep descriptions brief and include every required "
                "top-level property, especially related_concepts. Preserve the "
                "document-supported concepts and relationships."
            )
            try:
                _check_prompt_budget(concise_prompt)
            except ValueError:
                raise
            logger.warning(
                "Retrying truncated mind map merge with concise descriptions: "
                "stage=merge retry=1 max_completion_tokens=%d.",
                MAX_MIND_MAP_OUTPUT_TOKENS,
            )
            return _generate_validated(
                concise_prompt,
                partial=partial,
                stage="merge",
                retry_number=1,
                chunk_size=chunk_size,
                progress_callback=progress_callback,
                cancellation=cancellation,
            )
        raise
    try:
        validation_started = time.perf_counter()
        if progress_callback:
            progress_callback("validating")
        payload = _normalize_mind_map(_parse_json_response(response))
        validated = validate_mind_map(payload, **limits)
        logger.info(
            "Mind map validation completed: stage=%s duration_ms=%.1f nodes=%d.",
            stage,
            (time.perf_counter() - validation_started) * 1000,
            1 + sum(1 + len(topic["subtopics"]) for topic in validated["main_topics"])
            + len(validated["related_concepts"]),
        )
        if cancellation is not None:
            cancellation.check()
        return validated
    except AmbiguousRelationshipReferenceError:
        # No model can safely infer which duplicate hierarchy node a link meant.
        logger.info(
            "Mind map validation rejected ambiguous relationships: stage=initial "
            "duration_ms=%.1f.",
            (time.perf_counter() - validation_started) * 1000,
        )
        raise
    except ValueError as first_error:
        logger.info(
            "Mind map validation rejected response: stage=initial "
            "duration_ms=%.1f error_type=%s.",
            (time.perf_counter() - validation_started) * 1000,
            type(first_error).__name__,
        )
        response_digest = hashlib.sha256(response.encode("utf-8")).hexdigest()[:16]
        logger.warning(
            "Mind map response failed validation "
            "(stage=initial, response_chars=%d, response_sha256=%s, shape=%s, "
            "error_type=%s).",
            len(response),
            response_digest,
            _response_shape(response),
            type(first_error).__name__,
        )
        repair_prompt = _make_repair_prompt(
            response,
            first_error,
            partial=partial,
        )
        if cancellation is not None:
            cancellation.check()
        logger.info(
            "Mind map repair required: stage=%s error_type=%s.",
            stage,
            type(first_error).__name__,
        )
        repaired_response = _call_mind_map(
            repair_prompt,
            stage="repair",
            retry_number=retry_number + 1,
            chunk_size=chunk_size,
            cancellation=cancellation,
        )
        if cancellation is not None:
            cancellation.check()
        try:
            validation_started = time.perf_counter()
            payload = _normalize_mind_map(_parse_json_response(repaired_response))
            validated = validate_mind_map(payload, **limits)
            logger.info(
                "Mind map validation completed: stage=repair duration_ms=%.1f.",
                (time.perf_counter() - validation_started) * 1000,
            )
            if cancellation is not None:
                cancellation.check()
            return validated
        except ValueError as second_error:
            logger.info(
                "Mind map validation rejected repaired response: stage=repair "
                "duration_ms=%.1f error_type=%s.",
                (time.perf_counter() - validation_started) * 1000,
                type(second_error).__name__,
            )
            repaired_digest = hashlib.sha256(
                repaired_response.encode("utf-8")
            ).hexdigest()[:16]
            logger.error(
                "Mind map response failed validation "
                "(stage=repair, response_chars=%d, response_sha256=%s, shape=%s, "
                "error_type=%s).",
                len(repaired_response),
                repaired_digest,
                _response_shape(repaired_response),
                type(second_error).__name__,
            )
            raise ValueError(
                "The AI returned a mind map that could not be validated. Please retry."
            ) from second_error


def _generate_partial_maps(
    source: str,
    language: str,
    progress_callback: ProgressCallback | None = None,
    cancellation: MindMapGenerationCancellation | None = None,
) -> list[dict[str, Any]]:
    """Generate independent chunks with bounded concurrency and ordered results."""
    jobs: list[dict[str, Any]] = [
        {"key": (index,), "text": chunk, "size": MIND_MAP_SOURCE_CHUNK_TOKENS, "retry": 0}
        for index, chunk in enumerate(_source_chunks(source, language))
    ]
    maps: dict[tuple[int, ...], dict[str, Any]] = {}
    completed = 0
    limit = _chunk_concurrency()
    rate_limited = threading.Event()
    child_cancellations: set[MindMapGenerationCancellation] = set()
    children_lock = threading.Lock()

    def report_progress(total: int) -> None:
        if progress_callback:
            try:
                progress_callback("generating_branches", completed, total)
            except TypeError:
                # Keep compatibility with callbacks supplied by existing callers.
                progress_callback("generating_branches")

    def run_job(job: dict[str, Any], child: MindMapGenerationCancellation | None) -> dict[str, Any]:
        try:
            prompt = _make_prompt(job["text"], language, partial=True)
            return _generate_validated(
                prompt,
                partial=True,
                stage="chunk",
                retry_number=job["retry"],
                chunk_size=job["size"],
                progress_callback=None,
                cancellation=child or cancellation,
            )
        finally:
            if child is not None:
                # run_job executes on the worker thread that created the child's
                # event loop; finish all request work before disposing its client.
                child.close()
                child.release()

    async def run_wave(wave: list[dict[str, Any]]) -> list[tuple[dict[str, Any], Any, float]]:
        async def execute(job: dict[str, Any]) -> tuple[dict[str, Any], Any, float]:
            if rate_limited.is_set() or (cancellation is not None and cancellation.cancelled):
                raise MindMapGenerationCancelled("Mind map generation stopped.")
            child = cancellation.fork() if cancellation is not None else None
            if child is not None:
                with children_lock:
                    child_cancellations.add(child)
            started = time.perf_counter()
            try:
                result = await asyncio.to_thread(run_job, job, child)
                return job, result, (time.perf_counter() - started) * 1000
            except CloudflareRateLimitError:
                # Stop dispatch and abort sibling in-flight requests immediately.
                rate_limited.set()
                with children_lock:
                    siblings = tuple(child_cancellations)
                for sibling in siblings:
                    if sibling is not child:
                        sibling.cancel()
                return job, CloudflareRateLimitError(
                    "Cloudflare Workers AI is rate limiting Mind Map requests. Please wait before trying again."
                ), (time.perf_counter() - started) * 1000
            except Exception as error:
                with children_lock:
                    siblings = tuple(child_cancellations)
                for sibling in siblings:
                    if sibling is not child:
                        sibling.cancel()
                return job, error, (time.perf_counter() - started) * 1000
            finally:
                if child is not None:
                    with children_lock:
                        child_cancellations.discard(child)

        return list(await asyncio.gather(*(execute(job) for job in wave), return_exceptions=True))

    pending = list(jobs)
    while pending:
        if cancellation is not None:
            cancellation.check()
        if rate_limited.is_set():
            raise CloudflareRateLimitError(
                "Cloudflare Workers AI is rate limiting Mind Map requests. Please wait before trying again."
            )
        total = len(maps) + len(pending)
        report_progress(total)
        wave, pending = pending[:limit], pending[limit:]
        outcomes = asyncio.run(run_wave(wave))
        replacements: list[dict[str, Any]] = []
        retrying_keys: set[tuple[int, ...]] = set()
        first_error: BaseException | None = None
        cancelled_error: BaseException | None = None
        for outcome in outcomes:
            if isinstance(outcome, BaseException):
                if isinstance(outcome, MindMapGenerationCancelled):
                    cancelled_error = cancelled_error or outcome
                else:
                    first_error = first_error or outcome
                continue
            job, result, duration_ms = outcome
            if isinstance(result, MindMapTruncatedResponseError):
                retrying_keys.add(job["key"])
                if job["retry"] >= MAX_MIND_MAP_CHUNK_RETRIES:
                    first_error = first_error or ValueError(
                        "A document section could not fit a complete mind map response after bounded retries. No document sections were omitted."
                    )
                    continue
                actual_tokens = _token_count(job["text"])
                next_size = min(job["size"] // 2, actual_tokens // 2)
                if next_size < 1:
                    first_error = first_error or ValueError(
                        "A truncated document section could not be split safely; no document sections were omitted."
                    )
                    continue
                replacement = _source_chunks(job["text"], language, next_size)
                if len(replacement) < 2:
                    first_error = first_error or ValueError(
                        "A truncated document section could not be split safely; no document sections were omitted."
                    )
                    continue
                replacements.extend(
                    {
                        "key": (*job["key"], child_index),
                        "text": text,
                        "size": next_size,
                        "retry": job["retry"] + 1,
                    }
                    for child_index, text in enumerate(replacement)
                )
                continue
            if isinstance(result, BaseException):
                if isinstance(result, MindMapGenerationCancelled):
                    cancelled_error = cancelled_error or result
                else:
                    first_error = first_error or result
                continue
            maps[job["key"]] = result
            completed += 1
            logger.info(
                "Mind map chunk completed: chunk_index=%s completed_chunks=%d "
                "chunk_count=%d duration_ms=%.1f retry=%d.",
                ".".join(str(part + 1) for part in job["key"]),
                completed,
                len(maps) + len(pending) + sum(1 for item in wave if item["key"] not in maps),
                duration_ms,
                job["retry"],
            )
        first_error = first_error or cancelled_error
        if first_error is not None:
            if cancellation is not None and cancellation.cancelled:
                cancellation.check()
            if rate_limited.is_set():
                raise CloudflareRateLimitError(
                    "Cloudflare Workers AI is rate limiting Mind Map requests. Please wait before trying again."
                ) from first_error
            # Do not silently omit failed sections, even if sibling jobs completed.
            raise RuntimeError(f"Mind map chunk generation failed: {first_error}") from first_error
        for job in wave:
            if job["key"] in maps or job["key"] in retrying_keys:
                continue
            # A missing result indicates a failed/cancelled task; fail closed.
            raise RuntimeError(f"Mind map chunk {job['key']} produced no result.")
        pending.extend(replacements)
        report_progress(len(maps) + len(pending))
        pending.extend(replacements)
    report_progress(len(maps))
    return [maps[key] for key in sorted(maps)]


def _generate_mind_map_impl(
    text: str,
    language: str = "english",
    progress_callback: ProgressCallback | None = None,
    cancellation: MindMapGenerationCancellation | None = None,
) -> dict[str, Any]:
    """Generate a validated mind map using bounded, sequential token batches."""
    generation_started = time.perf_counter()
    if cancellation is not None:
        cancellation.check()
    source = text.strip()
    if not source:
        raise ValueError("The uploaded document has no usable study content.")
    if len(source) > MAX_MIND_MAP_SOURCE_CHARS:
        raise MindMapTooLargeError(
            "This document is too large to map in one request. Split it into smaller files and try again."
        )

    language = language.strip() or "English"
    document_token_count = _token_count(source)
    direct_prompt = _make_prompt(
        source,
        language,
        partial=False,
        document_token_count=document_token_count,
    )
    try:
        _check_prompt_budget(direct_prompt)
    except ValueError:
        pass
    else:
        try:
            if progress_callback:
                progress_callback("generating_branches")
            result = _generate_validated(
                direct_prompt,
                stage="chunk",
                progress_callback=progress_callback,
                cancellation=cancellation,
            )
            logger.info(
                "Mind map generation completed: path=direct duration_ms=%.1f.",
                (time.perf_counter() - generation_started) * 1000,
            )
            return result
        except MindMapTruncatedResponseError:
            logger.warning(
                "Direct mind map response was truncated; switching to sequential source chunks."
            )

    partial_maps = _generate_partial_maps(
        source, language, progress_callback, cancellation
    )

    compacted = False
    while len(partial_maps) > 1:
        if cancellation is not None:
            cancellation.check()
        if progress_callback:
            progress_callback("connecting_concepts")
        batches = _merge_batches(partial_maps, language, partial=True)
        if len(batches) == 1:
            final_prompt = _make_merge_prompt(
                partial_maps,
                language,
                partial=False,
                document_token_count=document_token_count,
            )
            try:
                _check_prompt_budget(final_prompt)
            except ValueError:
                pass
            else:
                result = _generate_validated(
                    final_prompt,
                    stage="merge",
                    progress_callback=progress_callback,
                    cancellation=cancellation,
                )
                logger.info(
                    "Mind map generation completed: path=single_final_merge "
                    "chunk_count=%d duration_ms=%.1f.",
                    len(partial_maps),
                    (time.perf_counter() - generation_started) * 1000,
                )
                return result
        if len(batches) == len(partial_maps) and all(
            len(batch) == 1 for batch in batches
        ):
            final_prompt = _make_merge_prompt(
                partial_maps,
                language,
                partial=False,
                document_token_count=document_token_count,
            )
            if compacted:
                try:
                    _check_prompt_budget(final_prompt)
                except ValueError as error:
                    raise ValueError(
                        "The document produced too many distinct concepts to merge "
                        "within the safe token budget. Please try a smaller document."
                    ) from error
                result = _generate_validated(
                    final_prompt,
                    stage="merge",
                    progress_callback=progress_callback,
                    cancellation=cancellation,
                )
                logger.info(
                    "Mind map generation completed: path=multi_merge "
                    "duration_ms=%.1f.",
                    (time.perf_counter() - generation_started) * 1000,
                )
                return result

            compacted_maps: list[dict[str, Any]] = []
            for batch in batches:
                prompt = _make_merge_prompt(
                    batch, language, partial=True, compact=True
                )
                compacted_maps.append(_generate_validated(
                    prompt, partial=True, stage="merge",
                    progress_callback=progress_callback,
                    cancellation=cancellation,
                ))
            partial_maps = compacted_maps
            compacted = True
            continue

        merged_maps: list[dict[str, Any]] = []
        for batch in batches:
            if len(batch) == 1:
                merged_maps.append(batch[0])
                continue
            prompt = _make_merge_prompt(batch, language, partial=True)
            merged_maps.append(_generate_validated(
                prompt, partial=True, stage="merge",
                progress_callback=progress_callback,
                cancellation=cancellation,
            ))
        partial_maps = merged_maps

    final_prompt = _make_merge_prompt(
        partial_maps,
        language,
        partial=False,
        document_token_count=document_token_count,
    )
    if progress_callback:
        progress_callback("connecting_concepts")
    result = _generate_validated(
        final_prompt,
        stage="merge",
        progress_callback=progress_callback,
        cancellation=cancellation,
    )
    logger.info(
        "Mind map generation completed: path=multi_merge duration_ms=%.1f.",
        (time.perf_counter() - generation_started) * 1000,
    )
    return result


def generate_mind_map(
    text: str,
    language: str = "english",
    progress_callback: ProgressCallback | None = None,
    cancellation: MindMapGenerationCancellation | None = None,
) -> dict[str, Any]:
    """Generate a map and release any per-request async provider resources."""
    try:
        return _generate_mind_map_impl(
            text,
            language,
            progress_callback,
            cancellation,
        )
    finally:
        if cancellation is not None:
            cancellation.close()


def customize_mind_map(
    current_map: Any, instruction: str, source_chunks: list[str], language: str = "english"
) -> dict[str, Any]:
    """Apply a source-grounded instruction to an existing validated map."""
    current = validate_mind_map(_normalize_mind_map(current_map))
    instruction = instruction.strip()
    if not instruction or len(instruction) > 1_000:
        raise ValueError("Please enter an instruction between 1 and 1000 characters.")
    terms = {term.lower() for term in re.findall(r"[\w'-]{3,}", instruction)}
    ranked = sorted(source_chunks, key=lambda chunk: sum(chunk.lower().count(term) for term in terms), reverse=True)
    context = "\n\n".join(ranked[:3])
    while _token_count(context) > 450 and context:
        context = context[: int(len(context) * 0.8)]
    def make_prompt(relevant_source: str) -> str:
        return f"""You are modifying an existing StudyMate source-grounded mind map.
Follow the user's instruction while preserving useful supported content. Use only
the source excerpts and current map; never add unsupported facts. Keep the result
within the schema limits, preserve IDs for retained nodes, and write in {language}.
Return a complete map JSON object, with no explanatory prose.

{_schema_instructions(MAX_MAIN_TOPICS, MAX_SUBTOPICS_PER_TOPIC, MAX_RELATED_CONCEPTS)}

User instruction: {instruction}
Current map: <current_map>{json.dumps(current, ensure_ascii=False, separators=(",", ":"))}</current_map>
Relevant source: <source>{relevant_source}</source>"""
    prompt = make_prompt(context)
    while context and _token_count(prompt) > MAX_MIND_MAP_PROMPT_TOKENS:
        context = context[: int(len(context) * 0.75)]
        prompt = make_prompt(context)
    return _generate_validated(prompt, stage="merge")
