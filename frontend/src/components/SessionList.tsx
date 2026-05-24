"use client";

import { useEffect, useState } from "react";
import { ChatSession, createSession, getSessions, deleteSession } from "@/lib/chat";

interface SessionListProps {
  docId: string;
  currentSessionId?: string;
  onSelect: (sessionId: string) => void;
  onNewSession: () => void;
}

export default function SessionList({
  docId,
  currentSessionId,
  onSelect,
  onNewSession,
}: SessionListProps) {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadSessions();
  }, [docId]);

  const loadSessions = async () => {
    setLoading(true);
    try {
      const data = await getSessions(docId);
      setSessions(data);
    } catch (err) {
      console.error("Failed to load sessions:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async () => {
    try {
      const session = await createSession(docId);
      await loadSessions();
      onSelect(session.id);
    } catch (err) {
      console.error("Failed to create session:", err);
    }
  };

  const handleDelete = async (sessionId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await deleteSession(sessionId);
      await loadSessions();
    } catch (err) {
      console.error("Failed to delete session:", err);
    }
  };

  const formatDate = (dateStr: string) => {
    const d = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - d.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return "Vừa xong";
    if (diffMins < 60) return `${diffMins} phút`;
    if (diffHours < 24) return `${diffHours} giờ`;
    if (diffDays < 7) return `${diffDays} ngày`;
    return d.toLocaleDateString("vi-VN");
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-gray-200">
        <h3 className="text-sm font-semibold text-gray-700">Phiên trò chuyện</h3>
        <button
          onClick={handleCreate}
          className="p-1 rounded hover:bg-gray-100 text-gray-500 hover:text-gray-700"
          title="Tạo phiên mới"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="h-4 w-4"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 4v16m8-8H4"
            />
          </svg>
        </button>
      </div>

      {/* Session list */}
      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="flex items-center justify-center py-8">
            <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-gray-400" />
          </div>
        ) : sessions.length === 0 ? (
          <div className="px-3 py-8 text-center">
            <p className="text-sm text-gray-400">Chưa có phiên trò chuyện</p>
            <button
              onClick={handleCreate}
              className="mt-2 text-xs text-blue-500 hover:text-blue-700"
            >
              Tạo phiên mới
            </button>
          </div>
        ) : (
          <div className="py-1">
            {sessions.map((session) => (
              <div
                key={session.id}
                onClick={() => onSelect(session.id)}
                className={`
                  group flex items-center justify-between px-3 py-2 cursor-pointer
                  hover:bg-gray-50 transition-colors
                  ${currentSessionId === session.id ? "bg-blue-50 border-l-2 border-blue-500" : ""}
                `}
              >
                <div className="flex-1 min-w-0 mr-2">
                  <p className="text-sm text-gray-800 truncate">
                    {session.title || "Cuộc trò chuyện mới"}
                  </p>
                  <p className="text-xs text-gray-400 mt-0.5">
                    {formatDate(session.updated_at)}
                  </p>
                </div>
                <button
                  onClick={(e) => handleDelete(session.id, e)}
                  className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-red-100 text-gray-400 hover:text-red-500 transition-opacity"
                  title="Xóa phiên"
                >
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    className="h-3.5 w-3.5"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                    />
                  </svg>
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
