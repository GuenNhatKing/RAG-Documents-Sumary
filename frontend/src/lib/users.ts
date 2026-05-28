import { API, getToken } from "./auth";

export interface UserItem {
  id: string;
  username: string;
  role: string;
}

function authHeaders(): Record<string, string> {
  const token = getToken();
  if (token) {
    return { Authorization: `Bearer ${token}` };
  }
  return {};
}

export async function getUsers(): Promise<UserItem[]> {
  const res = await fetch(`${API}/auth/users`, { headers: authHeaders() });
  if (!res.ok) throw new Error("Failed to fetch users");
  return res.json();
}

export async function updateUserRole(userId: string, role: string): Promise<UserItem> {
  const res = await fetch(`${API}/auth/users/${userId}/role`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ role }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to update role");
  }
  return res.json();
}
