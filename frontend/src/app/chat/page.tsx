"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getSessions, ChatSession, deleteSession } from "@/lib/chat";
import { API } from "@/lib/auth";

type Document = {
  id: string;
  filename: string;
  status: string;
};

export default function ChatMasterPage() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [docsRes, sessionsData] = await Promise.all([
        fetch(`${API}/documents`).then((r) => r.json()),
        getSessions(),
      ]);
      setDocuments(docsRes);
      setSessions(sessionsData);
    } catch (err) {
      console.error("Failed to load data:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteSession = async (sessionId: string, e: React.MouseEvent) => {
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

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="animate-spin h-8 w-8 border-4 border-primary border-t-transparent rounded-full" />
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto py-6 px-4">
      <h1 className="text-2xl font-bold text-text-main mb-6">Hỏi đáp</h1>

      {/* Recent Chat Sessions */}
      {sessions.length > 0 && (
        <section className="mb-8">
          <h2 className="text-lg font-semibold text-gray-700 mb-3">
            Lịch sử trò chuyện
          </h2>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {sessions.slice(0, 9).map((session) => (
              <Link
                key={session.id}
                href={`/chat/${session.doc_id}?session=${session.id}`}
                className="group relative bg-white rounded-lg border border-gray-200 p-4 hover:border-primary hover:shadow-md transition-all"
              >
                <button
                  onClick={(e) => handleDeleteSession(session.id, e)}
                  className="absolute top-2 right-2 p-1 rounded opacity-0 group-hover:opacity-100 hover:bg-red-50 text-gray-400 hover:text-red-500 transition-all"
                  title="Xóa phiên"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                </button>
                <h3 className="font-medium text-gray-800 truncate pr-6">
                  {session.title || "Cuộc trò chuyện"}
                </h3>
                <p className="text-xs text-gray-400 mt-1">
                  {formatDate(session.updated_at)}
                </p>
              </Link>
            ))}
          </div>
        </section>
      )}

      {/* Document List */}
      <section>
        <h2 className="text-lg font-semibold text-gray-700 mb-3">
          Tài liệu
        </h2>
        {documents.length === 0 ? (
          <div className="text-center py-12 bg-white rounded-lg border border-gray-200">
            <svg className="mx-auto h-12 w-12 text-gray-300 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            <p className="text-gray-400">Chưa có tài liệu nào</p>
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {documents.map((doc) => (
              <Link
                key={doc.id}
                href={`/chat/${doc.id}`}
                className="bg-white rounded-lg border border-gray-200 p-4 hover:border-primary hover:shadow-md transition-all"
              >
                <div className="flex items-start gap-3">
                  <div className="p-2 bg-primary/10 rounded-lg">
                    <svg className="w-5 h-5 text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                  </div>
                  <div className="flex-1 min-w-0">
                    <h3 className="font-medium text-gray-800 truncate">
                      {doc.filename}
                    </h3>
                    <span className={`inline-block mt-1 text-xs px-2 py-0.5 rounded-full ${
                      doc.status === "processed"
                        ? "bg-green-100 text-green-700"
                        : "bg-yellow-100 text-yellow-700"
                    }`}>
                      {doc.status === "processed" ? "Sẵn sàng" : doc.status}
                    </span>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
