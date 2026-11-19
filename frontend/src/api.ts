const API_BASE = "/api";

async function apiRequest<T>(
  endpoint: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(`${API_BASE}${endpoint}`, options);

  if (!response.ok) {
    let message = `Request failed (${response.status})`;

    try {
      const error = await response.json();
      message = error.detail || message;
    } catch {
      // Keep the fallback error message.
    }

    throw new Error(message);
  }

  return response.json() as Promise<T>;
}

export type UploadedDocument = {
  document_id: string;
  filename: string;
  word_count: number;
  char_count: number;
  chunks: number;
  preview: string;
};

export type QuizDifficulty = "easy" | "medium" | "hard";

export type QuizOption = {
  id: string;
  text: string;
};

export type QuizQuestion = {
  id: string;
  question: string;
  options: QuizOption[];
};

export type GeneratedQuiz = {
  quiz_id: string;
  questions: QuizQuestion[];
};

export type QuizSubmissionResult = {
  question_id: string;
  selected_option_id: string;
  correct_option_id: string;
  correct_answer: string;
  is_correct: boolean;
  explanation: string;
};

export type QuizScore = {
  score: number;
  total: number;
  percentage: number;
  results: QuizSubmissionResult[];
};

export type StudyChatMessage = {
  role: "user" | "assistant";
  content: string;
  createdAt?: string;
};

export type MindMapTopicNode = {
  id: string;
  label: string;
  description: string;
  subtopics: Array<{
    id: string;
    label: string;
    description: string;
  }>;
};

export type MindMapRelatedConcept = {
  id: string;
  label: string;
  description: string;
  related_to: string[];
  relationship: string;
};

export type GeneratedMindMap = {
  central_topic: {
    id: "central";
    label: string;
    description: string;
  };
  main_topics: MindMapTopicNode[];
  related_concepts: MindMapRelatedConcept[];
};

export async function generateQuiz(
  documentId: string,
  questionCount: 5 | 10 | 15,
  difficulty: QuizDifficulty,
  previousQuizId?: string,
): Promise<GeneratedQuiz> {
  return apiRequest<GeneratedQuiz>("/generate-quiz", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      document_id: documentId,
      question_count: questionCount,
      difficulty,
      language: "english",
      ...(previousQuizId ? { previous_quiz_id: previousQuizId } : {}),
    }),
  });
}

export async function submitQuiz(
  quizId: string,
  answers: Record<string, string>,
): Promise<QuizScore> {
  return apiRequest<QuizScore>("/submit-quiz", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ quiz_id: quizId, answers }),
  });
}

export async function validateQuizAnswer(
  quizId: string,
  questionId: string,
  selectedOptionId: string,
): Promise<QuizSubmissionResult> {
  return apiRequest<QuizSubmissionResult>("/validate-quiz-answer", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      quiz_id: quizId,
      question_id: questionId,
      selected_option_id: selectedOptionId,
    }),
  });
}

export async function uploadNotes(
  file: File,
): Promise<UploadedDocument> {
  const formData = new FormData();
  formData.append("file", file);

  return apiRequest<UploadedDocument>("/upload", {
    method: "POST",
    body: formData,
  });
}

export async function generateSummary(
  documentId: string,
): Promise<{ summary: string; mode: string }> {
  return apiRequest("/summarize", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      document_id: documentId,
      mode: "medium",
      language: "english",
    }),
  });
}

export async function generateMindMap(
  documentId: string,
  language = "english",
  signal?: AbortSignal,
  generationId?: string,
): Promise<GeneratedMindMap> {
  return apiRequest<GeneratedMindMap>("/mind-map", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ document_id: documentId, language, generation_id: generationId }),
    signal,
  });
}

export async function cancelMindMapGeneration(generationId: string): Promise<{ cancelled: boolean; status: string }> {
  return apiRequest(`/mind-map/cancel/${encodeURIComponent(generationId)}`, { method: "POST" });
}

export type MindMapProgress = {
  stage: "reading_document" | "generating_branches" | "connecting_concepts" | "validating_mind_map" | "cancelling" | "cancelled" | "complete" | "failed";
  elapsed_seconds: number;
  completed_chunks?: number | null;
  total_chunks?: number | null;
};

export async function getMindMapProgress(documentId: string, signal?: AbortSignal): Promise<MindMapProgress> {
  return apiRequest<MindMapProgress>(`/mind-map/progress/${encodeURIComponent(documentId)}`, { signal });
}

export async function customizeMindMap(
  documentId: string,
  currentMap: GeneratedMindMap,
  instruction: string,
): Promise<GeneratedMindMap> {
  return apiRequest<GeneratedMindMap>("/mind-map/customize", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ document_id: documentId, current_map: currentMap, instruction }),
  });
}

export async function askAboutNotes(
  documentId: string,
  question: string,
  chatHistory: Array<{ user: string; assistant: string }> = [],
): Promise<{ answer: string; question: string }> {
  return apiRequest("/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      document_id: documentId,
      question,
      chat_history: chatHistory,
      language: "english",
    }),
  });
}

export async function askStudyMate(
  question: string,
  chatHistory: StudyChatMessage[] = [],
): Promise<{ answer: string; question: string }> {
  return apiRequest("/general-chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      chat_history: chatHistory,
      language: "english",
    }),
  });
}
export type StudyPlanRequest = {
  subject: string;
  topics: string;
  exam_date: string;
  hours_per_day: number;
  language?: string;
};

export async function generateStudyPlan(
  request: StudyPlanRequest,
): Promise<{ plan: string }> {
  return apiRequest<{ plan: string }>("/study-plan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ...request,
      language: request.language ?? "english",
    }),
  });
}

export type Flashcard = {
  front: string;
  back: string;
};

export async function generateFlashcards(
  documentId: string,
  count: 5 | 10 | 15 = 10,
): Promise<{ flashcards: Flashcard[]; count: number }> {
  return apiRequest("/flashcards", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      document_id: documentId,
      count,
      language: "english",
    }),
  });
}
