"use client";

import { useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

type Props = {
  markdown: string;
  highlight: string;
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
}: Props) {
  const highlightedLines = parseLineRange(highlight);

  useEffect(() => {
    if (!highlight) return;

    const firstLine = highlight.split(",")[0].split("-")[0];
    const el = document.getElementById(`line-${firstLine}`);

    el?.scrollIntoView({
      behavior: "smooth",
      block: "center",
    });
  }, [highlight]);

  const lines = markdown.split("\n");

  return (
    <main className="bg-white px-10 py-8 text-slate-800">
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
                  ? "bg-yellow-100 border-l-4 border-yellow-500"
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
                      <h1 className="mt-8 mb-5 text-3xl font-bold text-slate-950">
                        {children}
                      </h1>
                    ),
                    h2: ({ children }) => (
                      <h2 className="mt-7 mb-4 text-2xl font-bold text-slate-900">
                        {children}
                      </h2>
                    ),
                    h3: ({ children }) => (
                      <h3 className="mt-8 mb-3 text-xl font-bold text-slate-900">
                        {children}
                      </h3>
                    ),
                    h4: ({ children }) => (
                      <h4 className="mt-4 mb-2 rounded-md border-l-4 border-emerald-500 bg-emerald-50 px-3 py-2 text-base font-semibold text-emerald-900">
                        {children}
                      </h4>
                    ),
                    p: ({ children }) => (
                      <p className="my-2 text-slate-700">
                        {children}
                      </p>
                    ),
                    strong: ({ children }) => (
                      <strong className="font-semibold text-slate-900">
                        {children}
                      </strong>
                    ),
                    table: ({ children }) => (
                      <table className="my-4 w-full border-collapse text-sm">
                        {children}
                      </table>
                    ),
                    th: ({ children }) => (
                      <th className="border bg-slate-100 px-3 py-2 text-left font-semibold">
                        {children}
                      </th>
                    ),
                    td: ({ children }) => (
                      <td className="border px-3 py-2">
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
  );
}