"use client";

import { useEffect, useState, useRef } from "react";
import Link from "next/link";
import ProtectedRoute from "@/components/ProtectedRoute";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
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
        fetch(`${API}/documents`, { headers }).then((r) => {
          if (!r.ok) throw new Error(`Documents API ${r.status}`);
          return r.json();
        }),
        getSessions(),
      ]);
      setDocuments(Array.isArray(docsRes) ? docsRes : []);
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
    if (diffMins < 60) return `${diffMins} phút`;
    if (diffHours < 24) return `${diffHours} giờ`;
    if (diffDays < 7) return `${diffDays} ngày`;
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
      // Create session on first message if needed
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
          <div className="animate-spin h-8 w-8 border-4 border-primary border-t-transparent rounded-full" />
        </div>
      </ProtectedRoute>
    );
  }

  return (
    <ProtectedRoute>
      <div className="flex h-[calc(100vh-64px)] -m-4">
        {/* LEFT: Documents + Sessions */}
        <div className="flex-1 overflow-y-auto p-6">
          <h1 className="text-2xl font-bold text-text-main mb-4">Hỏi đáp</h1>

          {/* Search Bar */}
          <div className="relative mb-6">
            <svg
              className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
              />
            </svg>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Tìm tài liệu theo tên..."
              className="w-full pl-10 pr-4 py-2.5 rounded-lg border border-gray-300 bg-white text-sm focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
            />
          </div>

          {/* Recent Sessions */}
          {sessions.length > 0 && (
            <section className="mb-8">
              <h2 className="text-lg font-semibold text-gray-700 mb-3">
                Lịch sử trò chuyện
              </h2>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {sessions.slice(0, 9).map((session) => {
                  const isGlobal = session.doc_id === "__global__";
                  const docName = isGlobal
                    ? "Chat tổng hợp"
                    : docNameMap.get(session.doc_id) || session.doc_id;
                  return (
                    <Link
                      key={session.id}
                      href={isGlobal ? "/chat" : `/chat/${session.doc_id}?session=${session.id}`}
                      onClick={(e) => handleSessionClick(session, e)}
                      className="group relative bg-white rounded-lg border border-gray-200 p-4 hover:border-primary hover:shadow-md transition-all"
                    >
                      <button
                        onClick={(e) => handleDeleteSession(session.id, e)}
                        className="absolute top-2 right-2 p-1 rounded opacity-0 group-hover:opacity-100 hover:bg-red-50 text-gray-400 hover:text-red-500 transition-all"
                        title="Xóa phiên"
                      >
                        <svg
                          className="w-4 h-4"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                          />
                        </svg>
                      </button>
                      <p className="text-xs text-primary font-medium truncate pr-6">
                        {docName}
                      </p>
                      <h3 className="font-medium text-gray-800 truncate pr-6 mt-0.5">
                        {session.title || "Cuộc trò chuyện"}
                      </h3>
                      <p className="text-xs text-gray-400 mt-1">
                        {formatDate(session.updated_at)}
                      </p>
                    </Link>
                  );
                })}
              </div>
            </section>
          )}

          {/* Documents */}
          <section>
            <h2 className="text-lg font-semibold text-gray-700 mb-3">
              Tài liệu
            </h2>
            {filteredDocs.length === 0 ? (
              <div className="text-center py-12 bg-white rounded-lg border border-gray-200">
                <svg
                  className="mx-auto h-12 w-12 text-gray-300 mb-3"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={1.5}
                    d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                  />
                </svg>
                <p className="text-gray-400">
                  {searchQuery
                    ? "Không tìm thấy tài liệu"
                    : "Chưa có tài liệu nào"}
                </p>
              </div>
            ) : (
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {filteredDocs.map((doc) => (
                  <Link
                    key={doc.id}
                    href={`/chat/${doc.id}`}
                    className="bg-white rounded-lg border border-gray-200 p-4 hover:border-primary hover:shadow-md transition-all"
                  >
                    <div className="flex items-start gap-3">
                      <div className="p-2 bg-primary/10 rounded-lg">
                        <svg
                          className="w-5 h-5 text-primary"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                          />
                        </svg>
                      </div>
                      <div className="flex-1 min-w-0">
                        <h3 className="font-medium text-gray-800 truncate">
                          {doc.filename}
                        </h3>
                        <span
                          className={`inline-block mt-1 text-xs px-2 py-0.5 rounded-full ${
                            doc.status === "processed"
                              ? "bg-green-100 text-green-700"
                              : "bg-yellow-100 text-yellow-700"
                          }`}
                        >
                          {doc.status === "processed"
                            ? "Sẵn sàng"
                            : doc.status}
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
        <div className="w-96 flex-shrink-0 flex flex-col bg-white border-l border-gray-200">
          <div className="px-4 py-3 border-b border-gray-200">
            <h2 className="text-sm font-semibold text-gray-700">
              Chat tìm tài liệu
            </h2>
            <p className="text-xs text-gray-400 mt-0.5">
              Hỏi đáp qua tất cả tài liệu
            </p>
          </div>

          <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
            {globalMessages.length === 0 && !globalLoading && (
              <div className="flex flex-col items-center justify-center h-full text-center">
                <div className="text-gray-300 mb-3">
                  <svg
                    className="w-12 h-12"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={1.5}
                      d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                    />
                  </svg>
                </div>
                <p className="text-sm text-gray-400">
                  Tìm kiếm trên tất cả tài liệu
                </p>
              </div>
            )}

            {globalMessages.map((msg, idx) => (
              <div
                key={idx}
                className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[90%] rounded-lg px-3 py-2 ${
                    msg.role === "user"
                      ? "bg-blue-600 text-white"
                      : "bg-gray-100 text-gray-800"
                  }`}
                >
                  {msg.role === "assistant" ? (
                    <div className="prose prose-sm max-w-none prose-p:my-1 prose-headings:my-2">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {msg.content}
                      </ReactMarkdown>
                    </div>
                  ) : (
                    <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                  )}

                  {/* Relevant docs */}
                  {msg.relevantDocs && msg.relevantDocs.length > 0 && (
                    <div className="mt-2 pt-2 border-t border-gray-200/50">
                      <p className="text-xs font-medium text-gray-500 mb-1">
                        Tài liệu liên quan:
                      </p>
                      <div className="flex flex-col gap-1">
                        {msg.relevantDocs.map((doc) => (
                          <Link
                            key={doc.doc_id}
                            href={`/chat/${doc.doc_id}`}
                            className={`text-xs rounded px-2 py-1 transition-colors ${
                              msg.role === "user"
                                ? "bg-white/20 hover:bg-white/30 text-white"
                                : "bg-white hover:bg-blue-50 text-gray-600 hover:text-blue-600"
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
                    <div className="mt-2 pt-2 border-t border-gray-200/50">
                      <p className="text-xs font-medium text-gray-500 mb-1">
                        Nguồn:
                      </p>
                      <div className="flex flex-wrap gap-1">
                        {msg.sources.map((src, sIdx) => (
                          <span
                            key={sIdx}
                            className={`inline-block text-xs rounded px-1.5 py-0.5 ${
                              msg.role === "user"
                                ? "bg-white/20 text-white"
                                : "bg-white text-gray-500"
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
                <div className="bg-gray-100 rounded-lg px-3 py-2">
                  <div className="flex items-center space-x-1.5">
                    <div
                      className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"
                      style={{ animationDelay: "0ms" }}
                    />
                    <div
                      className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"
                      style={{ animationDelay: "150ms" }}
                    />
                    <div
                      className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"
                      style={{ animationDelay: "300ms" }}
                    />
                  </div>
                </div>
              </div>
            )}

            <div ref={globalEndRef} />
          </div>

          <div className="px-4 py-3 border-t border-gray-200">
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={globalQuestion}
                onChange={(e) => setGlobalQuestion(e.target.value)}
                onKeyDown={handleGlobalKeyDown}
                placeholder="Hỏi về tài liệu..."
                className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                disabled={globalLoading}
              />
              <button
                onClick={handleGlobalSend}
                disabled={globalLoading || !globalQuestion.trim()}
                className="p-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                <svg
                  className="w-4 h-4"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"
                  />
                </svg>
              </button>
            </div>
          </div>
        </div>
      </div>
    </ProtectedRoute>
  );
}
