import type { GeneratedQuiz, QuizDifficulty, QuizScore } from "../api";
import FlashcardsSection from "../sections/FlashcardsSection";
import PracticeSection from "../sections/PracticeSection";

type PracticePageProps = {
  userId: string;
  documentId: string | null;
  documentTitle: string;
  onQuizCompleted: (
    userId: string,
    quiz: GeneratedQuiz,
    answers: Record<string, string>,
    score: QuizScore,
    difficulty: QuizDifficulty,
    documentTitle: string,
  ) => void;
};

export default function PracticePage({
  userId,
  documentId,
  documentTitle,
  onQuizCompleted,
}: PracticePageProps) {
  return (
    <>
      <PracticeSection
        userId={userId}
        documentId={documentId}
        documentTitle={documentTitle}
        onQuizCompleted={onQuizCompleted}
      />
      <FlashcardsSection
        documentId={documentId}
        userId={userId}
        documentTitle={documentTitle}
      />
    </>
  );
}
