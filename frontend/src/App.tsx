import { useEffect, useRef, useState } from "react";
import type { Session, User } from "@supabase/supabase-js";
import { Navigate, useLocation } from "react-router-dom";
import {
  uploadNotes,
  generateSummary,
  askAboutNotes,
  askStudyMate,
  type GeneratedQuiz,
  type QuizDifficulty,
  type QuizScore,
  type StudyChatMessage,
} from "./api";
import { supabase } from "./Lib/supabase";
import {
  fetchStudyHistory,
  saveStudyHistory,
  updateStudyHistory,
} from "./Lib/studyHistory";
import Auth from "./components/Auth";
import ApplicationLayout from "./components/ApplicationLayout";
import GlobalParticleBackground from "./components/GlobalParticleBackground";
import type { ConversationItem } from "./components/RecentConversations";
import type { UploadStatus } from "./components/ChatWorkspace";
import type { HistoryNotice } from "./pages/types";
import ChatPage from "./pages/ChatPage";
import MindMapPage from "./pages/MindMapPage";
import PracticePage from "./pages/PracticePage";
import StudyPlannerPage from "./pages/StudyPlannerPage";

function toNotesChatHistory(
  messages: StudyChatMessage[],
): Array<{ user: string; assistant: string }> {
  const turns: Array<{ user: string; assistant: string }> = [];
  for (let index = 0; index + 1 < messages.length; index += 2) {
    const userMessage = messages[index];
    const assistantMessage = messages[index + 1];
    if (userMessage.role === "user" && assistantMessage.role === "assistant") {
      turns.push({
        user: userMessage.content,
        assistant: assistantMessage.content,
      });
    }
  }
  return turns;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function toStoredChatMessages(content: unknown): StudyChatMessage[] {
  const messages = asRecord(content)?.messages;
  if (!Array.isArray(messages)) return [];

  return messages.flatMap((value) => {
    const message = asRecord(value);
    if (
      !message ||
      (message.role !== "user" && message.role !== "assistant") ||
      typeof message.content !== "string"
    ) return [];

    return [{
      role: message.role,
      content: message.content,
      ...(typeof message.createdAt === "string"
        ? { createdAt: message.createdAt }
        : {}),
    }];
  });
}

const pageTitles: Record<string, string> = {
  "/chat": "Chat",
  "/mind-map": "Mind Map",
  "/practice": "Practice",
  "/study-planner": "Study Planner",
};

export default function App() {
  const location = useLocation();
  const currentPath = location.pathname.replace(/\/+$/, "") || "/";
  const pageTitle = pageTitles[currentPath];
  const [session, setSession] = useState<Session | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [authError, setAuthError] = useState("");
  const [loggingOut, setLoggingOut] = useState(false);
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [uploadStatus, setUploadStatus] = useState<UploadStatus>("idle");
  const [uploadError, setUploadError] = useState("");
  const [documentId, setDocumentId] = useState<string | null>(null);
  const [summary, setSummary] = useState("");
  const [chatAnswer, setChatAnswer] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [chatMessages, setChatMessages] = useState<StudyChatMessage[]>([]);
  const [historyNotice, setHistoryNotice] = useState<HistoryNotice | null>(null);
  const [historyRevision, setHistoryRevision] = useState(0);
  const [historyLoadError, setHistoryLoadError] = useState("");
  const [historyLoading, setHistoryLoading] = useState(false);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [conversations, setConversations] = useState<ConversationItem[]>([]);
  const activeUserId = useRef<string | null>(null);
  const previousUserId = useRef<string | null>(null);
  const documentRequestId = useRef(0);
  const chatRequestId = useRef(0);
  const chatHistoryId = useRef<string | null>(null);
  const savedSummaryKeys = useRef(new Set<string>());

  useEffect(() => {
    const isChatPage = currentPath === "/chat" && session !== null;
    document.body.classList.toggle("chat-page-active", isChatPage);
    return () => document.body.classList.remove("chat-page-active");
  }, [currentPath, session]);

  const reportHistorySave = async (
    userId: string,
    save: () => Promise<unknown>,
  ) => {
    try {
      await save();
      if (activeUserId.current === userId) {
        setHistoryNotice(null);
        setHistoryRevision((revision) => revision + 1);
      }
    } catch (saveError) {
      if (activeUserId.current === userId) {
        setHistoryNotice({
          type: "error",
          message: `Your study material is ready, but could not be saved to history: ${saveError instanceof Error ? saveError.message : "Please try again."
            }`,
        });
      }
    }
  };

  useEffect(() => {
    let active = true;
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      if (!active) return;
      activeUserId.current = nextSession?.user.id ?? null;
      setSession(nextSession);
      setAuthLoading(false);
      setAuthError("");
      setLoggingOut(false);
    });

    void supabase.auth
      .getSession()
      .then(({ data, error }) => {
        if (!active) return;
        if (error) {
          activeUserId.current = null;
          setAuthError(error.message);
          setSession(null);
        } else {
          activeUserId.current = data.session?.user.id ?? null;
          setSession(data.session);
        }
        setAuthLoading(false);
      })
      .catch((error: unknown) => {
        if (!active) return;
        activeUserId.current = null;
        setAuthError(
          error instanceof Error
            ? error.message
            : "We couldn't restore your session. Please try again.",
        );
        setSession(null);
        setAuthLoading(false);
      });

    return () => {
      active = false;
      subscription.unsubscribe();
    };
  }, []);

  useEffect(() => {
    const userId = session?.user.id ?? null;
    if (previousUserId.current === userId) return;
    previousUserId.current = userId;
    documentRequestId.current += 1;
    chatRequestId.current += 1;
    chatHistoryId.current = null;
    savedSummaryKeys.current.clear();
    setUploadedFile(null);
    setUploadStatus("idle");
    setUploadError("");
    setDocumentId(null);
    setSummary("");
    setChatAnswer("");
    setChatLoading(false);
    setChatMessages([]);
    setHistoryNotice(null);
    setActiveConversationId(null);
  }, [session?.user.id]);

  useEffect(() => {
    const userId = session?.user.id;
    if (!userId) {
      setConversations([]);
      setHistoryLoadError("");
      setHistoryLoading(false);
      return;
    }
    let active = true;
    setHistoryLoadError("");
    setHistoryLoading(true);
    void fetchStudyHistory(userId)
      .then((records) => {
        if (!active) return;
        const chatRecords = records
          .filter((record) => record.content_type === "chat")
          .map((record) => ({
            id: record.id,
            title: record.title,
            updatedAt: record.updated_at || record.created_at,
            messages: toStoredChatMessages(record.content),
          }))
          .sort(
            (left, right) =>
              new Date(right.updatedAt).getTime() -
              new Date(left.updatedAt).getTime(),
          );
        setConversations(chatRecords);
      })
      .catch((error) => {
        console.error("Failed to load chat history:", error);
        if (active) {
          setHistoryLoadError(
            error instanceof Error
              ? error.message
              : "Conversations could not be loaded.",
          );
        }
      })
      .finally(() => {
        if (active) setHistoryLoading(false);
      });
    return () => {
      active = false;
    };
  }, [session?.user.id, historyRevision]);

  const handleLogout = async () => {
    setLoggingOut(true);
    setAuthError("");
    try {
      const { error } = await supabase.auth.signOut();
      if (error) {
        setAuthError(error.message);
        setLoggingOut(false);
      }
    } catch (error) {
      setAuthError(
        error instanceof Error
          ? error.message
          : "We couldn't sign you out. Please try again.",
      );
      setLoggingOut(false);
    }
  };

  const handleDocumentSelected = async (file: File | null) => {
    const requestId = ++documentRequestId.current;
    const ownerId = activeUserId.current;
    chatRequestId.current += 1;
    chatHistoryId.current = null;
    setChatMessages([]);
    setChatLoading(false);
    setUploadedFile(file);
    setDocumentId(null);
    setSummary("");
    setChatAnswer("");
    setUploadError("");

    if (!file) {
      setUploadStatus("idle");
      return;
    }

    setUploadStatus("uploading");
    let uploadedDocumentId: string | null = null;

    try {
      const uploaded = await uploadNotes(file);
      if (
        documentRequestId.current !== requestId ||
        activeUserId.current !== ownerId
      ) return;
      uploadedDocumentId = uploaded.document_id;
      setDocumentId(uploaded.document_id);
      setUploadStatus("ai-processing");

      const result = await generateSummary(uploaded.document_id);
      if (
        documentRequestId.current !== requestId ||
        activeUserId.current !== ownerId
      ) return;
      setSummary(result.summary);
      setUploadStatus("success");
      const summaryKey = `${ownerId}:${uploaded.document_id}`;
      if (ownerId && !savedSummaryKeys.current.has(summaryKey)) {
        savedSummaryKeys.current.add(summaryKey);
        void reportHistorySave(
          ownerId,
          () => saveStudyHistory(ownerId, file.name, "summary", {
            summary: result.summary,
            sourceFilename: file.name,
            mode: result.mode,
          }),
        );
      }
    } catch (error) {
      if (
        documentRequestId.current !== requestId ||
        activeUserId.current !== ownerId
      ) return;
      const message = error instanceof Error ? error.message : "Something went wrong.";
      setUploadStatus("error");
      setUploadError(
        uploadedDocumentId
          ? `The document was uploaded, but its summary could not be generated: ${message}`
          : message,
      );
      console.error("StudyMate AI error:", error);
    }
  };

  const handleSubmitQuestion = async (question: string) => {
    if (chatLoading) return;
    const ownerId = activeUserId.current;
    if (!ownerId) return;
    const requestId = ++chatRequestId.current;
    const previousMessages = chatMessages;
    const userMessage: StudyChatMessage = {
      role: "user",
      content: question,
      createdAt: new Date().toISOString(),
    };
    setChatMessages([...previousMessages, userMessage]);
    setChatLoading(true);
    setChatAnswer("");

    try {
      const result = documentId
        ? await askAboutNotes(
          documentId,
          question,
          toNotesChatHistory(previousMessages),
        )
        : await askStudyMate(
          question,
          previousMessages.map(({ role, content }) => ({ role, content })),
        );

      if (
        chatRequestId.current !== requestId ||
        activeUserId.current !== ownerId
      ) return;
      setChatAnswer(result.answer);
      const nextMessages: StudyChatMessage[] = [
        ...previousMessages,
        userMessage,
        {
          role: "assistant",
          content: result.answer,
          createdAt: new Date().toISOString(),
        },
      ];
      setChatMessages(nextMessages);
      const firstQuestion = nextMessages.find((message) => message.role === "user")?.content;
      const title = `Study chat: ${(firstQuestion ?? question).slice(0, 72)}`;
      const content = {
        messages: nextMessages,
        sourceFilename: uploadedFile?.name ?? null,
      };
      await reportHistorySave(
        ownerId,
        async () => {
          if (chatHistoryId.current) {
            await updateStudyHistory(ownerId, chatHistoryId.current, title, content);
            setActiveConversationId(chatHistoryId.current);
          } else {
            const historyId = await saveStudyHistory(ownerId, title, "chat", content);
            if (
              chatRequestId.current === requestId &&
              activeUserId.current === ownerId
            ) {
              chatHistoryId.current = historyId;
              setActiveConversationId(historyId);
            }
          }
        },
      );
    } catch (error) {
      if (
        chatRequestId.current !== requestId ||
        activeUserId.current !== ownerId
      ) return;
      console.error("Chat error:", error);
      setChatAnswer(
        error instanceof Error ? error.message : "Something went wrong.",
      );
    } finally {
      if (chatRequestId.current === requestId) setChatLoading(false);
    }
  };

  const handleNewChat = () => {
    chatRequestId.current += 1;
    setActiveConversationId(null);
    chatHistoryId.current = null;
    setChatMessages([]);
    setSummary("");
    setChatAnswer("");
    setChatLoading(false);
  };

  const handleDeleteConversation = (conversationId: string) => {
    setConversations((current) => current.filter((item) => item.id !== conversationId));
    if (
      activeConversationId === conversationId ||
      chatHistoryId.current === conversationId
    ) handleNewChat();
    setHistoryRevision((revision) => revision + 1);
  };

  const handleOpenChat = (messages: StudyChatMessage[], historyId: string) => {
    chatRequestId.current += 1;
    setChatMessages(messages);
    setSummary("");
    setChatAnswer("");
    setChatLoading(false);
    chatHistoryId.current = historyId;
    setActiveConversationId(historyId);
  };

  const handleQuizCompleted = (
    ownerId: string,
    quiz: GeneratedQuiz,
    answers: Record<string, string>,
    score: QuizScore,
    difficulty: QuizDifficulty,
    documentTitle: string,
  ) => {
    if (!ownerId || activeUserId.current !== ownerId) return;
    const title = `Quiz: ${documentTitle || "Study materials"}`;
    void reportHistorySave(
      ownerId,
      () => saveStudyHistory(ownerId, title, "quiz", {
        questions: quiz.questions,
        answers,
        score: {
          score: score.score,
          total: score.total,
          percentage: score.percentage,
        },
        results: score.results,
        difficulty,
        sourceFilename: documentTitle || null,
      }),
    );
  };

  const userMetadata = session?.user.user_metadata;
  const metadataName =
    typeof userMetadata?.full_name === "string" && userMetadata.full_name.trim()
      ? userMetadata.full_name.trim()
      : typeof userMetadata?.name === "string" && userMetadata.name.trim()
        ? userMetadata.name.trim()
        : "";
  const userName = metadataName || session?.user.email?.split("@")[0] || "Student";
  const avatarMetadata =
    typeof userMetadata?.avatar_url === "string"
      ? userMetadata.avatar_url
      : typeof userMetadata?.picture === "string"
        ? userMetadata.picture
        : "";

  const handleProfileUpdated = (user: User) => {
    setSession((currentSession) =>
      currentSession ? { ...currentSession, user } : currentSession,
    );
  };

  return (
    <GlobalParticleBackground enabled={false}>
      {authLoading ? (
        <div className="auth-loading" role="status" aria-live="polite">
          <span className="auth-loading__spinner" aria-hidden="true" />
          <p>Restoring your StudyMate session…</p>
        </div>
      ) : session ? currentPath === "/" || !pageTitle ? (
        <Navigate to="/chat" replace />
      ) : (
        <div className="global-particle-background__content font-body">
          <ApplicationLayout
            pageTitle={pageTitle}
            isChatWorkspace={currentPath === "/chat"}
            isMindMapWorkspace={currentPath === "/mind-map"}
            user={session.user}
            userId={session.user.id}
            userName={userName}
            avatarUrl={avatarMetadata || null}
            onLogout={handleLogout}
            loggingOut={loggingOut}
            logoutError={authError}
            onProfileUpdated={handleProfileUpdated}
            conversations={conversations}
            conversationLoadError={historyLoadError}
            conversationsLoading={historyLoading}
            activeConversationId={activeConversationId}
            onNewChat={handleNewChat}
            onOpenChat={handleOpenChat}
            onDeleteChat={handleDeleteConversation}
          >
            <div className="workspace-page-stack">
              <section
                className="workspace-page"
                hidden={currentPath !== "/chat"}
                aria-hidden={currentPath !== "/chat"}
              >
                <ChatPage
                  userName={userName}
                  uploadedFile={uploadedFile}
                  uploadStatus={uploadStatus}
                  uploadError={uploadError}
                  onDocumentSelected={handleDocumentSelected}
                  onSubmitQuestion={handleSubmitQuestion}
                  summary={summary}
                  chatMessages={chatMessages}
                  chatAnswer={chatAnswer}
                  chatLoading={chatLoading}
                  historyError={
                    historyNotice?.type === "error" ? historyNotice.message : ""
                  }
                />
              </section>
              <section
                className="workspace-page"
                hidden={currentPath !== "/mind-map"}
                aria-hidden={currentPath !== "/mind-map"}
              >
                <MindMapPage />
              </section>
              <section
                className="workspace-page"
                hidden={currentPath !== "/practice"}
                aria-hidden={currentPath !== "/practice"}
              >
                <PracticePage
                  userId={session.user.id}
                  documentId={documentId}
                  documentTitle={uploadedFile?.name ?? ""}
                  onQuizCompleted={handleQuizCompleted}
                />
              </section>
              <section
                className="workspace-page"
                hidden={currentPath !== "/study-planner"}
                aria-hidden={currentPath !== "/study-planner"}
              >
                <StudyPlannerPage />
              </section>
            </div>
          </ApplicationLayout>
        </div>
      ) : (
        <Auth error={authError} />
      )}
    </GlobalParticleBackground>
  );
}
