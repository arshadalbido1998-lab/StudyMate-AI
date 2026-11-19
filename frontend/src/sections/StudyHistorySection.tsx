import { useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  deleteStudyHistory,
  fetchStudyHistory,
  type StudyHistoryRecord,
  type StudyHistoryType,
} from "../Lib/studyHistory";
import "./StudyHistorySection.css";

import type { StudyChatMessage } from "../api";

type StudyHistorySectionProps = {
  userId: string;
  refreshToken: number;
  onOpenChat?: (messages: StudyChatMessage[], historyId: string) => void;
};

type HistoryFilter = "all" | StudyHistoryType;

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function asText(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "Date unavailable"
    : new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(date);
}

function HistoryDetail({
  item,
  onClose,
  onOpenChat,
}: {
  item: StudyHistoryRecord;
  onClose: () => void;
  onOpenChat?: (messages: StudyChatMessage[], historyId: string) => void;
}) {
  const content = asRecord(item.content) ?? {};

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  return (
    <div
      className="history-detail-overlay"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <article
        className="history-detail"
        role="dialog"
        aria-modal="true"
        aria-labelledby="history-detail-title"
      >
        <header className="history-detail__header">
          <div>
            <span className={`history-type history-type--${item.content_type}`}>
              {item.content_type}
            </span>
            <h3 id="history-detail-title">{item.title}</h3>
            <time dateTime={item.created_at}>{formatDate(item.created_at)}</time>
          </div>
          <button type="button" onClick={onClose} aria-label="Close history item">
            ×
          </button>
        </header>

        <div className="history-detail__body">
          {item.content_type === "summary" && (
            typeof content.summary === "string" && content.summary.trim() ? (
              <>
                {asText(content.sourceFilename) && (
                  <p className="history-detail__source">Source: {asText(content.sourceFilename)}</p>
                )}
                <div className="history-detail__markdown">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {content.summary}
                  </ReactMarkdown>
                </div>
              </>
            ) : (
              <p className="history-detail__empty">Saved summary content is unavailable.</p>
            )
          )}

          {item.content_type === "chat" && (() => {
            const messages = asArray(content.messages)
              .map((message) => asRecord(message))
              .filter((message): message is Record<string, unknown> =>
                Boolean(
                  message &&
                  (message.role === "user" || message.role === "assistant") &&
                  typeof message.content === "string",
                ),
              );
            return messages.length ? (
              <div className="history-detail__messages">
                {messages.map((message, index) => (
                  <div
                    className={`history-message${message.role === "user" ? " history-message--user" : ""}`}
                    key={`${asText(message.createdAt)}-${index}`}
                  >
                    <span>{message.role === "user" ? "You" : "StudyMate AI"}</span>
                    <div className="history-detail__markdown">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {asText(message.content)}
                      </ReactMarkdown>
                    </div>
                    {asText(message.createdAt) && (
                      <time dateTime={asText(message.createdAt)}>
                        {formatDate(asText(message.createdAt))}
                      </time>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <p className="history-detail__empty">No saved messages are available for this conversation.</p>
            );
          })()}

          {item.content_type === "chat" && onOpenChat && (
            <button
              type="button"
              className="history-detail__open-chat"
              onClick={() => {
                const messages = asArray(content.messages)
                  .map((message) => asRecord(message))
                  .filter((message): message is Record<string, unknown> =>
                    Boolean(
                      message &&
                      (message.role === "user" || message.role === "assistant") &&
                      typeof message.content === "string",
                    ),
                  );
                onOpenChat(
                  messages.map((message) => ({
                    role: message.role === "assistant" ? "assistant" : "user",
                    content: asText(message.content),
                    createdAt: asText(message.createdAt) || undefined,
                  })),
                  item.id,
                );
                onClose();
              }}
            >
              Continue in chat
            </button>
          )}

          {item.content_type === "quiz" && (() => {
            const questions = asArray(content.questions)
              .map(asRecord)
              .filter((question): question is Record<string, unknown> =>
                Boolean(question && typeof question.question === "string"),
              );
            const answers = asRecord(content.answers) ?? {};
            const results = asArray(content.results)
              .map(asRecord)
              .filter((result): result is Record<string, unknown> => Boolean(result));
            const score = asRecord(content.score);
            return (
              <div className="history-detail__quiz">
                {score && typeof score.score === "number" && typeof score.total === "number" ? (
                  <p className="history-quiz-score">
                    Score: <strong>{score.score} / {score.total}</strong>
                    {typeof score.percentage === "number" && ` · ${score.percentage}%`}
                  </p>
                ) : (
                  <p className="history-detail__empty">A quiz score was not saved with this item.</p>
                )}
                {questions.length ? questions.map((question, index) => {
                  const questionId = asText(question.id);
                  const options = asArray(question.options)
                    .map(asRecord)
                    .filter((option): option is Record<string, unknown> => Boolean(option));
                  const selectedOption = asText(answers[questionId]);
                  const result = results.find((candidate) => candidate.question_id === questionId);
                  const selectedText = options.find((option) => option.id === selectedOption);
                  const correctText = asText(result?.correct_answer) ||
                    asText(options.find((option) => option.id === result?.correct_option_id)?.text);

                  return (
                    <section className="history-quiz-question" key={questionId || index}>
                      <h4>{index + 1}. {asText(question.question)}</h4>
                      <ul>
                        {options.map((option, optionIndex) => (
                          <li key={asText(option.id) || optionIndex}>
                            {asText(option.text)}
                            {option.id === selectedOption && " — Your answer"}
                            {result && option.id === result.correct_option_id && " — Correct"}
                          </li>
                        ))}
                      </ul>
                      {selectedText && <p>Your answer: {asText(selectedText.text)}</p>}
                      {correctText && <p>Correct answer: {correctText}</p>}
                      {asText(result?.explanation) && <p>{asText(result?.explanation)}</p>}
                    </section>
                  );
                }) : (
                  <p className="history-detail__empty">Saved quiz questions are unavailable.</p>
                )}
              </div>
            );
          })()}
        </div>
      </article>
    </div>
  );
}

const filters: Array<{ value: HistoryFilter; label: string }> = [
  { value: "all", label: "All" },
  { value: "summary", label: "Summaries" },
  { value: "chat", label: "Chats" },
  { value: "quiz", label: "Quizzes" },
];

export default function StudyHistorySection({
  userId,
  refreshToken,
  onOpenChat,
}: StudyHistorySectionProps) {
  const [items, setItems] = useState<StudyHistoryRecord[]>([]);
  const [loadedUserId, setLoadedUserId] = useState<string | null>(null);
  const [filter, setFilter] = useState<HistoryFilter>("all");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [deleteError, setDeleteError] = useState("");
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [selectedItem, setSelectedItem] = useState<StudyHistoryRecord | null>(null);

  useEffect(() => {
    let active = true;
    setItems([]);
    setLoadedUserId(null);
    setSelectedItem(null);
    setError("");
    setDeleteError("");
    setDeletingId(null);
    setLoading(true);

    void fetchStudyHistory(userId)
      .then((records) => {
        if (active) {
          setItems(records);
          setLoadedUserId(userId);
        }
      })
      .catch((fetchError: unknown) => {
        if (active) {
          setLoadedUserId(userId);
          setError(
            fetchError instanceof Error
              ? fetchError.message
              : "Study history could not be loaded.",
          );
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [refreshToken, userId]);

  const visibleItems = useMemo(() => {
    const normalizedSearch = search.trim().toLocaleLowerCase();
    const userItems = loadedUserId === userId ? items : [];
    return userItems.filter((item) =>
      (filter === "all" || item.content_type === filter) &&
      (!normalizedSearch || item.title.toLocaleLowerCase().includes(normalizedSearch)),
    );
  }, [filter, items, loadedUserId, search, userId]);

  const isLoading = loading || loadedUserId !== userId;

  const handleDelete = async (item: StudyHistoryRecord) => {
    if (!window.confirm(`Delete "${item.title}" from your study history?`)) return;
    setDeletingId(item.id);
    setDeleteError("");
    try {
      await deleteStudyHistory(userId, item.id);
      setItems((current) => current.filter((record) => record.id !== item.id));
      setSelectedItem((current) => current?.id === item.id ? null : current);
    } catch (deleteFailure) {
      setDeleteError(
        deleteFailure instanceof Error
          ? deleteFailure.message
          : "This history item could not be deleted. Please try again.",
      );
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <section id="study-history" className="study-history" aria-labelledby="study-history-title">
      <div className="study-history__container">
        <header className="study-history__header">
          <p className="study-history__eyebrow">YOUR LEARNING JOURNEY</p>
          <h2 id="study-history-title">Study history</h2>
          <p>Return to summaries, conversations, and quiz results you have saved.</p>
        </header>

        <div className="study-history__toolbar">
          <div className="study-history__filters" role="group" aria-label="Filter study history">
            {filters.map((option) => (
              <button
                key={option.value}
                type="button"
                className={filter === option.value ? "is-active" : ""}
                aria-pressed={filter === option.value}
                onClick={() => setFilter(option.value)}
              >
                {option.label}
              </button>
            ))}
          </div>
          <label className="study-history__search">
            <span className="sr-only">Search history titles</span>
            <input
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search your history"
            />
          </label>
        </div>

        {error && (
          <p className="study-history__state study-history__state--error" role="alert">
            History could not be loaded: {error}
          </p>
        )}
        {deleteError && (
          <p className="study-history__state study-history__state--error" role="alert">
            {deleteError}
          </p>
        )}
        {isLoading ? (
          <p className="study-history__state" role="status">
            <span className="study-history__spinner" aria-hidden="true" />
            Loading your study history…
          </p>
        ) : error ? null : visibleItems.length === 0 ? (
          <div className="study-history__empty">
            <span aria-hidden="true">✦</span>
            <h3>
              {loadedUserId === userId && items.length
                ? "No matching study materials"
                : "Your history starts here"}
            </h3>
            <p>
              {loadedUserId === userId && items.length
                ? "Try another title or category filter."
                : "Generated summaries, answered study chats, and completed quizzes will appear here."}
            </p>
          </div>
        ) : (
          <div className="study-history__list">
            {visibleItems.map((item) => (
              <article className="study-history__item" key={item.id}>
                <button
                  className="study-history__item-open"
                  type="button"
                  onClick={() => setSelectedItem(item)}
                >
                  <span className={`history-type history-type--${item.content_type}`}>
                    {item.content_type}
                  </span>
                  <strong>{item.title}</strong>
                  <time dateTime={item.created_at}>{formatDate(item.created_at)}</time>
                </button>
                <button
                  className="study-history__delete"
                  type="button"
                  onClick={() => void handleDelete(item)}
                  disabled={deletingId === item.id}
                  aria-label={`Delete ${item.title}`}
                >
                  {deletingId === item.id ? "Deleting…" : "Delete"}
                </button>
              </article>
            ))}
          </div>
        )}
      </div>
      {selectedItem && (
        <HistoryDetail
          item={selectedItem}
          onClose={() => setSelectedItem(null)}
          onOpenChat={onOpenChat}
        />
      )}
    </section>
  );
}
