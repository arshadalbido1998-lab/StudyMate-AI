import { supabase } from "./supabase";

export type StudyHistoryType = "summary" | "chat" | "quiz" | "flashcards";

export type StudyHistoryRecord = {
  id: string;
  user_id: string;
  title: string;
  content_type: StudyHistoryType;
  content: unknown;
  created_at: string;
  updated_at: string;
};

const historyColumns =
  "id, user_id, title, content_type, content, created_at, updated_at";

export async function fetchStudyHistory(
  userId: string,
): Promise<StudyHistoryRecord[]> {
  const { data, error } = await supabase
    .from("study_history")
    .select(historyColumns)
    .eq("user_id", userId)
    .order("created_at", { ascending: false });

  if (error) throw error;
  return (data ?? []) as StudyHistoryRecord[];
}

export async function saveStudyHistory(
  userId: string,
  title: string,
  contentType: StudyHistoryType,
  content: Record<string, unknown>,
): Promise<string> {
  const { data, error } = await supabase
    .from("study_history")
    .insert({
      user_id: userId,
      title,
      content_type: contentType,
      content,
    })
    .select("id")
    .single();

  if (error) throw error;
  return data.id as string;
}

export async function updateStudyHistory(
  userId: string,
  historyId: string,
  title: string,
  content: Record<string, unknown>,
): Promise<void> {
  const { data, error } = await supabase
    .from("study_history")
    .update({ title, content })
    .eq("id", historyId)
    .eq("user_id", userId)
    .select("id")
    .maybeSingle();

  if (error) throw error;
  if (!data) throw new Error("This history item could not be updated.");
}

export async function deleteStudyHistory(
  userId: string,
  historyId: string,
): Promise<void> {
  const { data, error } = await supabase
    .from("study_history")
    .delete()
    .eq("id", historyId)
    .eq("user_id", userId)
    .select("id")
    .maybeSingle();

  if (error) throw error;
  if (!data) throw new Error("This history item could not be deleted.");
}
