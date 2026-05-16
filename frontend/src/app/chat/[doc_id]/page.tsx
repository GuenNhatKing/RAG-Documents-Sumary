"use client";

import { use, useRef, useState } from "react";
import axios from "axios";
import { ArrowLeftRightIcon, RefreshCcwIcon } from "lucide-react";

// Color palette (Tailwind config names)
const COLORS = {
  bgBase: "bg-bg-base",
  textMain: "text-text-main",
  primary: "bg-primary text-white",
  accent: "bg-accent text-white",
};

type Message = {
  role: "user" | "assistant";
  content: string;
};

type SourceTag = {
  file: string;
  lines: string;
};

type PageProps = {
  params: Promise<{
    doc_id: string;
  }>;
};

export default function ChatPage({ params }: PageProps) {
  const { doc_id } = use(params);

  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>("");
  const [sources, setSources] = useState<SourceTag[]>([]);

  const pdfRef = useRef<HTMLIFrameElement>(null);

  const sendQuestion = async () => {
    if (!question.trim()) return;

    const userMsg: Message = {
      role: "user",
      content: question,
    };

    setMessages((prev) => [...prev, userMsg]);

    setLoading(true);
    setError("");

    try {
      const res = await axios.post("/chat/ask", {
        doc_id,
        question,
      });

      const answer: string = res.data.result.answer;
      const srcs: SourceTag[] = res.data.result.sources;

      const assistantMsg: Message = {
        role: "assistant",
        content: answer,
      };

      setMessages((prev) => [...prev, assistantMsg]);
      setSources(srcs);
    } catch (e: any) {
      console.error(e);

      setError(
        e?.response?.data?.detail || "Chat request failed"
      );
    } finally {
      setLoading(false);
      setQuestion("");
    }
  };

  // Highlight source in viewer
  const handleSourceClick = (tag: SourceTag) => {
    if (!pdfRef.current) return;

    const anchor = `#line-${tag.lines}`;

    pdfRef.current.contentWindow?.location.replace(anchor);

    pdfRef.current.contentWindow?.scrollTo({
      top: 0,
      behavior: "smooth",
    });
  };

  const onKeyPress = (
    e: React.KeyboardEvent<HTMLTextAreaElement>
  ) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendQuestion();
    }
  };

  return (
    <div className={`${COLORS.bgBase} min-h-screen flex`}>
      {/* Left panel – document viewer */}
      <div
        className="w-1/2 border-r border-gray-300 overflow-auto"
        style={{ backgroundColor: "#fff" }}
      >
        <iframe
          ref={pdfRef}
          src={`/documents/${doc_id}/view`}
          className="w-full h-full"
          title="Document viewer"
        />
      </div>

      {/* Right panel – chat */}
      <div className="w-1/2 flex flex-col p-4">
        <h2
          className={`${COLORS.textMain} text-2xl font-semibold mb-4`}
        >
          Chat with Document
        </h2>

        <div className="flex-1 overflow-y-auto mb-4 space-y-3">
          {messages.map((msg, idx) => (
            <div
              key={idx}
              className={`p-3 rounded ${
                msg.role === "assistant"
                  ? "bg-gray-100"
                  : "bg-primary text-white"
              }`}
            >
              <p>{msg.content}</p>
            </div>
          ))}

          {loading && (
            <div className="flex items-center space-x-2 text-primary">
              <svg
                className="animate-spin h-5 w-5"
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />

                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8v8H4z"
                />
              </svg>

              <span>Thinking…</span>
            </div>
          )}

          {error && (
            <p className="text-red-600">
              {error}
            </p>
          )}
        </div>

        {/* Sources */}
        {sources.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-2">
            {sources.map((s, i) => (
              <button
                key={i}
                onClick={() => handleSourceClick(s)}
                className={`${COLORS.accent} py-1 px-2 rounded text-sm cursor-pointer`}
              >
                {s.file} – Dòng {s.lines}
              </button>
            ))}
          </div>
        )}

        {/* Input */}
        <div className="flex gap-2">
          <textarea
            value={question}
            onChange={(e) =>
              setQuestion(e.target.value)
            }
            onKeyDown={onKeyPress}
            rows={2}
            className="flex-1 border border-gray-300 rounded p-2 focus:outline-none focus:border-primary"
            placeholder="Nhập câu hỏi..."
          />

          <button
            onClick={sendQuestion}
            disabled={loading}
            className={`${COLORS.primary} py-2 px-4 rounded disabled:opacity-50`}
          >
            Gửi
          </button>
        </div>
      </div>
    </div>
  );
}