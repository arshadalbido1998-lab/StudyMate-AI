import { useEffect, useState } from "react";
import {
  deleteStudyHistory,
  fetchStudyHistory,
  saveStudyHistory,
  type StudyHistoryRecord,
} from "../Lib/studyHistory";
import { generateFlashcards, type Flashcard } from "../api";
import "./FlashcardsSection.css";

type FlashcardsSectionProps = {
  documentId: string | null;
  userId: string | null;
  documentTitle?: string;
};

export default function FlashcardsSection({
  documentId,
  userId,
  documentTitle,
}: FlashcardsSectionProps) {
  const [count, setCount] = useState<5 | 10 | 15>(10);
  const [cards, setCards] = useState<Flashcard[]>([]);
  const [index, setIndex] = useState(0);
  const [flipped, setFlipped] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [savedSets, setSavedSets] = useState<StudyHistoryRecord[]>([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!userId) return;
    let active = true;
    void fetchStudyHistory(userId)
      .then((records) => {
        if (!active) return;
        setSavedSets(records.filter((record) => record.content_type === "flashcards"));
      })
      .catch(() => {
        if (active) setSavedSets([]);
      });
    return () => {
      active = false;
    };
  }, [userId]);

  function shuffleCards(cardsToShuffle: Flashcard[]): Flashcard[] {
    const next = [...cardsToShuffle];
    for (let i = next.length - 1; i > 0; i -= 1) {
      const j = Math.floor(Math.random() * (i + 1));
      [next[i], next[j]] = [next[j], next[i]];
    }
    return next;
  }

  async function handleGenerate() {
    if (!documentId) {
      setError("Upload a document before generating flashcards.");
      return;
    }
    setLoading(true);
    setError("");
    setNotice("");
    setCards([]);
    setIndex(0);
    setFlipped(false);
    try {
      const result = await generateFlashcards(documentId, count);
      setCards(result.flashcards);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate flashcards.");
    } finally {
      setLoading(false);
    }
  }

  async function handleSave() {
    if (!userId || cards.length === 0) return;
    setSaving(true);
    setNotice("");
    try {
      await saveStudyHistory(userId, `Flashcards: ${documentTitle || "Study materials"}`, "flashcards", {
        cards,
        sourceFilename: documentTitle ?? null,
      });
      setNotice("Flashcard set saved to study history.");
      const records = await fetchStudyHistory(userId);
      setSavedSets(records.filter((record) => record.content_type === "flashcards"));
    } catch (err) {
      setNotice(err instanceof Error ? `Could not save flashcards: ${err.message}` : "Could not save flashcards.");
    } finally {
      setSaving(false);
    }
  }

  function handleShuffle() {
    setCards((current) => shuffleCards(current));
    setIndex(0);
    setFlipped(false);
  }

  function openSavedSet(record: StudyHistoryRecord) {
    const content = record.content as { cards?: Flashcard[] };
    if (Array.isArray(content?.cards) && content.cards.length > 0) {
      setCards(content.cards);
      setIndex(0);
      setFlipped(false);
      setError("");
      setNotice(`Opened saved set: ${record.title}`);
    }
  }

  async function handleDeleteSaved(record: StudyHistoryRecord) {
    if (!userId) return;
    try {
      await deleteStudyHistory(userId, record.id);
      setSavedSets((current) => current.filter((item) => item.id !== record.id));
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Could not delete saved set.");
    }
  }

  const currentCard = cards[index];

  return (
    <section
      id="flashcards"
      className="mx-auto w-full max-w-[128rem] px-4 py-10 sm:px-6 md:py-14 lg:px-[4vw]"
      aria-labelledby="flashcards-title"
    >
      <div className="rounded-2xl border border-white/10 bg-black/40 p-5 sm:p-7 md:p-9 ">
        <p className="mb-3 text-base uppercase tracking-[0.16em] text-white">
          Active Recall
        </p>

        <h2
          id="flashcards-title"
          className="mb-3 font-display text-3xl font-semibold text-paper md:text-4xl"
        >
          AI Flashcards
        </h2>

        <p className="mb-7 text-base leading-relaxed text-paper/70">
          Generate revision cards from your uploaded notes, flip to test your memory, shuffle, and save decks.
        </p>

        {/* Controls Bar */}
        <div className="mb-6 flex flex-wrap items-center justify-between gap-4 border-b border-white/10 pb-6">
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2">
              <label htmlFor="flashcard-count" className="text-sm font-medium text-paper/80 sm:text-base">
                Cards:
              </label>
              <select
                id="flashcard-count"
                value={count}
                onChange={(e) => setCount(Number(e.target.value) as 5 | 10 | 15)}
                disabled={loading}
                className="rounded-xl border border-white/15 bg-black/40 px-3 py-2 text-sm text-paper outline-none transition-colors focus:border-white/60 disabled:opacity-50 sm:text-base"
              >
                <option value={5} className="bg-black text-white">5 cards</option>
                <option value={10} className="bg-black text-white">10 cards</option>
                <option value={15} className="bg-black text-white">15 cards</option>
              </select>
            </div>

            <button
              type="button"
              onClick={handleGenerate}
              disabled={loading || !documentId}
              className="min-h-11 rounded-xl bg-black px-5 py-2.5 text-sm font-semibold text-black transition-opacity hover:opacity-85 disabled:cursor-not-allowed disabled:opacity-50 sm:text-base"
            >
              {loading ? "Generating..." : "Generate Flashcards"}
            </button>
          </div>

          {cards.length > 0 && (
            <div className="flex flex-wrap items-center gap-2.5">
              <button
                type="button"
                onClick={handleShuffle}
                disabled={loading}
                className="inline-flex min-h-10 items-center gap-1.5 rounded-xl border border-white/15 bg-white/[0.04] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-white/[0.08] hover:border-white/30 disabled:opacity-50"
                title="Shuffle flashcards"
              >
                <svg
                  aria-hidden="true"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  className="h-4 w-4"
                >
                  <polyline points="16 3 21 3 21 8" />
                  <line x1="4" y1="20" x2="21" y2="3" />
                  <polyline points="21 16 21 21 16 21" />
                  <line x1="15" y1="15" x2="21" y2="21" />
                  <line x1="4" y1="4" x2="9" y2="9" />
                </svg>
                Shuffle
              </button>

              <button
                type="button"
                onClick={() => void handleSave()}
                disabled={saving || !userId}
                className="inline-flex min-h-10 items-center gap-1.5 rounded-xl border border-white/15 bg-white/[0.04] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-white/[0.08] hover:border-white/30 disabled:opacity-50"
              >
                <svg
                  aria-hidden="true"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  className="h-4 w-4"
                >
                  <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z" />
                  <polyline points="17 21 17 13 7 13 7 21" />
                  <polyline points="7 3 7 8 15 8" />
                </svg>
                {saving ? "Saving..." : "Save Deck"}
              </button>
            </div>
          )}
        </div>

        {notice && (
          <p
            role="status"
            className="mb-6 rounded-xl border border-white/30 bg-black/10 p-4 text-base text-white"
          >
            {notice}
          </p>
        )}

        {error && (
          <p
            role="alert"
            className="mb-6 rounded-xl border border-red-400/30 bg-red-400/10 p-4 text-base text-red-200"
          >
            {error}
          </p>
        )}

        {loading && (
          <p role="status" className="py-8 text-center text-base text-paper/60">
            StudyMate AI is preparing your flashcards...
          </p>
        )}

        {!loading && cards.length === 0 && !error && (
          <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-white/15 bg-white/[0.02] px-6 py-12 text-center">
            <div className="mb-4 grid h-14 w-14 place-items-center rounded-2xl border border-white/30 bg-black/10 text-white">
              <svg
                aria-hidden="true"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
                className="h-6 w-6"
              >
                <rect x="5" y="3" width="14" height="18" rx="2" />
                <path d="M9 8h6M9 12h6M9 16h3" />
              </svg>
            </div>
            <p className="font-display text-lg font-semibold text-paper sm:text-xl">
              No flashcards active
            </p>
            <p className="mt-2 max-w-md text-sm text-paper/60 sm:text-base">
              {documentId
                ? "Click 'Generate Flashcards' above to create revision cards from your document."
                : "Upload your notes above, then generate flashcards for active recall practice."}
            </p>
          </div>
        )}

        {/* Active Flashcard Viewer */}
        {currentCard && !loading && (
          <div className="flex flex-col items-center py-2" aria-live="polite">
            <div className="mb-4 flex w-full max-w-2xl items-center justify-between text-sm">
              <span className="rounded-full border border-white/10 bg-white/[0.04] px-3.5 py-1 font-semibold text-paper/80">
                Card {index + 1} of {cards.length}
              </span>
              <span className="text-xs text-paper/50 sm:text-sm">
                Click card to flip
              </span>
            </div>

            <div className="flashcard-scene w-full max-w-2xl">
              <button
                type="button"
                className={`flashcard-3d ${flipped ? "is-flipped" : ""}`}
                onClick={() => setFlipped((value) => !value)}
                aria-label={flipped ? "Showing answer. Click to show question." : "Showing question. Click to reveal answer."}
              >
                {/* Front Face: Question */}
                <div className="flashcard-face flashcard-front">
                  <div className="flex items-center justify-between">
                    <span className="rounded-lg border border-white/40 bg-black/15 px-2.5 py-1 text-xs font-bold uppercase tracking-wider text-white">
                      Question
                    </span>
                    <span className="text-xs text-paper/40">Tap to flip ↻</span>
                  </div>
                  <div className="my-auto py-6">
                    <p className="font-display text-lg font-medium leading-relaxed text-paper sm:text-2xl">
                      {currentCard.front}
                    </p>
                  </div>
                  <div className="flex items-center justify-between text-xs text-paper/40">
                    <span>StudyMate AI</span>
                    <span>Click to reveal answer</span>
                  </div>
                </div>

                {/* Back Face: Answer */}
                <div className="flashcard-face flashcard-back">
                  <div className="flex items-center justify-between">
                    <span className="rounded-lg border border-white/40 bg-black/15 px-2.5 py-1 text-xs font-bold uppercase tracking-wider text-white">
                      Answer
                    </span>
                    <span className="text-xs text-paper/40">Tap to flip ↻</span>
                  </div>
                  <div className="my-auto py-6">
                    <p className="text-base font-normal leading-relaxed text-paper/90 sm:text-lg">
                      {currentCard.back}
                    </p>
                  </div>
                  <div className="flex items-center justify-between text-xs text-paper/40">
                    <span>StudyMate AI</span>
                    <span>Click to view question</span>
                  </div>
                </div>
              </button>
            </div>

            {/* Navigation buttons */}
            <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
              <button
                type="button"
                onClick={() => {
                  setIndex((v) => Math.max(0, v - 1));
                  setFlipped(false);
                }}
                disabled={index === 0}
                className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-white/15 bg-white/[0.04] px-5 py-2.5 text-base font-semibold text-white transition-colors hover:bg-white/[0.08] hover:border-white/30 disabled:cursor-not-allowed disabled:opacity-40"
              >
                ← Previous
              </button>

              <button
                type="button"
                onClick={() => setFlipped((value) => !value)}
                className="min-h-11 rounded-xl border border-white/40 bg-black/10 px-5 py-2.5 text-base font-semibold text-white transition-colors hover:bg-black/20"
              >
                Flip Card ↺
              </button>

              <button
                type="button"
                onClick={() => {
                  setIndex((v) => Math.min(cards.length - 1, v + 1));
                  setFlipped(false);
                }}
                disabled={index === cards.length - 1}
                className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-white/15 bg-white/[0.04] px-5 py-2.5 text-base font-semibold text-white transition-colors hover:bg-white/[0.08] hover:border-white/30 disabled:cursor-not-allowed disabled:opacity-40"
              >
                Next →
              </button>
            </div>
          </div>
        )}

        {/* Saved Flashcard Sets */}
        {savedSets.length > 0 && (
          <div className="mt-10 border-t border-white/10 pt-7">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="font-display text-xl font-semibold text-paper">
                Saved Flashcard Sets
              </h3>
              <span className="text-xs text-paper/50">
                {savedSets.length} {savedSets.length === 1 ? "set" : "sets"} saved
              </span>
            </div>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {savedSets.map((record) => {
                const recordContent = record.content as { cards?: Flashcard[] };
                const cardTotal = recordContent?.cards?.length ?? 0;
                return (
                  <div
                    key={record.id}
                    className="group flex flex-col justify-between rounded-xl border border-white/10 bg-white/[0.03] p-4 transition-colors hover:border-white/20 hover:bg-white/[0.05]"
                  >
                    <div>
                      <p className="line-clamp-1 font-semibold text-paper" title={record.title}>
                        {record.title}
                      </p>
                      <p className="mt-1 text-xs text-paper/50">
                        {cardTotal} cards
                      </p>
                    </div>
                    <div className="mt-4 flex items-center gap-2 border-t border-white/5 pt-3">
                      <button
                        type="button"
                        onClick={() => openSavedSet(record)}
                        className="flex-1 rounded-lg bg-black/20 px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-black/30"
                      >
                        Study Set
                      </button>
                      <button
                        type="button"
                        onClick={() => void handleDeleteSaved(record)}
                        aria-label={`Delete ${record.title}`}
                        className="rounded-lg border border-red-400/20 px-2.5 py-1.5 text-xs font-medium text-red-300 transition-colors hover:border-red-400/40 hover:bg-red-400/10"
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
