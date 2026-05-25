"use client";

import { useEffect, useState } from "react";
import { useParams, useSearchParams, useRouter } from "next/navigation";
import DocumentViewerClient from "./viewer-client";
import { API, getToken } from "@/lib/auth";

export default function DocumentViewPage() {
  const params = useParams<{ doc_id: string }>();
  const searchParams = useSearchParams();
  const router = useRouter();
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
      <main className="min-h-screen flex flex-col items-center justify-center bg-white p-8 gap-4">
        <p className="text-red-600 text-xl">
          Không thể tải tài liệu
        </p>
        <button
          onClick={() => router.push("/files")}
          className="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 text-sm"
        >
          Quay lại danh sách
        </button>
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
    <div className="flex flex-col h-full">
      <div className="flex-shrink-0 px-4 py-2 bg-white border-b border-gray-200">
        <button
          onClick={() => router.push("/files")}
          className="text-sm text-[#2fa084] hover:underline"
        >
          &larr; Quay lại danh sách
        </button>
      </div>
      <div className="flex-1 min-h-0">
        <DocumentViewerClient
          markdown={markdown}
          highlight={highlight}
          docId={docId}
        />
      </div>
    </div>
  );
}
