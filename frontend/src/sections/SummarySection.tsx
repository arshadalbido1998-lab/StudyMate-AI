import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import "./SummarySection.css";

type SummarySectionProps = {
  summary?: string;
};

export default function SummarySection({ summary = "" }: SummarySectionProps) {
  const hasSummary = Boolean(summary.trim());

  return (
    <section
      id="summary"
      className="summary-section"
      aria-labelledby="summary-title"
    >
      <div className="summary-section__layout">
        <header className="summary-section__intro">
          <p className="summary-section__eyebrow">
            <span aria-hidden="true">02</span>
            AI-generated summary
          </p>
          <h2 id="summary-title">The noise falls away. The idea stays.</h2>
          <p>
            StudyMate compresses dense pages into a clear explanation while
            keeping the source close enough to verify.
          </p>
        </header>

        <article className="summary-reader" aria-label="Document summary">
          <div className="summary-reader__header">
            <div>
              <span className="summary-reader__indicator" aria-hidden="true" />
              <p>{hasSummary ? "Your summary" : "Summary preview"}</p>
            </div>
            {hasSummary && <span className="summary-reader__format">Markdown</span>}
          </div>

          <div className="summary-reader__content" aria-live="polite">
            {hasSummary ? (
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  table: ({ children }) => (
                    <div className="summary-reader__table-wrap">
                      <table>{children}</table>
                    </div>
                  ),
                }}
              >
                {summary}
              </ReactMarkdown>
            ) : (
              <p className="summary-reader__placeholder">
                Your AI-generated summary will appear here after you upload
                your notes.
              </p>
            )}
          </div>
        </article>
      </div>
    </section>
  );
}
