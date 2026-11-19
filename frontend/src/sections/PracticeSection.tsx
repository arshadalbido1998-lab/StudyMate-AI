import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  generateQuiz,
  submitQuiz,
  type GeneratedQuiz,
  type QuizDifficulty,
  type QuizScore,
  type QuizSubmissionResult,
  validateQuizAnswer,
} from "../api";
import { stages } from "../data/pipeline";

const stage = stages[3];

type PracticeSectionProps = {
  userId: string;
  documentId: string | null;
  documentTitle: string;
  onQuizCompleted: (
    userId: string,
    quiz: GeneratedQuiz,
    answers: Record<string, string>,
    score: QuizScore,
    difficulty: QuizDifficulty,
    documentTitle: string,
  ) => void;
};

export default function PracticeSection({
  userId,
  documentId,
  documentTitle,
  onQuizCompleted,
}: PracticeSectionProps) {
  const [questionCount, setQuestionCount] = useState<5 | 10 | 15>(5);
  const [difficulty, setDifficulty] = useState<QuizDifficulty>("medium");
  const [quiz, setQuiz] = useState<GeneratedQuiz | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [score, setScore] = useState<QuizScore | null>(null);
  const [answerFeedback, setAnswerFeedback] = useState<
    Record<string, QuizSubmissionResult>
  >({});
  const [loading, setLoading] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [error, setError] = useState("");
  const activeRequest = useRef(0);
  const currentDocumentId = useRef(documentId);
  const currentUserId = useRef(userId);
  const quizOwnerId = useRef(userId);
  const currentQuizId = useRef(quiz?.quiz_id);
  const selectedAnswers = useRef<Record<string, string>>({});
  const validatingQuestions = useRef(new Set<string>());
  const completedQuizIds = useRef(new Set<string>());
  const [validatingQuestionIds, setValidatingQuestionIds] = useState<
    Set<string>
  >(new Set());

  currentDocumentId.current = documentId;
  currentUserId.current = userId;
  currentQuizId.current = quiz?.quiz_id;

  useEffect(() => {
    activeRequest.current += 1;
    setQuiz(null);
    setAnswers({});
    setScore(null);
    setAnswerFeedback({});
    selectedAnswers.current = {};
    validatingQuestions.current.clear();
    setValidatingQuestionIds(new Set());
    setLoading(false);
    setRegenerating(false);
    setError("");
    quizOwnerId.current = userId;
  }, [documentId]);

  async function handleGenerateQuiz(
    event?: FormEvent<HTMLFormElement>,
    regenerate = false,
  ) {
    event?.preventDefault();
    if (!documentId) {
      setError(
        regenerate
          ? "This document is no longer available. Please upload it again to regenerate the quiz."
          : "Upload a document before generating a quiz.",
      );
      return;
    }
    if (regenerate && !quiz) {
      setError("Generate a quiz before asking for new questions.");
      return;
    }

    const requestId = ++activeRequest.current;
    const requestUserId = userId;
    setLoading(true);
    setRegenerating(regenerate);
    setError("");
    if (!regenerate) {
      setQuiz(null);
      setAnswers({});
      setScore(null);
      setAnswerFeedback({});
      selectedAnswers.current = {};
      validatingQuestions.current.clear();
      setValidatingQuestionIds(new Set());
    }

    try {
      const generated = await generateQuiz(
        documentId,
        questionCount,
        difficulty,
        regenerate ? quiz?.quiz_id : undefined,
      );
      if (
        activeRequest.current === requestId &&
        currentDocumentId.current === documentId &&
        currentUserId.current === requestUserId
      ) {
        quizOwnerId.current = requestUserId;
        currentQuizId.current = generated.quiz_id;
        setQuiz(generated);
        setAnswers({});
        setScore(null);
        setAnswerFeedback({});
        selectedAnswers.current = {};
        validatingQuestions.current.clear();
        setValidatingQuestionIds(new Set());
      }
    } catch (err) {
      if (
        activeRequest.current === requestId &&
        currentUserId.current === requestUserId
      ) {
        const message =
          err instanceof Error
            ? err.message
            : "Unable to generate your quiz. Please try again.";
        setError(
          regenerate && message.toLowerCase().includes("document not found")
            ? "This document is no longer available. Please upload it again to regenerate the quiz."
            : message,
        );
      }
    } finally {
      if (
        activeRequest.current === requestId &&
        currentUserId.current === requestUserId
      ) {
        setLoading(false);
        setRegenerating(false);
      }
    }
  }

  async function handleSubmitQuiz() {
    if (!quiz || quizOwnerId.current !== currentUserId.current) return;

    const requestId = ++activeRequest.current;
    const ownerId = quizOwnerId.current;
    setLoading(true);
    setRegenerating(false);
    setError("");
    try {
      const result = await submitQuiz(quiz.quiz_id, answers);
      if (
        activeRequest.current === requestId &&
        currentUserId.current === ownerId
      ) {
        setScore(result);
        if (!completedQuizIds.current.has(quiz.quiz_id)) {
          completedQuizIds.current.add(quiz.quiz_id);
          onQuizCompleted(ownerId, quiz, answers, result, difficulty, documentTitle);
        }
      }
    } catch (err) {
      if (
        activeRequest.current === requestId &&
        currentUserId.current === ownerId
      ) {
        setError(
          err instanceof Error
            ? err.message
            : "Unable to submit your quiz. Please try again.",
        );
      }
    } finally {
      if (
        activeRequest.current === requestId &&
        currentUserId.current === ownerId
      ) setLoading(false);
    }
  }

  async function handleSelectAnswer(
    questionId: string,
    optionId: string,
    retry = false,
  ) {
    if (
      !quiz ||
      quizOwnerId.current !== currentUserId.current ||
      loading ||
      score
    ) return;
    if (!retry && selectedAnswers.current[questionId]) return;
    if (answerFeedback[questionId] || validatingQuestions.current.has(questionId)) {
      return;
    }

    if (!retry) {
      selectedAnswers.current = {
        ...selectedAnswers.current,
        [questionId]: optionId,
      };
      setAnswers((current) => ({ ...current, [questionId]: optionId }));
    }

    validatingQuestions.current.add(questionId);
    setValidatingQuestionIds(new Set(validatingQuestions.current));
    setError("");
    const requestQuizId = quiz.quiz_id;
    const requestUserId = quizOwnerId.current;

    try {
      const result = await validateQuizAnswer(
        requestQuizId,
        questionId,
        optionId,
      );
      if (
        currentQuizId.current === requestQuizId &&
        currentUserId.current === requestUserId
      ) {
        setAnswerFeedback((current) => ({
          ...current,
          [questionId]: result,
        }));
      }
    } catch (err) {
      if (
        currentQuizId.current === requestQuizId &&
        currentUserId.current === requestUserId
      ) {
        setError(
          err instanceof Error
            ? err.message
            : "Unable to check that answer. Please try again.",
        );
      }
    } finally {
      validatingQuestions.current.delete(questionId);
      setValidatingQuestionIds(new Set(validatingQuestions.current));
    }
  }

  const answeredCount = Object.keys(answers).length;
  const resultByQuestion = new Map<string, QuizSubmissionResult>(
    Object.entries(answerFeedback),
  );
  score?.results.forEach((result) =>
    resultByQuestion.set(result.question_id, result),
  );

  return (
    <section
      id="practice"
      className="mx-auto w-full max-w-[128rem] px-4 py-10 sm:px-6 md:py-14 lg:px-[4vw]"
      aria-labelledby="quiz-title"
    >
      <div className="rounded-2xl border border-white/10 bg-black/40 p-5 sm:p-7 md:p-9 ">
        <p className="mb-3 text-base uppercase tracking-[0.16em] text-white">
          Stage {stage.index} · {stage.label}
        </p>

        <h2
          id="quiz-title"
          className="mb-3 font-display text-3xl font-semibold text-paper md:text-4xl"
        >
          AI-Generated Quiz
        </h2>

        <p className="mb-7 text-base leading-relaxed text-paper/70">
          {stage.description}
        </p>

        {quiz && (
          <>
            <div className="mb-6 flex flex-wrap items-center justify-between gap-3 border-y border-white/10 py-4">
              <div className="flex items-center gap-2.5">
                <span className="h-2.5 w-2.5 rounded-full bg-black" aria-hidden="true" />
                <p className="text-base font-bold uppercase tracking-[0.12em] text-white">
                  {score
                    ? "Quiz results"
                    : `${quiz.questions.length} questions · ${answeredCount} answered`}
                </p>
              </div>
              <span className="text-base font-semibold capitalize text-paper/70">
                {difficulty} difficulty
              </span>
            </div>
            <div
              className="mb-8 h-2 overflow-hidden rounded-full bg-white/10"
              role="progressbar"
              aria-label="Quiz completion"
              aria-valuemin={0}
              aria-valuemax={quiz.questions.length}
              aria-valuenow={answeredCount}
            >
              <div
                className="h-full rounded-full bg-black transition-[width] duration-300"
                style={{
                  width: `${(answeredCount / quiz.questions.length) * 100}%`,
                }}
              />
            </div>
          </>
        )}

        {!quiz && (
          <form
            onSubmit={handleGenerateQuiz}
            className="space-y-6"
          >
            <div className="grid gap-5 sm:grid-cols-2">
              <div>
                <label
                  htmlFor="quiz-question-count"
                  className="mb-2 block text-base text-paper/80"
                >
                  Number of questions
                </label>
                <select
                  id="quiz-question-count"
                  value={questionCount}
                  onChange={(event) => {
                    const value = Number(event.target.value);
                    if (value === 5 || value === 10 || value === 15) {
                      setQuestionCount(value);
                    }
                  }}
                  disabled={loading}
                  className="w-full rounded-xl border border-white/15 bg-black/40 px-4 py-3 text-base text-paper outline-none transition-colors focus:border-white/60 focus:bg-white/[0.05] disabled:opacity-50"
                >
                  <option value={5} className="bg-black text-white">5 questions</option>
                  <option value={10} className="bg-black text-white">10 questions</option>
                  <option value={15} className="bg-black text-white">15 questions</option>
                </select>
              </div>

              <div>
                <label
                  htmlFor="quiz-difficulty"
                  className="mb-2 block text-base text-paper/80"
                >
                  Difficulty
                </label>
                <select
                  id="quiz-difficulty"
                  value={difficulty}
                  onChange={(event) => {
                    const value = event.target.value;
                    if (
                      value === "easy" ||
                      value === "medium" ||
                      value === "hard"
                    ) {
                      setDifficulty(value);
                    }
                  }}
                  disabled={loading}
                  className="w-full rounded-xl border border-white/15 bg-black/40 px-4 py-3 text-base capitalize text-paper outline-none transition-colors focus:border-white/60 focus:bg-white/[0.05] disabled:opacity-50"
                >
                  <option value="easy" className="bg-black text-white">Easy</option>
                  <option value="medium" className="bg-black text-white">Medium</option>
                  <option value="hard" className="bg-black text-white">Hard</option>
                </select>
              </div>
            </div>

            {!documentId && (
              <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4 text-base leading-relaxed text-paper/70">
                Upload your notes above to create an AI quiz tailored to your document.
              </div>
            )}

            <button
              type="submit"
              disabled={loading || !documentId}
              className="min-h-12 rounded-xl bg-black px-6 py-3 text-base font-semibold text-black transition-opacity hover:opacity-85 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {loading ? "Generating your quiz..." : "Generate Quiz"}
            </button>
          </form>
        )}

        {quiz && (
          <div className="space-y-8">
            {score && (
              <div className="rounded-2xl border border-white/30 bg-black/[0.08] px-6 py-6 text-center">
                <p className="font-display text-2xl font-semibold text-white sm:text-3xl">
                  You scored {score.score} / {score.total}
                </p>
                <p className="mt-2 text-base text-white/70">
                  {score.percentage}% correct
                </p>
              </div>
            )}

            <div className="space-y-8">
              {quiz.questions.map((question, questionIndex) => {
                const result = resultByQuestion.get(question.id);
                return (
                  <div
                    key={question.id}
                    className="border-b border-white/10 pb-8 last:border-0 last:pb-0"
                  >
                    <p className="font-display text-xl font-semibold leading-snug text-white sm:text-2xl">
                      <span className="mr-2 text-white">
                        {questionIndex + 1}.
                      </span>
                      {question.question}
                    </p>
                    <div className="mt-4 space-y-3">
                      {question.options.map((option) => {
                        const isSelected = answers[question.id] === option.id;
                        const isCorrect =
                          result?.correct_option_id === option.id;
                        const isWrongSelection =
                          result !== undefined && isSelected && !isCorrect;
                        const accessibleState = isCorrect
                          ? "Correct answer."
                          : isWrongSelection
                            ? "Your selected answer is incorrect."
                            : "";
                        return (
                          <button
                            key={option.id}
                            type="button"
                            onClick={() =>
                              void handleSelectAnswer(question.id, option.id)
                            }
                            disabled={
                              loading ||
                              score !== null ||
                              answers[question.id] !== undefined
                            }
                            aria-pressed={isSelected}
                            aria-label={`${option.text}${accessibleState ? ` ${accessibleState}` : ""}`}
                            className={[
                              "w-full rounded-xl border px-4 py-3.5 text-left text-base leading-relaxed transition-colors duration-200 sm:text-lg",
                              !result &&
                              (isSelected
                                ? "border-white/50 bg-black/10 text-white"
                                : "border-white/10 hover:border-white/50 hover:bg-black/[0.06]"),
                              result &&
                              isCorrect &&
                              "border-white/60 bg-black/10 text-white",
                              isWrongSelection &&
                              "border-red-400/60 bg-red-400/10 text-white",
                              result &&
                              !isCorrect &&
                              !isWrongSelection &&
                              "border-white/10 text-white/65",
                            ]
                              .filter(Boolean)
                              .join(" ")}
                          >
                            <span className="flex items-center gap-3">
                              <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-white/[0.06] text-base font-bold uppercase text-white/60">
                                {option.id}
                              </span>
                              <span className="min-w-0 flex-1">
                                {option.text}
                              </span>
                              {result && isCorrect && (
                                <span
                                  aria-hidden="true"
                                  className="shrink-0 text-lg font-bold leading-none text-white"
                                >
                                  ✓
                                </span>
                              )}
                              {isWrongSelection && (
                                <span
                                  aria-hidden="true"
                                  className="shrink-0 text-lg font-bold leading-none text-red-400"
                                >
                                  ✕
                                </span>
                              )}
                            </span>
                          </button>
                        );
                      })}
                    </div>
                    {result && (
                      <div
                        role="status"
                        aria-live="polite"
                        className={[
                          "mt-3 rounded-xl px-4 py-3 text-base text-white/90",
                          result.is_correct
                            ? "border border-white/30 bg-black/[0.08]"
                            : "border border-red-400/30 bg-red-400/[0.08]",
                        ].join(" ")}
                      >
                        <p className="font-semibold">
                          {result.is_correct
                            ? "Correct!"
                            : `Not quite. Correct answer: ${result.correct_answer}`}
                        </p>
                        <p className="mt-1 leading-relaxed text-white/65">
                          {result.explanation}
                        </p>
                      </div>
                    )}
                    {answers[question.id] !== undefined && !result && (
                      <div className="mt-3 flex items-center justify-between gap-3 text-base text-white/65">
                        <span role="status" aria-live="polite">
                          {validatingQuestionIds.has(question.id)
                            ? "Checking your answer..."
                            : "Answer selected; feedback is not available yet."}
                        </span>
                        {!validatingQuestionIds.has(question.id) && (
                          <button
                            type="button"
                            onClick={() =>
                              void handleSelectAnswer(
                                question.id,
                                answers[question.id],
                                true,
                              )
                            }
                            className="shrink-0 font-semibold text-white underline underline-offset-2"
                          >
                            Retry check
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            <div className="mt-8 flex flex-col items-center justify-between gap-4 border-t border-white/10 pt-6 sm:flex-row">
              <div className="flex w-full flex-col gap-2 sm:w-auto">
                {!score && (
                  <>
                    <button
                      type="button"
                      onClick={handleSubmitQuiz}
                      disabled={
                        loading ||
                        answeredCount !== quiz.questions.length ||
                        resultByQuestion.size !== quiz.questions.length ||
                        validatingQuestionIds.size > 0
                      }
                      className="min-h-12 rounded-xl bg-black px-6 py-3 text-base font-semibold text-black transition-opacity hover:opacity-85 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {loading && !regenerating
                        ? "Submitting your answers..."
                        : "Submit Quiz"}
                    </button>
                    {resultByQuestion.size !== quiz.questions.length && (
                      <p className="text-sm text-paper/60">
                        Check every answer before submitting.
                      </p>
                    )}
                  </>
                )}
              </div>

              <button
                type="button"
                onClick={() => void handleGenerateQuiz(undefined, true)}
                disabled={loading}
                className="inline-flex min-h-12 w-full items-center justify-center gap-2 rounded-xl border border-white/15 bg-white/[0.04] px-6 py-3 text-base font-semibold text-white transition-colors hover:bg-white/[0.08] hover:border-white/30 disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto"
              >
                <svg
                  aria-hidden="true"
                  viewBox="0 0 24 24"
                  fill="none"
                  className={`h-5 w-5 ${regenerating ? "animate-spin" : ""}`}
                >
                  <path
                    d="M20 7v5h-5M4 17v-5h5"
                    stroke="currentColor"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="1.8"
                  />
                  <path
                    d="M5.6 9a7 7 0 0 1 11.7-2L20 9M4 15l2.7 2a7 7 0 0 0 11.7-2"
                    stroke="currentColor"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="1.8"
                  />
                </svg>
                {regenerating
                  ? "Generating new questions..."
                  : "Regenerate Quiz"}
              </button>
            </div>
          </div>
        )}

        {error && (
          <p
            role="alert"
            className="mt-6 rounded-xl border border-red-400/30 bg-red-400/10 p-4 text-base text-red-200"
          >
            {error}
          </p>
        )}
        {loading && (
          <p role="status" className="mt-6 text-center text-base text-paper/60">
            {regenerating
              ? "StudyMate AI is generating new questions from the same document..."
              : quiz
                ? "StudyMate AI is submitting your answers..."
                : "StudyMate AI is preparing your document-based quiz..."}
          </p>
        )}
      </div>
    </section>
  );
}
