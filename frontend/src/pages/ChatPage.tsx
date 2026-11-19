import type { StudyChatMessage } from "../api";
import type { UploadStatus } from "../components/ChatWorkspace";
import ChatWorkspace from "../components/ChatWorkspace";

type ChatPageProps = {
  userName: string;
  uploadedFile: File | null;
  uploadStatus: UploadStatus;
  uploadError: string;
  onDocumentSelected: (file: File | null) => void;
  onSubmitQuestion: (question: string) => void;
  summary: string;
  chatMessages: StudyChatMessage[];
  chatAnswer: string;
  chatLoading: boolean;
  historyError: string;
};

export default function ChatPage({
  userName,
  uploadedFile,
  uploadStatus,
  uploadError,
  onDocumentSelected,
  onSubmitQuestion,
  summary,
  chatMessages,
  chatAnswer,
  chatLoading,
  historyError,
}: ChatPageProps) {
  return (
    <ChatWorkspace
      userName={userName}
      uploadedFile={uploadedFile}
      uploadStatus={uploadStatus}
      uploadError={uploadError}
      onDocumentSelected={onDocumentSelected}
      onSubmitQuestion={onSubmitQuestion}
      summary={summary}
      chatMessages={chatMessages}
      chatAnswer={chatAnswer}
      chatLoading={chatLoading}
      historyError={historyError}
    />
  );
}
