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
  ArrowLeft,
  Loader2,
  AlertCircle
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
    // Fetch real filename
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

  // Close summary menu when clicking outside
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
      <div className="flex h-full w-full bg-transparent overflow-hidden">
        {/* Session List Panel */}
        {showSessions && (
          <div className="w-64 flex-shrink-0 bg-[#27273a]/60 backdrop-blur-md border-r border-white/10 h-full overflow-hidden flex flex-col">
            <SessionList
              docId={doc_id}
              currentSessionId={sessionId}
              onSelect={handleSelectSession}
              onNewSession={handleNewSession}
            />
          </div>
        )}

        {/* Document Viewer Panel */}
        <div className="flex-1 flex flex-col border-r border-white/10 min-w-0 bg-[#1e1e2d]/20 h-full overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 bg-[#27273a]/60 backdrop-blur-md border-b border-white/10">
            <div className="flex items-center gap-2">
              <button
                onClick={() => setShowSessions(!showSessions)}
                className="p-1.5 rounded-xl hover:bg-indigo-500/10 text-slate-350 hover:text-indigo-400 transition-colors cursor-pointer"
                title={showSessions ? "Ẩn danh sách phiên" : "Hiện danh sách phiên"}
              >
                {showSessions ? <ChevronLeft className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
              </button>
              <div className="flex items-center gap-1.5 px-3 py-1 rounded-xl bg-[#27273a] border border-white/10 text-[10px] uppercase font-black tracking-wider text-slate-400 select-none">
                <FileText className="w-3.5 h-3.5 text-indigo-455" />
                <span>Nội dung tài liệu</span>
              </div>
            </div>
            <h1 className="text-xs font-black text-slate-100 truncate max-w-xs md:max-w-md" title={docFilename}>
              {docFilename}
            </h1>
            <div className="w-8" />
          </div>

          <div className="flex-1 overflow-hidden">
            {docLoading ? (
              <div className="flex items-center justify-center h-full">
                <Loader2 className="animate-spin h-8 w-8 text-indigo-500" />
              </div>
            ) : (
              <DocumentViewerClient markdown={markdown} highlight={highlight} docId={doc_id} />
            )}
          </div>
        </div>

        {/* Chat Panel */}
        <div className="w-[450px] flex-shrink-0 flex flex-col bg-[#27273a]/60 backdrop-blur-md h-full overflow-hidden">
          {/* Header */}
          <div className="px-5 py-4 border-b border-white/10 bg-[#1e1e2d]/40 flex items-start gap-3 select-none">
            <div className="w-8 h-8 rounded-xl bg-indigo-500/10 text-indigo-400 flex items-center justify-center">
              <MessageSquare className="w-4.5 h-4.5" />
            </div>
            <div>
              <h2 className="text-sm font-black text-slate-100 leading-tight">
                {sessionId ? "Cuộc trò chuyện" : "Trò chuyện mới"}
              </h2>
              <p className="text-[10px] text-slate-500 mt-0.5 font-bold">
                Truy vấn AI về nội dung tài liệu hiện tại
              </p>
            </div>
          </div>

          {/* Messages stream */}
          <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4 scrollbar-thin scrollbar-thumb-[#27273a]">
            {messages.length === 0 && !loading && (
              <div className="flex flex-col items-center justify-center h-full text-center p-6">
                <div className="w-11 h-11 rounded-2xl bg-indigo-500/10 text-indigo-400 flex items-center justify-center mb-3">
                  <Sparkles className="w-4.5 h-4.5" />
                </div>
                <h3 className="text-[20px] font-bold text-slate-300">Hỏi đáp tài liệu thông minh</h3>
                <p className="text-[12px] text-slate-550 mt-1 max-w-[220px] leading-relaxed">
                  Nhập câu hỏi hoặc chọn chức năng <strong>Tóm tắt văn bản</strong> bên dưới để bắt đầu.
                </p>
              </div>
            )}

            {messages.map((msg, idx) => (
              <div
                key={idx}
                className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[88%] rounded-2xl px-3.5 py-2.5 text-xs transition-all duration-300 leading-relaxed ${msg.role === "user"
                    ? "bg-neon-gradient text-white shadow-md shadow-indigo-500/10 rounded-tr-none font-semibold"
                    : "bg-[#2d2d42] text-slate-100 border border-white/20 shadow-sm rounded-tl-none"
                    }`}
                >
                  {msg.role === "assistant" ? (
                    <div className="prose prose-sm prose-invert max-w-none prose-p:my-1 prose-headings:my-2 prose-ul:my-1 prose-ol:my-1 leading-relaxed font-medium text-[11.5px] text-slate-200">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {msg.content}
                      </ReactMarkdown>
                    </div>
                  ) : (
                    <p className="whitespace-pre-wrap font-bold">{msg.content}</p>
                  )}

                  {msg.sources && msg.sources.length > 0 && (
                    <div className="mt-3 pt-2.5 border-t border-white/5">
                      <div className="flex items-center gap-1 text-[10px] font-extrabold text-slate-450 mb-2">
                        <BookOpen className="w-3.5 h-3.5 text-indigo-400" />
                        <span>Nguồn tham chiếu:</span>
                      </div>
                      <div className="flex flex-wrap gap-1">
                        {msg.sources.map((src, sIdx) => (
                          <button
                            key={sIdx}
                            onClick={() => handleSourceClick(src)}
                            className={`inline-block text-[9px] font-extrabold rounded-lg px-2.5 py-1 transition-all cursor-pointer border ${highlight === src.lines
                              ? "bg-yellow-500/20 border-yellow-500/40 text-yellow-400 font-semibold"
                              : msg.role === "user"
                                ? "bg-white/10 hover:bg-white/20 text-white border-transparent"
                                : "bg-[#1e1e2d] border-white/5 hover:bg-[#1e1e2d]/60 text-slate-400 hover:text-indigo-400"
                              }`}
                            title={`Highlight dòng ${src.lines} trong tài liệu`}
                          >
                            {src.file.replace(/\.md$/i, "").replace(doc_id, docFilename)}:{src.lines}
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
                <div className="bg-[#27273a]/80 border border-white/5 rounded-2xl rounded-tl-none px-4 py-2.5">
                  <div className="flex items-center space-x-1">
                    <div className="w-1.5 h-1.5 bg-indigo-500 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                    <div className="w-1.5 h-1.5 bg-indigo-500 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                    <div className="w-1.5 h-1.5 bg-indigo-500 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
                  </div>
                </div>
              </div>
            )}

            {error && (
              <div className="bg-rose-500/10 border border-rose-500/20 text-rose-450 text-[10px] font-bold rounded-2xl px-3.5 py-2.5 flex items-center gap-2">
                <AlertCircle className="w-4 h-4 text-rose-550" />
                <span>{error}</span>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Action Input Bar */}
          <div className="p-4 border-t border-white/10 bg-[#1e1e2d]/40">
            <div className="flex items-center gap-2">
              <input
                ref={inputRef}
                type="text"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Nhập câu hỏi tại đây..."
                className="flex-1 px-4 py-2.5 rounded-2xl border border-white/10 bg-[#1e1e2d]/60 text-slate-100 placeholder-slate-500 shadow-soft transition-all duration-300 outline-none focus:border-indigo-500 focus:ring-4 focus:ring-indigo-500/10 text-xs"
                disabled={loading}
              />

              {/* Send Button */}
              <button
                onClick={sendQuestion}
                disabled={loading || !question.trim()}
                className="p-2.5 bg-neon-gradient hover:bg-neon-hover text-white rounded-2xl shadow-md shadow-indigo-500/10 active:scale-95 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer outline-none flex items-center justify-center flex-shrink-0"
              >
                <Send className="w-4 h-4" />
              </button>

              {/* Summarize button */}
              <div className="relative">
                <button
                  onClick={(e) => { e.stopPropagation(); setShowSummaryMenu(!showSummaryMenu); }}
                  disabled={loading}
                  className="p-2.5 bg-purple-600 hover:bg-purple-550 text-white rounded-2xl shadow-md shadow-purple-550/10 hover:shadow-purple-550/25 active:scale-95 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer outline-none flex items-center justify-center flex-shrink-0"
                  title="Tóm tắt văn bản"
                >
                  <Sparkles className="w-4 h-4" />
                </button>
                {showSummaryMenu && (
                  <div onClick={(e) => e.stopPropagation()} className="absolute bottom-full right-0 mb-3 w-52 rounded-2xl border border-white/10 bg-[#27273a] shadow-xl py-1.5 z-50 overflow-hidden animate-fade-in">
                    <div className="px-4 py-1.5 text-[9px] font-black text-slate-500 border-b border-white/5 uppercase tracking-widest">
                      Độ dài tóm tắt
                    </div>
                    {SUMMARY_LENGTH_OPTIONS.map((opt) => (
                      <button
                        key={opt.value}
                        onClick={() => handleSummarize(opt.value)}
                        className="w-full text-left px-4 py-2 text-xs text-slate-350 hover:bg-purple-500/10 hover:text-purple-400 transition-colors cursor-pointer font-bold"
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
