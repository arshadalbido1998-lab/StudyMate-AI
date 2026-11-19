import logging
import time
from uuid import uuid4
from typing import Literal, Optional

from fastapi import FastAPI, UploadFile, File, HTTPException
from starlette.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

from services.pdf_service import (
    MAX_PDF_SIZE_BYTES,
    MAX_PDF_SIZE_MB,
    OCRDependencyError,
    PDFPageLimitError,
    PDFProcessingError,
    extract_text_from_pdf,
    extract_text_from_txt,
    chunk_text,
    get_context_window,
)
from services.gemini_service import (
    answer_question,
    generate_flashcards,
    generate_quiz,
    generate_study_plan,
    summarize_content,
)
from services.cloudflare_service import CloudflareRateLimitError
from services.mind_map_service import (
    MAX_MIND_MAP_SOURCE_CHARS,
    MindMapTooLargeError,
    generate_mind_map,
    customize_mind_map,
    validate_mind_map,
)
from services.mind_map_cancellation import (
    MindMapGenerationCancellation,
    MindMapGenerationCancelled,
)

app = FastAPI(title="StudyMate AI API", version="1.0.0")
logger = logging.getLogger(__name__)
MAX_UPLOAD_SIZE = 20 * 1024 * 1024

# CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── In-Memory Document Store (per session via document_id) ───────────────────
document_store: dict[str, dict] = {}
quiz_store: dict[str, dict] = {}
mind_map_progress: dict[str, dict] = {}
active_mind_map_generations: dict[str, tuple[MindMapGenerationCancellation, str]] = {}
cancelled_mind_map_generations: dict[str, float] = {}

# ─── Request Models ───────────────────────────────────────────────────────────

class SummarizeRequest(BaseModel):
    document_id: str
    mode: str = "medium"
    language: str = "english"

class MindMapRequest(BaseModel):
    document_id: str = Field(min_length=1)
    language: str = Field(default="english", min_length=1, max_length=50)
    generation_id: Optional[str] = Field(default=None, min_length=1, max_length=64)

class MindMapCustomizeRequest(BaseModel):
    document_id: str = Field(min_length=1)
    instruction: str = Field(min_length=1, max_length=1000)
    current_map: dict
    language: str = Field(default="english", min_length=1, max_length=50)

class QuestionRequest(BaseModel):
    document_id: str
    question: str
    chat_history: Optional[list] = []
    language: str = "english"

class StudyPlanRequest(BaseModel):
    subject: str
    topics: str
    exam_date: str
    hours_per_day: int = 4
    language: str = "english"

class GeneralChatRequest(BaseModel):
    question: str
    chat_history: Optional[list] = []
    language: str = "english"

class GenerateQuizRequest(BaseModel):
    document_id: str = Field(min_length=1)
    question_count: Literal[5, 10, 15]
    difficulty: Literal["easy", "medium", "hard"]
    language: str = Field(default="english", min_length=1, max_length=50)
    previous_quiz_id: Optional[str] = Field(default=None, min_length=1)

class SubmitQuizRequest(BaseModel):
    quiz_id: str = Field(min_length=1)
    answers: dict[str, str]
class FlashcardsRequest(BaseModel):
    document_id: str = Field(min_length=1)
    count: Literal[5, 10, 15] = 10
    language: str = Field(default="english", min_length=1, max_length=50)



class ValidateQuizAnswerRequest(BaseModel):
    quiz_id: str = Field(min_length=1)
    question_id: str = Field(min_length=1)
    selected_option_id: str = Field(min_length=1)

# ─── Routes ───────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"message": "StudyMate AI API is running 🚀"}


