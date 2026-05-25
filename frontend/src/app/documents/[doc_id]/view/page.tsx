"use client";

import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import DocumentViewerClient from "./viewer-client";
import { API, getToken } from "@/lib/auth";

export default function DocumentViewPage() {
  const params = useParams<{ doc_id: string }>();
  const searchParams = useSearchParams();
  const docId = params.doc_id;
  const highlight = searchParams.get("highlight") ?? "";

  const [markdown, setMarkdown] = useState<string | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    async function load() {
      const token = getToken();
      const headers: Record<string, string> = {
        Accept: "application/json",
      };
      if (token) headers.Authorization = `Bearer ${token}`;

      try {
        const res = await fetch(
          `${API}/documents/${docId}/markdown`,
          { headers, cache: "no-store" }
        );
        if (!res.ok) {
          setError(true);
          return;
        }
        const data = await res.json();
        setMarkdown(data.markdown);
      } catch {
        setError(true);
      }
    }
    load();
  }, [docId]);

  if (error) {
    return (
      <main className="min-h-screen flex items-center justify-center bg-white p-8">
        <p className="text-red-600 text-xl">
          Failed to load document
        </p>
      </main>
    );
  }

  if (markdown === null) {
    return (
      <main className="min-h-screen flex items-center justify-center bg-white p-8">
        <p className="text-gray-500">Đang tải tài liệu…</p>
      </main>
    );
  }

  return (
    <DocumentViewerClient
      markdown={markdown}
      highlight={highlight}
      docId={docId}
    />
  );
}
