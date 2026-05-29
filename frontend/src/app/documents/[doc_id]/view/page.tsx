"use client";

import { useEffect, useState } from "react";
import { useParams, useSearchParams, useRouter } from "next/navigation";
import DocumentViewerClient, { ViewMode } from "./viewer-client";
import { API, getToken } from "@/lib/auth";
import { ArrowLeft, FileText, Eye } from "lucide-react";

export default function DocumentViewPage() {
  const params = useParams<{ doc_id: string }>();
  const searchParams = useSearchParams();
  const router = useRouter();
  const docId = params.doc_id;
  const highlight = searchParams.get("highlight") ?? "";

  const [markdown, setMarkdown] = useState<string | null>(null);
  const [error, setError] = useState(false);
  const [viewMode, setViewMode] = useState<ViewMode>("md");

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
      <main className="min-h-[calc(100vh-64px)] flex flex-col items-center justify-center p-6">
        <div className="glass-panel p-8 rounded-3xl text-center max-w-sm w-full">
          <div className="p-4 bg-rose-500/10 text-rose-500 rounded-full mb-4 inline-block">
            <svg className="w-10 h-10" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <p className="text-primary text-lg font-bold mb-4">
            Không thể tải tài liệu
          </p>
          <button
            onClick={() => router.push("/files")}
            className="w-full px-5 py-2.5 rounded-xl border border-theme bg-secondary hover:bg-tertiary hover:border-theme-accent text-secondary font-bold hover:-translate-y-0.5 active:scale-95 transition-all text-sm cursor-pointer"
          >
            Quay lại danh sách
          </button>
        </div>
      </main>
    );
  }

  if (markdown === null) {
    return (
      <main className="min-h-[calc(100vh-64px)] flex items-center justify-center p-6">
        <div className="glass-panel p-8 rounded-3xl max-w-sm w-full text-center">
          <div className="animate-spin h-8 w-8 border-4 border-indigo-600 border-t-transparent rounded-full mb-3 mx-auto" />
          <p className="text-slate-400 font-medium text-sm">Đang tải tài liệu…</p>
        </div>
      </main>
    );
  }

  return (
    <div className="flex flex-col bg-transparent" style={{ height: 'calc(100dvh - 7rem)' }}>
      <div className="sticky top-0 z-20 flex items-center gap-2 px-5 py-3 bg-tertiary/80 backdrop-blur-md border-b border-theme">
        <button
          onClick={() => router.push("/files")}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-theme bg-secondary hover:bg-tertiary hover:border-theme-accent text-secondary hover:text-primary transition-all text-xs font-bold cursor-pointer"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          Quay lại
        </button>
        <div className="ml-auto flex items-center gap-1.5">
          <button
            onClick={() => setViewMode("md")}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-bold transition-all cursor-pointer ${
              viewMode === "md"
                ? "bg-gradient-to-r from-indigo-500 to-violet-600 text-white shadow-sm shadow-indigo-500/20"
                : "border border-theme bg-secondary text-secondary hover:bg-tertiary hover:border-theme-accent"
            }`}
          >
            <FileText className="w-3.5 h-3.5" />
            Xem Markdown
          </button>
          <button
            onClick={() => setViewMode("raw")}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-bold transition-all cursor-pointer ${
              viewMode === "raw"
                ? "bg-gradient-to-r from-indigo-500 to-violet-600 text-white shadow-sm shadow-indigo-500/20"
                : "border border-theme bg-secondary text-secondary hover:bg-tertiary hover:border-theme-accent"
            }`}
          >
            <Eye className="w-3.5 h-3.5" />
            Xem file gốc
          </button>
        </div>
      </div>
      <div className="flex-1 min-h-0 flex flex-col">
        <DocumentViewerClient
          markdown={markdown}
          highlight={highlight}
          docId={docId}
          viewMode={viewMode}
          onViewModeChange={setViewMode}
        />
      </div>
    </div>
  );
}