@app.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    """Upload a PDF or text file and extract its content."""
    filename = file.filename or ""
    supported_pdf = filename.lower().endswith(".pdf")
    supported_text = filename.lower().endswith((".txt", ".md"))
    if not supported_pdf and not supported_text:
        raise HTTPException(
            status_code=400,
            detail="Only PDF, TXT, and MD files are supported.",
        )

    content = bytearray()
    while chunk := await file.read(1024 * 1024):
        upload_limit = MAX_PDF_SIZE_BYTES if supported_pdf else MAX_UPLOAD_SIZE
        if len(content) + len(chunk) > upload_limit:
            limit_mb = MAX_PDF_SIZE_MB if supported_pdf else 20
            raise HTTPException(
                status_code=413,
                detail=f"Files must be {limit_mb} MB or smaller.",
            )
        content.extend(chunk)
    content_bytes = bytes(content)

    if supported_pdf:
        extraction_started = time.perf_counter()
        try:
            text = extract_text_from_pdf(content_bytes)
        except PDFPageLimitError as error:
            raise HTTPException(status_code=413, detail=str(error)) from error
        except PDFProcessingError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except OCRDependencyError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        finally:
            logger.info(
                "PDF text extraction completed: duration_ms=%.1f file_bytes=%d "
                "extracted_chars=%d.",
                (time.perf_counter() - extraction_started) * 1000,
                len(content_bytes),
                len(text) if "text" in locals() else 0,
            )
    else:
        text = extract_text_from_txt(content_bytes)

    if not text or len(text.strip()) < 50:
        if supported_pdf:
            raise HTTPException(
                status_code=400,
                detail=(
                    "No readable text was found in this PDF, even after OCR. "
                    "Check the scan quality and try again."
                ),
            )
        raise HTTPException(
            status_code=400,
            detail="Could not extract meaningful text from the file. Please try another file.",
        )

    chunking_started = time.perf_counter()
    chunks = chunk_text(text)
    logger.info(
        "Document text chunking completed: duration_ms=%.1f chars=%d chunks=%d.",
        (time.perf_counter() - chunking_started) * 1000,
        len(text),
        len(chunks),
    )
    document_id = str(uuid4())

    document_store[document_id] = {
        "filename": filename,
        "full_text": text,
        "chunks": chunks,
        "word_count": len(text.split()),
        "char_count": len(text),
    }

    return {
        "document_id": document_id,
        "filename": filename,
        "word_count": len(text.split()),
        "char_count": len(text),
        "chunks": len(chunks),
        "preview": text[:500] + "..." if len(text) > 500 else text,
    }


