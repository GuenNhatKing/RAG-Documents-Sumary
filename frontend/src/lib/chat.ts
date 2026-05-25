import { API, getToken } from "./auth";

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

function authHeaders(): Record<string, string> {
  const token = getToken();
  if (token) {
    return { Authorization: `Bearer ${token}` };
  }
  return {};
}

export async function createSession(
  docId: string,
  title?: string
): Promise<ChatSession> {
  const res = await fetch(`${API}/chat/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ doc_id: docId, title }),
  });
  if (!res.ok) throw new Error("Failed to create session");
  return res.json();
}

export async function getSessions(docId?: string): Promise<ChatSession[]> {
  const url = docId
    ? `${API}/chat/sessions?doc_id=${encodeURIComponent(docId)}`
    : `${API}/chat/sessions`;
  const res = await fetch(url, { headers: authHeaders() });
  if (!res.ok) return [];
  return res.json();
}

export async function getSession(sessionId: string): Promise<ChatSession> {
  const res = await fetch(`${API}/chat/sessions/${sessionId}`, {
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error("Failed to fetch session");
  return res.json();
}

export async function deleteSession(sessionId: string): Promise<void> {
  const res = await fetch(`${API}/chat/sessions/${sessionId}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error("Failed to delete session");
}

export async function getMessages(
  sessionId: string
): Promise<ChatMessage[]> {
  const res = await fetch(`${API}/chat/sessions/${sessionId}/messages`, {
    headers: authHeaders(),
  });
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
    headers: { "Content-Type": "application/json", ...authHeaders() },
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

// ============================================================
// MASTER TREE SEARCH & GLOBAL ASK
// ============================================================
export interface DocSearchResult {
  doc_id: string;
  filename: string;
  summary: string;
}

export async function searchMasterTree(
  query: string
): Promise<DocSearchResult[]> {
  const res = await fetch(`${API}/chat/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ query }),
  });
  if (!res.ok) throw new Error("Search failed");
  return res.json();
}

export async function askGlobal(
  question: string,
  sessionId?: string
): Promise<{
  answer: string;
  sources: { file: string; lines: string }[];
  relevant_docs: DocSearchResult[];
}> {
  const res = await fetch(`${API}/chat/ask-global`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ question, session_id: sessionId }),
  });
  if (!res.ok) throw new Error("Global ask failed");
  return res.json();
}
