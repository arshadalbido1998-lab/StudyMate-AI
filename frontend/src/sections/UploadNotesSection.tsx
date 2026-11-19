import "./UploadNotesSection.css";

export default function UploadNotesSection() {
  return (
    <section
      id="document-workflow"
      className="upload-notes-section"
      aria-labelledby="upload-notes-title"
    >
      <div className="upload-notes-section__layout">
        <header className="upload-notes-section__intro">
          <p className="upload-notes-section__eyebrow">
            <span aria-hidden="true" />
            Stage 01 / Upload notes
          </p>
          <h2 id="upload-notes-title">
            Start with the material you already have.
          </h2>
          <p className="upload-notes-section__description">
            Upload a PDF, lecture note, or scan in the composer below. StudyMate
            extracts the text so you can chat with your notes and review a
            generated summary.
          </p>
        </header>
      </div>
    </section>
  );
}
