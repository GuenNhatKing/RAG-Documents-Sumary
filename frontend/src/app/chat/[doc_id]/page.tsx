"use client";

import { use, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import ProtectedRoute from "@/components/ProtectedRoute";
import SessionList from "@/components/SessionList";
import DocumentViewerClient from "@/app/documents/[doc_id]/view/viewer-client";
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
  Plus
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
      long: "Chi tiết",
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
        {/* Session List Panel */}
        {showSessions && (
          <div className="w-64 flex-shrink-0 bg-[#1a1f2e]/60 backdrop-blur-md border-r border-white/[0.06] h-full overflow-hidden flex flex-col">
            <SessionList
              docId={doc_id}
              currentSessionId={sessionId}
              onSelect={handleSelectSession}
              onNewSession={handleNewSession}
            />
          </div>
        )}

        {/* Document Viewer Panel */}
        <div className="flex-1 flex flex-col border-r border-white/[0.06] min-w-0 bg-[#1a1f2e]/20 h-full overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 bg-[#1a1f2e]/60 backdrop-blur-md border-b border-white/[0.06]">
            <div className="flex items-center gap-2">
              <button
                onClick={() => setShowSessions(!showSessions)}
                className="p-1.5 rounded-lg hover:bg-white/[0.06] text-slate-400 hover:text-indigo-400 transition-colors cursor-pointer"
                title={showSessions ? "Ẩn danh sách phiên" : "Hiện danh sách phiên"}
              >
                {showSessions ? <ChevronLeft className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
              </button>
              <div className="flex items-center gap-1.5 px-3 py-1 rounded-lg bg-[#222840] border border-white/[0.06] text-[10px] font-medium text-slate-400 select-none">
                <FileText className="w-3.5 h-3.5 text-indigo-400" />
                <span>Nội dung tài liệu</span>
              </div>
            </div>
            <h1 className="text-sm font-medium text-slate-200 truncate max-w-xs md:max-w-md" title={docFilename}>
              {docFilename}
            </h1>
          </div>

          <div className="flex-1 overflow-hidden">
            {docLoading ? (
              <div className="flex items-center justify-center h-full">
                <Loader2 className="animate-spin h-8 w-8 text-indigo-400" />
              </div>
            ) : (
              <DocumentViewerClient markdown={markdown} highlight={highlight} docId={doc_id} />
            )}
          </div>
        </div>

        {/* Chat Panel */}
        <div className="w-[420px] flex-shrink-0 flex flex-col bg-[#1a1f2e]/80 backdrop-blur-md h-full overflow-hidden">
          {/* Header */}
          <div className="px-5 py-4 border-b border-white/[0.06] flex items-center gap-3 select-none">
            <div className="w-9 h-9 rounded-xl bg-indigo-500/10 text-indigo-400 flex items-center justify-center">
              <MessageSquare className="w-4 h-4" />
            </div>
            <div className="flex-1">
              <h2 className="text-sm font-semibold text-slate-200 leading-tight">
                {sessionId ? "Cuộc trò chuyện" : "Trò chuyện mới"}
              </h2>
              <p className="text-[11px] text-slate-500 mt-0.5">
                Truy vấn AI về nội dung tài liệu
              </p>
            </div>
            {sessionId && (
              <button
                onClick={handleNewSession}
                className="p-2 rounded-lg hover:bg-white/[0.06] text-slate-400 hover:text-indigo-400 transition-colors cursor-pointer"
                title="Tạo phiên mới"
              >
                <Plus className="w-4 h-4" />
              </button>
            )}
          </div>

          {/* Messages stream */}
          <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
            {messages.length === 0 && !loading && (
              <div className="flex flex-col items-center justify-center h-full text-center px-6">
                <div className="w-12 h-12 rounded-2xl bg-indigo-500/10 text-indigo-400 flex items-center justify-center mb-4">
                  <Sparkles className="w-5 h-5" />
                </div>
                <h3 className="text-sm font-semibold text-slate-300">Hỏi đáp tài liệu thông minh</h3>
                <p className="text-xs text-slate-500 mt-1.5 max-w-[240px] leading-relaxed">
                  Nhập câu hỏi hoặc chọn <strong className="text-indigo-400">Tóm tắt văn bản</strong> để bắt đầu.
                </p>
              </div>
            )}

            {messages.map((msg, idx) => (
              <div
                key={idx}
                className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div className={`flex gap-2.5 max-w-[90%] ${msg.role === "user" ? "flex-row-reverse" : ""}`}>
                  <div className={`w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 mt-1 ${
                    msg.role === "user"
                      ? "bg-gradient-to-br from-indigo-500 to-blue-500 text-white shadow-md"
                      : "bg-gradient-to-br from-slate-500 to-slate-600 text-white shadow-md"
                  }`}>
                    {msg.role === "user" ? <User className="w-3.5 h-3.5" /> : <Bot className="w-3.5 h-3.5" />}
                  </div>
                  <div
                    className={`rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
                      msg.role === "user"
                        ? "bg-gradient-to-br from-indigo-500 to-blue-500 text-white rounded-tr-sm shadow-lg shadow-indigo-500/15"
                        : "bg-gradient-to-br from-[#1e243a] to-[#1a2038] border border-white/[0.06] text-slate-200 rounded-tl-sm"
                    }`}
                  >
                    {msg.role === "assistant" ? (
                      <div className="prose prose-sm prose-invert max-w-none prose-p:my-1 prose-headings:my-2 prose-ul:my-1 prose-ol:my-1 leading-relaxed text-slate-300">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                          {msg.content}
                        </ReactMarkdown>
                      </div>
                    ) : (
                      <p className="whitespace-pre-wrap">{msg.content}</p>
                    )}

                    {msg.sources && msg.sources.length > 0 && (
                      <div className="mt-3 pt-2.5 border-t border-white/[0.06]">
                        <div className="flex items-center gap-1.5 text-[10px] font-medium text-slate-500 mb-2">
                          <BookOpen className="w-3 h-3 text-indigo-400" />
                          <span>Nguồn tham chiếu:</span>
                        </div>
                        <div className="flex flex-wrap gap-1">
                          {msg.sources.map((src, sIdx) => (
                            <button
                              key={sIdx}
                              onClick={() => handleSourceClick(src)}
                              className={`inline-block text-[10px] rounded-lg px-2.5 py-1 transition-all cursor-pointer border ${
                                highlight === src.lines
                                  ? "bg-yellow-500/15 border-yellow-500/30 text-yellow-400"
                                  : "bg-white/[0.04] border-white/[0.06] text-slate-500 hover:text-indigo-400 hover:border-indigo-500/30"
                              }`}
                              title={`Highlight dòng ${src.lines}`}
                            >
                              {src.file.replace(/\.md$/i, "").replace(doc_id, docFilename)}:{src.lines}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))}

            {loading && (
              <div className="flex justify-start">
                <div className="flex gap-2.5">
                  <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-slate-500 to-slate-600 text-white shadow-md flex items-center justify-center flex-shrink-0 mt-1">
                    <Bot className="w-3.5 h-3.5" />
                  </div>
                  <div className="bg-gradient-to-br from-[#1e243a] to-[#1a2038] border border-white/[0.06] rounded-2xl rounded-tl-sm px-4 py-3">
                    <div className="flex items-center gap-1.5">
                      <div className="w-2 h-2 bg-indigo-400 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                      <div className="w-2 h-2 bg-indigo-400 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                      <div className="w-2 h-2 bg-indigo-400 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
                    </div>
                  </div>
                </div>
              </div>
            )}

            {error && (
              <div className="bg-red-500/10 border border-red-500/20 text-red-400 text-xs rounded-xl px-4 py-3 flex items-center gap-2">
                <span>{error}</span>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Action Input Bar */}
          <div className="p-4 border-t border-white/[0.06]">
            <div className="flex items-center gap-2 bg-[#222840] border border-white/[0.06] rounded-xl px-3 py-1.5 focus-within:border-indigo-500/40 transition-all">
              <input
                ref={inputRef}
                type="text"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Nhập câu hỏi tại đây..."
                className="flex-1 bg-transparent text-sm text-slate-200 placeholder-slate-500 outline-none py-1.5"
                disabled={loading}
              />
              <button
                onClick={sendQuestion}
                disabled={loading || !question.trim()}
                className="p-2 rounded-lg bg-indigo-500 hover:bg-indigo-400 text-white transition-all disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer flex items-center justify-center"
              >
                <Send className="w-3.5 h-3.5" />
              </button>

              {/* Summarize button */}
              <div className="relative">
                <button
                  onClick={(e) => { e.stopPropagation(); setShowSummaryMenu(!showSummaryMenu); }}
                  disabled={loading}
                  className="p-2 rounded-lg bg-violet-500/15 hover:bg-violet-500/25 text-violet-400 transition-all disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer flex items-center justify-center"
                  title="Tóm tắt văn bản"
                >
                  <Sparkles className="w-3.5 h-3.5" />
                </button>
                {showSummaryMenu && (
                  <div onClick={(e) => e.stopPropagation()} className="absolute bottom-full right-0 mb-2 w-48 rounded-xl border border-white/[0.06] bg-[#222840] shadow-xl py-1 z-50 overflow-hidden">
                    <div className="px-4 py-1.5 text-[9px] font-medium text-slate-500 border-b border-white/[0.04] uppercase tracking-widest">
                      Độ dài tóm tắt
                    </div>
                    {SUMMARY_LENGTH_OPTIONS.map((opt) => (
                      <button
                        key={opt.value}
                        onClick={() => handleSummarize(opt.value)}
                        className="w-full text-left px-4 py-2 text-xs text-slate-400 hover:bg-violet-500/10 hover:text-violet-400 transition-colors cursor-pointer"
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </ProtectedRoute>
  );
}
