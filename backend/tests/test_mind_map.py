import json
import os
import re
import asyncio
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import ANY, patch

import fitz
import httpx
from fastapi.testclient import TestClient

import main
from services import gemini_service
from services.mind_map_cancellation import (
    MindMapGenerationCancellation,
    MindMapGenerationCancelled,
)
from services.mind_map_service import (
    MAX_MIND_MAP_OUTPUT_TOKENS,
    MAX_MIND_MAP_PROMPT_TOKENS,
    MAX_MIND_MAP_REQUEST_TOKENS,
    MindMapTruncatedResponseError,
    _make_repair_prompt,
    _call_mind_map,
    _generate_partial_maps,
    _generate_validated,
    _make_merge_prompt,
    _make_prompt,
    _normalize_mind_map,
    _parse_json_response,
    _source_chunks,
    _token_count,
    customize_mind_map,
    generate_mind_map,
    mind_map_json_schema,
    validate_mind_map,
)


def make_map() -> dict[str, object]:
    return {
        "central_topic": {
            "id": "central",
            "label": "Photosynthesis",
            "description": "How plants convert light into stored chemical energy.",
        },
        "main_topics": [
            {
                "id": "light-reactions",
                "label": "Light reactions",
                "description": "Light energy drives electron transfer.",
                "subtopics": [
                    {
                        "id": "electron-transport",
                        "label": "Electron transport",
                        "description": "Electrons move through membrane proteins.",
                    }
                ],
            },
            {
                "id": "carbon-fixation",
                "label": "Carbon fixation",
                "description": "Carbon dioxide is incorporated into sugars.",
                "subtopics": [],
            },
        ],
        "related_concepts": [
            {
                "id": "atp-and-nadph",
                "label": "ATP and NADPH",
                "description": "Energy carriers connect the two stages.",
                "related_to": ["light-reactions", "carbon-fixation"],
                "relationship": "Produced in the light reactions and used in carbon fixation.",
            }
        ],
    }


def chat_result(content: str, finish_reason: str = "stop") -> gemini_service.ChatCompletionResult:
    return gemini_service.ChatCompletionResult(content, finish_reason, 100, 50, 150)


def make_text_pdf(page_count: int) -> bytes:
    document = fitz.open()
    for page_number in range(page_count):
        page = document.new_page()
        for row in range(75):
            page.insert_text(
                (40, 40 + row * 9),
                (
                    f"Section {page_number + 1} concept {row + 1}: "
                    "Biology study material explains cell processes and energy."
                ),
                fontsize=7,
            )
    pdf_bytes = document.tobytes()
    document.close()
    return pdf_bytes


class MindMapServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.documents = main.document_store.copy()
        main.document_store.clear()
        self.client = TestClient(main.app)

    def tearDown(self) -> None:
        self.client.close()
        main.document_store.clear()
        main.document_store.update(self.documents)

    def test_full_map_prompt_adapts_branch_targets_to_document_length(self) -> None:
        cases = (
            (1_000, "short", "3 to 4 main branches"),
            (5_000, "medium", "4 to 6 main branches"),
            (15_000, "long", "5 to 7 main branches"),
        )
        for document_tokens, size_label, branch_target in cases:
            with self.subTest(size=size_label):
                prompt = _make_prompt(
                    "Synthetic source material.",
                    "English",
                    partial=False,
                    document_token_count=document_tokens,
                )
                self.assertIn(f"Balanced sizing for this {size_label} document", prompt)
                self.assertIn(branch_target, prompt)
                self.assertIn("Add subtopics when they represent", prompt)
                self.assertIn("15 to 25 total nodes", prompt)
                self.assertIn("concise 2-5 word labels", prompt)
                self.assertIn("Aim for one 6-14 word", prompt)

    @patch("services.mind_map_service.cloudflare_mind_map_completion")
    def test_generates_and_validates_a_structured_map(self, mock_chat) -> None:
        mock_chat.return_value = chat_result(json.dumps(make_map()))

        result = generate_mind_map(
            "Photosynthesis uses light energy. Carbon fixation uses ATP and NADPH.",
            language="English",
        )

        self.assertEqual(result["central_topic"]["label"], "Photosynthesis")
        self.assertEqual(len(result["main_topics"]), 2)
        self.assertEqual(result["related_concepts"][0]["related_to"], [
            "light-reactions",
            "carbon-fixation",
        ])
        self.assertIn("Photosynthesis uses light energy", mock_chat.call_args.args[0])
        self.assertEqual(mock_chat.call_args.kwargs["response_format"]["type"], "json_schema")
        self.assertIn("schema", mock_chat.call_args.kwargs["response_format"]["json_schema"])
        self.assertEqual(mock_chat.call_args.kwargs["max_tokens"], 4_000)

    @patch("services.mind_map_service.cloudflare_mind_map_completion")
    def test_customization_uses_cloudflare_and_existing_validation(self, mock_chat) -> None:
        mock_chat.return_value = chat_result(json.dumps(make_map()))

        result = customize_mind_map(
            make_map(),
            "Clarify how ATP connects the two stages",
            ["ATP and NADPH connect the light reactions with carbon fixation."],
        )

        self.assertEqual(result["central_topic"]["id"], "central")
        self.assertEqual(mock_chat.call_count, 1)
        self.assertIn("Clarify how ATP connects", mock_chat.call_args.args[0])
        self.assertIn("ATP and NADPH connect", mock_chat.call_args.args[0])
        self.assertEqual(mock_chat.call_args.kwargs["response_format"]["type"], "json_schema")
        self.assertIn("concise 2-5 word labels", mock_chat.call_args.args[0])

    @patch("services.mind_map_service.cloudflare_mind_map_completion")
    def test_concise_mocked_output_reduces_tokens_without_losing_concepts_or_links(
        self, mock_chat
    ) -> None:
        verbose_map = make_map()
        verbose_map["central_topic"]["description"] = (
            "Plants capture light energy and convert it into stored chemical energy, "
            "which is then held in glucose molecules for later use by the plant."
        )
        verbose_map["main_topics"][0]["description"] = (
            "The light reactions use light to excite electrons and move them through "
            "membrane proteins, transferring energy between molecules."
        )
        verbose_map["main_topics"][0]["subtopics"][0]["description"] = (
            "Electrons travel through a series of membrane proteins, and this "
            "electron transport helps generate the energy carriers used later."
        )
        verbose_map["main_topics"][1]["description"] = (
            "Carbon fixation incorporates carbon dioxide into organic molecules, "
            "eventually allowing the plant to build sugar from atmospheric carbon."
        )
        verbose_map["related_concepts"][0]["description"] = (
            "ATP and NADPH are energy carriers produced during the light reactions "
            "and then used by carbon fixation to support sugar production."
        )

        concise_map = make_map()
        concise_map["central_topic"]["description"] = (
            "Plants convert light into stored chemical energy."
        )
        concise_map["main_topics"][0]["description"] = (
            "Light excites electrons for energy transfer."
        )
        concise_map["main_topics"][0]["subtopics"][0]["description"] = (
            "Electrons pass through membrane proteins."
        )
        concise_map["main_topics"][1]["description"] = (
            "Carbon dioxide is fixed into sugars."
        )
        concise_map["related_concepts"][0]["description"] = (
            "ATP and NADPH transfer energy between stages."
        )

        source = (
            "Photosynthesis uses light to move electrons; ATP and NADPH from the "
            "light reactions support carbon fixation into sugars."
        )
        verbose_json = json.dumps(verbose_map)
        concise_json = json.dumps(concise_map)
        mock_chat.side_effect = [chat_result(verbose_json), chat_result(concise_json)]

        verbose_result = generate_mind_map(source)
        concise_result = generate_mind_map(source)

        self.assertLess(_token_count(concise_json), _token_count(verbose_json))
        def labels(payload: dict[str, object]) -> list[str]:
            values = [payload["central_topic"]["label"]]
            for topic in payload["main_topics"]:
                values.append(topic["label"])
                values.extend(subtopic["label"] for subtopic in topic["subtopics"])
            values.extend(concept["label"] for concept in payload["related_concepts"])
            return values

        self.assertEqual(labels(concise_result), labels(verbose_result))
        self.assertEqual(
            [topic["id"] for topic in concise_result["main_topics"]],
            [topic["id"] for topic in verbose_result["main_topics"]],
        )
        self.assertEqual(
            [sub["id"] for topic in concise_result["main_topics"] for sub in topic["subtopics"]],
            [sub["id"] for topic in verbose_result["main_topics"] for sub in topic["subtopics"]],
        )
        self.assertEqual(
            concise_result["related_concepts"][0]["related_to"],
            verbose_result["related_concepts"][0]["related_to"],
        )
        self.assertEqual(
            concise_result["related_concepts"][0]["relationship"],
            verbose_result["related_concepts"][0]["relationship"],
        )
        self.assertEqual(mock_chat.call_count, 2)

    @patch("services.mind_map_service.cloudflare_mind_map_completion")
    def test_representative_study_maps_cover_concepts_through_synonyms(self, mock_chat) -> None:
        membrane_source = (
            "Osmosis moves water across a selectively permeable membrane toward "
            "higher solute concentration. Facilitated diffusion uses channels to "
            "move polar solutes down gradients. Active transport uses ATP-driven "
            "pumps to move ions against electrochemical gradients. The lipid bilayer "
            "controls exchange and ion gradients can power secondary transport."
        )
        membrane_map = {
            "central_topic": {
                "id": "central", "label": "Membrane Transport",
                "description": "Membranes regulate cellular exchange.",
            },
            "main_topics": [
                {
                    "id": "passive", "label": "Passive Transport",
                    "description": "Molecules move down concentration gradients without ATP.",
                    "subtopics": [
                        {"id": "osmosis", "label": "Water Balance", "description": "Water crosses toward higher solute concentration."},
                        {"id": "channel-diffusion", "label": "Channel Diffusion", "description": "Channels move polar solutes down their gradient."},
                    ],
                },
                {
                    "id": "active", "label": "Active Transport",
                    "description": "ATP-powered pumps move ions against concentration gradients.",
                    "subtopics": [],
                },
                {
                    "id": "membrane-structure", "label": "Membrane Structure",
                    "description": "Lipid bilayer controls passage of different molecules.",
                    "subtopics": [],
                },
            ],
            "related_concepts": [
                {
                    "id": "ion-gradient", "label": "Ion Gradients",
                    "description": "Charge and concentration differences store potential energy.",
                    "related_to": ["active", "passive"],
                    "relationship": "ATP-powered pumps create gradients for secondary transport.",
                }
            ],
        }
        membrane_concepts = {
            "osmosis": ("osmosis", "water crosses toward higher solute concentration"),
            "facilitated diffusion": ("facilitated diffusion", "channels move polar solutes down their gradient"),
            "active transport": ("active transport", "atp-powered pumps move ions against"),
            "phospholipid bilayer": ("phospholipid bilayer", "lipid bilayer controls passage"),
            "electrochemical gradient": ("electrochemical gradient", "charge and concentration differences"),
        }

        genetics_source = (
            "Gene expression turns DNA information into proteins. During transcription, "
            "RNA polymerase makes messenger RNA from a DNA template. In translation, "
            "ribosomes read mRNA codons while transfer RNA brings amino acids. DNA "
            "replication copies the genome before cell division. Chromatin and "
            "regulatory proteins control which genes are transcribed."
        )
        genetics_map = {
            "central_topic": {
                "id": "central", "label": "Gene Expression",
                "description": "Cells convert genetic information into functional proteins.",
            },
            "main_topics": [
                {
                    "id": "transcription", "label": "RNA Transcription",
                    "description": "RNA polymerase copies DNA into messenger RNA.",
                    "subtopics": [],
                },
                {
                    "id": "translation", "label": "Protein Translation",
                    "description": "Ribosomes decode messenger RNA into an amino-acid chain.",
                    "subtopics": [
                        {"id": "trna", "label": "Transfer RNA", "description": "tRNA matches codons and delivers amino acids."},
                    ],
                },
                {
                    "id": "regulation", "label": "Gene Regulation",
                    "description": "Chromatin state and regulatory proteins control transcription.",
                    "subtopics": [],
                },
            ],
            "related_concepts": [
                {
                    "id": "genome-copy", "label": "Genome Replication",
                    "description": "DNA is copied before cell division.",
                    "related_to": ["transcription", "regulation"],
                    "relationship": "DNA polymerase duplicates the template later used in transcription.",
                }
            ],
        }
        genetics_concepts = {
            "transcription": ("transcription", "rna polymerase copies dna into messenger rna"),
            "translation": ("translation", "ribosomes decode messenger rna"),
            "protein synthesis": ("protein synthesis", "functional proteins", "amino-acid chain"),
            "DNA replication": ("dna replication", "genome replication", "dna is copied before cell division"),
            "gene regulation": ("gene regulation", "regulatory proteins control transcription"),
        }

        mock_chat.side_effect = [
            chat_result(json.dumps(membrane_map)),
            chat_result(json.dumps(genetics_map)),
        ]
        for source, expected_map, concept_groups in (
            (membrane_source, membrane_map, membrane_concepts),
            (genetics_source, genetics_map, genetics_concepts),
        ):
            with self.subTest(document=expected_map["central_topic"]["label"]):
                prompt = _make_prompt(source, "English", partial=False)
                self.assertIn("definitions,", prompt)
                self.assertIn("classifications,", prompt)
                self.assertIn("processes, characteristics", prompt)
                self.assertIn("Preserve source terminology", prompt)
                self.assertIn("a synonym to clarify, not", prompt)
                self.assertIn("not a quota", prompt)

                result = generate_mind_map(source)
                map_text = " ".join(
                    f"{node.get('label', '')} {node.get('description', '')} "
                    f"{node.get('relationship', '')}"
                    for node in [
                        result["central_topic"],
                        *result["main_topics"],
                        *(sub for topic in result["main_topics"] for sub in topic["subtopics"]),
                        *result["related_concepts"],
                    ]
                ).lower()
                missing = [
                    concept for concept, aliases in concept_groups.items()
                    if not any(alias in map_text for alias in aliases)
                ]
                self.assertEqual(missing, [])
                self.assertTrue(result["related_concepts"])
                self.assertGreaterEqual(len(result["related_concepts"][0]["related_to"]), 2)

        self.assertEqual(mock_chat.call_count, 2)

    def test_merge_prompts_carry_concise_output_and_coverage_guidance(self) -> None:
        prompt = _make_merge_prompt([make_map(), make_map()], "English", partial=False)
        self.assertIn("concise 2-5 word labels", prompt)
        self.assertIn("relationship states", prompt)
        self.assertIn("supported link", prompt)
        self.assertIn("Shorten wording before", prompt)
        self.assertIn("Use 4 to 6 main branches", prompt)

    def test_parser_accepts_fenced_json_with_surrounding_text_and_escapes(self) -> None:
        payload = make_map()
        payload["central_topic"]["label"] = 'Photosynthesis "light"\nresponse'
        response = (
            "An example is {}. The requested result:\n```json\n"
            f"{json.dumps(payload)}\n```\nDone."
        )

        parsed = _parse_json_response(response)

        self.assertEqual(parsed, payload)

    def test_parser_rejects_incomplete_json(self) -> None:
        with self.assertRaisesRegex(ValueError, "incomplete or malformed JSON"):
            _parse_json_response('preface {"central_topic": {"label": "cut off"')

    def test_repair_prompt_stays_within_the_token_budget(self) -> None:
        malformed = f'{{"start":"{"x" * 5_000}","end":"keep-me"}}'

        prompt = _make_repair_prompt(
            malformed,
            ValueError("main_topics[0].id is invalid."),
            partial=False,
        )

        self.assertIn('"start"', prompt)
        self.assertIn('"end":"keep-me"', prompt)
        self.assertLessEqual(_token_count(prompt), MAX_MIND_MAP_PROMPT_TOKENS)
        self.assertLessEqual(
            _token_count(prompt) + MAX_MIND_MAP_OUTPUT_TOKENS,
            MAX_MIND_MAP_REQUEST_TOKENS,
        )

    def test_normalizes_recoverable_schema_aliases(self) -> None:
        payload = make_map()
        aliased = {
            "centralTopic": {
                "title": payload["central_topic"]["label"],
                "summary": payload["central_topic"]["description"],
            },
            "topics": [
                {
                    "nodeId": topic["id"],
                    "name": topic["label"],
                    "details": topic["description"],
                    "children": [
                        {
                            "identifier": subtopic["id"],
                            "title": subtopic["label"],
                            "summary": subtopic["description"],
                        }
                        for subtopic in topic["subtopics"]
                    ],
                }
                for topic in payload["main_topics"]
            ],
            "relatedConcepts": [
                {
                    "node_id": concept["id"],
                    "name": concept["label"],
                    "details": concept["description"],
                    "relatedTo": concept["related_to"],
                    "relation": concept["relationship"],
                }
                for concept in payload["related_concepts"]
            ],
        }

        self.assertEqual(
            validate_mind_map(_normalize_mind_map(aliased)),
            validate_mind_map(payload),
        )

    def test_rejects_missing_required_fields(self) -> None:
        payload = make_map()
        del payload["central_topic"]["description"]

        with self.assertRaisesRegex(ValueError, "central_topic.description"):
            validate_mind_map(payload)

    def test_rejects_missing_related_concepts_property(self) -> None:
        payload = make_map()
        del payload["related_concepts"]
        with self.assertRaisesRegex(ValueError, "related_concepts"):
            validate_mind_map(payload)

    def test_duplicate_main_topic_ids_are_normalized_deterministically(self) -> None:
        payload = make_map()
        payload["main_topics"][1]["id"] = payload["main_topics"][0]["id"]
        payload["related_concepts"] = []
        result = validate_mind_map(payload)
        self.assertNotEqual(result["main_topics"][0]["id"], result["main_topics"][1]["id"])
        self.assertEqual(validate_mind_map(payload), result)

    def test_duplicate_subtopic_ids_across_branches_are_normalized(self) -> None:
        payload = make_map()
        payload["main_topics"][1]["subtopics"] = [{
            **payload["main_topics"][0]["subtopics"][0],
        }]
        result = validate_mind_map(payload)
        ids = [topic["subtopics"][0]["id"] for topic in result["main_topics"]]
        self.assertEqual(len(set(ids)), 2)

    def test_duplicate_related_concept_ids_are_normalized_without_changing_links(self) -> None:
        payload = make_map()
        duplicate = {**payload["related_concepts"][0]}
        duplicate["related_to"] = ["light-reactions", "electron-transport"]
        payload["related_concepts"].append(duplicate)
        result = validate_mind_map(payload)
        self.assertNotEqual(
            result["related_concepts"][0]["id"],
            result["related_concepts"][1]["id"],
        )
        self.assertEqual(
            result["related_concepts"][1]["related_to"],
            ["light-reactions", "electron-transport"],
        )

    def test_related_concept_collision_gets_renamed_and_hierarchy_links_stay_correct(self) -> None:
        payload = make_map()
        payload["related_concepts"][0]["id"] = "light-reactions"
        result = validate_mind_map(payload)
        self.assertEqual(result["related_concepts"][0]["related_to"], [
            "light-reactions", "carbon-fixation"
        ])
        self.assertNotEqual(result["related_concepts"][0]["id"], "light-reactions")

    def test_ambiguous_duplicate_hierarchy_reference_is_rejected(self) -> None:
        payload = make_map()
        payload["main_topics"][1]["id"] = "light-reactions"
        with self.assertRaisesRegex(ValueError, "ambiguous node id"):
            validate_mind_map(payload)

    @patch("services.mind_map_service.cloudflare_mind_map_completion")
    def test_duplicate_ids_are_normalized_without_provider_repair(self, mock_chat) -> None:
        payload = make_map()
        payload["main_topics"][1]["id"] = payload["main_topics"][0]["id"]
        payload["related_concepts"] = []
        mock_chat.return_value = chat_result(json.dumps(payload))
        result = generate_mind_map("Short biology notes.")
        self.assertEqual(len({topic["id"] for topic in result["main_topics"]}), 2)
        mock_chat.assert_called_once()

    @patch("services.mind_map_service._generate_validated")
    @patch("services.mind_map_service._generate_partial_maps")
    def test_uses_one_document_merge_when_all_section_maps_fit(
        self, generate_sections, generate_validated
    ) -> None:
        generate_sections.return_value = [make_map(), make_map()]
        generate_validated.return_value = make_map()
        result = generate_mind_map("study material " * 5_000)
        self.assertEqual(result["central_topic"]["id"], "central")
        generate_validated.assert_called_once()
        self.assertEqual(generate_validated.call_args.kwargs["stage"], "merge")

    @patch("services.mind_map_service._generate_validated")
    @patch("services.mind_map_service._generate_partial_maps")
    def test_long_document_final_merge_uses_long_balanced_size_guidance(
        self, generate_sections, generate_validated
    ) -> None:
        generate_sections.return_value = [make_map(), make_map()]
        generate_validated.return_value = make_map()
        source = "photosynthesis chlorophyll stomata " * 12_000

        generate_mind_map(source)

        final_prompt = generate_validated.call_args.args[0]
        self.assertIn("Balanced sizing for this long document", final_prompt)
        self.assertIn("Use 5 to 7 main branches", final_prompt)
        self.assertIn("15 to 25 total nodes", final_prompt)

    @patch("services.mind_map_service._tokenizer")
    def test_source_chunking_drops_empty_and_duplicate_chunks(self, tokenizer) -> None:
        class Encoding:
            def encode(self, _source, disallowed_special=()):
                return [1, 2, 1, 2]

            def decode_single_token_bytes(self, token_id):
                return {1: b"duplicate", 2: b" content"}[token_id]

        tokenizer.return_value = Encoding()
        self.assertEqual(
            _source_chunks("synthetic repeated source", "English", chunk_size=2),
            ["duplicate content"],
        )

    @patch("services.mind_map_service._generate_validated")
    @patch("services.mind_map_service._source_chunks")
    def test_cancel_after_first_chunk_prevents_later_chunk_requests(
        self, source_chunks, generate_validated
    ) -> None:
        source_chunks.return_value = ["first section", "second section", "third section"]
        cancellation = MindMapGenerationCancellation()

        def complete_then_cancel(*_args, **_kwargs):
            cancellation.cancel()
            return make_map()

        generate_validated.side_effect = complete_then_cancel
        with self.assertRaises(MindMapGenerationCancelled):
            _generate_partial_maps("source", "English", cancellation=cancellation)
        generate_validated.assert_called_once()

    @patch("services.mind_map_service._call_mind_map")
    def test_cancelled_invalid_response_does_not_start_a_repair_request(self, call_map) -> None:
        cancellation = MindMapGenerationCancellation()

        def return_invalid_then_cancel(*_args, **_kwargs):
            cancellation.cancel()
            return "not json"

        call_map.side_effect = return_invalid_then_cancel
        with self.assertRaises(MindMapGenerationCancelled):
            _generate_validated(
                _make_prompt("Short notes", "English", partial=False),
                stage="chunk",
                cancellation=cancellation,
            )
        call_map.assert_called_once()

    @patch("services.mind_map_service._call_mind_map")
    def test_cancelled_merge_response_does_not_validate_or_start_more_requests(self, call_map) -> None:
        cancellation = MindMapGenerationCancellation()

        def return_map_then_cancel(*_args, **_kwargs):
            cancellation.cancel()
            return json.dumps(make_map())

        call_map.side_effect = return_map_then_cancel
        with self.assertRaises(MindMapGenerationCancelled):
            _generate_validated(
                _make_prompt("Short notes", "English", partial=False),
                stage="merge",
                cancellation=cancellation,
            )
        call_map.assert_called_once()

    @patch("services.gemini_service.openrouter_api_key", "test-key")
    @patch("services.gemini_service.AsyncOpenAI")
    def test_cancelling_token_aborts_the_active_async_openrouter_request(
        self, async_openrouter
    ) -> None:
        started = threading.Event()
        calls = []

        class AsyncCompletions:
            async def create(self, **_kwargs):
                calls.append("started")
                started.set()
                await asyncio.Event().wait()

        class AsyncClient:
            def __init__(self, **_kwargs):
                self.chat = SimpleNamespace(completions=AsyncCompletions())

            async def close(self):
                return None

        async_openrouter.side_effect = AsyncClient
        cancellation = MindMapGenerationCancellation()
        with ThreadPoolExecutor(max_workers=1) as executor:
            request = executor.submit(
                gemini_service._openrouter_chat_completion,
                "safe test prompt",
                100,
                None,
                "chunk",
                0,
                None,
                cancellation,
            )
            self.assertTrue(started.wait(2))
            cancellation.cancel()
            with self.assertRaises(MindMapGenerationCancelled):
                request.result(timeout=3)
        cancellation.close()
        self.assertEqual(calls, ["started"])

    @patch("services.gemini_service.gemini_api_key", "test-key")
    @patch("services.gemini_service.genai.Client")
    def test_cancelling_token_aborts_the_active_async_gemini_request(
        self, sdk_client_factory
    ) -> None:
        started = threading.Event()
        calls = []

        class AsyncModels:
            async def generate_content(self, **_kwargs):
                calls.append("started")
                started.set()
                await asyncio.Event().wait()

        class AsyncClient:
            def __init__(self):
                self.models = AsyncModels()

            async def aclose(self):
                return None

        class SDKClient:
            def __init__(self, **_kwargs):
                self.aio = SimpleNamespace(models=AsyncModels(), aclose=AsyncClient().aclose)

            def close(self):
                return None

        sdk_client_factory.side_effect = SDKClient
        cancellation = MindMapGenerationCancellation()
        with ThreadPoolExecutor(max_workers=1) as executor:
            request = executor.submit(
                gemini_service._gemini_mind_map_completion,
                "safe test prompt",
                100,
                None,
                "chunk",
                0,
                None,
                cancellation,
            )
            self.assertTrue(started.wait(2))
            cancellation.cancel()
            with self.assertRaises(MindMapGenerationCancelled):
                request.result(timeout=3)
        cancellation.close()
        self.assertEqual(calls, ["started"])

    @patch("services.mind_map_service.cloudflare_mind_map_completion")
    def test_retries_malformed_ai_json_once(self, mock_chat) -> None:
        mock_chat.side_effect = [chat_result("not json"), chat_result(json.dumps(make_map()))]

        source = "Document-grounded source material containing private notes."
        with self.assertLogs("services.mind_map_service", level="WARNING") as logs:
            result = generate_mind_map(source)

        self.assertEqual(result["central_topic"]["label"], "Photosynthesis")
        self.assertEqual(mock_chat.call_count, 2)
        self.assertIn(
            "repair the json mind map",
            mock_chat.call_args.args[0].lower(),
        )
        self.assertIn("Malformed response:\nnot json", mock_chat.call_args.args[0])
        self.assertLessEqual(
            _token_count(mock_chat.call_args.args[0]),
            MAX_MIND_MAP_PROMPT_TOKENS,
        )
        self.assertNotIn(source, "\n".join(logs.output))

    @patch("services.mind_map_service.cloudflare_mind_map_completion")
    def test_invalid_json_without_truncation_is_repaired_not_adaptively_split(self, mock_chat) -> None:
        from services.cloudflare_service import CloudflareCompletionResult

        mock_chat.side_effect = [
            CloudflareCompletionResult("not json", completion_tokens=17),
            CloudflareCompletionResult(json.dumps(make_map()), completion_tokens=80),
        ]

        result = generate_mind_map("Short study material about photosynthesis.")

        self.assertEqual(result["central_topic"]["label"], "Photosynthesis")
        self.assertEqual(
            [call.kwargs["request_stage"] for call in mock_chat.call_args_list],
            ["chunk", "repair"],
        )
        self.assertIsNone(mock_chat.call_args_list[0].kwargs["chunk_size"])

    @patch("services.mind_map_service._chunk_concurrency", return_value=1)
    @patch("services.mind_map_service.cloudflare_mind_map_completion")
    def test_confirmed_token_cap_uses_adaptive_chunk_splitting(self, mock_chat, _limit) -> None:
        from services.cloudflare_service import CloudflareCompletionResult

        calls = []

        def complete(prompt: str, **kwargs: object) -> CloudflareCompletionResult:
            calls.append(kwargs)
            if len(calls) == 1:
                return CloudflareCompletionResult(
                    json.dumps(make_map()),
                    completion_tokens=MAX_MIND_MAP_OUTPUT_TOKENS,
                    truncated=True,
                )
            return CloudflareCompletionResult(json.dumps(make_map()), completion_tokens=100)

        mock_chat.side_effect = complete
        source = "Photosynthesis uses light energy to produce glucose. " * 500

        result = generate_mind_map(source)

        self.assertEqual(result["central_topic"]["label"], "Photosynthesis")
        self.assertGreaterEqual(len(calls), 5)
        self.assertEqual(calls[0]["chunk_size"], 2_200)
        self.assertTrue(any(call.get("chunk_size", 2_200) < 2_200 for call in calls))
        self.assertIn("merge", [call["request_stage"] for call in calls])

    @patch("services.mind_map_service._call_mind_map")
    def test_quota_error_does_not_trigger_repair_or_another_generation(self, call_map) -> None:
        from services.gemini_service import GeminiRateLimitError

        call_map.side_effect = GeminiRateLimitError(
            "Gemini quota is exhausted.", quota_exhausted=True, retry_after=None
        )
        with self.assertRaises(GeminiRateLimitError):
            _generate_validated("safe prompt", stage="chunk")
        call_map.assert_called_once()

    @patch("services.mind_map_service.cloudflare_mind_map_completion")
    def test_large_source_is_token_batched_and_merged_within_budget(self, mock_chat) -> None:
        mock_chat.side_effect = lambda *_args, **_kwargs: chat_result(json.dumps(make_map()))
        source = ("A study section about biology. " * 2_000) + "FINAL_SECTION_MARKER"

        result = generate_mind_map(source)

        self.assertEqual(result["central_topic"]["label"], "Photosynthesis")
        self.assertGreater(mock_chat.call_count, 3)
        prompts = [call.args[0] for call in mock_chat.call_args_list]
        self.assertIn("A study section about biology", prompts[0])
        self.assertTrue(any("FINAL_SECTION_MARKER" in prompt for prompt in prompts))
        for call, prompt in zip(mock_chat.call_args_list, prompts):
            self.assertLessEqual(_token_count(prompt), MAX_MIND_MAP_PROMPT_TOKENS)
            self.assertLessEqual(
                _token_count(prompt) + call.kwargs["max_tokens"],
                MAX_MIND_MAP_REQUEST_TOKENS,
            )
            self.assertEqual(call.kwargs["max_tokens"], MAX_MIND_MAP_OUTPUT_TOKENS)

    @patch("services.mind_map_service.cloudflare_mind_map_completion")
    def test_small_source_uses_one_bounded_request(self, mock_chat) -> None:
        mock_chat.return_value = chat_result(json.dumps(make_map()))

        result = generate_mind_map("Short study material about photosynthesis.")

        self.assertEqual(result["central_topic"]["label"], "Photosynthesis")
        mock_chat.assert_called_once()
        self.assertLessEqual(
            _token_count(mock_chat.call_args.args[0]) + mock_chat.call_args.kwargs["max_tokens"],
            MAX_MIND_MAP_REQUEST_TOKENS,
        )

    @patch("services.mind_map_service.cloudflare_mind_map_completion")
    def test_small_pdf_upload_can_generate_a_mind_map(self, mock_chat) -> None:
        mock_chat.return_value = chat_result(json.dumps(make_map()))
        response = self.client.post(
            "/upload",
            files={
                "file": (
                    "small-study.pdf",
                    make_text_pdf(1),
                    "application/pdf",
                )
            },
        )

        self.assertEqual(response.status_code, 200, response.json())
        generated = self.client.post(
            "/mind-map",
            json={"document_id": response.json()["document_id"]},
        )

        self.assertEqual(generated.status_code, 200, generated.json())
        self.assertEqual(generated.json()["central_topic"]["label"], "Photosynthesis")
        mock_chat.assert_called_once()

    @patch("services.mind_map_service.cloudflare_mind_map_completion")
    def test_large_pdf_is_chunked_and_all_requests_stay_below_budget(
        self, mock_chat
    ) -> None:
        def generate_section_map(prompt: str, **_kwargs: object) -> str:
            if "<source>" in prompt:
                section_numbers = sorted(
                    {
                        int(number)
                        for number in re.findall(r"Section (\d+) concept", prompt)
                    }
                )
                topics = [
                    {
                        "id": f"section-{number}",
                        "label": f"Section {number} concepts",
                        "description": f"Key study concepts from section {number}.",
                        "subtopics": [],
                    }
                    for number in section_numbers[:4]
                ]
            else:
                topic_maps = json.loads(
                    prompt.split("<topic_maps>\n", 1)[1].split("\n</topic_maps>", 1)[0]
                )
                topics_by_label = {
                    topic["label"]: topic
                    for topic_map in topic_maps
                    for topic in topic_map["main_topics"]
                }
                topic_limit = 4 if "Use 1 to 4 main topics" in prompt else 8
                topics = [
                    {**topic, "id": f"section-topic-{index}"}
                    for index, topic in enumerate(
                        list(topics_by_label.values())[:topic_limit],
                        start=1,
                    )
                ]
            return chat_result(json.dumps(
                {
                    "central_topic": {
                        "id": "central",
                        "label": "Biology study material",
                        "description": "Key ideas across the study sections.",
                    },
                    "main_topics": topics,
                    "related_concepts": [],
                }
            ))

        mock_chat.side_effect = generate_section_map
        response = self.client.post(
            "/upload",
            files={
                "file": (
                    "large-study.pdf",
                    make_text_pdf(4),
                    "application/pdf",
                )
            },
        )

        self.assertEqual(response.status_code, 200, response.json())
        generated = self.client.post(
            "/mind-map",
            json={"document_id": response.json()["document_id"]},
        )

        self.assertEqual(generated.status_code, 200, generated.json())
        self.assertGreater(mock_chat.call_count, 3)
        prompts = [call.args[0] for call in mock_chat.call_args_list]
        self.assertTrue(any("Section 1 concept" in prompt for prompt in prompts))
        self.assertTrue(any("Section 4 concept" in prompt for prompt in prompts))
        final_topic_labels = {
            topic["label"] for topic in generated.json()["main_topics"]
        }
        self.assertIn("Section 1 concepts", final_topic_labels)
        self.assertIn("Section 4 concepts", final_topic_labels)
        for call, prompt in zip(mock_chat.call_args_list, prompts):
            self.assertLessEqual(_token_count(prompt), MAX_MIND_MAP_PROMPT_TOKENS)
            self.assertLessEqual(
                _token_count(prompt) + call.kwargs["max_tokens"],
                MAX_MIND_MAP_REQUEST_TOKENS,
            )

    def test_strict_schema_matches_required_frontend_structure(self) -> None:
        schema = mind_map_json_schema()
        def assert_strict_objects(node: dict[str, object]) -> None:
            allowed = {"type", "properties", "required", "additionalProperties", "items", "enum"}
            self.assertLessEqual(set(node), allowed)
            if node.get("type") == "object":
                properties = node["properties"]
                self.assertFalse(node["additionalProperties"])
                self.assertEqual(set(properties), set(node["required"]))
                for child in properties.values():
                    assert_strict_objects(child)
            elif node.get("type") == "array":
                assert_strict_objects(node["items"])

        assert_strict_objects(schema)
        central = schema["properties"]["central_topic"]
        self.assertEqual(central["properties"]["id"]["enum"], ["central"])
        topic = schema["properties"]["main_topics"]["items"]
        related = schema["properties"]["related_concepts"]["items"]
        self.assertTrue({"related_to", "relationship"}.issubset(related["required"]))

    @patch("services.mind_map_service.cloudflare_mind_map_completion")
    def test_does_not_retry_with_unconstrained_json_after_schema_rejection(self, mock_chat) -> None:
        from services.gemini_service import GeminiStructuredOutputUnsupportedError

        mock_chat.side_effect = GeminiStructuredOutputUnsupportedError("rejected")
        prompt = _make_prompt("Short biology notes.", "English", partial=False)
        with self.assertRaisesRegex(GeminiStructuredOutputUnsupportedError, "rejected"):
            _call_mind_map(prompt)
        mock_chat.assert_called_once()

    @patch("services.mind_map_service.cloudflare_mind_map_completion")
    def test_provider_api_error_does_not_silently_fallback(self, mock_chat) -> None:
        mock_chat.side_effect = RuntimeError("provider unavailable")
        with self.assertRaisesRegex(RuntimeError, "provider unavailable"):
            _call_mind_map(_make_prompt("Short biology notes.", "English", partial=False))
        mock_chat.assert_called_once()

    @patch("services.mind_map_service.cloudflare_mind_map_completion")
    def test_truncated_response_is_rejected_and_chunking_reduces_source_size(self, mock_chat) -> None:
        mock_chat.side_effect = [
            chat_result("{", "length"),
            chat_result(json.dumps(make_map())),
            chat_result(json.dumps(make_map())),
        ]
        result = generate_mind_map("Biology process details and key concepts.")
        self.assertEqual(result["central_topic"]["label"], "Photosynthesis")
        self.assertGreaterEqual(mock_chat.call_count, 2)
        self.assertNotEqual(mock_chat.call_args_list[0].kwargs["response_format"]["type"], "json_object")
        self.assertTrue(all(call.kwargs["max_tokens"] == 4_000 for call in mock_chat.call_args_list))

    @patch("services.mind_map_service.cloudflare_mind_map_completion")
    def test_length_finish_reason_is_never_parsed_as_complete_json(self, mock_chat) -> None:
        mock_chat.return_value = chat_result(json.dumps(make_map()), "length")
        with self.assertRaises(MindMapTruncatedResponseError):
            _call_mind_map(_make_prompt("Short biology notes.", "English", partial=False))

    @patch("services.mind_map_service.cloudflare_mind_map_completion")
    def test_final_graph_includes_and_validates_related_concepts(self, mock_chat) -> None:
        mock_chat.return_value = chat_result(json.dumps(make_map()))
        result = generate_mind_map("Short study material about photosynthesis.")
        self.assertEqual(result["central_topic"]["id"], "central")
        self.assertGreaterEqual(len(result["main_topics"]), 1)
        self.assertIsInstance(result["related_concepts"], list)
        self.assertEqual(result["related_concepts"][0]["related_to"], [
            "light-reactions", "carbon-fixation"
        ])

    @patch("services.mind_map_service.cloudflare_mind_map_completion")
    def test_truncated_final_merge_retries_with_full_budget_and_validates_complete_graph(self, mock_chat) -> None:
        mock_chat.side_effect = [
            chat_result('{"central_topic":', "length"),
            chat_result(json.dumps(make_map()), "stop"),
        ]
        result = _generate_validated(
            _make_prompt("Short biology notes.", "English", partial=False),
            stage="merge",
        )
        self.assertEqual(mock_chat.call_count, 2)
        self.assertEqual([call.kwargs["max_tokens"] for call in mock_chat.call_args_list], [4_000, 4_000])
        self.assertEqual(mock_chat.call_args_list[1].kwargs["request_stage"], "merge")
        self.assertIn("related_concepts", mock_chat.call_args_list[1].args[0])
        self.assertEqual(result["central_topic"]["id"], "central")
        self.assertTrue(result["related_concepts"])

    @patch("services.gemini_service.groq_client")
    @patch("services.gemini_service.AI_PROVIDER", "groq")
    def test_missing_related_concepts_from_strict_error_is_classified_as_truncation(self, groq_client) -> None:
        from services.gemini_service import GroqCompletionOutputTruncatedError

        error = Exception("Groq could not validate generated output")
        error.status_code = 400
        error.body = {
            "error": {
                "message": "Output was truncated before related_concepts was generated.",
                "code": "json_validate_failed",
                "failed_generation": '{"central_topic":{"id":"central"},"main_topics":[]',
            }
        }
        groq_client.chat.completions.create.side_effect = error
        with self.assertRaises(GroqCompletionOutputTruncatedError) as raised:
            gemini_service._groq_chat_completion(
                "safe synthetic prompt",
                MAX_MIND_MAP_OUTPUT_TOKENS,
                response_format={"type": "json_schema"},
            )
        self.assertIn("related_concepts", raised.exception.missing_properties)
        self.assertEqual(raised.exception.output_chars, len(error.body["error"]["failed_generation"]))

    @patch("services.mind_map_service._chunk_concurrency", return_value=1)
    @patch("services.mind_map_service._source_chunks")
    @patch("services.mind_map_service._generate_validated")
    def test_adaptive_retry_preserves_successful_chunks_and_splits_only_failed_chunk(
        self, generate, source_chunks, _limit
    ) -> None:
        source_chunks.side_effect = [
            ["already completed section", "section that truncates"],
            ["section that truncates A", "section that truncates B"],
        ]
        def generate_for_section(prompt, **_kwargs):
            if "section that truncates A" in prompt:
                return {"marker": "recovered-a"}
            if "section that truncates B" in prompt:
                return {"marker": "recovered-b"}
            if "section that truncates" in prompt:
                raise MindMapTruncatedResponseError("truncated")
            return {"marker": "preserved"}
        generate.side_effect = generate_for_section
        result = _generate_partial_maps("synthetic full source", "English")
        self.assertEqual([item["marker"] for item in result], ["preserved", "recovered-a", "recovered-b"])
        first_call_text = generate.call_args_list[0].args[0]
        self.assertIn("already completed section", first_call_text)
        self.assertEqual(sum("already completed section" in call.args[0] for call in generate.call_args_list), 1)
        self.assertLess(
            generate.call_args_list[2].kwargs["chunk_size"],
            generate.call_args_list[1].kwargs["chunk_size"],
        )

    @patch("services.mind_map_service._chunk_concurrency", return_value=2)
    @patch("services.mind_map_service._source_chunks", return_value=["first", "second", "third", "fourth"])
    @patch("services.mind_map_service._generate_validated")
    def test_concurrent_chunks_are_bounded_and_return_in_source_order(
        self, generate, _chunks, _limit
    ) -> None:
        lock = threading.Lock()
        active = 0
        peak = 0

        def delayed(prompt, **_kwargs):
            nonlocal active, peak
            marker = next(word for word in ("first", "second", "third", "fourth") if word in prompt)
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep({"first": .04, "second": .01, "third": .03, "fourth": .01}[marker])
            with lock:
                active -= 1
            return {"marker": marker}

        generate.side_effect = delayed
        result = _generate_partial_maps("source", "English")
        self.assertEqual([item["marker"] for item in result], ["first", "second", "third", "fourth"])
        self.assertEqual(peak, 2)

    def test_chunk_concurrency_setting_defaults_and_clamps_to_safe_range(self) -> None:
        from services.mind_map_service import _chunk_concurrency
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("STUDYMATE_MIND_MAP_CONCURRENCY", None)
            self.assertEqual(_chunk_concurrency(), 2)
        with patch.dict(os.environ, {"STUDYMATE_MIND_MAP_CONCURRENCY": "99"}):
            self.assertEqual(_chunk_concurrency(), 3)
        with patch.dict(os.environ, {"STUDYMATE_MIND_MAP_CONCURRENCY": "0"}):
            self.assertEqual(_chunk_concurrency(), 1)

    @patch("services.mind_map_service._source_chunks", return_value=["first", "bad", "third"])
    @patch("services.mind_map_service._generate_validated")
    def test_failed_chunk_fails_generation_instead_of_disappearing(self, generate, _chunks) -> None:
        def result(prompt, **_kwargs):
            if "bad" in prompt:
                raise ValueError("bad source section")
            return {"marker": "ok"}
        generate.side_effect = result
        with self.assertRaisesRegex(RuntimeError, "bad source section"):
            _generate_partial_maps("source", "English")

    @patch("services.mind_map_service._chunk_concurrency", return_value=2)
    @patch("services.mind_map_service._source_chunks", return_value=["one", "two", "three", "four"])
    @patch("services.mind_map_service._generate_validated")
    def test_rate_limit_stops_later_chunk_waves(self, generate, _chunks, _limit) -> None:
        from services.cloudflare_service import CloudflareRateLimitError
        started = []
        lock = threading.Lock()
        def result(prompt, **_kwargs):
            marker = next(word for word in ("one", "two", "three", "four") if word in prompt)
            with lock:
                started.append(marker)
            if marker == "one":
                raise CloudflareRateLimitError("rate limited")
            return {"marker": marker}
        generate.side_effect = result
        with self.assertRaises(CloudflareRateLimitError):
            _generate_partial_maps("source", "English")
        self.assertFalse(set(started).intersection({"three", "four"}))

    @patch("services.mind_map_service._source_chunks", return_value=["one", "two", "three"])
    @patch("services.mind_map_service._generate_validated")
    def test_cancellation_cancels_concurrent_chunk_requests(self, generate, _chunks) -> None:
        cancellation = MindMapGenerationCancellation()
        started = threading.Event()
        def wait_for_cancel(_prompt, cancellation=None, **_kwargs):
            started.set()
            while cancellation is not None and not cancellation.cancelled:
                time.sleep(.005)
            raise MindMapGenerationCancelled("cancelled")
        generate.side_effect = wait_for_cancel
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_generate_partial_maps, "source", "English", None, cancellation)
            self.assertTrue(started.wait(2))
            cancellation.cancel()
            with self.assertRaises(MindMapGenerationCancelled):
                future.result(timeout=3)

    @patch("services.mind_map_service._chunk_concurrency", return_value=2)
    @patch("services.mind_map_service._source_chunks", return_value=["slow", "bad"])
    @patch("services.mind_map_service._generate_validated")
    def test_failed_chunk_cancels_and_awaits_sibling_before_reporting_original_error(
        self, generate, _chunks, _limit
    ) -> None:
        cancellation = MindMapGenerationCancellation()
        slow_started = threading.Event()
        slow_cancelled = threading.Event()

        def fail_one_chunk(prompt, cancellation=None, **_kwargs):
            if "slow" in prompt:
                slow_started.set()
                while cancellation is not None and not cancellation.cancelled:
                    time.sleep(.005)
                slow_cancelled.set()
                cancellation.check()
            self.assertTrue(slow_started.wait(2))
            raise ValueError("original chunk failure")

        generate.side_effect = fail_one_chunk
        with self.assertRaisesRegex(RuntimeError, "original chunk failure"):
            _generate_partial_maps(
                "source", "English", cancellation=cancellation
            )
        self.assertTrue(slow_cancelled.is_set())

    @patch("services.mind_map_service._chunk_concurrency", return_value=2)
    @patch("services.mind_map_service._source_chunks", return_value=["limited", "slow"])
    @patch("services.mind_map_service._generate_validated")
    def test_rate_limit_cancels_and_awaits_sibling_chunk(
        self, generate, _chunks, _limit
    ) -> None:
        from services.cloudflare_service import CloudflareRateLimitError

        cancellation = MindMapGenerationCancellation()
        slow_started = threading.Event()
        slow_cancelled = threading.Event()

        def rate_limit_one_chunk(prompt, cancellation=None, **_kwargs):
            if "slow" in prompt:
                slow_started.set()
                while cancellation is not None and not cancellation.cancelled:
                    time.sleep(.005)
                slow_cancelled.set()
                cancellation.check()
            self.assertTrue(slow_started.wait(2))
            raise CloudflareRateLimitError("rate limited")

        generate.side_effect = rate_limit_one_chunk
        with self.assertRaises(CloudflareRateLimitError):
            _generate_partial_maps(
                "source", "English", cancellation=cancellation
            )
        self.assertTrue(slow_cancelled.is_set())

    @patch("services.mind_map_service._chunk_concurrency", return_value=2)
    @patch("services.mind_map_service._source_chunks", return_value=["one", "two"])
    @patch("services.mind_map_service._generate_validated")
    def test_chunk_progress_reports_completed_and_total(self, generate, _chunks, _limit) -> None:
        generate.side_effect = [{"marker": "one"}, {"marker": "two"}]
        progress = []
        _generate_partial_maps("source", "English", lambda *args: progress.append(args))
        self.assertIn(("generating_branches", 0, 2), progress)
        self.assertIn(("generating_branches", 2, 2), progress)

    @patch("services.mind_map_service._chunk_concurrency", return_value=2)
    @patch("services.mind_map_service._source_chunks", return_value=["one", "two"])
    @patch("services.mind_map_service._generate_validated")
    def test_chunk_client_cleanup_does_not_run_on_the_active_orchestration_loop(
        self, generate, _chunks, _limit
    ) -> None:
        closed = []

        class AsyncClient:
            async def aclose(self):
                closed.append(asyncio.get_running_loop())

        def generate_with_owned_loop(_prompt, cancellation=None, **_kwargs):
            cancellation.async_cloudflare_client = AsyncClient()
            cancellation.run_async(asyncio.sleep(0))
            return {"marker": "complete"}

        generate.side_effect = generate_with_owned_loop
        cancellation = MindMapGenerationCancellation()

        async def invoke_from_active_loop():
            return await asyncio.to_thread(
                _generate_partial_maps, "source", "English", None, cancellation
            )

        result = asyncio.run(invoke_from_active_loop())
        self.assertEqual([item["marker"] for item in result], ["complete", "complete"])
        self.assertEqual(len(closed), 2)

    def test_cleanup_from_another_running_loop_uses_the_client_loop_once(self) -> None:
        closed_on = []

        class AsyncClient:
            async def aclose(self):
                closed_on.append(asyncio.get_running_loop())

        cancellation = MindMapGenerationCancellation()
        cancellation.async_cloudflare_client = AsyncClient()
        cancellation.run_async(asyncio.sleep(0))
        client_loop = cancellation._loop

        async def close_inside_unrelated_loop():
            cancellation.close()
            await asyncio.sleep(0)

        asyncio.run(close_inside_unrelated_loop())

        self.assertEqual(closed_on, [client_loop])
        self.assertIsNone(cancellation.async_cloudflare_client)
        self.assertIsNone(cancellation._loop)
        self.assertTrue(client_loop.is_closed())

    @patch("services.mind_map_service._chunk_concurrency", return_value=1)
    @patch("services.mind_map_service._source_chunks", return_value=["bad"])
    @patch("services.mind_map_service._generate_validated")
    def test_cleanup_failure_is_logged_without_replacing_chunk_error(
        self, generate, _chunks, _limit
    ) -> None:
        class BrokenClient:
            async def aclose(self):
                raise RuntimeError("cleanup failed")

        def fail_after_opening_client(_prompt, cancellation=None, **_kwargs):
            cancellation.async_cloudflare_client = BrokenClient()
            cancellation.run_async(asyncio.sleep(0))
            raise ValueError("original chunk failure")

        generate.side_effect = fail_after_opening_client
        cancellation = MindMapGenerationCancellation()
        with self.assertLogs("services.mind_map_cancellation", level="ERROR") as logs:
            with self.assertRaisesRegex(RuntimeError, "original chunk failure"):
                _generate_partial_maps(
                    "source", "English", cancellation=cancellation
                )
        self.assertTrue(any("async client cleanup failed" in line for line in logs.output))

    @patch("services.mind_map_service._chunk_concurrency", return_value=2)
    @patch("services.mind_map_service._source_chunks", return_value=["first", "second", "third"])
    @patch("services.mind_map_service._generate_validated")
    def test_hierarchical_merge_receives_all_concurrent_maps_in_source_order(
        self, generate, _chunks, _limit
    ) -> None:
        merge_prompts = []
        def make_chunk_or_merge(prompt, *, stage="merge", **_kwargs):
            if stage == "merge":
                merge_prompts.append(prompt)
                return make_map()
            marker = next(word for word in ("first", "second", "third") if word in prompt)
            return {"marker": marker}
        generate.side_effect = make_chunk_or_merge
        result = generate_mind_map("study material " * 4_000)
        self.assertEqual(result["central_topic"]["label"], "Photosynthesis")
        self.assertEqual(len(merge_prompts), 1)
        positions = [merge_prompts[0].index(f'"marker":"{marker}"') for marker in ("first", "second", "third")]
        self.assertEqual(positions, sorted(positions))

    @patch("services.mind_map_service._chunk_concurrency", return_value=2)
    @patch("services.mind_map_service._source_chunks", return_value=["one", "two"])
    @patch("services.mind_map_service._call_mind_map")
    def test_concurrent_chunk_validation_prevents_duplicate_node_ids(
        self, call_map, _chunks, _limit
    ) -> None:
        payload = make_map()
        payload["main_topics"][1]["id"] = payload["main_topics"][0]["id"]
        payload["related_concepts"] = []
        call_map.return_value = json.dumps(payload)
        results = _generate_partial_maps("source", "English")
        self.assertEqual(len(results), 2)
        for mind_map in results:
            ids = ["central"]
            for topic in mind_map["main_topics"]:
                ids.append(topic["id"])
                ids.extend(subtopic["id"] for subtopic in topic["subtopics"])
            self.assertEqual(len(ids), len(set(ids)))

    def test_rejects_related_concepts_with_unknown_targets(self) -> None:
        payload = make_map()
        payload["related_concepts"][0]["related_to"] = [
            "not-a-topic",
            "still-not-a-topic",
        ]

        with self.assertRaisesRegex(ValueError, "unknown node id"):
            validate_mind_map(payload)


class MindMapRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.documents = main.document_store.copy()
        main.document_store.clear()
        self.client = TestClient(main.app)

    def tearDown(self) -> None:
        self.client.close()
        main.document_store.clear()
        main.document_store.update(self.documents)

    @patch("main.generate_mind_map")
    def test_route_uses_the_uploaded_document_text(self, mock_generate) -> None:
        source = (
            "Photosynthesis converts light energy into chemical energy. "
            "Carbon fixation uses ATP and NADPH to produce sugars. "
        ) * 4
        upload = self.client.post(
            "/upload",
            files={"file": ("biology.txt", source.encode(), "text/plain")},
        )
        self.assertEqual(upload.status_code, 200)
        mock_generate.return_value = make_map()

        response = self.client.post(
            "/mind-map",
            json={"document_id": upload.json()["document_id"], "language": "english"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["central_topic"]["label"], "Photosynthesis")
        mock_generate.assert_called_once_with(source.strip(), "english", ANY, ANY)
        progress = self.client.get(f"/mind-map/progress/{upload.json()['document_id']}")
        self.assertEqual(progress.json()["stage"], "complete")

    def test_route_rejects_unknown_documents(self) -> None:
        response = self.client.post("/mind-map", json={"document_id": "missing"})

        self.assertEqual(response.status_code, 404)

    @patch(
        "main.generate_mind_map",
        side_effect=RuntimeError(
            "Cloudflare Workers AI could not generate a mind map response. Please try again later."
        ),
    )
    def test_provider_errors_return_a_retryable_gateway_error(self, _mock_generate) -> None:
        main.document_store["notes-1"] = {"full_text": "Document text " * 8}

        response = self.client.post("/mind-map", json={"document_id": "notes-1"})

        self.assertEqual(response.status_code, 502)
        self.assertIn("Cloudflare Workers AI could not generate", response.json()["detail"])

    @patch("main.generate_mind_map")
    def test_route_rejects_sources_above_the_safety_limit(self, mock_generate) -> None:
        main.document_store["notes-1"] = {
            "full_text": "x" * (main.MAX_MIND_MAP_SOURCE_CHARS + 1)
        }

        response = self.client.post("/mind-map", json={"document_id": "notes-1"})

        self.assertEqual(response.status_code, 413)
        mock_generate.assert_not_called()

    @patch("main.generate_mind_map")
    def test_pre_start_cancellation_prevents_generation_without_poisoning_next_request(
        self, mock_generate
    ) -> None:
        main.document_store["notes-cancel"] = {"full_text": "Study notes " * 20}
        mock_generate.return_value = make_map()
        stopped = self.client.post("/mind-map/cancel/generation-stopped")
        self.assertEqual(stopped.status_code, 200)

        cancelled = self.client.post("/mind-map", json={
            "document_id": "notes-cancel", "generation_id": "generation-stopped"
        })
        self.assertEqual(cancelled.status_code, 409)
        mock_generate.assert_not_called()

        resumed = self.client.post("/mind-map", json={
            "document_id": "notes-cancel", "generation_id": "generation-next"
        })
        self.assertEqual(resumed.status_code, 200, resumed.json())
        mock_generate.assert_called_once()

    def test_active_cancel_endpoint_signals_only_its_generation(self) -> None:
        first = MindMapGenerationCancellation()
        second = MindMapGenerationCancellation()
        main.active_mind_map_generations["cancel-me"] = (first, "doc-a")
        main.active_mind_map_generations["keep-running"] = (second, "doc-b")
        main.mind_map_progress["doc-a"] = {"stage": "generating_branches", "started_at": 0}
        main.mind_map_progress["doc-b"] = {"stage": "generating_branches", "started_at": 0}
        try:
            response = self.client.post("/mind-map/cancel/cancel-me")
            self.assertEqual(response.status_code, 200)
            self.assertTrue(first.cancelled)
            self.assertFalse(second.cancelled)
            self.assertEqual(main.mind_map_progress["doc-a"]["stage"], "cancelling")
        finally:
            main.active_mind_map_generations.pop("cancel-me", None)
            main.active_mind_map_generations.pop("keep-running", None)
            main.mind_map_progress.pop("doc-a", None)
            main.mind_map_progress.pop("doc-b", None)

    @patch("main.generate_mind_map")
    def test_mind_map_rate_limit_is_returned_as_actionable_429(self, generate) -> None:
        from services.cloudflare_service import CloudflareRateLimitError

        main.document_store["notes-rate-limited"] = {"full_text": "Document text " * 8}
        generate.side_effect = CloudflareRateLimitError(
            "Cloudflare Workers AI is rate limiting Mind Map requests.",
            retry_after=None,
        )
        response = self.client.post(
            "/mind-map", json={"document_id": "notes-rate-limited"}
        )
        self.assertEqual(response.status_code, 429)
        self.assertIn("rate limiting", response.json()["detail"])

    @patch("main.customize_mind_map")
    def test_customization_rate_limit_is_returned_as_429(self, customize) -> None:
        from services.cloudflare_service import CloudflareRateLimitError

        main.document_store["notes-rate-limited"] = {"chunks": ["Study notes " * 20]}
        customize.side_effect = CloudflareRateLimitError(
            "Cloudflare Workers AI is rate limiting Mind Map requests.",
            retry_after=20,
        )
        response = self.client.post("/mind-map/customize", json={
            "document_id": "notes-rate-limited",
            "instruction": "Add a brief explanation",
            "current_map": make_map(),
        })
        self.assertEqual(response.status_code, 429)
        self.assertIn("rate limiting", response.json()["detail"])


class ProviderIntegrationTests(unittest.TestCase):
    @patch("services.gemini_service.gemini_api_key", "test-key")
    @patch("services.gemini_service.gemini_client")
    def test_mind_map_completion_uses_gemini_supported_json_schema_config(
        self, gemini_client
    ) -> None:
        schema = mind_map_json_schema()
        gemini_client.models.generate_content.return_value = SimpleNamespace(
            text=json.dumps(make_map()),
            candidates=[SimpleNamespace(finish_reason="STOP")],
            usage_metadata=SimpleNamespace(
                prompt_token_count=21,
                candidates_token_count=34,
                total_token_count=55,
            ),
        )

        result = gemini_service._gemini_mind_map_completion(
            "safe synthetic mind-map prompt",
            max_tokens=MAX_MIND_MAP_OUTPUT_TOKENS,
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "mind_map", "strict": True, "schema": schema},
            },
            request_stage="chunk",
        )

        request = gemini_client.models.generate_content.call_args.kwargs
        self.assertEqual(request["model"], "gemini-3.6-flash")
        self.assertEqual(request["contents"], "safe synthetic mind-map prompt")
        self.assertEqual(request["config"].max_output_tokens, MAX_MIND_MAP_OUTPUT_TOKENS)
        self.assertEqual(request["config"].response_mime_type, "application/json")
        self.assertEqual(
            request["config"].response_json_schema["required"], schema["required"]
        )
        self.assertNotIn("additionalProperties", request["config"].response_json_schema)
        self.assertEqual(
            request["config"].response_json_schema["properties"]["central_topic"]["properties"]["id"]["enum"],
            ["central"],
        )
        self.assertEqual(
            (result.finish_reason, result.prompt_tokens, result.completion_tokens, result.total_tokens),
            ("stop", 21, 34, 55),
        )

    @patch("services.gemini_service.time.sleep")
    @patch("services.gemini_service.gemini_api_key", "test-key")
    @patch("services.gemini_service.gemini_client")
    def test_gemini_transient_429_retries_once_after_provider_delay(
        self, gemini_client, sleep
    ) -> None:
        rate_limit = Exception("Rate limit reached for requests per minute")
        rate_limit.status_code = 429
        rate_limit.message = "Rate limit reached for requests per minute"
        rate_limit.response = SimpleNamespace(headers={"Retry-After": "7"})
        response = SimpleNamespace(
            text=json.dumps(make_map()),
            candidates=[SimpleNamespace(finish_reason="STOP")],
            usage_metadata=SimpleNamespace(),
        )
        gemini_client.models.generate_content.side_effect = [rate_limit, response]

        result = gemini_service._gemini_mind_map_completion(
            "safe synthetic mind-map prompt",
            response_format={"type": "json_schema", "json_schema": {"schema": mind_map_json_schema()}},
        )

        self.assertEqual(result.finish_reason, "stop")
        self.assertEqual(gemini_client.models.generate_content.call_count, 2)
        sleep.assert_called_once_with(7.0)

    @patch("services.gemini_service.time.sleep")
    @patch("services.gemini_service.gemini_api_key", "test-key")
    @patch("services.gemini_service.gemini_client")
    def test_gemini_exhausted_quota_is_not_retried(self, gemini_client, sleep) -> None:
        from services.gemini_service import GeminiRateLimitError

        quota_error = Exception("Quota exceeded: daily limit reached")
        quota_error.status_code = 429
        quota_error.message = "Quota exceeded: daily limit reached"
        gemini_client.models.generate_content.side_effect = quota_error

        with self.assertRaises(GeminiRateLimitError) as raised:
            gemini_service._gemini_mind_map_completion("safe prompt")

        self.assertTrue(raised.exception.quota_exhausted)
        self.assertIn("quota and billing", str(raised.exception))
        gemini_client.models.generate_content.assert_called_once()
        sleep.assert_not_called()

    def test_gemini_retry_info_is_extracted_without_marking_quota_exhausted(self) -> None:
        error = Exception("Resource exhausted")
        error.status_code = 429
        error.message = "Resource exhausted"
        error.details = [{
            "@type": "type.googleapis.com/google.rpc.RetryInfo",
            "retryDelay": "3.25s",
        }, {
            "quotaMetric": "requests_per_minute",
        }]

        exhausted, retry_after = gemini_service._gemini_rate_limit_details(error)

        self.assertFalse(exhausted)
        self.assertEqual(retry_after, 3.25)

    @patch("services.gemini_service.gemini_client")
    @patch("services.gemini_service.groq_client")
    @patch("services.gemini_service.AI_PROVIDER", "groq")
    def test_shared_non_mind_map_chat_path_remains_on_groq(
        self, groq_client, gemini_client
    ) -> None:
        groq_client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Groq response"))]
        )

        result = gemini_service._chat("ordinary StudyMate feature prompt")

        self.assertEqual(result, "Groq response")
        groq_client.chat.completions.create.assert_called_once()
        gemini_client.models.generate_content.assert_not_called()

    @patch("services.gemini_service.groq_client")
    @patch("services.gemini_service.AI_PROVIDER", "groq")
    def test_groq_chat_call_sends_strict_schema_and_captures_usage(self, groq_client) -> None:
        response = SimpleNamespace(
            choices=[SimpleNamespace(
                message=SimpleNamespace(content='{"ok":true}'), finish_reason="stop"
            )],
            usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7, total_tokens=18),
        )
        groq_client.chat.completions.create.return_value = response
        result = gemini_service._groq_chat_completion(
            "prompt", 100, response_format={"type": "json_schema"}
        )
        request = groq_client.chat.completions.create.call_args.kwargs
        self.assertEqual(request["model"], "openai/gpt-oss-120b")
        self.assertEqual(request["response_format"], {"type": "json_schema"})
        self.assertEqual((result.finish_reason, result.prompt_tokens, result.completion_tokens, result.total_tokens), ("stop", 11, 7, 18))

    @patch("services.gemini_service.groq_client")
    @patch("services.gemini_service.AI_PROVIDER", "groq")
    def test_structured_output_json_validation_failure_is_classified_as_truncation(self, groq_client) -> None:
        error = Exception(
            "Error code: 400 - {'error': {'message': 'Failed to validate JSON. "
            "Please adjust your prompt. See failed_generation for more details.', "
            "'type': 'invalid_request_error', 'code': 'json_validate_failed'}}"
        )
        error.status_code = 400
        error.body = {
            "error": {
                "message": "Failed to validate JSON. Please adjust your prompt. "
                "See 'failed_generation' for more details.",
                "type": "invalid_request_error",
                "code": "json_validate_failed",
                "failed_generation": "PRIVATE_DOCUMENT_EXCERPT_MUST_NOT_BE_LOGGED",
            }
        }
        groq_client.chat.completions.create.side_effect = error
        with self.assertRaises(gemini_service.GroqCompletionOutputTruncatedError) as raised:
            gemini_service._groq_chat_completion(
                "prompt", 100, response_format={"type": "json_schema"}
            )
        self.assertEqual(raised.exception.status_code, 400)
        self.assertEqual(raised.exception.api_code, "json_validate_failed")
        self.assertIn("Failed to validate JSON", raised.exception.api_message)
        self.assertNotIn("PRIVATE_DOCUMENT", raised.exception.api_message)
        self.assertGreater(raised.exception.output_chars, 0)
        groq_client.chat.completions.create.assert_called_once()

    @patch("services.mind_map_service.cloudflare_mind_map_completion")
    def test_diagnostics_confirm_cloudflare_handles_mind_map_requests(self, mock_chat) -> None:
        mock_chat.return_value = chat_result(json.dumps(make_map()))
        prompt = _make_prompt("Synthetic notes for a safe diagnostic.", "English", partial=False)
        with self.assertLogs("services.mind_map_service", level="INFO") as captured:
            _call_mind_map(prompt, stage="chunk", chunk_size=1100)
        log_output = "\n".join(captured.output)
        self.assertIn("provider=Cloudflare Workers AI", log_output)
        self.assertIn("@cf/meta/llama-3.3-70b-instruct-fp8-fast", log_output)
        self.assertEqual(mock_chat.call_count, 1)


