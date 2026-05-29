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
  Plus,
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
    const date = new Date(dateStr);
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
            <div className="relative">
              <div className="animate-spin h-10 w-10 border-[3px] border-indigo-500/30 border-t-indigo-500 rounded-full" />
            </div>
            <p className="text-sm text-slate-400">Đang tải dữ liệu...</p>
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
          <div>
            <h1 className="text-2xl font-bold text-white tracking-tight">
              Hỏi đáp tài liệu
            </h1>
            <p className="text-sm text-slate-400 mt-1">
              Lựa chọn tài liệu để bắt đầu phân tích hoặc hỏi đáp thông minh.
            </p>
          </div>

          {/* Search Bar */}
          <div className="relative">
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Tìm tài liệu theo tên..."
              className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-white/[0.06] bg-[#222840]/60 text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500/50 focus:ring-2 focus:ring-indigo-500/10 text-sm transition-all"
            />
          </div>

          {/* Recent Sessions */}
          {sessions.length > 0 && (
            <section>
              <div className="flex items-center gap-2 mb-3">
                <Clock className="w-4 h-4 text-indigo-400" />
                <h2 className="text-sm font-semibold text-slate-300">
                  Gần đây
                </h2>
                <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-white/[0.04] text-slate-500">
                  {Math.min(sessions.length, 9)}
                </span>
              </div>
              <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
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
                      className="group relative rounded-xl border border-white/[0.06] bg-[#222840]/40 p-4 hover:border-indigo-500/30 hover:bg-[#222840]/70 transition-all duration-200"
                    >
                      <button
                        onClick={(e) => handleDeleteSession(session.id, e)}
                        className="absolute top-2.5 right-2.5 p-1 rounded-lg opacity-0 group-hover:opacity-100 hover:bg-red-500/10 text-slate-500 hover:text-red-400 transition-all cursor-pointer"
                        title="Xóa phiên"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                      <span className="text-[10px] font-medium text-indigo-400/70 block truncate pr-5 uppercase tracking-wider">
                        {isGlobal ? "Cross-Document" : "Tài liệu riêng"}
                      </span>
                      <h3 className="font-semibold text-slate-200 truncate pr-5 mt-1 text-sm">
                        {session.title || "Cuộc trò chuyện"}
                      </h3>
                      <div className="flex items-center gap-1.5 text-[10px] text-slate-500 mt-2.5 pt-2.5 border-t border-white/[0.04]">
                        <Calendar className="w-3 h-3" />
                        <span>{formatDate(session.updated_at)}</span>
                      </div>
                    </Link>
                  );
                })}
              </div>
            </section>
          )}

          {/* Documents */}
          <section>
            <div className="flex items-center gap-2 mb-3">
              <FileText className="w-4 h-4 text-indigo-400" />
              <h2 className="text-sm font-semibold text-slate-300">
                Thư viện tài liệu
              </h2>
              <span className="text-[10px] font-medium px-2 py-0.5 rounded-full bg-white/[0.04] text-slate-500">
                {filteredDocs.length}
              </span>
            </div>
            {filteredDocs.length === 0 ? (
              <div               className="text-center py-16 rounded-xl border border-dashed border-white/[0.06] bg-[#222840]/20">
                <FileText className="mx-auto h-8 w-8 text-slate-600 mb-3" />
                <p className="text-sm text-slate-500">
                  {searchQuery
                    ? "Không tìm thấy tài liệu nào khớp"
                    : "Chưa có tài liệu nào sẵn sàng"}
                </p>
              </div>
            ) : (
              <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
                {filteredDocs.map((doc) => (
                  <Link
                    key={doc.id}
                    href={`/chat/${doc.id}`}
                    className="group rounded-xl border border-white/[0.06] bg-[#222840]/40 p-4 hover:border-indigo-500/30 hover:bg-[#222840]/70 transition-all duration-200 flex items-start gap-3"
                  >
                    <div className="p-2.5 bg-indigo-500/10 text-indigo-400 rounded-lg transition-all duration-200">
                      <FileText className="w-4 h-4" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <h3 className="font-semibold text-slate-200 truncate text-sm">
                        {doc.filename}
                      </h3>
                      <div className="flex items-center justify-between mt-2">
                        <span
                          className={`inline-flex items-center gap-1.5 text-[10px] font-medium px-2 py-0.5 rounded-full ${
                            doc.status === "processed"
                              ? "bg-emerald-500/10 text-emerald-400"
                              : "bg-amber-500/10 text-amber-400"
                          }`}
                        >
                          <span className={`w-1.5 h-1.5 rounded-full ${doc.status === "processed" ? "bg-emerald-400" : "bg-amber-400 animate-pulse"}`} />
                          {doc.status === "processed" ? "Sẵn sàng" : "Đang xử lý"}
                        </span>
                        <span className="text-[10px] text-indigo-400 font-medium flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
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
        <div className="w-[400px] flex-shrink-0 flex flex-col bg-[#1a1f2e]/80 backdrop-blur-md border-l border-white/[0.06]">
          {/* Header */}
          <div className="px-5 py-4 border-b border-white/[0.06] flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-500 to-violet-500 flex items-center justify-center text-white shadow-lg shadow-indigo-500/15">
              <Sparkles className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-slate-200">
                Tra Cứu Tổng Hợp
              </h2>
              <p className="text-[11px] text-slate-500 mt-0.5">
                Hỏi đáp chéo trên toàn bộ kho tài liệu
              </p>
            </div>
          </div>

          {/* Messages Area */}
          <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
            {globalMessages.length === 0 && !globalLoading && (
              <div className="flex flex-col items-center justify-center h-full text-center px-6">
                <div className="w-12 h-12 rounded-2xl bg-indigo-500/10 text-indigo-400 flex items-center justify-center mb-4">
                  <Layers className="w-5 h-5" />
                </div>
                <h3 className="text-sm font-semibold text-slate-300">
                  Hỏi đáp ngữ cảnh chéo
                </h3>
                <p className="text-xs text-slate-500 mt-1.5 max-w-[220px] leading-relaxed">
                  Nhập câu hỏi để tìm kiếm thông tin đối chiếu trên tất cả tài liệu của bạn.
                </p>
              </div>
            )}

            {globalMessages.map((msg, idx) => (
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
                        : "bg-gradient-to-br from-[#2a3148] to-[#222840] border border-white/[0.06] text-slate-200 rounded-tl-sm"
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

                    {msg.relevantDocs && msg.relevantDocs.length > 0 && (
                      <div className="mt-3 pt-2.5 border-t border-white/20">
                        <div className="flex items-center gap-1.5 text-[10px] font-medium text-white/70 mb-2">
                          <BookOpen className="w-3 h-3" />
                          <span>Tài liệu tham khảo:</span>
                        </div>
                        <div className="flex flex-col gap-1">
                          {msg.relevantDocs.map((doc) => (
                            <Link
                                key={doc.doc_id}
                                href={`/chat/${doc.doc_id}`}
                                className="text-[11px] rounded-lg px-2.5 py-1.5 transition-all block truncate bg-white/10 hover:bg-white/20 text-white/90"
                            >
                              {docNameMap.get(doc.doc_id) || doc.filename}
                            </Link>
                          ))}
                        </div>
                      </div>
                    )}

                    {msg.sources && msg.sources.length > 0 && (
                      <div className="mt-2.5 pt-2 border-t border-white/[0.06]">
                        <p className="text-[10px] font-medium text-slate-500 mb-1.5">
                          Nguồn đối chiếu:
                        </p>
                        <div className="flex flex-wrap gap-1.5">
                          {msg.sources.map((src, sIdx) => (
                            <span
                              key={sIdx}
                              className="inline-block text-[10px] rounded-lg px-2 py-0.5 bg-white/[0.05] text-slate-400 border border-white/[0.06]"
                            >
                              {(() => {
                                const srcId = src.file.replace(/\.md$/i, "");
                                const realName = docNameMap.get(srcId);
                                return realName ? `${realName}:${src.lines}` : `${src.file}:${src.lines}`;
                              })()}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))}

            {globalLoading && (
              <div className="flex justify-start">
                  <div className="flex gap-2.5">
                  <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-slate-500 to-slate-600 text-white shadow-md flex items-center justify-center flex-shrink-0 mt-1">
                    <Bot className="w-3.5 h-3.5" />
                  </div>
                  <div className="bg-gradient-to-br from-[#2a3148] to-[#222840] border border-white/[0.06] rounded-2xl rounded-tl-sm px-4 py-3">
                    <div className="flex items-center gap-1.5">
                      <div className="w-2 h-2 bg-indigo-400 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                      <div className="w-2 h-2 bg-indigo-400 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                      <div className="w-2 h-2 bg-indigo-400 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
                    </div>
                  </div>
                </div>
              </div>
            )}

            <div ref={globalEndRef} />
          </div>

          {/* Input Panel */}
          <div className="p-4 border-t border-white/[0.06]">
            <div className="flex items-center gap-2 bg-[#222840] border border-white/[0.06] rounded-xl px-3 py-1.5 focus-within:border-indigo-500/40 transition-all">
              <input
                type="text"
                value={globalQuestion}
                onChange={(e) => setGlobalQuestion(e.target.value)}
                onKeyDown={handleGlobalKeyDown}
                placeholder="Nhập câu hỏi tại đây..."
                className="flex-1 bg-transparent text-sm text-slate-200 placeholder-slate-500 outline-none py-1.5"
                disabled={globalLoading}
              />
              <button
                onClick={handleGlobalSend}
                disabled={globalLoading || !globalQuestion.trim()}
                className="p-2 rounded-lg bg-indigo-500 hover:bg-indigo-400 text-white transition-all disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer flex items-center justify-center"
              >
                <Send className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </ProtectedRoute>
  );
}
