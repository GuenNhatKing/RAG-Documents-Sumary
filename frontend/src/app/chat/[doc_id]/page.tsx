"use client";

import { use, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import ProtectedRoute from "@/components/ProtectedRoute";
import SessionList from "@/components/SessionList";
import DocumentViewerClient from "@/app/documents/[doc_id]/view/viewer-client";
import { ChatMessage, getMessages, askQuestion } from "@/lib/chat";
import { API } from "@/lib/auth";

type SourceTag = {
  file: string;
  lines: string;
};

type Message = {
  role: "user" | "assistant";
  content: string;
  sources?: SourceTag[];
};

type PageProps = {
  params: Promise<{
    doc_id: string;
  }>;
};

export default function ChatPage({ params }: PageProps) {
  const { doc_id } = use(params);
  const searchParams = useSearchParams();
  const initialSessionId = searchParams.get("session") || undefined;

  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [sessionId, setSessionId] = useState<string | undefined>(initialSessionId);
  const [showSessions, setShowSessions] = useState(true);
  const [highlight, setHighlight] = useState("");
  const [markdown, setMarkdown] = useState<string>("");
  const [docLoading, setDocLoading] = useState(true);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setDocLoading(true);
    fetch(`${API}/documents/${doc_id}/markdown`)
      .then((r) => r.json())
      .then((data) => setMarkdown(data.markdown))
      .catch(() => setMarkdown("# Không thể tải tài liệu"))
      .finally(() => setDocLoading(false));
  }, [doc_id]);

  useEffect(() => {
    if (initialSessionId) {
      loadSession(initialSessionId);
    }
  }, [initialSessionId]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const loadSession = useCallback(async (sid: string) => {
    setSessionId(sid);
    setError("");
    try {
      const dbMessages: ChatMessage[] = await getMessages(sid);
      const converted: Message[] = dbMessages.map((m) => ({
        role: m.role as "user" | "assistant",
        content: m.content,
        sources: m.sources ? JSON.parse(m.sources) : undefined,
      }));
      setMessages(converted);
    } catch (err) {
      console.error("Failed to load messages:", err);
      setError("Không thể tải tin nhắn.");
    }
  }, []);

  const handleNewSession = useCallback(() => {
    setSessionId(undefined);
    setMessages([]);
    setError("");
  }, []);

  const handleSelectSession = useCallback(
    (sid: string) => {
      loadSession(sid);
    },
    [loadSession]
  );

  const sendQuestion = async () => {
    if (!question.trim() || loading) return;

    const userMsg: Message = { role: "user", content: question };
    setMessages((prev) => [...prev, userMsg]);
    setQuestion("");
    setLoading(true);
    setError("");

    try {
      const data = await askQuestion(doc_id, question, sessionId);

      const cleanAnswer = data.answer
        .replace(/\s*\[Nguồn:\s*.*?,\s*Dòng:\s*.*?\]\.?/g, "")
        .trim();

      const assistantMsg: Message = {
        role: "assistant",
        content: cleanAnswer,
        sources: data.sources,
      };
      setMessages((prev) => [...prev, assistantMsg]);

      if (data.sources && data.sources.length > 0) {
        setHighlight(data.sources[0].lines);
      }
    } catch (err) {
      setError("Đã xảy ra lỗi khi gửi câu hỏi.");
      console.error(err);
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendQuestion();
    }
  };

  const handleSourceClick = (src: SourceTag) => {
    setHighlight(src.lines);
  };

  return (
    <ProtectedRoute>
      <div className="flex h-[calc(100vh-64px)] bg-gray-50 -m-4">
        {/* Session List Panel */}
        {showSessions && (
          <div className="w-64 flex-shrink-0 bg-white border-r border-gray-200">
            <SessionList
              docId={doc_id}
              currentSessionId={sessionId}
              onSelect={handleSelectSession}
              onNewSession={handleNewSession}
            />
          </div>
        )}

        {/* Document Viewer Panel */}
        <div className="flex-1 flex flex-col border-r border-gray-200 min-w-0">
          <div className="flex items-center justify-between px-3 py-2 bg-white border-b border-gray-200">
            <button
              onClick={() => setShowSessions(!showSessions)}
              className="p-1 rounded hover:bg-gray-100 text-gray-500"
              title={showSessions ? "Ẩn phiên" : "Hiện phiên"}
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h7" />
              </svg>
            </button>
            <span className="text-sm text-gray-500">Tài liệu</span>
            <div className="w-8" />
          </div>
          <div className="flex-1 overflow-auto">
            {docLoading ? (
              <div className="flex items-center justify-center h-full">
                <div className="animate-spin h-8 w-8 border-4 border-primary border-t-transparent rounded-full" />
              </div>
            ) : (
              <DocumentViewerClient markdown={markdown} highlight={highlight} />
            )}
          </div>
        </div>

        {/* Chat Panel */}
        <div className="w-[480px] flex-shrink-0 flex flex-col bg-white">
          <div className="px-4 py-3 border-b border-gray-200">
            <h2 className="text-sm font-semibold text-gray-700">
              {sessionId ? "Cuộc trò chuyện" : "Trò chuyện mới"}
            </h2>
          </div>

          <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
            {messages.length === 0 && !loading && (
              <div className="flex flex-col items-center justify-center h-full text-center">
                <div className="text-gray-300 mb-3">
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-12 w-12" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                  </svg>
                </div>
                <p className="text-sm text-gray-400">
                  Đặt câu hỏi về tài liệu này
                </p>
              </div>
            )}

            {messages.map((msg, idx) => (
              <div
                key={idx}
                className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`
                    max-w-[85%] rounded-lg px-3 py-2
                    ${msg.role === "user"
                      ? "bg-blue-600 text-white"
                      : "bg-gray-100 text-gray-800"
                    }
                  `}
                >
                  {msg.role === "assistant" ? (
                    <div className="prose prose-sm max-w-none prose-p:my-1 prose-headings:my-2 prose-ul:my-1 prose-ol:my-1">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {msg.content}
                      </ReactMarkdown>
                    </div>
                  ) : (
                    <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                  )}

                  {msg.sources && msg.sources.length > 0 && (
                    <div className="mt-2 pt-2 border-t border-gray-200/50">
                      <p className="text-xs font-medium text-gray-500 mb-1">Nguồn:</p>
                      <div className="flex flex-wrap gap-1">
                        {msg.sources.map((src, sIdx) => (
                          <button
                            key={sIdx}
                            onClick={() => handleSourceClick(src)}
                            className={`inline-block text-xs rounded px-1.5 py-0.5 transition-colors cursor-pointer ${
                              highlight === src.lines
                                ? "bg-yellow-200 text-yellow-800 font-medium"
                                : msg.role === "user"
                                  ? "bg-white/20 hover:bg-white/30 text-white"
                                  : "bg-white hover:bg-blue-50 text-gray-600 hover:text-blue-600"
                            }`}
                            title={`Highlight dòng ${src.lines} trong tài liệu`}
                          >
                            {src.file}:{src.lines}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            ))}

            {loading && (
              <div className="flex justify-start">
                <div className="bg-gray-100 rounded-lg px-3 py-2">
                  <div className="flex items-center space-x-1.5">
                    <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                    <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                    <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
                  </div>
                </div>
              </div>
            )}

            {error && (
              <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg px-3 py-2">
                {error}
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          <div className="px-4 py-3 border-t border-gray-200">
            <div className="flex items-center space-x-2">
              <input
                ref={inputRef}
                type="text"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Đặt câu hỏi..."
                className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                disabled={loading}
              />
              <button
                onClick={sendQuestion}
                disabled={loading || !question.trim()}
                className="p-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      </div>
    </ProtectedRoute>
  );
}