class CloudflareClientTests(unittest.TestCase):
    @patch("services.cloudflare_service.cloudflare_account_id", "account-test")
    @patch("services.cloudflare_service.cloudflare_api_token", "secret-test-token")
    @patch("services.cloudflare_service.httpx.post")
    def test_sends_cloudflare_model_and_supported_json_schema(self, post) -> None:
        from services.cloudflare_service import cloudflare_mind_map_completion

        post.return_value = httpx.Response(
            200,
            json={"success": True, "result": {"response": json.dumps(make_map())}},
        )
        schema = mind_map_json_schema()
        result = cloudflare_mind_map_completion(
            "safe synthetic prompt",
            max_tokens=MAX_MIND_MAP_OUTPUT_TOKENS,
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "mind_map", "strict": True, "schema": schema},
            },
            request_stage="chunk",
        )

        self.assertEqual(json.loads(result.content), make_map())
        args = post.call_args
        self.assertIn("@cf/meta/llama-3.3-70b-instruct-fp8-fast", args.args[0])
        self.assertEqual(args.kwargs["headers"]["Authorization"], "Bearer secret-test-token")
        self.assertEqual(args.kwargs["json"]["response_format"]["type"], "json_schema")
        self.assertEqual(args.kwargs["json"]["response_format"]["json_schema"], schema)
        self.assertEqual(args.kwargs["json"]["max_tokens"], MAX_MIND_MAP_OUTPUT_TOKENS)
        self.assertEqual(args.kwargs["timeout"], 60.0)
        post.assert_called_once()

    @patch("services.cloudflare_service.cloudflare_account_id", "account-test")
    @patch("services.cloudflare_service.cloudflare_api_token", "secret-test-token")
    @patch("services.cloudflare_service.httpx.post")
    def test_returns_invalid_model_json_for_existing_validation_repair(self, post) -> None:
        from services.cloudflare_service import cloudflare_mind_map_completion

        post.return_value = httpx.Response(
            200, json={"success": True, "result": {"response": '{"central_topic":'}},
        )
        result = cloudflare_mind_map_completion("safe synthetic prompt")
        self.assertEqual(result.content, '{"central_topic":')
        post.assert_called_once()

    @patch("services.cloudflare_service.cloudflare_account_id", "account-test")
    @patch("services.cloudflare_service.cloudflare_api_token", "secret-test-token")
    @patch("services.cloudflare_service.httpx.post")
    def test_usage_at_requested_token_ceiling_confirms_truncation(self, post) -> None:
        from services.cloudflare_service import cloudflare_mind_map_completion

        post.return_value = httpx.Response(
            200,
            json={
                "success": True,
                "result": {
                    "response": json.dumps(make_map()),
                    "usage": {"completion_tokens": MAX_MIND_MAP_OUTPUT_TOKENS},
                },
            },
        )

        result = cloudflare_mind_map_completion(
            "safe synthetic prompt", max_tokens=MAX_MIND_MAP_OUTPUT_TOKENS
        )

        self.assertIsNone(result.finish_reason)
        self.assertEqual(result.completion_tokens, MAX_MIND_MAP_OUTPUT_TOKENS)
        self.assertTrue(result.truncated)

    @patch("services.cloudflare_service.cloudflare_account_id", "account-test")
    @patch("services.cloudflare_service.cloudflare_api_token", "secret-test-token")
    @patch("services.cloudflare_service.httpx.post")
    def test_missing_finish_reason_and_usage_below_cap_are_not_truncated(self, post) -> None:
        from services.cloudflare_service import cloudflare_mind_map_completion

        post.return_value = httpx.Response(
            200,
            json={
                "success": True,
                "result": {
                    "response": json.dumps(make_map()),
                    "usage": {"completion_tokens": 120},
                },
            },
        )

        result = cloudflare_mind_map_completion(
            "safe synthetic prompt", max_tokens=MAX_MIND_MAP_OUTPUT_TOKENS
        )

        self.assertIsNone(result.finish_reason)
        self.assertEqual(result.completion_tokens, 120)
        self.assertFalse(result.truncated)

    @patch("services.cloudflare_service.cloudflare_account_id", "account-test")
    @patch("services.cloudflare_service.cloudflare_api_token", "secret-test-token")
    @patch("services.cloudflare_service.httpx.post")
    def test_explicit_finish_reason_is_exposed(self, post) -> None:
        from services.cloudflare_service import cloudflare_mind_map_completion

        post.return_value = httpx.Response(
            200,
            json={
                "success": True,
                "result": {
                    "response": json.dumps(make_map()),
                    "finish_reason": "length",
                    "usage": {"completion_tokens": 500},
                },
            },
        )
        result = cloudflare_mind_map_completion(
            "safe synthetic prompt", max_tokens=MAX_MIND_MAP_OUTPUT_TOKENS
        )
        self.assertEqual(result.finish_reason, "length")
        self.assertTrue(result.truncated)

    @patch("services.cloudflare_service.cloudflare_account_id", "account-test")
    @patch("services.cloudflare_service.cloudflare_api_token", "secret-test-token")
    @patch("services.cloudflare_service.httpx.post")
    def test_explicit_normal_finish_reason_overrides_token_count_at_cap(self, post) -> None:
        from services.cloudflare_service import cloudflare_mind_map_completion

        post.return_value = httpx.Response(
            200,
            json={
                "success": True,
                "result": {
                    "response": json.dumps(make_map()),
                    "finish_reason": "stop",
                    "usage": {"completion_tokens": MAX_MIND_MAP_OUTPUT_TOKENS},
                },
            },
        )
        result = cloudflare_mind_map_completion(
            "safe synthetic prompt", max_tokens=MAX_MIND_MAP_OUTPUT_TOKENS
        )
        self.assertEqual(result.finish_reason, "stop")
        self.assertFalse(result.truncated)

    @patch("services.cloudflare_service.cloudflare_account_id", "account-test")
    @patch("services.cloudflare_service.cloudflare_api_token", "secret-test-token")
    @patch("services.cloudflare_service.httpx.post")
    def test_http_429_is_not_retried_and_preserves_retry_after(self, post) -> None:
        from services.cloudflare_service import (
            CloudflareRateLimitError,
            cloudflare_mind_map_completion,
        )

        post.return_value = httpx.Response(
            429,
            headers={"Retry-After": "30"},
            json={"success": False, "errors": [{"message": "Rate limited"}]},
        )
        with self.assertRaises(CloudflareRateLimitError) as raised:
            cloudflare_mind_map_completion("safe synthetic prompt")
        self.assertEqual(raised.exception.retry_after, 30)
        post.assert_called_once()

    @patch("services.cloudflare_service.cloudflare_account_id", "account-test")
    @patch("services.cloudflare_service.cloudflare_api_token", "secret-test-token")
    @patch("services.cloudflare_service.httpx.AsyncClient")
    def test_cancellation_aborts_the_active_cloudflare_request(self, async_client_factory) -> None:
        from services.cloudflare_service import cloudflare_mind_map_completion

        started = threading.Event()
        calls = []

        class AsyncClient:
            async def post(self, *_args, **_kwargs):
                calls.append("started")
                started.set()
                await asyncio.Event().wait()

            async def aclose(self):
                return None

        async_client_factory.return_value = AsyncClient()
        cancellation = MindMapGenerationCancellation()
        with ThreadPoolExecutor(max_workers=1) as executor:
            request = executor.submit(
                cloudflare_mind_map_completion,
                "safe synthetic prompt",
                None,
                None,
                "chunk",
                0,
                None,
                cancellation,
            )
            self.assertTrue(started.wait(2))
            cancellation.cancel()
            with self.assertRaises(MindMapGenerationCancelled):
                request.result(timeout=3)
        cancellation.close()
        self.assertEqual(calls, ["started"])


