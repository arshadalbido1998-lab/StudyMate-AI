import { useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Link } from "react-router-dom";
import {
  deleteStudyHistory,
  fetchStudyHistory,
  type StudyHistoryRecord,
  type StudyHistoryType,
} from "../Lib/studyHistory";
import type { StudyChatMessage } from "../api";
import "./StudyHistorySidebar.css";

type StudyHistorySidebarProps = {
  isOpen: boolean;
  onClose: () => void;
  userId: string;
  refreshToken: number;
  onNewChat?: () => void;
  onOpenChat?: (messages: StudyChatMessage[], historyId: string) => void;
  onDeleteChat?: (historyId: string) => void;
};

type HistoryFilter = "all" | StudyHistoryType;

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
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
              <p className="history-detail__empty">This summary does not have any content saved.</p>
            )
          )}

          {item.content_type === "chat" && (
            <>
              {asText(content.sourceFilename) && (
                <p className="history-detail__source">Source: {asText(content.sourceFilename)}</p>
              )}
              {asArray(content.messages).length ? (
                <div className="history-detail__chat">
                  {asArray(content.messages).map((messageValue, index) => {
                    const message = asRecord(messageValue) ?? {};
                    const role = asText(message.role);
                    const text = asText(message.content);
                    return (
                      <div
                        key={index}
                        className={`history-detail__chat-turn history-detail__chat-turn--${role || "assistant"}`}
                      >
                        <strong>{role === "user" ? "You" : "StudyMate AI"}</strong>
                        <div className="history-detail__markdown">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {text}
                          </ReactMarkdown>
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="history-detail__empty">This conversation has no saved messages.</p>
              )}
              {onOpenChat && asArray(content.messages).length > 0 && (
                <div className="history-detail__footer">
                  <button
                    type="button"
                    onClick={() => {
                      onOpenChat(
                        asArray(content.messages).map((entry) => {
                          const message = asRecord(entry) ?? {};
                          return {
                            role: asText(message.role) === "user" ? "user" : "assistant",
                            content: asText(message.content),
                            createdAt: asText(message.createdAt) || undefined,
                          };
                        }),
                        item.id,
                      );
                      onClose();
                    }}
                  >
                    Open in StudyMate chat
                  </button>
                </div>
              )}
            </>
          )}

          {item.content_type === "quiz" && (
            <div className="history-detail__quiz">
              {asRecord(content.score) && (
                <div className="history-detail__quiz-score">
                  <p className="history-detail__quiz-score-number">
                    {Number(asRecord(content.score)?.score ?? 0)} / {Number(asRecord(content.score)?.total ?? 0)}
                  </p>
                  <p className="history-detail__quiz-score-label">
                    {Number(asRecord(content.score)?.percentage ?? 0)}% correct
                  </p>
                </div>
              )}
              {asText(content.sourceFilename) && (
                <p className="history-detail__source">Source: {asText(content.sourceFilename)}</p>
              )}
              {asText(content.difficulty) && (
                <p className="history-detail__quiz-difficulty">Difficulty: {asText(content.difficulty)}</p>
              )}
              {asArray(content.questions).length ? (
                <ol className="history-detail__quiz-questions">
                  {asArray(content.questions).map((questionValue, qIndex) => {
                    const question = asRecord(questionValue) ?? {};
                    const questionId = asText(question.id);
                    const selected = asRecord(content.answers)?.[questionId];
                    return (
                      <li key={questionId || qIndex} className="history-detail__quiz-question">
                        <p className="history-detail__quiz-question-text">{asText(question.question)}</p>
                        <ul className="history-detail__quiz-options">
                          {asArray(question.options).map((optValue, oIndex) => {
                            const option = asRecord(optValue) ?? {};
                            const optionId = asText(option.id);
                            const isChosen = optionId === selected;
                            return (
                              <li
                                key={optionId || oIndex}
                                className={`history-detail__quiz-option ${isChosen ? "history-detail__quiz-option--selected" : ""}`}
                              >
                                <span className="history-detail__quiz-option-letter">{optionId}</span>
                                <span>{asText(option.text)}</span>
                                {isChosen && <span className="history-detail__quiz-option-tag">Your answer</span>}
                              </li>
                            );
                          })}
                        </ul>
                      </li>
                    );
                  })}
                </ol>
              ) : null}
            </div>
          )}

          {item.content_type === "flashcards" && (
            <div className="history-detail__flashcards">
              {asText(content.sourceFilename) && (
                <p className="history-detail__source">Source: {asText(content.sourceFilename)}</p>
              )}
              {asArray(content.cards).length ? (
                <div className="history-detail__flashcards-grid">
                  {asArray(content.cards).map((cardValue, index) => {
                    const card = asRecord(cardValue) ?? {};
                    return (
                      <article key={index} className="history-detail__flashcard">
                        <span className="history-detail__flashcard-index">Card {index + 1}</span>
                        <div className="history-detail__flashcard-front">
                          <p className="history-detail__flashcard-label">Front</p>
                          <p>{asText(card.front)}</p>
                        </div>
                        <div className="history-detail__flashcard-back">
                          <p className="history-detail__flashcard-label">Back</p>
                          <p>{asText(card.back)}</p>
                        </div>
                      </article>
                    );
                  })}
                </div>
              ) : (
                <p className="history-detail__empty">This set has no saved flashcards.</p>
              )}
            </div>
          )}
        </div>
      </article>
    </div>
  );
}

const filters: Array<{ label: string; value: HistoryFilter }> = [
  { label: "All", value: "all" },
  { label: "Summaries", value: "summary" },
  { label: "Chats", value: "chat" },
  { label: "Quizzes", value: "quiz" },
  { label: "Flashcards", value: "flashcards" },
];

export default function StudyHistorySidebar({
  isOpen,
  onClose,
  userId,
  refreshToken,
  onNewChat,
  onOpenChat,
  onDeleteChat,
}: StudyHistorySidebarProps) {
  const [items, setItems] = useState<StudyHistoryRecord[]>([]);
  const [loadedUserId, setLoadedUserId] = useState<string | null>(null);
  const [filter, setFilter] = useState<HistoryFilter>("all");
  const [search, setSearch] = useState("");
  const [selectedItem, setSelectedItem] = useState<StudyHistoryRecord | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [deleteError, setDeleteError] = useState("");
  const [deletingId, setDeletingId] = useState<string | null>(null);

  // Close on Escape key and manage body scroll
  useEffect(() => {
    if (!isOpen) return;

    document.body.classList.add("menu-open");

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);

    return () => {
      document.body.classList.remove("menu-open");
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen, onClose]);

  // Load history data
  useEffect(() => {
    if (!userId) {
      setItems([]);
      setLoadedUserId(null);
      setLoading(false);
      return;
    }

    let active = true;
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
    return userItems.filter(
      (item) =>
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
      setSelectedItem((current) => (current?.id === item.id ? null : current));
      if (item.content_type === "chat") onDeleteChat?.(item.id);
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
    <>
      {/* Backdrop */}
      <div
        className={`history-sidebar-backdrop ${isOpen ? "is-open" : ""}`}
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Slide-out Sidebar from Left */}
      <aside
        id="study-history-sidebar"
        className={`history-sidebar ${isOpen ? "is-open" : ""}`}
        aria-label="Study History & Sessions"
        aria-hidden={!isOpen}
      >
        {/* Header */}
        <div className="history-sidebar__header">
          <div className="history-sidebar__brand">
            <span className="history-sidebar__logo-badge" aria-hidden="true">
              S
            </span>
            <div className="history-sidebar__title-wrap">
              <span className="history-sidebar__title">
                StudyMate <span>AI</span>
              </span>
              <span className="history-sidebar__subtitle">Study History</span>
            </div>
          </div>

          <button
            type="button"
            className="history-sidebar__close-btn"
            onClick={onClose}
            aria-label="Close study history sidebar"
            title="Close sidebar (Esc)"
          >
            ×
          </button>
        </div>

        {/* Action: New Chat */}
        {onNewChat && (
          <div className="history-sidebar__actions">
            <button
              type="button"
              className="history-sidebar__new-chat-btn"
              onClick={() => {
                onNewChat();
                onClose();
              }}
              title="Start a new chat session"
            >
              <span aria-hidden="true" className="text-lg leading-none">
                +
              </span>
              <span>New Chat</span>
            </button>
          </div>
        )}

        {/* Search Input */}
        <div className="history-sidebar__search-wrap">
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search study history..."
            className="history-sidebar__search-input"
            aria-label="Search study history titles"
          />
        </div>

        {/* Category Filter Chips */}
        <div className="history-sidebar__filters" role="group" aria-label="Filter by category">
          {filters.map((opt) => (
            <button
              key={opt.value}
              type="button"
              className={`history-sidebar__filter-btn ${filter === opt.value ? "is-active" : ""}`}
              onClick={() => setFilter(opt.value)}
              aria-pressed={filter === opt.value}
            >
              {opt.label}
            </button>
          ))}
        </div>

        {/* Content list */}
        <div className="history-sidebar__content">
          {error && (
            <div className="rounded-xl border border-red-400/30 bg-red-400/10 p-3 text-xs text-red-200">
              {error}
            </div>
          )}

          {deleteError && (
            <div className="mb-2 rounded-xl border border-red-400/30 bg-red-400/10 p-3 text-xs text-red-200">
              {deleteError}
            </div>
          )}

          {isLoading ? (
            <div className="py-12 text-center text-sm text-white/50">
              <span className="study-history__spinner" aria-hidden="true" />
              <p className="mt-2">Loading your study history…</p>
            </div>
          ) : visibleItems.length === 0 ? (
            <div className="history-sidebar__empty">
              <span className="history-sidebar__empty-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 3 14.2 9.8 21 12l-6.8 2.2L12 21l-2.2-6.8L3 12l6.8-2.2L12 3Z" />
                </svg>
              </span>
              <h4>
                {loadedUserId === userId && items.length
                  ? "No matching items"
                  : "No history yet"}
              </h4>
              <p>
                {loadedUserId === userId && items.length
                  ? "Try searching for another term or selecting a different filter."
                  : "Your summaries, chats, and quizzes will be saved here."}
              </p>
            </div>
          ) : (
            <div>
              {visibleItems.map((item) => (
                <div key={item.id} className="history-sidebar__item">
                  <button
                    type="button"
                    className="history-sidebar__item-open"
                    onClick={() => setSelectedItem(item)}
                    title={`Open ${item.title}`}
                  >
                    <div className="history-sidebar__item-top">
                      <span
                        className={`history-sidebar__item-badge history-sidebar__item-badge--${item.content_type}`}
                      >
                        {item.content_type}
                      </span>
                      <time dateTime={item.created_at} className="history-sidebar__item-time">
                        {formatDate(item.created_at)}
                      </time>
                    </div>
                    <span className="history-sidebar__item-title">{item.title}</span>
                  </button>

                  <button
                    type="button"
                    className="history-sidebar__item-delete"
                    onClick={() => void handleDelete(item)}
                    disabled={deletingId === item.id}
                    aria-label={`Delete ${item.title}`}
                    title="Delete item"
                  >
                    <svg
                      aria-hidden="true"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      className="h-3.5 w-3.5"
                    >
                      <polyline points="3 6 5 6 21 6" />
                      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                    </svg>
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer (Quick section navigation) */}
        <div className="history-sidebar__footer">
          <p className="history-sidebar__footer-title">Jump to section</p>
          <div className="history-sidebar__nav-links">
            <Link
              to="/chat"
              className="history-sidebar__nav-link"
              onClick={onClose}
            >
              Chat
            </Link>
            <Link
              to="/mind-map"
              className="history-sidebar__nav-link"
              onClick={onClose}
            >
              Mind Map
            </Link>
            <Link
              to="/practice"
              className="history-sidebar__nav-link"
              onClick={onClose}
            >
              Practice
            </Link>
            <Link
              to="/study-planner"
              className="history-sidebar__nav-link"
              onClick={onClose}
            >
              Planner
            </Link>
          </div>
        </div>
      </aside>

      {/* Selected Item Full Detail Modal */}
      {selectedItem && (
        <HistoryDetail
          item={selectedItem}
          onClose={() => setSelectedItem(null)}
          onOpenChat={onOpenChat}
        />
      )}
    </>
  );
}
