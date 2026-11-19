import { useState, type FormEvent } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { generateStudyPlan } from "../api";
import "./StudyPlannerSection.css";

export default function StudyPlannerSection() {
  const [subject, setSubject] = useState("");
  const [topics, setTopics] = useState("");
  const [examDate, setExamDate] = useState("");
  const [hoursPerDay, setHoursPerDay] = useState(4);
  const [plan, setPlan] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();


    const cleanSubject = subject.trim();
    const cleanTopics = topics.trim();

    if (!cleanSubject || !cleanTopics || !examDate) {
      setError("Please fill in all fields.");
      return;
    }

    if (!Number.isInteger(hoursPerDay) || hoursPerDay < 1 || hoursPerDay > 16) {
      setError("Study hours must be between 1 and 16 per day.");
      return;
    }

    const today = new Date();
    const todayString = [
      today.getFullYear(),
      String(today.getMonth() + 1).padStart(2, "0"),
      String(today.getDate()).padStart(2, "0"),
    ].join("-");

    if (examDate < todayString) {
      setError("Please select today or a future exam date.");
      return;
    }

    setLoading(true);
    setError("");
    setPlan("");

    try {
      const result = await generateStudyPlan({
        subject: cleanSubject,
        topics: cleanTopics,
        exam_date: examDate,
        hours_per_day: hoursPerDay,
        language: "english",
      });

      setPlan(result.plan);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to generate your study plan. Please try again.",
      );
    } finally {
      setLoading(false);
    }


  }

  return (<section
    id="study-planner"
    className="mx-auto w-full max-w-[128rem] px-4 py-10 sm:px-6 md:py-14 lg:px-[4vw]"
  > <div className="rounded-2xl border border-white/10 bg-black/40 p-5 sm:p-7 md:p-9"> <p className="mb-3 text-base uppercase tracking-[0.16em] text-paper/70">
    Personalized learning </p>


      <h2 className="mb-3 font-display text-3xl font-semibold text-paper md:text-4xl">
        AI Study Planner
      </h2>

      <p className="mb-7 text-base leading-relaxed text-paper/70">
        Create a personalized study plan based on your subject, topics, and
        exam date.
      </p>

      <form onSubmit={handleSubmit} className="space-y-5">
        <div>
          <label
            htmlFor="planner-subject"
            className="mb-2 block text-base text-paper/80"
          >
            Subject
          </label>

          <input
            id="planner-subject"
            type="text"
            value={subject}
            onChange={(event) => setSubject(event.target.value)}
            placeholder="e.g. Python Programming"
            required
            maxLength={150}
            disabled={loading}
            className="w-full rounded-xl border border-white/15 bg-black/40 px-4 py-3 text-base text-paper outline-none focus:border-white/40 disabled:opacity-50"
          />
        </div>

        <div>
          <label
            htmlFor="planner-topics"
            className="mb-2 block text-base text-paper/80"
          >
            Topics to study
          </label>

          <textarea
            id="planner-topics"
            value={topics}
            onChange={(event) => setTopics(event.target.value)}
            placeholder="Enter your topics, separated by commas"
            required
            maxLength={5000}
            rows={4}
            disabled={loading}
            className="w-full resize-y rounded-xl border border-white/15 bg-black/40 px-4 py-3 text-base text-paper outline-none focus:border-white/40 disabled:opacity-50"
          />
        </div>

        <div className="grid gap-5 sm:grid-cols-2">
          <div>
            <label
              htmlFor="planner-date"
              className="mb-2 block text-base text-paper/80"
            >
              Exam date
            </label>

            <input
              id="planner-date"
              type="date"
              value={examDate}
              onChange={(event) => setExamDate(event.target.value)}
              min={(() => {
                const date = new Date();
                return [
                  date.getFullYear(),
                  String(date.getMonth() + 1).padStart(2, "0"),
                  String(date.getDate()).padStart(2, "0"),
                ].join("-");
              })()}
              required
              disabled={loading}
              className="w-full rounded-xl border border-white/15 bg-black/40 px-4 py-3 text-base text-paper outline-none focus:border-white/40 disabled:opacity-50"
            />
          </div>

          <div>
            <label
              htmlFor="planner-hours"
              className="mb-2 block text-base text-paper/80"
            >
              Study hours per day
            </label>

            <input
              id="planner-hours"
              type="number"
              min={1}
              max={16}
              step={1}
              value={hoursPerDay}
              onChange={(event) => {
                const value = event.target.value;
                setHoursPerDay(value === "" ? 0 : Number(value));
              }}
              required
              disabled={loading}
              className="w-full rounded-xl border border-white/15 bg-black/40 px-4 py-3 text-base text-paper outline-none focus:border-white/40 disabled:opacity-50"
            />
          </div>
        </div>

        <button
          type="submit"
          disabled={loading}
          className="min-h-12 rounded-xl bg-black px-6 py-3 text-base font-semibold text-black transition-opacity hover:opacity-85 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? "Creating your plan..." : "Generate Study Plan"}
        </button>
      </form>

      {error && (
        <p
          role="alert"
          className="mt-6 rounded-xl border border-red-400/30 bg-red-400/10 p-4 text-base text-red-200"
        >
          {error}
        </p>
      )}

      {loading && (
        <p role="status" className="mt-6 text-base text-paper/60">
          StudyMate AI is preparing your personalized plan...
        </p>
      )}

      {plan && (
        <div className="mt-7 rounded-xl border border-white/10 bg-black/30 p-5 sm:p-7">
          <h3 className="mb-4 font-display text-2xl font-semibold text-paper">
            Your Study Plan
          </h3>

          <div className="study-plan-markdown">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                table: ({ children }) => (
                  <div className="study-plan-table-wrap">
                    <table>{children}</table>
                  </div>
                ),
              }}
            >
              {plan}
            </ReactMarkdown>
          </div>
        </div>
      )}
    </div>
  </section>
  );
}