import "./KnowledgeTransformationSection.css";

const transformationSteps = [
  "RAW NOTES",
  "EXTRACTED IDEAS",
  "CONNECTED CONCEPTS",
  "UNDERSTANDING",
];

export default function KnowledgeTransformationSection() {
  return (
    <section
      id="knowledge-transformation"
      className="knowledge-transform"
      aria-labelledby="knowledge-transform-title"
    >
      <div className="knowledge-transform__stage">
        <header className="knowledge-transform__heading">
          <p className="knowledge-transform__eyebrow"><span /> THE STUDYMATE METHOD</p>
          <h2 id="knowledge-transform-title">
            <span>FROM INFORMATION</span>
            <span>TO <em>UNDERSTANDING</em></span>
          </h2>
          <p className="knowledge-transform__copy">StudyMate turns scattered study material into connected, structured knowledge.</p>
        </header>

        <ol className="knowledge-transform__flow" aria-label="How StudyMate structures your notes">
          {transformationSteps.map((step, index) => (
            <li key={step} className="knowledge-transform__step">
              <span className="knowledge-transform__step-number" aria-hidden="true">
                0{index + 1}
              </span>
              <span className="knowledge-transform__step-label">{step}</span>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}