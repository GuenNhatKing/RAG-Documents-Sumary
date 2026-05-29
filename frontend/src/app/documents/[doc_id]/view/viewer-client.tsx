"use client";

import { useState, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { API, getToken } from "@/lib/auth";

type Props = {
  markdown: string;
  highlight: string;
  docId?: string;
};

type ViewMode = "md" | "raw";

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
}: Props) {
  const [viewMode, setViewMode] = useState<ViewMode>("md");
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [pdfError, setPdfError] = useState("");
  const highlightedLines = parseLineRange(highlight);

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
    } catch (err) {
      console.error("Failed to load PDF:", err);
      setPdfError("Không thể tải file PDF.");
    } finally {
      setPdfLoading(false);
    }
  };

  const handleSwitchToRaw = () => {
    setViewMode("raw");
    loadPdf();
  };

  const lines = (markdown ?? "").split("\n");

  return (
    <div className="flex flex-col h-full bg-[#1e1e2d] text-slate-200">
      {/* Content area */}
      <div className="flex-1 overflow-auto">
        {viewMode === "md" ? (
          <main className="bg-[#1e1e2d] px-10 py-8 text-slate-350">
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
                            <h1 className="mt-8 mb-5 text-3xl font-bold text-slate-100">
                              {children}
                            </h1>
                          ),
                          h2: ({ children }) => (
                            <h2 className="mt-7 mb-4 text-2xl font-bold text-slate-200">
                              {children}
                            </h2>
                          ),
                          h3: ({ children }) => (
                            <h3 className="mt-8 mb-3 text-xl font-bold text-slate-200">
                              {children}
                            </h3>
                          ),
                          h4: ({ children }) => (
                            <h4 className="mt-4 mb-2 rounded-md border-l-4 border-indigo-500 bg-indigo-500/10 px-3 py-2 text-base font-semibold text-indigo-200">
                              {children}
                            </h4>
                          ),
                          p: ({ children }) => (
                            <p className="my-2 text-slate-300">
                              {children}
                            </p>
                          ),
                          strong: ({ children }) => (
                            <strong className="font-semibold text-slate-100">
                              {children}
                            </strong>
                          ),
                          table: ({ children }) => (
                            <table className="my-4 w-full border-collapse text-sm border border-white/10">
                              {children}
                            </table>
                          ),
                          th: ({ children }) => (
                            <th className="border border-white/10 bg-[#27273a] px-3 py-2 text-left font-semibold text-slate-200">
                              {children}
                            </th>
                          ),
                          td: ({ children }) => (
                            <td className="border border-white/10 px-3 py-2 text-slate-300">
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
        ) : pdfLoading ? (
          <div className="flex items-center justify-center h-full">
            <div className="animate-spin h-8 w-8 border-4 border-indigo-500 border-t-transparent rounded-full" />
          </div>
        ) : pdfError ? (
          <div className="flex items-center justify-center h-full">
            <p className="text-rose-500 font-bold text-xs">{pdfError}</p>
          </div>
        ) : pdfUrl ? (
          <object
            data={pdfUrl}
            type="application/pdf"
            className="w-full h-full"
          >
            <div className="flex flex-col items-center justify-center h-full gap-3">
              <p className="text-slate-400 font-bold text-xs">Trình duyệt không hỗ trợ xem PDF trực tiếp.</p>
              <a
                href={pdfUrl}
                download
                className="px-4 py-2 bg-indigo-650 text-white rounded-xl hover:bg-indigo-550 text-xs font-bold transition-all"
              >
                Tải file PDF
              </a>
            </div>
          </object>
        ) : null}
      </div>

      {/* Toggle buttons */}
      {docId && (
        <div className="flex-shrink-0 flex items-center justify-center gap-2 py-3 px-4 bg-[#27273a]/60 backdrop-blur-md border-t border-white/10">
          <button
            onClick={() => setViewMode("md")}
            className={`inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-bold transition-all cursor-pointer ${
              viewMode === "md"
                ? "bg-gradient-to-r from-[#4f46e5] to-[#a855f7] text-white shadow-md shadow-indigo-500/10"
                : "bg-white/5 text-slate-300 border border-white/10 hover:bg-white/10"
            }`}
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            Xem Markdown
          </button>
          <button
            onClick={handleSwitchToRaw}
            className={`inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-bold transition-all cursor-pointer ${
              viewMode === "raw"
                ? "bg-gradient-to-r from-[#4f46e5] to-[#a855f7] text-white shadow-md shadow-indigo-500/10"
                : "bg-white/5 text-slate-300 border border-white/10 hover:bg-white/10"
            }`}
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
            </svg>
            Xem file gốc
          </button>
        </div>
      )}
    </div>
  );
}
