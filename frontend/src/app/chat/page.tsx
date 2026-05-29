"use client";

import { useEffect, useState, useRef } from "react";
import Link from "next/link";
import ProtectedRoute from "@/components/ProtectedRoute";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Search,
  MessageSquare,
  FileText,
  Trash2,
  Send,
  Sparkles,
  BookOpen,
  Calendar,
  Layers,
  ChevronRight,
  Clock,
  Bot,
  User
} from "lucide-react";
import {
  getSessions,
  ChatSession,
  deleteSession,
  createSession,
  getMessages,
  askGlobal,
  DocSearchResult,
} from "@/lib/chat";
import { API, getToken, getPayload } from "@/lib/auth";

type Document = {
  id: string;
  filename: string;
  status: string;
};

type GlobalMsg = {
  role: "user" | "assistant";
  content: string;
  relevantDocs?: DocSearchResult[];
  sources?: { file: string; lines: string }[];
};

export default function ChatMasterPage() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");

  const [globalMessages, setGlobalMessages] = useState<GlobalMsg[]>([]);
  const [globalQuestion, setGlobalQuestion] = useState("");
  const [globalLoading, setGlobalLoading] = useState(false);
  const [globalSessionId, setGlobalSessionId] = useState<string | null>(null);
  const globalEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    loadData();
  }, []);

  useEffect(() => {
    globalEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [globalMessages]);

  const loadData = async () => {
    setLoading(true);
    try {
      const token = getToken();
      const headers: Record<string, string> = token
        ? { Authorization: `Bearer ${token}` }
        : {};
      const [docsRes, sessionsData] = await Promise.all([
        fetch(`${API}/documents?page_size=1000`, { headers }).then((r) => {
          if (!r.ok) throw new Error(`Documents API ${r.status}`);
          return r.json();
        }),
        getSessions(),
      ]);
      setDocuments(Array.isArray(docsRes?.items) ? docsRes.items : Array.isArray(docsRes) ? docsRes : []);
      setSessions(sessionsData);
    } catch (err) {
      console.error("Failed to load data:", err);
      setDocuments([]);
      setSessions([]);
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteSession = async (
    sessionId: string,
    e: React.MouseEvent
  ) => {
    e.preventDefault();
    e.stopPropagation();
    try {
      await deleteSession(sessionId);
      setSessions((prev) => prev.filter((s) => s.id !== sessionId));
    } catch (err) {
      console.error("Failed to delete session:", err);
    }
  };

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr.endsWith("Z") ? dateStr : dateStr + "Z");
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);
    if (diffMins < 1) return "Vừa xong";
    if (diffMins < 60) return `${diffMins} phút trước`;
    if (diffHours < 24) return `${diffHours} giờ trước`;
    if (diffDays < 7) return `${diffDays} ngày trước`;
    return date.toLocaleDateString("vi-VN");
  };

  const payload = getPayload();
  const role = payload?.role ?? "nguoi_dung";
  const canSeeAll = role === "admin" || role === "can_bo";

  const filteredDocs = documents
    .filter((doc) => {
      if (canSeeAll) return true;
      return doc.status === "processed";
    })
    .filter((doc) =>
      doc.filename.toLowerCase().includes(searchQuery.toLowerCase())
    );

  const docNameMap = new Map(documents.map((d) => [d.id, d.filename]));

  const handleSessionClick = async (session: ChatSession, e: React.MouseEvent) => {
    if (session.doc_id === "__global__") {
      e.preventDefault();
      setGlobalSessionId(session.id);
      try {
        const msgs = await getMessages(session.id);
        const loaded: GlobalMsg[] = msgs.map((m) => ({
          role: m.role as "user" | "assistant",
          content: m.content,
          sources: m.sources ? JSON.parse(m.sources) : undefined,
        }));
        setGlobalMessages(loaded);
      } catch {
        // ignore
      }
    }
  };

  const handleGlobalSend = async () => {
    if (!globalQuestion.trim() || globalLoading) return;
    const q = globalQuestion;
    setGlobalMessages((prev) => [...prev, { role: "user", content: q }]);
    setGlobalQuestion("");
    setGlobalLoading(true);
    try {
      let sid = globalSessionId;
      if (!sid) {
        const session = await createSession("__global__", q.slice(0, 100));
        sid = session.id;
        setGlobalSessionId(sid);
        setSessions((prev) => [session, ...prev]);
      }
      const data = await askGlobal(q, sid);
      setGlobalMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: data.answer,
          relevantDocs: data.relevant_docs,
          sources: data.sources,
        },
      ]);
    } catch (err) {
      setGlobalMessages((prev) => [
        ...prev,
        { role: "assistant", content: "Đã xảy ra lỗi khi tìm kiếm." },
      ]);
    } finally {
      setGlobalLoading(false);
    }
  };

  const handleGlobalKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleGlobalSend();
    }
  };

  if (loading) {
    return (
      <ProtectedRoute>
        <div className="flex items-center justify-center h-full">
          <div className="flex flex-col items-center gap-3">
            <div className="animate-spin h-10 w-10 border-[3px] border-emerald-500/30 dark:border-indigo-500/30 border-t-indigo-500 rounded-full" />
            <p className="text-sm text-muted">Đang tải dữ liệu...</p>
          </div>
        </div>
      </ProtectedRoute>
    );
  }

  return (
    <ProtectedRoute>
      <div className="flex h-full w-full overflow-hidden">
        {/* LEFT: Documents + Sessions */}
        <div className="flex-1 overflow-y-auto px-6 py-6 space-y-6">
          {/* Header */}
          <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-emerald-500/5 dark:from-indigo-500/5 to-emerald-500/5 dark:to-indigo-500/5 dark:from-emerald-500/8 dark:from-indigo-500/8 dark:to-emerald-500/5 dark:to-indigo-500/5 border border-theme-light p-5 sm:p-6">
            <div className="absolute top-0 right-0 w-40 h-40 bg-emerald-500/10 dark:bg-indigo-500/10 dark:bg-emerald-500/5 dark:bg-indigo-500/5 rounded-full blur-3xl -translate-y-1/2 translate-x-1/4 pointer-events-none" />
            <div className="relative">
              <div className="flex items-center gap-2.5 mb-2">
                <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-emerald-500 dark:from-indigo-500 to-emerald-600 dark:to-indigo-600 flex items-center justify-center shadow-md shadow-emerald-500/15 dark:shadow-indigo-500/15">
                  <MessageSquare className="w-4 h-4 text-white" />
                </div>
                <div>
                  <h1 className="text-xl font-bold text-primary tracking-tight">
                    Hỏi đáp tài liệu
                  </h1>
                  <p className="text-xs text-muted mt-0.5">
                    Lựa chọn tài liệu để bắt đầu phân tích hoặc hỏi đáp thông minh.
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Search */}
          <div className="relative group">
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted group-focus-within:text-emerald-500 dark:group-focus-within:text-indigo-500 transition-colors duration-200" />
            <input
              type="text"
              name="search"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Tìm tài liệu theo tên..."
              className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-theme bg-secondary text-primary placeholder-muted outline-none focus:border-emerald-500 dark:focus:border-indigo-500 focus:ring-[3px] focus:ring-emerald-500/10 dark:focus:ring-indigo-500/10 text-sm transition-all duration-200"
            />
          </div>

          {/* Recent Sessions */}
          {sessions.length > 0 && (
            <section>
              <div className="flex items-center gap-2 mb-3">
                <div className="w-6 h-6 rounded-lg bg-gradient-to-br from-emerald-500/20 dark:from-indigo-500/20 to-emerald-500/20 dark:to-indigo-500/20 flex items-center justify-center">
                  <Clock className="w-3.5 h-3.5 text-emerald-400 dark:text-indigo-400" />
                </div>
                <h2 className="text-sm font-semibold text-secondary">Gần đây</h2>
                <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-emerald-500/10 dark:bg-indigo-500/10 text-emerald-400 dark:text-indigo-400 border border-emerald-500/15 dark:border-indigo-500/15">
                  {Math.min(sessions.length, 9)}
                </span>
              </div>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {sessions.slice(0, 9).map((session) => {
                  const isGlobal = session.doc_id === "__global__";
                  const docName = isGlobal
                    ? "Hỏi đáp tổng hợp"
                    : docNameMap.get(session.doc_id) || session.doc_id;
                  return (
                    <Link
                      key={session.id}
                      href={isGlobal ? "/chat" : `/chat/${session.doc_id}?session=${session.id}`}
                      onClick={(e) => handleSessionClick(session, e)}
                      className="group relative rounded-xl border border-theme-light bg-secondary p-4 hover:border-emerald-500/30 dark:hover:border-indigo-500/30 hover:shadow-lg hover:shadow-emerald-500/5 dark:hover:shadow-indigo-500/5 hover:-translate-y-0.5 transition-all duration-200"
                    >
                      <button
                        onClick={(e) => handleDeleteSession(session.id, e)}
                        className="absolute top-2.5 right-2.5 p-1 rounded-lg opacity-0 group-hover:opacity-100 hover:bg-red-500/10 text-muted hover:text-red-400 transition-all cursor-pointer"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                      {isGlobal ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider rounded-md bg-gradient-to-r from-sky-500/15 to-blue-500/15 text-sky-500 border border-sky-500/20">
                          <span className="w-1.5 h-1.5 rounded-full bg-sky-400" />
                          HỎI ĐÁP CHUNG
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider rounded-md bg-gradient-to-r from-emerald-500/15 to-teal-500/15 text-emerald-500 border border-emerald-500/20">
                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                          Tài liệu riêng
                        </span>
                      )}
                      <h3 className="font-semibold text-primary truncate pr-5 mt-1 text-sm">
                        {session.title || "Cuộc trò chuyện"}
                      </h3>
                      <div className="flex items-center gap-1.5 text-[10px] text-muted mt-2.5 pt-2.5 border-t border-theme-light">
                        <Calendar className="w-3 h-3" />
                        <span>{formatDate(session.updated_at)}</span>
                      </div>
                    </Link>
                  );
                })}
              </div>
            </section>
          )}

          {/* Document Library */}
          <section>
            <div className="flex items-center gap-2 mb-3">
              <div className="w-6 h-6 rounded-lg bg-gradient-to-br from-emerald-500/20 to-teal-500/20 flex items-center justify-center">
                <FileText className="w-3.5 h-3.5 text-emerald-400" />
              </div>
              <h2 className="text-sm font-semibold text-secondary">Thư viện tài liệu</h2>
              <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/15">
                {filteredDocs.length}
              </span>
            </div>
            {filteredDocs.length === 0 ? (
              <div className="text-center py-16 rounded-xl border border-dashed border-theme-light bg-secondary">
                <div className="mx-auto w-12 h-12 rounded-2xl bg-gradient-to-br from-emerald-500/10 to-teal-500/10 flex items-center justify-center mb-3">
                  <FileText className="w-6 h-6 text-emerald-400/60" />
                </div>
                <p className="text-sm text-muted">
                  {searchQuery ? "Không tìm thấy tài liệu nào khớp" : "Chưa có tài liệu nào sẵn sàng"}
                </p>
              </div>
            ) : (
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {filteredDocs.map((doc) => (
                  <Link
                    key={doc.id}
                    href={`/chat/${doc.id}`}
                    className="group rounded-xl border border-theme-light bg-secondary p-4 hover:border-emerald-500/30 hover:shadow-lg hover:shadow-emerald-500/5 hover:-translate-y-0.5 transition-all duration-200 flex items-start gap-3"
                  >
                    <div className="p-2.5 bg-gradient-to-br from-emerald-500/15 to-teal-500/15 text-emerald-400 rounded-lg group-hover:scale-105 transition-transform duration-200">
                      <FileText className="w-4 h-4" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <h3 className="font-semibold text-primary truncate text-sm">{doc.filename}</h3>
                      <div className="flex items-center justify-between mt-2">
                        <span className={`inline-flex items-center gap-1.5 text-[10px] font-medium px-2 py-0.5 rounded-full ${
                          doc.status === "processed"
                            ? "bg-emerald-500/10 text-emerald-500"
                            : "bg-amber-500/10 text-amber-400"
                        }`}>
                          <span className={`w-1.5 h-1.5 rounded-full ${doc.status === "processed" ? "bg-emerald-500" : "bg-amber-400 animate-pulse"}`} />
                          {doc.status === "processed" ? "Sẵn sàng" : "Đang xử lý"}
                        </span>
                        <span className="text-[10px] text-emerald-400 dark:text-indigo-400 font-medium flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                          Hỏi đáp <ChevronRight className="w-3 h-3" />
                        </span>
                      </div>
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </section>
        </div>

        {/* RIGHT: Global Chat Panel */}
        <div className="w-[400px] flex-shrink-0 flex flex-col glass-panel border-l border-theme-light">
          {/* Chat Header */}
          <header className="h-14 flex items-center px-4 border-b border-theme-light bg-gradient-to-r from-emerald-500/5 dark:from-indigo-500/5 to-emerald-500/5 dark:to-indigo-500/5 dark:from-emerald-500/8 dark:from-indigo-500/8 dark:to-emerald-500/5 dark:to-indigo-500/5">
            <div className="w-6 h-6 rounded-lg bg-gradient-to-br from-emerald-500 dark:from-indigo-500 to-emerald-600 dark:to-indigo-600 flex items-center justify-center mr-2.5 shadow-sm shadow-emerald-500/20 dark:shadow-indigo-500/20">
              <Sparkles className="w-3 h-3 text-white" />
            </div>
            <span className="text-sm font-semibold text-primary">Tra Cứu Tổng Hợp</span>

          </header>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-4 py-4 space-y-5">
            {globalMessages.length === 0 && !globalLoading && (
              <div className="flex flex-col items-center justify-center h-full text-center px-6">
                <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-emerald-500/15 dark:from-indigo-500/15 to-emerald-500/15 dark:to-indigo-500/15 border border-emerald-500/10 dark:border-indigo-500/10 flex items-center justify-center mb-4 shadow-inner shadow-emerald-500/5 dark:shadow-indigo-500/5">
                  <Layers className="w-6 h-6 text-emerald-400/70 dark:text-indigo-400/70" />
                </div>
                <h3 className="text-sm font-semibold text-secondary">Hỏi đáp ngữ cảnh chéo</h3>
                <p className="text-xs text-muted mt-1.5 max-w-[220px] leading-relaxed">
                  Nhập câu hỏi để tìm kiếm thông tin đối chiếu trên tất cả tài liệu.
                </p>
              </div>
            )}

            {globalMessages.map((msg, idx) => (
              msg.role === "assistant" ? (
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

                    {msg.relevantDocs && msg.relevantDocs.length > 0 && (
                      <div className="mt-3 pt-2.5 border-t border-theme-light">
                        <div className="flex flex-col gap-1.5">
                          <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-400 dark:text-indigo-400">Tài liệu tham khảo:</span>
                          <div className="flex flex-wrap gap-1.5">
                            {msg.relevantDocs.map((doc) => (
                              <Link
                                key={doc.doc_id}
                                href={`/chat/${doc.doc_id}`}
                                className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg bg-emerald-500/10 dark:bg-indigo-500/10 border border-emerald-500/20 dark:border-indigo-500/20 text-xs font-semibold text-emerald-600 dark:text-indigo-300 hover:bg-emerald-500/20 dark:hover:bg-indigo-500/20 hover:scale-[1.02] transition-all cursor-pointer truncate"
                              >
                                <BookOpen className="w-3 h-3 text-emerald-500 dark:text-indigo-400" />
                                {docNameMap.get(doc.doc_id) || doc.filename}
                              </Link>
                            ))}
                          </div>
                        </div>
                      </div>
                    )}

                    {msg.sources && msg.sources.length > 0 && (
                      <div className="mt-2.5 pt-2 border-t border-theme-light">
                        <div className="flex flex-col gap-1.5">
                          <span className="text-[10px] font-bold uppercase tracking-wider text-amber-500 dark:text-amber-400">Nguồn trích dẫn:</span>
                          <div className="flex flex-wrap gap-1.5">
                            {msg.sources.map((src, sIdx) => (
                              <Link
                                key={sIdx}
                                href={`/chat/${src.file.replace(/\.md$/i, "")}?highlight=${src.lines}`}
                                className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg bg-amber-500/10 border border-amber-500/20 text-xs font-semibold text-amber-600 dark:text-amber-400 hover:bg-amber-500/20 hover:scale-[1.02] transition-all cursor-pointer whitespace-nowrap"
                              >
                                <Sparkles className="w-3 h-3 text-amber-500 dark:text-amber-400" />
                                {(() => {
                                  const srcId = src.file.replace(/\.md$/i, "");
                                  const realName = docNameMap.get(srcId);
                                  return realName ? `${realName}:${src.lines}` : `${src.file}:${src.lines}`;
                                })()}
                              </Link>
                            ))}
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                <div key={idx} className="flex flex-col items-end gap-1">
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className="text-xs font-medium text-emerald-400 dark:text-indigo-400">Bạn</span>
                    <div className="w-5 h-5 rounded-lg bg-gradient-to-br from-emerald-500 dark:from-indigo-500 to-emerald-600 dark:to-indigo-600 flex items-center justify-center">
                      <User className="w-3 h-3 text-white" />
                    </div>
                  </div>
                  <div className="max-w-[85%] rounded-2xl rounded-tr-none px-4 py-3 bg-gradient-to-br from-emerald-500 dark:from-indigo-500 to-emerald-600 dark:to-indigo-600 shadow-lg shadow-emerald-500/20 dark:shadow-indigo-500/20">
                    <p className="text-sm text-white whitespace-pre-wrap">{msg.content}</p>
                  </div>
                </div>
              )
            ))}

            {globalLoading && (
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

            <div ref={globalEndRef} />
          </div>

          {/* Chat Input */}
          <div className="px-4 py-3 border-t border-theme-light">
            <div className="flex items-center gap-2">
              <div className="relative group flex-1">
                <div className="chat-input flex items-center gap-2 px-4 py-1.5">
                  <MessageSquare className="w-4 h-4 text-emerald-400/60 dark:text-indigo-400/60 flex-shrink-0" />
                  <input
                    type="text"
                    name="global_question"
                    value={globalQuestion}
                    onChange={(e) => setGlobalQuestion(e.target.value)}
                    onKeyDown={handleGlobalKeyDown}
                    placeholder="Đặt câu hỏi về tài liệu..."
                    className="flex-1 bg-transparent text-sm text-primary placeholder-slate-500 outline-none py-1"
                    disabled={globalLoading}
                  />
                </div>
              </div>
              <button
                onClick={handleGlobalSend}
                disabled={globalLoading || !globalQuestion.trim()}
                className="send-btn group"
              >
                <Send className="w-4 h-4 group-hover:scale-110 transition-transform" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </ProtectedRoute>
  );
}
