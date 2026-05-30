"use client";

import { useEffect, useState } from "react";
import { ChatSession, createSession, getSessions, deleteSession } from "@/lib/chat";
import { Plus, Trash2, MessageSquare, History } from "lucide-react";

interface SessionListProps {
  docId: string;
  currentSessionId?: string;
  onSelect: (sessionId: string) => void;
  onNewSession: () => void;
  refreshTrigger?: number;
}

export default function SessionList({
  docId,
  currentSessionId,
  onSelect,
  onNewSession,
  refreshTrigger,
}: SessionListProps) {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadSessions();
  }, [docId, refreshTrigger]);

  const loadSessions = async () => {
    setLoading(true);
    try {
      const data = await getSessions(docId);
      setSessions(data);
      if (data.length > 0) {
        const hasCurrent = data.some((s) => s.id === currentSessionId);
        if (!currentSessionId || !hasCurrent) {
          onSelect(data[0].id);
        }
      } else {
        onSelect("");
      }
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
    const d = new Date(dateStr.endsWith("Z") ? dateStr : dateStr + "Z");
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

  const getGroupedSessions = () => {
    const today: ChatSession[] = [];
    const yesterday: ChatSession[] = [];
    const last7Days: ChatSession[] = [];
    const older: ChatSession[] = [];

    const now = new Date();
    const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const startOfYesterday = new Date(startOfToday.getTime() - 24 * 60 * 60 * 1000);
    const startOf7DaysAgo = new Date(startOfToday.getTime() - 7 * 24 * 60 * 60 * 1000);

    sessions.forEach((session) => {
      const d = new Date(session.updated_at.endsWith("Z") ? session.updated_at : session.updated_at + "Z");
      if (d >= startOfToday) {
        today.push(session);
      } else if (d >= startOfYesterday) {
        yesterday.push(session);
      } else if (d >= startOf7DaysAgo) {
        last7Days.push(session);
      } else {
        older.push(session);
      }
    });

    return { today, yesterday, last7Days, older };
  };

  const grouped = getGroupedSessions();

  const renderSessionItem = (session: ChatSession) => {
    const isActive = currentSessionId === session.id;
    return (
      <div
        key={session.id}
        onClick={() => onSelect(session.id)}
        className={`
          group relative cursor-pointer my-1 px-3 py-2.5 rounded-xl transition-all duration-200 flex items-start gap-3
          ${isActive
            ? "bg-emerald-500/10 dark:bg-indigo-500/15 border border-emerald-500/20 dark:border-indigo-500/30 shadow-sm"
            : "hover:bg-slate-500/5 dark:hover:bg-slate-500/10 border border-transparent hover:border-slate-500/10 dark:hover:border-slate-500/20"
          }
        `}
      >
        <MessageSquare className={`w-4 h-4 mt-0.5 flex-shrink-0 transition-colors duration-200 ${
          isActive 
            ? "text-emerald-600 dark:text-indigo-400" 
            : "text-slate-400 dark:text-slate-500 group-hover:text-slate-600 dark:group-hover:text-slate-400"
        }`} />
        
        <div className="flex-1 min-w-0 pr-6">
          <p className={`text-sm truncate font-medium leading-normal transition-colors duration-200 ${
            isActive 
              ? "text-emerald-950 dark:text-indigo-200 font-semibold" 
              : "text-slate-700 dark:text-slate-300 group-hover:text-slate-900 dark:group-hover:text-slate-100"
          }`}>
            {session.title || "Cuộc trò chuyện mới"}
          </p>
          <span className={`text-[10px] block mt-0.5 transition-colors duration-200 ${
            isActive 
              ? "text-emerald-700/80 dark:text-indigo-400/80" 
              : "text-slate-400 dark:text-slate-500"
          }`}>
            {formatDate(session.updated_at)}
          </span>
        </div>
        
        <button
          onClick={(e) => handleDelete(session.id, e)}
          className="absolute right-2 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 p-1.5 rounded-lg hover:bg-red-500/10 text-slate-400 hover:text-red-500 transition-all duration-150 cursor-pointer border-none outline-none"
          title="Xóa phiên"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      </div>
    );
  };

  return (
    <div className="flex flex-col h-full bg-slate-50/30 dark:bg-slate-950/40">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3.5 border-b border-theme-light bg-slate-100/40 dark:bg-slate-950/60">
        <div className="flex items-center gap-2">
          <History className="w-4.5 h-4.5 text-emerald-500 dark:text-indigo-400" />
          <h3 className="text-xs font-bold text-slate-700 dark:text-slate-300 uppercase tracking-wider">
            Lịch sử trò chuyện
          </h3>
        </div>
      </div>

      {/* Prominent Action Button for Creating Chat */}
      <div className="p-3">
        <button
          onClick={handleCreate}
          className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold text-white bg-gradient-to-r from-emerald-600 to-emerald-500 hover:from-emerald-500 hover:to-emerald-400 dark:from-indigo-600 dark:to-indigo-500 dark:hover:from-indigo-500 dark:hover:to-indigo-400 transition-all duration-200 shadow-md shadow-emerald-500/10 dark:shadow-indigo-500/10 cursor-pointer hover:scale-[1.02]"
        >
          <Plus className="w-4 h-4" />
          Tạo cuộc trò chuyện mới
        </button>
      </div>

      {/* Session list */}
      <div className="flex-1 overflow-y-auto px-3 pb-4">
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-6 w-6 border-2 border-emerald-400/30 dark:border-indigo-400/30 border-t-emerald-400 dark:border-t-indigo-400" />
          </div>
        ) : sessions.length === 0 ? (
          <div className="px-4 py-12 text-center">
            <MessageSquare className="w-6 h-6 text-slate-300 dark:text-slate-600 mx-auto mb-2.5" />
            <p className="text-xs text-slate-400 dark:text-slate-500 font-medium">Chưa có cuộc trò chuyện nào</p>
          </div>
        ) : (
          <div className="space-y-4">
            {grouped.today.length > 0 && (
              <div>
                <h4 className="text-[10px] font-bold tracking-widest text-slate-400 dark:text-slate-500 uppercase px-3 py-1.5 select-none">
                  Hôm nay
                </h4>
                <div className="space-y-0.5">
                  {grouped.today.map(renderSessionItem)}
                </div>
              </div>
            )}

            {grouped.yesterday.length > 0 && (
              <div>
                <h4 className="text-[10px] font-bold tracking-widest text-slate-400 dark:text-slate-500 uppercase px-3 py-1.5 select-none">
                  Hôm qua
                </h4>
                <div className="space-y-0.5">
                  {grouped.yesterday.map(renderSessionItem)}
                </div>
              </div>
            )}

            {grouped.last7Days.length > 0 && (
              <div>
                <h4 className="text-[10px] font-bold tracking-widest text-slate-400 dark:text-slate-500 uppercase px-3 py-1.5 select-none">
                  7 ngày qua
                </h4>
                <div className="space-y-0.5">
                  {grouped.last7Days.map(renderSessionItem)}
                </div>
              </div>
            )}

            {grouped.older.length > 0 && (
              <div>
                <h4 className="text-[10px] font-bold tracking-widest text-slate-400 dark:text-slate-500 uppercase px-3 py-1.5 select-none">
                  Cũ hơn
                </h4>
                <div className="space-y-0.5">
                  {grouped.older.map(renderSessionItem)}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
