"use client";
 
import { useEffect, useState } from "react";
import { ChatSession, createSession, getSessions, deleteSession } from "@/lib/chat";
import { Plus, Trash2, MessageSquare, History } from "lucide-react";
 
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
    return `${diffDays} ngày`;
  };
 
  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-white/[0.05] bg-[#2a3148]/30">
        <div className="flex items-center gap-2">
          <History className="w-4 h-4 text-indigo-400" />
          <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-widest">
            Lịch sử
          </h3>
        </div>
        <button
          onClick={handleCreate}
          className="p-1.5 rounded-lg hover:bg-indigo-500/10 text-slate-400 hover:text-indigo-400 transition-colors cursor-pointer"
          title="Tạo phiên mới"
        >
          <Plus className="w-4 h-4" />
        </button>
      </div>
 
      {/* Session list */}
      <div className="flex-1 overflow-y-auto py-2 px-2">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-6 w-6 border-2 border-indigo-400/30 border-t-indigo-400" />
          </div>
        ) : sessions.length === 0 ? (
          <div className="px-4 py-12 text-center">
            <MessageSquare className="w-6 h-6 text-slate-600 mx-auto mb-2" />
            <p className="text-xs text-slate-500">Chưa có phiên trò chuyện</p>
            <button
              onClick={() => { handleCreate(); onNewSession(); }}
              className="mt-2 text-xs text-indigo-400 hover:text-indigo-300 transition-colors cursor-pointer"
            >
              Tạo phiên mới
            </button>
          </div>
        ) : (
          <div className="space-y-0.5">
            {sessions.map((session) => (
              <div
                key={session.id}
                onClick={() => onSelect(session.id)}
                className={`
                  group relative cursor-pointer
                  ${currentSessionId === session.id
                    ? "bg-indigo-500/10 border-l-4 border-indigo-500"
                    : "hover:bg-white/[0.04] border-l-4 border-transparent"
                  }
                  px-3 py-2.5 rounded-r-lg transition-all
                `}
              >
                <div className="pr-6">
                  <p className={`text-xs truncate font-medium leading-normal ${
                    currentSessionId === session.id ? "text-indigo-400" : "text-slate-400 group-hover:text-slate-300"
                  }`}>
                    {session.title || "Cuộc trò chuyện mới"}
                  </p>
                  <p className={`text-[10px] mt-0.5 ${
                    currentSessionId === session.id ? "text-indigo-400/60" : "text-slate-500"
                  }`}>
                    {formatDate(session.updated_at)}
                  </p>
                </div>
                <button
                  onClick={(e) => handleDelete(session.id, e)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 p-1 rounded-lg hover:bg-red-500/10 text-slate-500 hover:text-red-400 transition-all cursor-pointer"
                  title="Xóa phiên"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}