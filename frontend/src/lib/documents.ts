import { API, getToken } from "@/lib/auth";

function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export type DocumentItem = {
  id: string;
  filename: string;
  status: string;
  total_pages: number | null;
  created_at: string;
  markdown_path: string | null;
  json_tree_path: string | null;
};

export type DocumentDetail = DocumentItem & {
  raw_file_path: string;
};

export async function getDocuments(): Promise<DocumentItem[]> {
  const res = await fetch(`${API}/documents`, { headers: authHeaders() });
  if (!res.ok) return [];
  return res.json();
}

export async function getDocumentDetail(docId: string): Promise<DocumentDetail | null> {
  const res = await fetch(`${API}/documents/${docId}`, { headers: authHeaders() });
  if (!res.ok) return null;
  return res.json();
}

export async function deleteDocument(docId: string): Promise<boolean> {
  const res = await fetch(`${API}/documents/${docId}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  return res.ok;
}

export async function getDocumentMarkdown(docId: string): Promise<string | null> {
  const res = await fetch(`${API}/documents/${docId}/markdown`, {
    headers: authHeaders(),
  });
  if (!res.ok) return null;
  const data = await res.json();
  return data.markdown ?? null;
}

export async function saveDocumentMarkdown(docId: string, markdown: string): Promise<boolean> {
  const res = await fetch(`${API}/documents/${docId}/markdown`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ markdown }),
  });
  return res.ok;
}

export async function confirmDocumentMd(docId: string): Promise<boolean> {
  const res = await fetch(`${API}/documents/${docId}/confirm-md`, {
    method: "POST",
    headers: authHeaders(),
  });
  return res.ok;
}

export async function rebuildTree(docId: string): Promise<boolean> {
  const res = await fetch(`${API}/documents/${docId}/build-tree`, {
    method: "POST",
    headers: authHeaders(),
  });
  return res.ok;
}
