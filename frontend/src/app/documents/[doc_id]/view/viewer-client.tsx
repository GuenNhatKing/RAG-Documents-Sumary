"use client";

import { useEffect } from "react";
import ReactMarkdown from "react-markdown";

type Props = {
  markdown: string;
  highlight: string;
};

function parseLineRange(range: string): Set<number> {
  const result = new Set<number>();

  if (!range) return result;

  const parts = range.split(",");

  for (const part of parts) {
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

    const firstLine = highlight.split("-")[0];
    const el = document.getElementById(`line-${firstLine}`);

    el?.scrollIntoView({
      behavior: "smooth",
      block: "center",
    });
  }, [highlight]);

  const lines = markdown.split("\n");

  return (
    <main className="min-h-screen bg-white p-8 overflow-auto">
      <article className="prose prose-sm max-w-none">
        {lines.map((line, index) => {
          const lineNumber = index + 1;
          const isHighlighted = highlightedLines.has(lineNumber);

          return (
            <div
              key={lineNumber}
              id={`line-${lineNumber}`}
              className={`rounded px-2 ${
                isHighlighted
                  ? "bg-yellow-200 border-l-4 border-yellow-500"
                  : ""
              }`}
            >
              {line.trim() ? (
                <ReactMarkdown>{line}</ReactMarkdown>
              ) : (
                <div className="h-4" />
              )}
            </div>
          );
        })}
      </article>
    </main>
  );
}