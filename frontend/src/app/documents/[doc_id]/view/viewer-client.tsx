"use client";

import { useState, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { API, getToken } from "@/lib/auth";

export type ViewMode = "md" | "raw";

type Props = {
  markdown: string;
  highlight: string;
  docId?: string;
  viewMode?: ViewMode;
  onViewModeChange?: (mode: ViewMode) => void;
};

function parseLineRange(range: string): Set<number> {
  const result = new Set<number>();

  if (!range) return result;

  for (const part of range.split(",")) {
    const trimmed = part.trim();

    if (trimmed.includes("-")) {
      const [startRaw, endRaw] = trimmed.split("-");
      const start = Number(startRaw);
      const end = Number(endRaw);

      if (!Number.isNaN(start) && !Number.isNaN(end)) {
        for (let i = start; i <= end; i++) {
          result.add(i);
        }
      }
    } else {
      const line = Number(trimmed);

      if (!Number.isNaN(line)) {
        result.add(line);
      }
    }
  }

  return result;
}

export default function DocumentViewerClient({
  markdown,
  highlight,
  docId,
  viewMode: externalViewMode,
  onViewModeChange,
}: Props) {
  const [internalViewMode, setInternalViewMode] = useState<ViewMode>("md");
  const viewMode = externalViewMode ?? internalViewMode;
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [pdfError, setPdfError] = useState("");
  const [pdfLoadedOnce, setPdfLoadedOnce] = useState(false);
  const highlightedLines = parseLineRange(highlight);

  // Auto-load PDF when switching to raw view
  useEffect(() => {
    if (viewMode === "raw" && !pdfLoadedOnce) {
      loadPdf();
    }
  }, [viewMode]);

  // Revoke object URL on unmount
  useEffect(() => {
    return () => {
      if (pdfUrl) URL.revokeObjectURL(pdfUrl);
    };
  }, [pdfUrl]);

  useEffect(() => {
    if (!highlight || viewMode !== "md") return;

    const firstLine = highlight.split(",")[0].split("-")[0];
    const el = document.getElementById(`line-${firstLine}`);

    el?.scrollIntoView({
      behavior: "smooth",
      block: "center",
    });
  }, [highlight, viewMode]);

  const loadPdf = async () => {
    if (pdfUrl) return; // already loaded
    setPdfLoading(true);
    setPdfError("");
    try {
      const token = getToken();
      const headers: Record<string, string> = token
        ? { Authorization: `Bearer ${token}` }
        : {};
      const res = await fetch(`${API}/documents/${docId}/raw`, { headers });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      setPdfUrl(url);
      setPdfLoadedOnce(true);
    } catch (err) {
      console.error("Failed to load PDF:", err);
      setPdfError("Không thể tải file PDF.");
    } finally {
      setPdfLoading(false);
    }
  };

  const lines = (markdown ?? "").split("\n");

  return (
    <div className="flex-1 min-h-0 h-full bg-primary text-primary">
      {viewMode === "md" ? (
        <div className="h-full overflow-auto">
          <main className="bg-primary px-10 py-8 text-secondary">
            <article className="mx-auto max-w-4xl text-[15px] leading-7">
              {lines.map((line, index) => {
                const lineNumber = index + 1;
                const isEmpty = line.trim() === "";

                const isHighlighted =
                  highlightedLines.has(lineNumber) && !isEmpty;

                return (
                  <div
                    key={lineNumber}
                    id={`line-${lineNumber}`}
                    className={`rounded-md px-2 ${
                      isHighlighted
                        ? "bg-yellow-500/10 border-l-4 border-yellow-500 text-yellow-300 font-semibold"
                        : ""
                    }`}
                  >
                    {isEmpty ? (
                      <div className="h-5" />
                    ) : (
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        components={{
                          h1: ({ children }) => (
                            <h1 className="mt-8 mb-5 text-3xl font-bold text-primary">
                              {children}
                            </h1>
                          ),
                          h2: ({ children }) => (
                            <h2 className="mt-7 mb-4 text-2xl font-bold text-primary">
                              {children}
                            </h2>
                          ),
                          h3: ({ children }) => (
                            <h3 className="mt-8 mb-3 text-xl font-bold text-primary">
                              {children}
                            </h3>
                          ),
                          h4: ({ children }) => (
                            <h4 className="mt-4 mb-2 rounded-md border-l-4 border-emerald-500 dark:border-indigo-500 bg-emerald-500/10 dark:bg-indigo-500/10 px-3 py-2 text-base font-semibold text-emerald-700 dark:text-indigo-300">
                              {children}
                            </h4>
                          ),
                          p: ({ children }) => (
                            <p className="my-2 text-secondary">
                              {children}
                            </p>
                          ),
                          strong: ({ children }) => (
                            <strong className="font-semibold text-primary">
                              {children}
                            </strong>
                          ),
                          table: ({ children }) => (
                            <table className="my-4 w-full border-collapse text-sm border border-theme">
                              {children}
                            </table>
                          ),
                          th: ({ children }) => (
                            <th className="border border-theme bg-tertiary px-3 py-2 text-left font-semibold text-primary">
                              {children}
                            </th>
                          ),
                          td: ({ children }) => (
                            <td className="border border-theme px-3 py-2 text-secondary">
                              {children}
                            </td>
                          ),
                        }}
                      >
                        {line}
                      </ReactMarkdown>
                    )}
                  </div>
                );
              })}
            </article>
          </main>
        </div>
      ) : pdfLoading ? (
        <div className="h-full flex items-center justify-center">
          <div className="animate-spin h-8 w-8 border-4 border-emerald-500 dark:border-indigo-500 border-t-transparent rounded-full" />
        </div>
      ) : pdfError ? (
        <div className="h-full flex items-center justify-center">
          <p className="text-rose-500 font-bold text-xs">{pdfError}</p>
        </div>
      ) : pdfUrl ? (
        <object
          data={pdfUrl}
          type="application/pdf"
          className="w-full h-full block"
        >
          <div className="h-full flex flex-col items-center justify-center gap-3">
            <p className="text-muted font-bold text-xs">Trình duyệt không hỗ trợ xem PDF trực tiếp.</p>
            <a
              href={pdfUrl}
              download
              className="px-4 py-2 bg-emerald-600 dark:bg-indigo-600 text-white rounded-xl hover:bg-emerald-700 dark:hover:bg-indigo-700 text-xs font-bold transition-all"
            >
              Tải file PDF
            </a>
          </div>
        </object>
      ) : (
        <div className="h-full flex items-center justify-center">
          <p className="text-muted text-xs">Chọn chế độ xem</p>
        </div>
      )}
    </div>
  );
}
