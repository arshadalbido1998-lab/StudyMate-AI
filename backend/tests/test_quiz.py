import json
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import main
from services.gemini_service import generate_quiz


def make_question(index: int) -> dict[str, object]:
    return {
        "question": f"Question {index}?",
        "options": [
            {"id": "A", "text": f"Correct option {index}"},
            {"id": "B", "text": f"Wrong option {index} B"},
            {"id": "C", "text": f"Wrong option {index} C"},
            {"id": "D", "text": f"Wrong option {index} D"},
        ],
        "correct_option_id": "A",
        "explanation": f"Explanation {index}",
    }


class QuizRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.documents = main.document_store.copy()
        self.quizzes = main.quiz_store.copy()
        main.document_store.clear()
        main.quiz_store.clear()
        main.document_store["notes-1"] = {
            "chunks": ["Study material that contains the topic for this test."]
        }
        self.client = TestClient(main.app)

    def tearDown(self) -> None:
        self.client.close()
        main.document_store.clear()
        main.document_store.update(self.documents)
        main.quiz_store.clear()
        main.quiz_store.update(self.quizzes)

    @patch("main.generate_quiz")
    def test_generated_quiz_hides_answers_until_submission(self, mock_generate) -> None:
        mock_generate.return_value = [make_question(index) for index in range(1, 6)]

        response = self.client.post(
            "/generate-quiz",
            json={
                "document_id": "notes-1",
                "question_count": 5,
                "difficulty": "medium",
                "language": "english",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["questions"]), 5)
        self.assertNotIn("correct_option_id", json.dumps(body))
        self.assertNotIn("correct_answer", body["questions"][0])
        self.assertNotIn("explanation", body["questions"][0])
        self.assertEqual(len(main.quiz_store[body["quiz_id"]]["questions"]), 5)

    @patch("main.generate_quiz")
    def test_regeneration_uses_previous_quiz_from_the_same_document(
        self, mock_generate
    ) -> None:
        mock_generate.side_effect = [
            [make_question(index) for index in range(1, 6)],
            [make_question(index + 5) for index in range(1, 6)],
        ]
        first = self.client.post(
            "/generate-quiz",
            json={
                "document_id": "notes-1",
                "question_count": 5,
                "difficulty": "medium",
            },
        ).json()

        regenerated = self.client.post(
            "/generate-quiz",
            json={
                "document_id": "notes-1",
                "question_count": 5,
                "difficulty": "medium",
                "previous_quiz_id": first["quiz_id"],
            },
        )

        self.assertEqual(regenerated.status_code, 200)
        self.assertNotEqual(regenerated.json()["quiz_id"], first["quiz_id"])
        self.assertEqual(mock_generate.call_count, 2)
        self.assertEqual(
            mock_generate.call_args_list[0].args[0],
            mock_generate.call_args_list[1].args[0],
        )
        self.assertEqual(
            mock_generate.call_args.kwargs["previous_questions"],
            [f"Question {index}?" for index in range(1, 6)],
        )

    @patch("main.generate_quiz")
    def test_regeneration_rejects_previous_quiz_from_another_document(
        self, mock_generate
    ) -> None:
        mock_generate.return_value = [
            make_question(index) for index in range(1, 6)
        ]
        first = self.client.post(
            "/generate-quiz",
            json={
                "document_id": "notes-1",
                "question_count": 5,
                "difficulty": "medium",
            },
        ).json()
        main.document_store["notes-2"] = {"chunks": ["Another document."]}

        response = self.client.post(
            "/generate-quiz",
            json={
                "document_id": "notes-2",
                "question_count": 5,
                "difficulty": "medium",
                "previous_quiz_id": first["quiz_id"],
            },
        )

        self.assertEqual(response.status_code, 409)
        self.assertIn("different document", response.json()["detail"])
        self.assertEqual(mock_generate.call_count, 1)

    @patch("main.generate_quiz")
    def test_submission_returns_score_and_explanations(self, mock_generate) -> None:
        mock_generate.return_value = [make_question(index) for index in range(1, 6)]
        generated = self.client.post(
            "/generate-quiz",
            json={
                "document_id": "notes-1",
                "question_count": 5,
                "difficulty": "easy",
            },
        ).json()

        response = self.client.post(
            "/submit-quiz",
            json={
                "quiz_id": generated["quiz_id"],
                "answers": {f"q{index}": "A" for index in range(1, 6)},
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["score"], 5)
        self.assertEqual(response.json()["percentage"], 100)
        self.assertEqual(
            response.json()["results"][0]["explanation"], "Explanation 1"
        )
        self.assertEqual(
            response.json()["results"][0]["correct_answer"], "Correct option 1"
        )

    @patch("main.generate_quiz")
    def test_answer_validation_returns_correct_feedback_and_locks_selection(
        self, mock_generate
    ) -> None:
        mock_generate.return_value = [make_question(index) for index in range(1, 6)]
        generated = self.client.post(
            "/generate-quiz",
            json={
                "document_id": "notes-1",
                "question_count": 5,
                "difficulty": "easy",
            },
        ).json()

        correct = self.client.post(
            "/validate-quiz-answer",
            json={
                "quiz_id": generated["quiz_id"],
                "question_id": "q1",
                "selected_option_id": "A",
            },
        )
        changed = self.client.post(
            "/validate-quiz-answer",
            json={
                "quiz_id": generated["quiz_id"],
                "question_id": "q1",
                "selected_option_id": "B",
            },
        )
        mismatched_submission = self.client.post(
            "/submit-quiz",
            json={
                "quiz_id": generated["quiz_id"],
                "answers": {
                    "q1": "B",
                    **{f"q{index}": "A" for index in range(2, 6)},
                },
            },
        )
        scored_submission = self.client.post(
            "/submit-quiz",
            json={
                "quiz_id": generated["quiz_id"],
                "answers": {f"q{index}": "A" for index in range(1, 6)},
            },
        )

        self.assertEqual(correct.status_code, 200)
        self.assertTrue(correct.json()["is_correct"])
        self.assertEqual(correct.json()["correct_option_id"], "A")
        self.assertEqual(correct.json()["explanation"], "Explanation 1")
        self.assertEqual(changed.status_code, 409)
        self.assertEqual(mismatched_submission.status_code, 400)
        self.assertEqual(scored_submission.status_code, 200)
        self.assertEqual(scored_submission.json()["score"], 5)
        self.assertEqual(
            scored_submission.json()["results"][0]["explanation"],
            correct.json()["explanation"],
        )

    @patch("main.generate_quiz")
    def test_wrong_answer_feedback_identifies_correct_option(self, mock_generate) -> None:
        mock_generate.return_value = [make_question(index) for index in range(1, 6)]
        generated = self.client.post(
            "/generate-quiz",
            json={
                "document_id": "notes-1",
                "question_count": 5,
                "difficulty": "easy",
            },
        ).json()

        response = self.client.post(
            "/validate-quiz-answer",
            json={
                "quiz_id": generated["quiz_id"],
                "question_id": "q1",
                "selected_option_id": "B",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["is_correct"])
        self.assertEqual(response.json()["selected_option_id"], "B")
        self.assertEqual(response.json()["correct_option_id"], "A")
        self.assertEqual(response.json()["correct_answer"], "Correct option 1")

    def test_missing_document_and_invalid_requests_are_rejected(self) -> None:
        missing_document = self.client.post(
            "/generate-quiz",
            json={
                "document_id": "missing",
                "question_count": 5,
                "difficulty": "easy",
            },
        )
        invalid_count = self.client.post(
            "/generate-quiz",
            json={
                "document_id": "notes-1",
                "question_count": 4,
                "difficulty": "easy",
            },
        )
        missing_quiz = self.client.post(
            "/submit-quiz",
            json={"quiz_id": "missing", "answers": {}},
        )

        self.assertEqual(missing_document.status_code, 404)
        self.assertEqual(invalid_count.status_code, 422)
        self.assertEqual(missing_quiz.status_code, 404)


class QuizGenerationTests(unittest.TestCase):
    @patch("services.gemini_service._chat")
    def test_generated_json_is_validated(self, mock_chat) -> None:
        mock_chat.return_value = json.dumps(
            {"questions": [make_question(index) for index in range(1, 6)]}
        )

        questions = generate_quiz(
            "Document-only study context",
            question_count=5,
            difficulty="hard",
            language="English",
        )

        self.assertEqual(len(questions), 5)
        self.assertEqual(questions[0]["correct_option_id"], "A")
        self.assertIn("Document-only study context", mock_chat.call_args.args[0])
        self.assertIn("hard difficulty", mock_chat.call_args.args[0])

    @patch("services.gemini_service._chat")
    def test_previous_questions_are_included_as_avoidance_context(
        self, mock_chat
    ) -> None:
        mock_chat.return_value = json.dumps(
            {"questions": [make_question(index) for index in range(1, 6)]}
        )

        generate_quiz(
            "Document-only study context",
            question_count=5,
            difficulty="medium",
            previous_questions=["What is retrieval practice?"],
        )

        prompt = mock_chat.call_args.args[0]
        self.assertIn("What is retrieval practice?", prompt)
        self.assertIn("Avoid repeating these questions", prompt)
        self.assertIn("prioritize accuracy over uniqueness", prompt)

    @patch("services.gemini_service._chat", return_value='{"questions": []}')
    def test_invalid_ai_json_raises_friendly_error(self, _mock_chat) -> None:
        with self.assertRaisesRegex(ValueError, "invalid quiz"):
            generate_quiz(
                "Document-only study context",
                question_count=5,
                difficulty="easy",
            )


if __name__ == "__main__":
    unittest.main()
