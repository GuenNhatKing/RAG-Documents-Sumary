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
  };
 
  return (
    <div className="flex flex-col h-full bg-[#27273a]/10">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-white/5 bg-[#1e1e2d]/40">
        <h3 className="text-xs uppercase tracking-wider font-extrabold text-slate-400 select-none">
          Phiên trò chuyện
        </h3>
        <button
          onClick={handleCreate}
          className="p-1.5 rounded-xl hover:bg-indigo-500/10 text-slate-400 hover:text-indigo-400 transition-colors cursor-pointer"
          title="Tạo phiên mới"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="h-4.5 w-4.5"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2.5}
              d="M12 4v16m8-8H4"
            />
          </svg>
        </button>
      </div>
 
      {/* Session list */}
      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-indigo-500" />
          </div>
        ) : sessions.length === 0 ? (
          <div className="px-4 py-12 text-center">
            <p className="text-xs font-bold text-slate-500">Chưa có phiên trò chuyện</p>
            <button
              onClick={handleCreate}
              className="mt-2 text-xs font-bold text-indigo-400 hover:text-indigo-300 hover:underline cursor-pointer"
            >
              Tạo phiên mới
            </button>
          </div>
        ) : (
          <div className="py-2">
            {sessions.map((session) => (
              <div
                key={session.id}
                onClick={() => onSelect(session.id)}
                className={`
                  group flex items-center justify-between px-4 py-3 cursor-pointer
                  transition-all duration-200 border-l-4
                  ${
                    currentSessionId === session.id
                      ? "bg-indigo-500/10 border-indigo-500 text-indigo-400 font-extrabold"
                      : "border-transparent hover:bg-[#1e1e2d]/40 text-slate-350"
                  }
                `}
              >
                <div className="flex-1 min-w-0 mr-2">
                  <p className="text-xs truncate font-bold leading-normal">
                    {session.title || "Cuộc trò chuyện mới"}
                  </p>
                  <p className="text-[10px] text-slate-500 mt-1 font-bold">
                    {formatDate(session.updated_at)}
                  </p>
                </div>
                <button
                  onClick={(e) => handleDelete(session.id, e)}
                  className="opacity-0 group-hover:opacity-100 p-1.5 rounded-xl hover:bg-rose-500/10 text-slate-400 hover:text-rose-500 transition-all duration-200 cursor-pointer"
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
