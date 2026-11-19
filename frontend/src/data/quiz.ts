export type QuizOption = {
  id: string;
  text: string;
  correct?: boolean;
};

export type QuizQuestion = {
  question: string;
  sourceCard: string;
  options: QuizOption[];
};

export const sampleQuestion: QuizQuestion = {
  question: "What is an Operating System?",
  sourceCard: "Flashcard · Operating Systems, Unit 1",
  options: [
    { id: "a", text: "A program that manages hardware and runs other software" },
    { id: "b", text: "A physical component inside the CPU" },
    { id: "c", text: "A type of programming language" },
    { id: "d", text: "A file format for storing documents" },
  ],
};

// index of the correct option, kept separate so the UI can't accidentally read it
export const correctOptionId = "a";