@app.post("/summarize")
async def summarize(req: SummarizeRequest):
    """Summarize the uploaded document."""
    doc = document_store.get(req.document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found. Please upload a file first.")

    context = get_context_window(doc["chunks"])
    summary = summarize_content(context, mode=req.mode, language=req.language)
    return {"summary": summary, "mode": req.mode}


@app.post("/mind-map")
async def create_mind_map(req: MindMapRequest):
    """Generate a validated, document-grounded topic hierarchy."""
    doc = document_store.get(req.document_id)
    if not doc:
        raise HTTPException(
            status_code=404,
            detail="Document not found. Please upload a file first.",
        )

    document_text = doc.get("full_text")
    if not isinstance(document_text, str) or not document_text.strip():
        chunks = doc.get("chunks")
        document_text = "\n\n".join(chunks) if isinstance(chunks, list) else ""
    if not document_text.strip():
        raise HTTPException(
            status_code=400,
            detail="The uploaded document has no usable study content.",
        )
    if len(document_text.strip()) > MAX_MIND_MAP_SOURCE_CHARS:
        raise HTTPException(
            status_code=413,
            detail=(
                "This document is too large to map in one request. "
                "Split it into smaller files and try again."
            ),
        )
    if not req.language.strip():
        raise HTTPException(status_code=422, detail="Language cannot be blank.")

    generation_id = req.generation_id or str(uuid4())
    now = time.monotonic()
    for stale_id, expires_at in list(cancelled_mind_map_generations.items()):
        if expires_at <= now:
            cancelled_mind_map_generations.pop(stale_id, None)
    if generation_id in cancelled_mind_map_generations:
        cancelled_mind_map_generations.pop(generation_id, None)
        raise HTTPException(status_code=409, detail="Mind map generation was stopped.")
    if generation_id in active_mind_map_generations:
        raise HTTPException(status_code=409, detail="This mind map generation is already active.")

    cancellation = MindMapGenerationCancellation()
    progress_started = time.monotonic()
    generation_started = time.perf_counter()
    active_mind_map_generations[generation_id] = (cancellation, req.document_id)
    mind_map_progress[req.document_id] = {
        "stage": "reading_document",
        "started_at": progress_started,
    }

    def update_progress(
        stage: str,
        completed_chunks: int | None = None,
        total_chunks: int | None = None,
    ) -> None:
        state = {"stage": stage, "started_at": progress_started}
        if completed_chunks is not None and total_chunks is not None:
            state.update({
                "completed_chunks": completed_chunks,
                "total_chunks": total_chunks,
            })
        mind_map_progress[req.document_id] = state

    try:
        result = await run_in_threadpool(
            generate_mind_map,
            document_text,
            req.language.strip(),
            update_progress,
            cancellation,
        )
        cancellation.check()
        update_progress("complete")
        return result
    except MindMapGenerationCancelled as error:
        update_progress("cancelled")
        raise HTTPException(status_code=409, detail="Mind map generation was stopped.") from error
    except MindMapTooLargeError as error:
        raise HTTPException(status_code=413, detail=str(error)) from error
    except CloudflareRateLimitError as error:
        logger.warning(
            "Mind map Cloudflare rate limit: retry_after_seconds=%s.",
            error.retry_after if error.retry_after is not None else "unknown",
        )
        raise HTTPException(status_code=429, detail=str(error)) from error
    except ValueError as error:
        logger.warning("Mind map generation returned invalid output: %s", error)
        raise HTTPException(
            status_code=502,
            detail=str(error),
        ) from error
    except RuntimeError as error:
        logger.exception("Mind map generation failed")
        raise HTTPException(status_code=502, detail=str(error)) from error
    finally:
        state = mind_map_progress.get(req.document_id)
        if state and state.get("stage") not in {"complete", "cancelled", "cancelling"}:
            update_progress("failed")
        active_mind_map_generations.pop(generation_id, None)
        logger.info(
            "Mind map endpoint completed: duration_ms=%.1f outcome=%s.",
            (time.perf_counter() - generation_started) * 1000,
            mind_map_progress[req.document_id]["stage"],
        )


@app.post("/mind-map/cancel/{generation_id}")
async def cancel_mind_map_generation(generation_id: str):
    """Cancel one generation without affecting other document requests."""
    now = time.monotonic()
    for stale_id, expires_at in list(cancelled_mind_map_generations.items()):
        if expires_at <= now:
            cancelled_mind_map_generations.pop(stale_id, None)

    active = active_mind_map_generations.get(generation_id)
    if active is None:
        # The Stop request can arrive just before the generation request registers.
        cancelled_mind_map_generations[generation_id] = now + 120
        return {"cancelled": True, "status": "cancelled_before_start"}

    cancellation, document_id = active
    cancellation.cancel()
    progress = mind_map_progress.get(document_id)
    if progress is not None:
        mind_map_progress[document_id] = {**progress, "stage": "cancelling"}
    return {"cancelled": True, "status": "cancelling"}


@app.get("/mind-map/progress/{document_id}")
async def get_mind_map_progress(document_id: str):
    state = mind_map_progress.get(document_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Mind map generation is not active.")
    return {
        "stage": state["stage"],
        "elapsed_seconds": round(time.monotonic() - state["started_at"], 1),
        "completed_chunks": state.get("completed_chunks"),
        "total_chunks": state.get("total_chunks"),
    }


@app.post("/mind-map/customize")
async def customize_mind_map_route(req: MindMapCustomizeRequest):
    """Customize a map with relevant excerpts from its source document."""
    doc = document_store.get(req.document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Mind map document not found. Upload it again.")
    try:
        current = validate_mind_map(req.current_map)
        chunks = doc.get("chunks") or [doc.get("full_text", "")]
        updated = customize_mind_map(current, req.instruction, chunks, req.language)
        return validate_mind_map(updated)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except CloudflareRateLimitError as error:
        logger.warning(
            "Mind map customization Cloudflare rate limit: retry_after_seconds=%s.",
            error.retry_after if error.retry_after is not None else "unknown",
        )
        raise HTTPException(status_code=429, detail=str(error)) from error
    except RuntimeError as error:
        logger.exception("Mind map customization failed")
        raise HTTPException(status_code=502, detail=str(error)) from error


@app.post("/ask")
async def ask_question(req: QuestionRequest):
    """Answer a question based on the uploaded document."""
    doc = document_store.get(req.document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found. Please upload a file first.")

    context = get_context_window(doc["chunks"])
    answer = answer_question(context, req.question, req.chat_history or [], language=req.language)
    return {"answer": answer, "question": req.question}


@app.post("/generate-quiz")
async def create_quiz(req: GenerateQuizRequest):
    """Generate a quiz and keep its answers private until submission."""
    doc = document_store.get(req.document_id)
    if not doc:
        raise HTTPException(
            status_code=404,
            detail="Document not found. Please upload a file first.",
        )
    if not req.language.strip():
        raise HTTPException(status_code=422, detail="Language cannot be blank.")

    previous_questions: list[str] = []
    if req.previous_quiz_id:
        previous_quiz = quiz_store.get(req.previous_quiz_id)
        if not previous_quiz:
            raise HTTPException(
                status_code=404,
                detail="Previous quiz not found. Generate a quiz before regenerating.",
            )
        if previous_quiz.get("document_id") != req.document_id:
            raise HTTPException(
                status_code=409,
                detail="The previous quiz belongs to a different document.",
            )
        previous_questions = [
            question["question"]
            for question in previous_quiz["questions"]
            if isinstance(question.get("question"), str)
        ]

    context = get_context_window(doc["chunks"])
    if not context:
        raise HTTPException(
            status_code=400,
            detail="The uploaded document has no usable study content.",
        )

    try:
        questions = generate_quiz(
            context,
            question_count=req.question_count,
            difficulty=req.difficulty,
            language=req.language.strip(),
            previous_questions=previous_questions,
        )
    except ValueError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except RuntimeError as error:
        logger.exception("Quiz generation failed")
        raise HTTPException(
            status_code=502,
            detail="Quiz generation is temporarily unavailable. Please try again.",
        ) from error

    quiz_id = str(uuid4())
    quiz_store[quiz_id] = {
        "document_id": req.document_id,
        "questions": questions,
        "validated_answers": {},
    }
    return {
        "quiz_id": quiz_id,
        "questions": [
            {
                "id": f"q{index}",
                "question": question["question"],
                "options": question["options"],
            }
            for index, question in enumerate(questions, start=1)
        ],
    }


@app.post("/validate-quiz-answer")
async def validate_quiz_answer(req: ValidateQuizAnswerRequest):
    """Lock and validate one answer, revealing feedback only after selection."""
    quiz = quiz_store.get(req.quiz_id)
    if not quiz:
        raise HTTPException(
            status_code=404,
            detail="Quiz not found. Generate a new quiz.",
        )

    questions = quiz["questions"]
    try:
        question_index = int(req.question_id.removeprefix("q")) - 1
    except ValueError as error:
        raise HTTPException(status_code=400, detail="Invalid question.") from error
    if (
        req.question_id != f"q{question_index + 1}"
        or question_index < 0
        or question_index >= len(questions)
    ):
        raise HTTPException(status_code=400, detail="Invalid question.")

    question = questions[question_index]
    option_ids = {option["id"] for option in question["options"]}
    if req.selected_option_id not in option_ids:
        raise HTTPException(status_code=400, detail="Invalid answer option.")

    validated_answers = quiz["validated_answers"]
    previous_answer = validated_answers.get(req.question_id)
    if previous_answer is not None and previous_answer != req.selected_option_id:
        raise HTTPException(
            status_code=409,
            detail="This question has already been answered and cannot be changed.",
        )
    validated_answers[req.question_id] = req.selected_option_id

    correct_option_id = question["correct_option_id"]
    correct_option = next(
        option for option in question["options"] if option["id"] == correct_option_id
    )
    return {
        "question_id": req.question_id,
        "selected_option_id": req.selected_option_id,
        "correct_option_id": correct_option_id,
        "correct_answer": correct_option["text"],
        "is_correct": req.selected_option_id == correct_option_id,
        "explanation": question["explanation"],
    }


@app.post("/submit-quiz")
async def submit_quiz(req: SubmitQuizRequest):
    """Score a completed quiz and return the answers and explanations."""
    quiz = quiz_store.get(req.quiz_id)
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found. Generate a new quiz.")

    questions = quiz["questions"]
    expected_ids = {f"q{index}" for index in range(1, len(questions) + 1)}
    supplied_ids = set(req.answers)
    if supplied_ids != expected_ids:
        raise HTTPException(
            status_code=400,
            detail="Submit exactly one answer for every question.",
        )
    for question_id, selected_option_id in quiz["validated_answers"].items():
        if req.answers.get(question_id) != selected_option_id:
            raise HTTPException(
                status_code=400,
                detail="Submitted answers must match the answers already validated.",
            )

    results = []
    score = 0
    for index, question in enumerate(questions, start=1):
        question_id = f"q{index}"
        selected_option_id = req.answers[question_id]
        options = question["options"]
        option_ids = {option["id"] for option in options}
        if selected_option_id not in option_ids:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid answer for question {index}.",
            )

        correct_option_id = question["correct_option_id"]
        is_correct = selected_option_id == correct_option_id
        score += int(is_correct)
        correct_option = next(
            option for option in options if option["id"] == correct_option_id
        )
        results.append(
            {
                "question_id": question_id,
                "selected_option_id": selected_option_id,
                "correct_option_id": correct_option_id,
                "correct_answer": correct_option["text"],
                "is_correct": is_correct,
                "explanation": question["explanation"],
            }
        )

    total = len(questions)
    return {
        "score": score,
        "total": total,
        "percentage": round(score / total * 100, 2),
        "results": results,
    }


@app.post("/flashcards")
async def create_flashcards(req: FlashcardsRequest):
    """Generate flashcards from an uploaded document."""
    doc = document_store.get(req.document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found. Please upload a file first.")

    context = get_context_window(doc["chunks"])
    if not context:
        raise HTTPException(status_code=400, detail="The uploaded document has no usable study content.")

    try:
        flashcards = generate_flashcards(
            context,
            count=req.count,
            language=req.language.strip(),
        )
    except ValueError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except RuntimeError as error:
        logger.exception("Flashcard generation failed")
        raise HTTPException(
            status_code=502,
            detail="Flashcard generation is temporarily unavailable. Please try again.",
        ) from error

    return {"flashcards": flashcards, "count": len(flashcards)}


@app.post("/study-plan")
async def create_study_plan(req: StudyPlanRequest):
    """Generate a personalized study plan."""
    plan = generate_study_plan(
        subject=req.subject,
        topics=req.topics,
        exam_date=req.exam_date,
        hours_per_day=req.hours_per_day,
        language=req.language,
    )
    return {"plan": plan}


@app.post("/general-chat")
async def general_chat(req: GeneralChatRequest):
    """Answer a general question without a document."""
    from services.gemini_service import general_answer
    answer = general_answer(req.question, req.chat_history or [], language=req.language)
    return {"answer": answer, "question": req.question}


@app.delete("/document/{document_id}")
async def delete_document(document_id: str):
    """Remove a document from the store."""
    if document_id in document_store:
        del document_store[document_id]
        for quiz_id in [
            quiz_id
            for quiz_id, quiz in quiz_store.items()
            if quiz["document_id"] == document_id
        ]:
            del quiz_store[quiz_id]
        return {"message": "Document removed successfully."}
    raise HTTPException(status_code=404, detail="Document not found.")


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
