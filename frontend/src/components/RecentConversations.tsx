import { useMemo, useState } from "react";
import type { StudyChatMessage } from "../api";
import { deleteStudyHistory } from "../Lib/studyHistory";

export type ConversationItem = {
  id: string;
  title: string;
  updatedAt: string;
  messages: StudyChatMessage[];
};

type RecentConversationsProps = {
  userId: string;
  conversations: ConversationItem[];
  loadError: string;
  isLoading: boolean;
  activeConversationId: string | null;
  onNewChat: () => void;
  onOpenChat: (messages: StudyChatMessage[], historyId: string) => void;
  onDeleteChat: (historyId: string) => void;
};

export default function RecentConversations({
  userId,
  conversations,
  loadError,
  isLoading,
  activeConversationId,
  onNewChat,
  onOpenChat,
  onDeleteChat,
}: RecentConversationsProps) {
  const [search, setSearch] = useState("");
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const normalizedSearch = search.trim().toLocaleLowerCase();
  const visibleConversations = useMemo(
    () =>
      conversations
        .filter((conversation) =>
          conversation.title.toLocaleLowerCase().includes(normalizedSearch),
        )
        .slice(0, 30),
    [conversations, normalizedSearch],
  );

  const handleDelete = async (conversation: ConversationItem) => {
    if (!window.confirm(`Delete "${conversation.title}"?`)) return;
    setDeletingId(conversation.id);
    setError("");
    try {
      await deleteStudyHistory(userId, conversation.id);
      onDeleteChat(conversation.id);
    } catch (deleteError) {
      setError(
        deleteError instanceof Error
          ? deleteError.message
          : "This conversation could not be deleted.",
      );
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <>
      <button
        className="workspace-new-chat"
        type="button"
        onClick={onNewChat}
        aria-label="New chat"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true">
          <path d="M12 5v14M5 12h14" />
        </svg>
        <span>New chat</span>
      </button>

      <section className="workspace-conversations" aria-label="Recent conversations">
        <h2 className="workspace-conversations__heading">Recent conversations</h2>
        <label className="workspace-conversations__search">
          <span className="sr-only">Search conversations</span>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" aria-hidden="true">
            <circle cx="10.8" cy="10.8" r="6.8" />
            <path d="m16 16 4.5 4.5" />
          </svg>
          <input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.currentTarget.value)}
            placeholder="Search chats"
          />
        </label>

        {error && (
          <p className="workspace-conversations__error" role="alert">
            {error}
          </p>
        )}
        {loadError && (
          <p className="workspace-conversations__error" role="alert">
            {loadError}
          </p>
        )}

        <div className="workspace-conversations__list">
          {isLoading ? (
            <p className="workspace-conversations__empty">Loading conversations…</p>
          ) : visibleConversations.length === 0 ? (
            <p className="workspace-conversations__empty">
              {loadError
                ? "Refresh to try again."
                : normalizedSearch
                  ? "No matching conversations"
                  : "No conversations yet"}
            </p>
          ) : (
            visibleConversations.map((conversation) => (
              <div
                className={`workspace-conversation${conversation.id === activeConversationId ? " is-active" : ""}`}
                key={conversation.id}
              >
                <button
                  type="button"
                  className="workspace-conversation__open"
                  aria-current={conversation.id === activeConversationId ? "page" : undefined}
                  title={conversation.title}
                  onClick={() => onOpenChat(conversation.messages, conversation.id)}
                >
                  {conversation.title}
                </button>
                <button
                  type="button"
                  className="workspace-conversation__delete"
                  aria-label={`Delete ${conversation.title}`}
                  title="Delete conversation"
                  disabled={deletingId === conversation.id}
                  onClick={() => void handleDelete(conversation)}
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <path d="M4 7h16M10 11v6m4-6v6M6 7l1 14h10l1-14M9 7V4h6v3" />
                  </svg>
                </button>
              </div>
            ))
          )}
        </div>
      </section>
    </>
  );
}
