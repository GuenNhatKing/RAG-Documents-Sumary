"use client";

import { use, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import ProtectedRoute from "@/components/ProtectedRoute";
import SessionList from "@/components/SessionList";
import DocumentViewerClient, { ViewMode } from "@/app/documents/[doc_id]/view/viewer-client";
import {
  Send,
  FileText,
  MessageSquare,
  Sparkles,
  ChevronLeft,
  ChevronRight,
  BookOpen,
  Loader2,
  Bot,
  User,
  Plus,
  Eye,
  Menu
} from "lucide-react";
import { ChatMessage, getMessages, askQuestion, summarizeDocument, SummaryLength, SUMMARY_LENGTH_OPTIONS } from "@/lib/chat";
import { API, getToken } from "@/lib/auth";
import { getDocumentDetail } from "@/lib/documents";

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
  const [docFilename, setDocFilename] = useState(doc_id);
  const [showSummaryMenu, setShowSummaryMenu] = useState(false);
  const [viewMode, setViewMode] = useState<ViewMode>("md");

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setDocLoading(true);
    const token = getToken();
    const headers: Record<string, string> = token
      ? { Authorization: `Bearer ${token}` }
      : {};
    fetch(`${API}/documents/${doc_id}/markdown`, { headers })
      .then((r) => r.json())
      .then((data) => setMarkdown(data.markdown ?? "# Không thể tải tài liệu"))
      .catch(() => setMarkdown("# Không thể tải tài liệu"))
      .finally(() => setDocLoading(false));
    getDocumentDetail(doc_id).then((doc) => {
      if (doc) setDocFilename(doc.filename);
    });
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

  useEffect(() => {
    if (!showSummaryMenu) return;
    const handleClickOutside = () => setShowSummaryMenu(false);
    document.addEventListener("click", handleClickOutside);
    return () => document.removeEventListener("click", handleClickOutside);
  }, [showSummaryMenu]);

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

  const handleSummarize = async (length: SummaryLength) => {
    if (loading) return;
    setShowSummaryMenu(false);

    const lengthLabels: Record<SummaryLength, string> = {
      short: "Ngắn (chỉ ý quan trọng)",
      medium: "Vừa",
      long: "Chi tiết (Dài)",
    };

    const userMsg: Message = {
      role: "user",
      content: `[Tóm tắt văn bản - Độ dài: ${lengthLabels[length]}]`,
    };
    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);
    setError("");

    try {
      const data = await summarizeDocument(doc_id, length, sessionId);
      const assistantMsg: Message = {
        role: "assistant",
        content: data.answer,
        sources: data.sources.length > 0 ? data.sources : undefined,
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <ProtectedRoute>
      <div className="flex h-full w-full overflow-hidden">
        {/* Session List Sidebar */}
        {showSessions && (
          <div className="w-64 flex-shrink-0 glass-panel border-r border-theme-light h-full overflow-hidden flex flex-col z-20">
            <SessionList
              docId={doc_id}
              currentSessionId={sessionId}
              onSelect={handleSelectSession}
              onNewSession={handleNewSession}
            />
          </div>
        )}

        {/* Document Viewer */}
        <div className="flex-1 flex flex-col border-r border-theme-light min-w-0 bg-tertiary h-full overflow-hidden">
          <header className="h-14 flex items-center justify-between px-4 border-b border-theme-light bg-tertiary">
            <div className="flex items-center gap-2">
              <button
                onClick={() => setShowSessions(!showSessions)}
                className="p-1.5 rounded-lg text-muted hover:text-emerald-400 dark:hover:text-indigo-400 hover:bg-tertiary transition-colors cursor-pointer"
              >
                {showSessions ? <ChevronLeft className="w-4 h-4" /> : <Menu className="w-4 h-4" />}
              </button>
              <div className="flex items-center gap-1.5 text-xs font-medium text-muted">
                <FileText className="w-4 h-4 text-emerald-400 dark:text-indigo-400" />
                <span className="hidden sm:inline">{docFilename}</span>
                <span className="sm:hidden">Tài liệu</span>
              </div>
            </div>
            <div className="flex items-center gap-1.5">
              <button
                onClick={() => setViewMode("md")}
                className={`inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                  viewMode === "md"
                    ? "bg-gradient-to-r from-emerald-500 dark:from-indigo-500 to-emerald-600 dark:to-indigo-600 text-white shadow-sm shadow-emerald-500/20 dark:shadow-indigo-500/20"
                    : "border border-theme bg-secondary text-muted hover:text-secondary hover:bg-tertiary hover:border-theme-accent"
                }`}
              >
                <FileText className="w-3.5 h-3.5" />
                Markdown
              </button>
              <button
                onClick={() => setViewMode("raw")}
                className={`inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                  viewMode === "raw"
                    ? "bg-gradient-to-r from-emerald-500 dark:from-indigo-500 to-emerald-600 dark:to-indigo-600 text-white shadow-sm shadow-emerald-500/20 dark:shadow-indigo-500/20"
                    : "border border-theme bg-secondary text-muted hover:text-secondary hover:bg-tertiary hover:border-theme-accent"
                }`}
              >
                <Eye className="w-3.5 h-3.5" />
                File gốc
              </button>
            </div>
          </header>

          <div className="flex-1 overflow-hidden flex flex-col">
            {docLoading ? (
              <div className="flex items-center justify-center h-full">
                <Loader2 className="animate-spin h-8 w-8 text-emerald-400 dark:text-indigo-400" />
              </div>
            ) : (
              <DocumentViewerClient markdown={markdown} highlight={highlight} docId={doc_id} viewMode={viewMode} onViewModeChange={setViewMode} />
            )}
          </div>
        </div>

        {/* Chat Panel */}
        <div className="w-[420px] flex-shrink-0 flex flex-col glass-panel h-full overflow-hidden">
          {/* Chat Header */}
          <header className="h-14 flex items-center px-4 border-b border-theme-light bg-tertiary">
            <span className="text-sm font-semibold text-primary">Trợ lý Phân tích AI</span>

          </header>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-4 py-4 space-y-5">
            {messages.length === 0 && !loading && (
              <div className="flex flex-col items-center justify-center h-full text-center px-6">
                <div className="w-12 h-12 rounded-2xl bg-emerald-500/10 dark:bg-indigo-500/10 text-emerald-400 dark:text-indigo-400 flex items-center justify-center mb-4">
                  <Sparkles className="w-5 h-5" />
                </div>
                <h3 className="text-sm font-semibold text-secondary">Trợ lý Phân tích AI</h3>
                <p className="text-xs text-muted mt-1.5 max-w-[240px] leading-relaxed">
                  Đã sẵn sàng phân tích tài liệu. Nhập câu hỏi hoặc để bắt đầu.
                </p>
              </div>
            )}

            {messages.map((msg, idx) => (
              msg.role === "assistant" ? (
                /* AI Message */
                <div key={idx} className="flex flex-col items-start gap-1.5">
                  <div className="flex items-center gap-2">
                    <div className="w-6 h-6 rounded-lg bg-emerald-500/20 dark:bg-indigo-500/20 flex items-center justify-center text-emerald-400 dark:text-indigo-400">
                      <Bot className="w-3.5 h-3.5" />
                    </div>
                    <span className="text-xs font-medium text-emerald-400 dark:text-indigo-400">AI Assistant</span>
                  </div>
                  <div className="max-w-[92%] ai-bubble rounded-2xl rounded-tl-none px-4 py-3 ai-glow border-l-2 border-emerald-500/40 dark:border-indigo-500/40">
                    <div className="prose prose-sm prose-invert max-w-none prose-p:my-1 prose-headings:my-2 prose-ul:my-1 prose-ol:my-1 leading-relaxed text-primary">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {msg.content}
                      </ReactMarkdown>
                    </div>

                    {msg.sources && msg.sources.length > 0 && (
                      <div className="mt-3 pt-2.5 border-t border-theme-light">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <span className="text-[9px] font-medium text-muted mr-1">Tham chiếu:</span>
                          {msg.sources.map((src, sIdx) => (
                            <button
                              key={sIdx}
                              onClick={() => handleSourceClick(src)}
                              className={`text-[9px] px-2.5 py-1 rounded-full border transition-all cursor-pointer ${highlight === src.lines
                                ? "bg-yellow-500/15 border-yellow-500/30 text-yellow-400"
                                : "bg-primary border-theme-light text-muted hover:text-secondary"
                                }`}
                            >
                              {src.file.replace(/\.md$/i, "").replace(doc_id, docFilename)}:{src.lines}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                /* User Message */
                <div key={idx} className="flex flex-col items-end gap-1">
                  <div className="max-w-[85%] user-bubble rounded-2xl rounded-tr-none px-4 py-3 shadow-lg shadow-emerald-500/10 dark:shadow-indigo-500/10">
                    <p className="text-sm text-white whitespace-pre-wrap">{msg.content}</p>
                  </div>
                </div>
              )
            ))}

            {loading && (
              <div className="flex flex-col items-start gap-1.5">
                <div className="flex items-center gap-2">
                  <div className="w-6 h-6 rounded-lg bg-emerald-500/20 dark:bg-indigo-500/20 flex items-center justify-center text-emerald-400 dark:text-indigo-400">
                    <Bot className="w-3.5 h-3.5" />
                  </div>
                  <span className="text-xs font-medium text-emerald-400 dark:text-indigo-400">AI Assistant</span>
                </div>
                <div className="ai-bubble rounded-2xl rounded-tl-none px-4 py-3">
                  <div className="flex items-center gap-1.5">
                    <div className="w-2 h-2 bg-emerald-400 dark:bg-indigo-400 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                    <div className="w-2 h-2 bg-emerald-400 dark:bg-indigo-400 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                    <div className="w-2 h-2 bg-emerald-400 dark:bg-indigo-400 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
                  </div>
                </div>
              </div>
            )}

            {error && (
              <div className="bg-red-500/10 border border-red-500/20 text-red-400 text-xs rounded-xl px-4 py-3">
                {error}
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Chat Input */}
          <div className="px-4 py-3 border-t border-theme-light space-y-2.5">
            <div className="flex items-center gap-2">
              <div className="relative group flex-1">
                <div className="chat-input flex items-center gap-2 px-4 py-1.5">
                  <MessageSquare className="w-4 h-4 text-emerald-400/60 dark:text-indigo-400/60 flex-shrink-0" />
                  <input
                    ref={inputRef}
                    type="text"
                    name="doc_question"
                    value={question}
                    onChange={(e) => setQuestion(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="Đặt câu hỏi về tài liệu..."
                    className="flex-1 bg-transparent text-sm text-primary placeholder-slate-500 outline-none py-1"
                    disabled={loading}
                  />
                </div>
              </div>

              <div className="relative">
                <button
                  onClick={(e) => { e.stopPropagation(); setShowSummaryMenu(!showSummaryMenu); }}
                  disabled={loading}
                  className="flex items-center gap-1.5 px-3 py-1.5 btn-accent-violet rounded-full text-xs font-medium disabled:opacity-40 cursor-pointer whitespace-nowrap hover:scale-110 hover:bg-emerald-600 dark:hover:bg-indigo-500 hover:text-white transition-all duration-200"
                >
                  <Sparkles className="w-3.5 h-3.5" />
                </button>
                {showSummaryMenu && (
                  <div onClick={(e) => e.stopPropagation()} className="absolute bottom-full right-0 mb-2 w-44 glass-panel border border-theme-light rounded-xl overflow-hidden shadow-2xl z-30">
                    {SUMMARY_LENGTH_OPTIONS.map((opt) => (
                      <button
                        key={opt.value}
                        onClick={() => handleSummarize(opt.value)}
                        className="w-full text-left px-4 py-2.5 text-xs text-muted hover:bg-emerald-500/10 dark:hover:bg-indigo-500/10 hover:text-emerald-700 dark:hover:text-indigo-300 hover:scale-[1.02] transition-all duration-200 cursor-pointer"
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>
                )}
              </div>

              <button
                onClick={sendQuestion}
                disabled={loading || !question.trim()}
                className="send-btn"
              >
                <Send className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </ProtectedRoute>
  );
}
