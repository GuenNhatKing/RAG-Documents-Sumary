import { API, getToken } from "./auth";

export interface StatsData {
  total_docs: number;
  docs_by_status: Record<string, number>;
  total_users: number;
  users_by_role: Record<string, number>;
  total_sessions: number;
  total_questions: number;
}

function authHeaders(): Record<string, string> {
  const token = getToken();
  if (token) {
    return { Authorization: `Bearer ${token}` };
  }
  return {};
}

export async function getStats(): Promise<StatsData> {
  const res = await fetch(`${API}/stats`, { headers: authHeaders() });
  if (!res.ok) throw new Error("Failed to fetch stats");
  return res.json();
}
