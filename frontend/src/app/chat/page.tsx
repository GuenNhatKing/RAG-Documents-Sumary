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
  ChevronRight
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

  // Global chat state
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

  // doc_id → filename lookup
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
        <div className="flex items-center justify-center h-full bg-transparent">
          <div className="relative flex items-center justify-center">
            <div className="animate-spin h-10 w-10 border-4 border-indigo-500 border-t-transparent rounded-full" />
            <div className="absolute animate-ping h-10 w-10 border border-indigo-500/35 rounded-full" />
          </div>
        </div>
      </ProtectedRoute>
    );
  }

  return (
    <ProtectedRoute>
      <div className="flex h-full w-full bg-transparent overflow-hidden">
        {/* LEFT: Documents + Sessions */}
        <div className="flex-1 overflow-y-auto px-6 py-6 scrollbar-thin scrollbar-thumb-[#27273a]">
          <div className="flex flex-col gap-1 mb-5">
            <h1 className="text-3xl font-black text-neon-gradient tracking-tight select-none">
              Hỏi đáp tài liệu
            </h1>
            <p className="text-xs text-slate-450 font-medium">
              Lựa chọn tài liệu để bắt đầu phân tích hoặc hỏi đáp thông minh.
            </p>
          </div>

          {/* Search Bar */}
          <div className="relative mb-6">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4.5 h-4.5 text-slate-500" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Tìm tài liệu theo tên..."
              className="w-full pl-11 pr-4 py-2.5 rounded-2xl border border-white/10 bg-[#27273a]/60 text-slate-100 placeholder-slate-500 shadow-soft transition-all duration-300 outline-none focus:border-indigo-500 focus:ring-4 focus:ring-indigo-500/10 text-sm"
            />
          </div>

          {/* Recent Sessions */}
          {sessions.length > 0 && (
            <section className="mb-6">
              <div className="flex items-center gap-2 mb-3.5 select-none">
                <MessageSquare className="w-4 h-4 text-indigo-400" />
                <h2 className="text-sm font-bold text-slate-350">
                  Lịch sử trò chuyện gần đây
                </h2>
                <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-[#27273a] text-slate-450">
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
                      className="group relative rounded-2xl border border-white/10 bg-[#27273a]/35 p-4 hover:border-indigo-500/70 hover:shadow-neon-indigo hover:-translate-y-0.5 transition-all duration-300 glass-card"
                    >
                      <button
                        onClick={(e) => handleDeleteSession(session.id, e)}
                        className="absolute top-2.5 right-2.5 p-1 rounded-lg opacity-0 group-hover:opacity-100 hover:bg-rose-500/10 text-slate-400 hover:text-rose-500 transition-all cursor-pointer"
                        title="Xóa phiên"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                      <span className="text-[10px] text-indigo-405 font-bold block truncate pr-5 uppercase tracking-wider">
                        {isGlobal ? "Cross-Document" : "Tài liệu riêng"}
                      </span>
                      <h3 className="font-extrabold text-slate-100 truncate pr-5 mt-1 text-xs">
                        {session.title || "Cuộc trò chuyện"}
                      </h3>
                      <div className="flex items-center gap-1.5 text-[9px] font-bold text-slate-500 mt-2.5 pt-2 border-t border-white/5">
                        <Calendar className="w-3 h-3 text-slate-650" />
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
            <div className="flex items-center gap-2 mb-3.5 select-none">
              <FileText className="w-4 h-4 text-indigo-400" />
              <h2 className="text-sm font-bold text-slate-350">
                Thư viện tài liệu của bạn
              </h2>
              <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-[#27273a] text-slate-450">
                {filteredDocs.length}
              </span>
            </div>
            {filteredDocs.length === 0 ? (
              <div className="text-center py-12 rounded-2xl border border-dashed border-white/10 bg-[#27273a]/20 shadow-soft">
                <FileText className="mx-auto h-9 w-9 text-slate-700 mb-2.5" />
                <p className="text-xs text-slate-500 font-bold">
                  {searchQuery
                    ? "Không tìm thấy tài liệu nào khớp với từ khoá"
                    : "Chưa có tài liệu nào sẵn sàng"}
                </p>
              </div>
            ) : (
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {filteredDocs.map((doc) => (
                  <Link
                    key={doc.id}
                    href={`/chat/${doc.id}`}
                    className="group relative rounded-2xl border border-white/10 bg-[#27273a]/35 p-4 hover:border-indigo-500/70 hover:shadow-neon-indigo hover:-translate-y-0.5 transition-all duration-300 flex items-start gap-3.5 glass-card"
                  >
                    <div className="p-2.5 bg-indigo-500/10 text-indigo-400 rounded-xl transition-all duration-200 group-hover:scale-105">
                      <FileText className="w-4.5 h-4.5" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <h3 className="font-extrabold text-slate-100 truncate text-xs">
                        {doc.filename}
                      </h3>
                      <div className="flex items-center justify-between mt-2.5">
                        <span
                          className={`inline-flex items-center gap-1 text-[9px] font-bold px-2 py-0.5 rounded-full ${
                            doc.status === "processed"
                              ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/15"
                              : "bg-amber-500/10 text-amber-400 border border-amber-500/15"
                          }`}
                        >
                          <span className={`w-1 h-1 rounded-full ${doc.status === "processed" ? "bg-emerald-500" : "bg-amber-500 animate-pulse"}`} />
                          {doc.status === "processed" ? "Sẵn sàng" : "Đang xử lý"}
                        </span>
                        
                        <span className="text-[10px] text-indigo-400 font-extrabold flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity duration-300">
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
        <div className="w-[380px] flex-shrink-0 flex flex-col bg-[#27273a]/60 backdrop-blur-md border-l border-white/10">
          {/* Header */}
          <div className="px-5 py-4.5 border-b border-white/10 bg-[#1e1e2d]/40 flex items-start gap-3">
            <div className="w-8 h-8 rounded-xl bg-gradient-to-tr from-indigo-500 to-purple-500 flex items-center justify-center text-white shadow-md shadow-indigo-500/10">
              <Sparkles className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-sm font-black text-slate-100">
                Tra Cứu Tổng Hợp
              </h2>
              <p className="text-[10px] text-slate-500 mt-0.5 font-bold leading-none">
                Hỏi đáp chéo trên toàn bộ kho tài liệu
              </p>
            </div>
          </div>

          {/* Messages Area */}
          <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4 scrollbar-thin scrollbar-thumb-[#27273a]">
            {globalMessages.length === 0 && !globalLoading && (
              <div className="flex flex-col items-center justify-center h-full text-center p-6">
                <div className="w-11 h-11 rounded-2xl bg-indigo-500/10 text-indigo-400 flex items-center justify-center mb-3">
                  <Layers className="w-5 h-5 text-indigo-400" />
                </div>
                <h3 className="text-xs font-bold text-slate-300">
                  Hỏi đáp ngữ cảnh chéo
                </h3>
                <p className="text-[10px] text-slate-550 mt-1 max-w-[200px] leading-relaxed">
                  Nhập câu hỏi để tìm kiếm thông tin đối chiếu trên tất cả tài liệu của bạn.
                </p>
              </div>
            )}

            {globalMessages.map((msg, idx) => (
              <div
                key={idx}
                className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[88%] rounded-2xl px-3.5 py-2.5 text-xs transition-all duration-300 leading-relaxed ${
                    msg.role === "user"
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

                  {/* Relevant docs */}
                  {msg.relevantDocs && msg.relevantDocs.length > 0 && (
                    <div className="mt-3 pt-2.5 border-t border-white/5">
                      <div className="flex items-center gap-1 text-[10px] font-extrabold text-slate-450 mb-2">
                        <BookOpen className="w-3.5 h-3.5 text-indigo-400" />
                        <span>Tài liệu tham khảo:</span>
                      </div>
                      <div className="flex flex-col gap-1">
                        {msg.relevantDocs.map((doc) => (
                          <Link
                              key={doc.doc_id}
                              href={`/chat/${doc.doc_id}`}
                              className={`text-[10px] rounded-xl px-2.5 py-1.5 transition-all font-bold block truncate border ${
                                msg.role === "user"
                                  ? "bg-white/10 hover:bg-white/20 text-white border-white/10"
                                  : "bg-[#1e1e2d]/80 hover:bg-indigo-500/5 text-slate-300 hover:text-indigo-450 border-white/5"
                              }`}
                          >
                            {docNameMap.get(doc.doc_id) || doc.filename}
                          </Link>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Sources */}
                  {msg.sources && msg.sources.length > 0 && (
                    <div className="mt-2.5 pt-2 border-t border-white/5">
                      <p className="text-[9px] font-extrabold text-slate-450 mb-1.5">
                        Nguồn đối chiếu:
                      </p>
                      <div className="flex flex-wrap gap-1">
                        {msg.sources.map((src, sIdx) => (
                          <span
                            key={sIdx}
                            className={`inline-block text-[9px] font-bold rounded-lg px-2 py-0.5 ${
                              msg.role === "user"
                                ? "bg-white/10 text-white"
                                : "bg-[#1e1e2d] text-slate-400 border border-white/5"
                            }`}
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
            ))}

            {globalLoading && (
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

            <div ref={globalEndRef} />
          </div>

          {/* Input Panel */}
          <div className="p-4.5 border-t border-white/10 bg-[#1e1e2d]/40">
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={globalQuestion}
                onChange={(e) => setGlobalQuestion(e.target.value)}
                onKeyDown={handleGlobalKeyDown}
                placeholder="Nhập câu hỏi tại đây..."
                className="flex-1 px-4 py-2.5 rounded-2xl border border-white/10 bg-[#1e1e2d]/60 text-slate-100 placeholder-slate-500 shadow-soft transition-all duration-300 outline-none focus:border-indigo-500 focus:ring-4 focus:ring-indigo-500/10 text-xs"
                disabled={globalLoading}
              />
              <button
                onClick={handleGlobalSend}
                disabled={globalLoading || !globalQuestion.trim()}
                className="p-2.5 bg-neon-gradient hover:bg-neon-hover text-white rounded-2xl shadow-md shadow-indigo-500/10 active:scale-95 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer outline-none flex items-center justify-center flex-shrink-0"
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
