import { useLayoutEffect, useRef, useState, type FormEvent } from "react";
import lottie from "lottie-web";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import scanAnimationData from "../assets/Document scanning orange(2).json";
import "./StudyMateComposer.css";
import type { StudyChatMessage } from "../api";

export type UploadStatus = "idle" | "uploading" | "ai-processing" | "success" | "error";

type StudyMateComposerProps = {
  uploadedFile: File | null;
  uploadStatus: UploadStatus;
  uploadError: string;
  onDocumentSelected: (file: File | null) => void;
  onSubmitQuestion: (question: string) => void;
  onNewChat?: () => void;
  summary: string;
  chatMessages: StudyChatMessage[];
  chatQuestion: string;
  chatAnswer: string;
  chatLoading: boolean;
};
export default function StudyMateComposer({
  uploadedFile,
  uploadStatus,
  uploadError,
  onDocumentSelected,
  onSubmitQuestion,
  onNewChat,
  summary,
  chatMessages,
  chatQuestion,
  chatAnswer,
  chatLoading,
}: StudyMateComposerProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const scanAnimationContainerRef = useRef<HTMLDivElement>(null);
  const [question, setQuestion] = useState("");
  const isProcessing = uploadStatus === "uploading" || uploadStatus === "ai-processing";
  const fileSize = uploadedFile
    ? uploadedFile.size >= 1024 * 1024
      ? `${(uploadedFile.size / (1024 * 1024)).toFixed(1)} MB`
      : `${Math.max(1, Math.round(uploadedFile.size / 1024))} KB`
    : "";

  useLayoutEffect(() => {
    const container = scanAnimationContainerRef.current;
    if (!isProcessing || !container) return;

    const animation = lottie.loadAnimation({
      container,
      renderer: "svg",
      loop: true,
      autoplay: true,
      animationData: scanAnimationData,
    });

    return () => animation.destroy();
  }, [isProcessing]);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    const trimmedQuestion = question.trim();
    if (!trimmedQuestion) return;

    onSubmitQuestion(trimmedQuestion);
    setQuestion("");
  };

  const handleQuestionChange = (event: React.ChangeEvent<HTMLTextAreaElement>) => {
    const textarea = event.currentTarget;
    setQuestion(textarea.value);
    textarea.style.height = "auto";
    const maxHeight = 192;
    textarea.style.height = `${Math.min(textarea.scrollHeight, maxHeight)}px`;
    textarea.style.overflowY = textarea.scrollHeight > maxHeight ? "auto" : "hidden";
  };

  return (
    <section
      id="upload"
      className="study-composer-section"
      aria-label="Upload notes or ask StudyMate"
    >
      <form id="ask" className="study-composer" onSubmit={handleSubmit}>
        {uploadedFile && (
          <div className="study-composer__attachment">
            <span className="study-composer__filetype" aria-hidden="true">
              {uploadedFile.name.split(".").pop()?.toUpperCase() ?? "FILE"}
            </span>
            <span className="study-composer__filename" title={uploadedFile.name}>
              {uploadedFile.name}
            </span>
            <span className="study-composer__filesize">{fileSize}</span>
            <button
              type="button"
              className="study-composer__remove"
              aria-label={`Remove ${uploadedFile.name}`}
              disabled={isProcessing}
              onClick={() => onDocumentSelected(null)}
            >
              ×
            </button>
          </div>
        )}
        {uploadedFile && (
          <div
            className={`study-document-state study-document-state--${uploadStatus}`}
            aria-live="polite"
          >
            <div className="study-document-state__heading">
              <div>
                <p>
                  {uploadStatus === "uploading"
                    ? "Uploading and extracting text"
                    : uploadStatus === "ai-processing"
                      ? "Preparing your AI summary"
                      : uploadStatus === "success"
                        ? "Document ready to study"
                        : uploadStatus === "error"
                          ? "Document processing failed"
                          : "Document selected"}
                </p>
                <span>
                  {uploadStatus === "uploading"
                    ? "Reading the file and extracting its contents."
                    : uploadStatus === "ai-processing"
                      ? "Your extracted notes are being turned into a summary."
                      : uploadStatus === "success"
                        ? "You can now ask questions about this document."
                        : uploadStatus === "error"
                          ? "Please check the message below and try again."
                          : "Ready to upload and analyze."}
                </span>
              </div>
            </div>
            {isProcessing ? (
              <div className="study-document-state__processing">
                <div className="study-document-state__scan-frame" aria-hidden="true">
                  <div className="study-document-state__page">
                    <span /><span /><span /><span /><span />
                    <i />
                  </div>
                  <div
                    ref={scanAnimationContainerRef}
                    className="study-document-state__lottie"
                    aria-hidden="true"
                  />
                </div>
                <p>
                  {uploadStatus === "uploading"
                    ? "Extracting document text"
                    : "Generating your summary"}
                </p>
              </div>
            ) : uploadStatus === "success" ? (
              <p className="study-document-state__confirmation" role="status">
                <span aria-hidden="true">✓</span>
                Processed successfully. Your summary is available below, and the
                chat is ready for questions.
              </p>
            ) : uploadStatus === "error" ? (
              <p className="study-document-state__error" role="alert">
                {uploadError}
              </p>
            ) : null}
          </div>
        )}
        <div className="study-composer__row">
          <input
            ref={fileInputRef}
            className="study-composer__file-input"
            type="file"
            accept=".pdf,.txt,.md,application/pdf,text/plain,text/markdown"
            aria-label="Upload a document"
            onChange={(event) => {
              const file = event.currentTarget.files?.[0];
              if (file && /\.(pdf|txt|md)$/i.test(file.name)) onDocumentSelected(file);
              event.currentTarget.value = "";
            }}
          />
          <textarea
            className="study-composer__question"
            rows={3}
            value={question}
            onChange={handleQuestionChange}
            disabled={isProcessing}
            onKeyDown={(event) => {
              if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
                event.preventDefault();
                event.currentTarget.form?.requestSubmit();
              }
            }}
            placeholder={uploadedFile ? "Ask anything about this document..." : "Ask StudyMate anything..."}
            aria-label="Ask StudyMate a question"
          />
          <div className="study-composer__toolbar">
            {chatMessages.length > 0 && onNewChat && (
              <button
                type="button"
                className="study-composer__upload"
                onClick={onNewChat}
                aria-label="Start a new chat"
              >
                <span aria-hidden="true">↺</span>
                <span>New chat</span>
              </button>
            )}
            <button
              type="button"
              className="study-composer__upload"
              disabled={isProcessing}
              onClick={() => fileInputRef.current?.click()}
            >
              <span className="study-composer__plus" aria-hidden="true">+</span>
              <span>Upload notes</span>
            </button>
            <span className="study-composer__hint">StudyMate answers from your material</span>
            <button
              type="submit"
              className="study-composer__send"
              aria-label="Send question"
              disabled={isProcessing || (!question.trim() && !uploadedFile)}
            >
              <span aria-hidden="true">↑</span>
            </button>
          </div>
        </div>
      </form>
      {summary && (
        <article
          className="study-chat-answer study-chat-summary"
          aria-label="Generated document summary"
        >
          <p className="study-chat-answer__title">StudyMate AI · Summary</p>
          <div className="study-markdown">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                table: ({ children }) => (
                  <div className="study-markdown__table-wrap">
                    <table>{children}</table>
                  </div>
                ),
              }}
            >
              {summary}
            </ReactMarkdown>
          </div>
        </article>
      )}

      {(chatMessages.length > 0 || chatLoading || chatQuestion || chatAnswer) && (
        <div className="study-chat-thread" aria-label="Conversation">
          {chatMessages.map((message, index) => (
            message.role === "user" ? (
              <p
                key={`user-${index}`}
                className="study-chat-question"
                aria-label="Your question"
              >
                {message.content}
              </p>
            ) : (
              <article
                key={`assistant-${index}`}
                className="study-chat-answer"
                aria-live="polite"
              >
                <p className="study-chat-answer__title">StudyMate AI</p>
                <div className="study-markdown">
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    components={{
                      table: ({ children }) => (
                        <div className="study-markdown__table-wrap">
                          <table>{children}</table>
                        </div>
                      ),
                    }}
                  >
                    {message.content}
                  </ReactMarkdown>
                </div>
              </article>
            )
          ))}

          {chatLoading && chatQuestion && !chatMessages.some((message) => message.role === "user" && message.content === chatQuestion && chatMessages[chatMessages.length - 1]?.role === "user") && (
            <p className="study-chat-question" aria-label="Your latest question">
              {chatQuestion}
            </p>
          )}

          {chatLoading && (
            <p className="study-chat-loading" role="status">
              StudyMate is thinking...
            </p>
          )}

          {!chatLoading && chatAnswer && chatMessages.length === 0 && (
            <article className="study-chat-answer" aria-live="polite">
              <p className="study-chat-answer__title">StudyMate AI</p>
              <div className="study-markdown">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={{
                    table: ({ children }) => (
                      <div className="study-markdown__table-wrap">
                        <table>{children}</table>
                      </div>
                    ),
                  }}
                >
                  {chatAnswer}
                </ReactMarkdown>
              </div>
            </article>
          )}
        </div>
      )}
    </section>
  );
}