import { API } from "./auth";

export interface ChatSession {
  id: string;
  user_id: string | null;
  doc_id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
}

export interface ChatMessage {
  id: string;
  session_id: string;
  role: "user" | "assistant";
  content: string;
  sources: string | null;
  created_at: string;
}

export async function createSession(
  docId: string,
  title?: string
): Promise<ChatSession> {
  const res = await fetch(`${API}/chat/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ doc_id: docId, title }),
  });
  if (!res.ok) throw new Error("Failed to create session");
  return res.json();
}

export async function getSessions(docId?: string): Promise<ChatSession[]> {
  const url = docId
    ? `${API}/chat/sessions?doc_id=${encodeURIComponent(docId)}`
    : `${API}/chat/sessions`;
  const res = await fetch(url);
  if (!res.ok) throw new Error("Failed to fetch sessions");
  return res.json();
}

export async function getSession(sessionId: string): Promise<ChatSession> {
  const res = await fetch(`${API}/chat/sessions/${sessionId}`);
  if (!res.ok) throw new Error("Failed to fetch session");
  return res.json();
}

export async function deleteSession(sessionId: string): Promise<void> {
  const res = await fetch(`${API}/chat/sessions/${sessionId}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error("Failed to delete session");
}

export async function getMessages(
  sessionId: string
): Promise<ChatMessage[]> {
  const res = await fetch(`${API}/chat/sessions/${sessionId}/messages`);
  if (!res.ok) throw new Error("Failed to fetch messages");
  return res.json();
}

export async function askQuestion(
  docId: string,
  question: string,
  sessionId?: string
): Promise<{ answer: string; sources: { file: string; lines: string }[] }> {
  const res = await fetch(`${API}/chat/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      doc_id: docId,
      question,
      session_id: sessionId,
    }),
  });
  if (!res.ok) throw new Error("Failed to get answer");
  const data = await res.json();
  return {
    answer: data.result.answer,
    sources: data.result.sources,
  };
}