class OpenRouterClientTests(unittest.TestCase):
    @patch("services.gemini_service.openrouter_api_key", "private-test-key")
    @patch("services.gemini_service.openrouter_client")
    def test_sends_openrouter_model_and_normalizes_reply(self, openrouter_client) -> None:
        openrouter_client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(
                message=SimpleNamespace(content='{"ok":true}'), finish_reason="stop"
            )],
            usage=SimpleNamespace(prompt_tokens=9, completion_tokens=4, total_tokens=13),
        )
        with self.assertLogs("services.gemini_service", level="INFO") as captured:
            result = gemini_service._openrouter_chat_completion(
                "safe test prompt",
                max_tokens=100,
                response_format={"type": "json_schema", "json_schema": {"name": "x"}},
                request_stage="chunk",
            )

        request = openrouter_client.chat.completions.create.call_args.kwargs
        self.assertEqual(request["model"], "openrouter/free")
        self.assertEqual(request["max_tokens"], 100)
        self.assertEqual(
            request["extra_body"], {"provider": {"require_parameters": True}}
        )
        self.assertEqual(result.content, '{"ok":true}')
        self.assertEqual(result.total_tokens, 13)
        self.assertNotIn("private-test-key", "\n".join(captured.output))

    @patch("services.gemini_service.OPENROUTER_MODEL", "baidu/ernie-5.5-flash-preview:free")
    @patch("services.gemini_service.openrouter_api_key", "private-test-key")
    @patch("services.gemini_service.openrouter_client")
    def test_sends_configured_openrouter_model(self, openrouter_client) -> None:
        openrouter_client.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(
                message=SimpleNamespace(content='{"ok":true}'), finish_reason="stop"
            )],
            usage=SimpleNamespace(prompt_tokens=9, completion_tokens=4, total_tokens=13),
        )

        gemini_service._openrouter_chat_completion("safe test prompt", max_tokens=100)

        request = openrouter_client.chat.completions.create.call_args.kwargs
        self.assertEqual(request["model"], "baidu/ernie-5.5-flash-preview:free")

    @patch("services.gemini_service.time.sleep")
    @patch("services.gemini_service.groq_client")
    @patch("services.gemini_service.AI_PROVIDER", "groq")
    def test_tpm_limit_is_not_retried_or_exposed(self, groq_client, _sleep) -> None:
        error = Exception(
            "Rate limit reached: limit 8000 tokens per minute, requested 11992"
        )
        error.status_code = 429
        groq_client.chat.completions.create.side_effect = error

        with self.assertRaisesRegex(RuntimeError, "exceeded Groq's token limit") as raised:
            gemini_service._chat("prompt", max_tokens=1_000)

        self.assertNotIn("11992", str(raised.exception))
        groq_client.chat.completions.create.assert_called_once()
        _sleep.assert_not_called()

    @patch("services.gemini_service.time.sleep")
    @patch("services.gemini_service.groq_client")
    @patch("services.gemini_service.AI_PROVIDER", "groq")
    def test_transient_rate_limit_uses_exponential_retry(
        self, groq_client, sleep
    ) -> None:
        error = Exception("Rate limit reached")
        error.status_code = 429
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
        )
        groq_client.chat.completions.create.side_effect = [error, response]

        self.assertEqual(gemini_service._chat("prompt"), "ok")

        self.assertEqual(groq_client.chat.completions.create.call_count, 2)
        sleep.assert_called_once_with(2)

    @patch("services.gemini_service.time.sleep")
    @patch("services.gemini_service.groq_client")
    @patch("services.gemini_service.AI_PROVIDER", "groq")
    def test_retry_after_is_respected_with_bounded_retries(self, groq_client, sleep) -> None:
        error = Exception("Rate limit reached")
        error.status_code = 429
        error.response = SimpleNamespace(headers={"retry-after": "124"})
        groq_client.chat.completions.create.side_effect = [error, error, error]
        with self.assertRaisesRegex(RuntimeError, "temporarily rate-limiting"):
            gemini_service._chat("prompt")
        self.assertEqual(groq_client.chat.completions.create.call_count, 3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [124.0, 124.0])


if __name__ == "__main__":
    unittest.main()

