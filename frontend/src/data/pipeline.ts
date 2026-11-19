export type Stage = {
  id: string;
  index: number;
  label: string;
  title: string;
  description: string;
  color: string; // token name, matched to tailwind.config colors
};

export const stages: Stage[] = [
  {
    id: "notes",
    index: 1,
    label: "Notes",
    title: "Drop in what you already have.",
    description:
      "Upload a scanned chapter, a lecture PDF, or a photo of your handwriting. StudyMate reads it like a classmate who never skims.",
    color: "electric",
  },
  {
    id: "understand",
    index: 2,
    label: "Understand",
    title: "See the shape of the material.",
    description:
      "Dense pages compress into a plain-language summary and a map of how the concepts connect to each other.",
    color: "violet",
  },
  {
    id: "remember",
    index: 3,
    label: "Remember",
    title: "Turn concepts into recall.",
    description:
      "Key ideas become flashcards sized for real memory work — one idea per card, spaced for review.",
    color: "mint",
  },
  {
    id: "practice",
    index: 4,
    label: "Practice",
    title: "Test what actually stuck.",
    description:
      "Flashcards convert into short quizzes. Wrong answers loop back into your next review, not into a red mark and nothing else.",
    color: "coral",
  },
  {
    id: "master",
    index: 5,
    label: "Master",
    title: "Watch the trend, not just the score.",
    description:
      "Every session adds to a single progress line — streaks, accuracy, and time spent, so you know what's working before exam week does.",
    color: "lavender",
  },
];
