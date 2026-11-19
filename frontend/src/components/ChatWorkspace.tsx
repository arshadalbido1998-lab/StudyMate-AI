import { useEffect, useRef, useState, type FormEvent, type ChangeEvent, type KeyboardEvent } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { StudyChatMessage } from "../api";
import "./ChatWorkspace.css";

export type UploadStatus = "idle" | "uploading" | "ai-processing" | "success" | "error";

type ChatWorkspaceProps = {
  userName: string;
  uploadedFile: File | null;
  uploadStatus: UploadStatus;
  uploadError: string;
  onDocumentSelected: (file: File | null) => void;
  onSubmitQuestion: (question: string) => void;
  summary: string;
  chatMessages: StudyChatMessage[];
  chatAnswer: string;
  chatLoading: boolean;
  historyError: string;
};

export default function ChatWorkspace({
  userName,
  uploadedFile,
  uploadStatus,
  uploadError,
  onDocumentSelected,
  onSubmitQuestion,
  summary,
  chatMessages,
  chatAnswer,
  chatLoading,
  historyError,
}: ChatWorkspaceProps) {
  const [question, setQuestion] = useState("");
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const isScanning = uploadStatus === "uploading" || uploadStatus === "ai-processing";
  const activeAttachment = pendingFile || uploadedFile;

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ block: "end", behavior: "auto" });
  }, [chatMessages, chatLoading, chatAnswer, historyError, isScanning, summary]);

  const handleTextareaChange = (event: ChangeEvent<HTMLTextAreaElement>) => {
    const textarea = event.currentTarget;
    setQuestion(textarea.value);
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 140)}px`;
  };

  const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.currentTarget.files?.[0];
    if (file && /\.(pdf|txt|md)$/i.test(file.name)) {
      setPendingFile(file);
      onDocumentSelected(file);
    }
    event.currentTarget.value = "";
  };

  const handleRemoveAttachment = () => {
    setPendingFile(null);
    onDocumentSelected(null);
  };

  const handleSubmit = (event?: FormEvent) => {
    event?.preventDefault();
    const trimmed = question.trim();
    if (!trimmed || isScanning || chatLoading) return;

    onSubmitQuestion(trimmed);
    setQuestion("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
    setPendingFile(null);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (
      event.key === "Enter" &&
      !event.shiftKey &&
      !event.nativeEvent.isComposing
    ) {
      event.preventDefault();
      handleSubmit();
    }
  };

  const fileSize = activeAttachment
    ? activeAttachment.size >= 1024 * 1024
      ? `${(activeAttachment.size / (1024 * 1024)).toFixed(1)} MB`
      : `${Math.max(1, Math.round(activeAttachment.size / 1024))} KB`
    : "";

  const lastMessage = chatMessages[chatMessages.length - 1];
  const failedMessage =
    !chatLoading && lastMessage?.role === "user" ? chatAnswer : "";

  return (
    <section
      id="chat-workspace"
      className="chat-workspace-section"
      aria-label="Chat"
    >
      <div className="chat-main">
        <div className="chat-stream" role="log" aria-live="polite">
          <div className="chat-stream__content">
            {chatMessages.length === 0 &&
              !summary &&
              !isScanning &&
              !chatLoading && (
                <h2 className="chat-welcome">
                  Hello, {userName}! What’s up?
                </h2>
              )}

            {summary && (
              <div className="chat-message-row chat-message-row--assistant chat-summary">
                <div className="chat-markdown">
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    components={{
                      table: ({ children }) => (
                        <div className="chat-markdown-table-wrap">
                          <table>{children}</table>
                        </div>
                      ),
                    }}
                  >
                    {summary}
                  </ReactMarkdown>
                </div>
              </div>
            )}

            {chatMessages.map((message, index) =>
              message.role === "user" ? (
                <div
                  key={`${message.createdAt ?? "user"}-${index}`}
                  className="chat-message-row chat-message-row--user"
                >
                  <div className="chat-message-bubble--user">
                    {message.content}
                  </div>
                </div>
              ) : (
                <div
                  key={`${message.createdAt ?? "assistant"}-${index}`}
                  className="chat-message-row chat-message-row--assistant"
                >
                  <div className="chat-markdown">
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      components={{
                        table: ({ children }) => (
                          <div className="chat-markdown-table-wrap">
                            <table>{children}</table>
                          </div>
                        ),
                      }}
                    >
                      {message.content}
                    </ReactMarkdown>
                  </div>
                </div>
              ),
            )}

            {isScanning && (
              <p className="chat-status" role="status" aria-live="polite">
                {uploadStatus === "uploading"
                  ? "Uploading notes…"
                  : "Processing notes…"}
              </p>
            )}

            {uploadError && !isScanning && (
              <p className="chat-status chat-status--error" role="alert">
                {uploadError}
              </p>
            )}

            {chatLoading && (
              <p className="chat-status" role="status" aria-live="polite">
                StudyMate is thinking…
              </p>
            )}

            {failedMessage && (
              <p className="chat-status chat-status--error" role="alert">
                {failedMessage}
              </p>
            )}

            {historyError && (
              <p className="chat-status chat-status--error" role="alert">
                {historyError}
              </p>
            )}

            <div ref={messagesEndRef} />
          </div>
        </div>

        <div className="chat-composer-wrapper">
          <form className="chat-composer-box" onSubmit={handleSubmit}>
            {activeAttachment && (
              <div className="chat-attachment-chip">
                <span className="chat-attachment-chip__type">
                  {activeAttachment.name.split(".").pop()?.toUpperCase() ?? "FILE"}
                </span>
                <span
                  className="chat-attachment-chip__name"
                  title={activeAttachment.name}
                >
                  {activeAttachment.name}
                </span>
                <span className="chat-attachment-chip__size">{fileSize}</span>
                <button
                  type="button"
                  className="chat-attachment-chip__remove"
                  onClick={handleRemoveAttachment}
                  disabled={isScanning}
                  aria-label={`Remove ${activeAttachment.name}`}
                  title="Remove attachment"
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true">
                    <path d="m6 6 12 12M18 6 6 18" />
                  </svg>
                </button>
              </div>
            )}

            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.txt,.md,application/pdf,text/plain,text/markdown"
              className="chat-file-input"
              onChange={handleFileChange}
              aria-label="Upload PDF or notes"
            />

            <div className="chat-composer-row">
              <button
                type="button"
                className="chat-composer-attach-btn"
                onClick={() => fileInputRef.current?.click()}
                disabled={isScanning}
                aria-label="Attach notes (PDF, TXT, MD)"
                title="Attach notes"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M12 5v14M5 12h14" />
                </svg>
              </button>

              <textarea
                ref={textareaRef}
                value={question}
                onChange={handleTextareaChange}
                onKeyDown={handleKeyDown}
                disabled={isScanning}
                rows={1}
                placeholder={
                  activeAttachment
                    ? "Ask about your notes"
                    : "Message StudyMate"
                }
                className="chat-composer-textarea"
                aria-label="Message StudyMate"
              />

              <button
                type="submit"
                disabled={isScanning || chatLoading || !question.trim()}
                className="chat-composer-send-btn"
                aria-label="Send message"
                title="Send message"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M12 19V5m-7 7 7-7 7 7" />
                </svg>
              </button>
            </div>
          </form>
        </div>
      </div>
    </section>
  );
}
