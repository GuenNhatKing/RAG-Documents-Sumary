"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import ProtectedRoute from "@/components/ProtectedRoute";
import { getDocuments, deleteDocument, renameDocument, type DocumentItem } from "@/lib/documents";
import Pagination from "@/components/Pagination";
import { 
  FileText, 
  Lock, 
  Edit2, 
  Eye, 
  Edit3, 
  Trash2, 
  Plus, 
  HardDrive, 
  CheckCircle2, 
  Clock, 
  AlertCircle, 
  Loader2 
} from "lucide-react";

const statusConfig: Record<string, { label: string; color: string; dot: string }> = {
  pending: { 
    label: "Chờ xử lý", 
    color: "bg-white/5 text-slate-300 border border-white/10", 
    dot: "bg-slate-400" 
  },
  processing: { 
    label: "Đang xử lý", 
    color: "bg-amber-500/10 text-amber-500 border border-amber-500/20", 
    dot: "bg-amber-500 animate-pulse" 
  },
  pending_review: { 
    label: "Chờ review", 
    color: "bg-emerald-500/10 dark:bg-indigo-500/10 text-emerald-400 dark:text-indigo-400 border border-emerald-500/20 dark:border-indigo-500/20", 
    dot: "bg-emerald-400 dark:bg-indigo-400" 
  },
  processed: { 
    label: "Hoàn thành", 
    color: "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20", 
    dot: "bg-emerald-400" 
  },
  vector_processed: { 
    label: "Hoàn thành (Vector DB)", 
    color: "bg-indigo-500/10 text-indigo-400 border border-indigo-500/20", 
    dot: "bg-indigo-400" 
  },
  error: { 
    label: "Lỗi", 
    color: "bg-rose-500/10 text-rose-400 border border-rose-500/20", 
    dot: "bg-rose-450" 
  },
};

export default function FilesPage() {
  const [docs, setDocs] = useState<DocumentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState("");
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const pageSize = 15;

  const loadDocs = useCallback(async (p: number) => {
    setLoading(true);
    try {
      const data = await getDocuments(p, pageSize);
      setDocs(data.items ?? []);
      setTotal(data.total ?? 0);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDocs(page);
  }, [loadDocs, page]);

  const handleRenameStart = (docId: string, currentName: string) => {
    setEditingId(docId);
    setEditingName(currentName);
  };

  const handleRenameSave = async (docId: string) => {
    const trimmed = editingName.trim();
    if (!trimmed) {
      setEditingId(null);
      return;
    }
    const ok = await renameDocument(docId, trimmed);
    if (ok) {
      setDocs((prev) =>
        prev.map((d) => (d.id === docId ? { ...d, filename: trimmed } : d))
      );
    } else {
      alert("Đổi tên thất bại.");
    }
    setEditingId(null);
  };

  const handleRenameKeyDown = (e: React.KeyboardEvent, docId: string) => {
    if (e.key === "Enter") handleRenameSave(docId);
    if (e.key === "Escape") setEditingId(null);
  };

  const handleDelete = async (docId: string, filename: string) => {
    if (!confirm(`Xác nhận xóa tài liệu "${filename}"?`)) return;
    const ok = await deleteDocument(docId);
    if (ok) {
      loadDocs(page);
    } else {
      alert("Xóa thất bại.");
    }
  };

  const formatDate = (iso: string) => {
    try {
      return new Date(iso.endsWith("Z") ? iso : iso + "Z").toLocaleDateString("vi-VN", {
        day: "2-digit",
        month: "2-digit",
        year: "numeric"
      });
    } catch {
      return iso;
    }
  };

  // Metrics counters
  const countProcessed = docs.filter(d => d.status === "processed" || d.status === "vector_processed").length;
  const countPending = docs.filter(d => d.status === "pending" || d.status === "processing").length;
  const countErrors = docs.filter(d => d.status === "error").length;

  return (
    <ProtectedRoute requiredRole={["admin", "can_bo"]}>
      <div className="flex-1 overflow-y-auto px-8 py-8 w-full max-w-6xl mx-auto select-none font-sans">
        
        {/* Header Toolbar */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-3xl font-outfit font-bold text-neon-gradient tracking-tight">
              Quản Lý Tài Liệu
            </h1>
            <p className="text-xs text-muted font-medium mt-1">
              Tổng hợp và quản lý tài nguyên trích xuất tri thức của hệ thống.
            </p>
          </div>
          
          <Link
            href="/upload"
            className="px-5 py-2.5 btn-primary text-xs cursor-pointer flex items-center gap-1.5"
          >
            <Plus className="w-4 h-4" />
            Tải lên tài liệu
          </Link>
        </div>

        {/* Content panel */}
        {loading ? (
          <div className="flex items-center justify-center py-24 gap-3">
            <Loader2 className="animate-spin h-7 w-7 text-emerald-400 dark:text-indigo-400" />
            <span className="text-muted text-xs font-bold">Đang tải danh sách tài liệu...</span>
          </div>
        ) : docs.length === 0 ? (
          <div className="text-center py-20 rounded-2xl glass-panel">
            <FileText className="mx-auto h-12 w-12 text-slate-500 mb-4 animate-pulse" />
            <p className="text-muted font-bold text-sm">Chưa có tài liệu nào trong thư viện.</p>
          </div>
        ) : (
          <div className="glass-panel rounded-2xl overflow-hidden shadow-2xl flex flex-col w-full">
            {/* Table Header */}
            <div className="grid grid-cols-12 gap-4 px-6 py-3.5 bg-secondary border-b border-theme select-none">
              <div className="col-span-5 text-[10px] uppercase font-black tracking-widest text-muted">Tên file</div>
              <div className="col-span-2 text-[10px] uppercase font-black tracking-widest text-muted">Trạng thái</div>
              <div className="col-span-2 text-[10px] uppercase font-black tracking-widest text-muted">Ngày tạo</div>
              <div className="col-span-3 text-[10px] uppercase font-black tracking-widest text-muted text-right pr-6">Thao tác</div>
            </div>

            {/* Table Body */}
            <div className="flex-1 overflow-y-auto divide-y divide-theme-light bg-tertiary max-h-[calc(100vh-320px)] scrollbar-thin">
              {docs.map((doc) => {
                const cfg = statusConfig[doc.status] ?? statusConfig.pending;
                return (
                  <div
                    key={doc.id}
                    className="grid grid-cols-12 gap-4 px-6 py-4 items-center glass-card hover:z-10 group"
                  >
                    <div className="col-span-5 font-bold text-primary text-xs">
                      {editingId === doc.id ? (
                        <div className="relative group max-w-sm flex items-center">
                          <input
                            type="text"
                            name="rename"
                            value={editingName}
                            onChange={(e) => setEditingName(e.target.value)}
                            onKeyDown={(e) => handleRenameKeyDown(e, doc.id)}
                            onBlur={() => handleRenameSave(doc.id)}
                            className="w-full px-3 py-1.5 rounded-xl border border-emerald-500 dark:border-indigo-500 bg-secondary text-primary text-xs outline-none focus:ring-4 focus:ring-emerald-500/10 dark:focus:ring-indigo-500/10 font-bold"
                            autoFocus
                          />
                        </div>
                      ) : (
                        <div className="flex items-center gap-2.5">
                          <FileText className="w-4 h-4 text-emerald-400 dark:text-indigo-400" />
                          <span
                            className="cursor-pointer hover:text-emerald-400 dark:hover:text-indigo-400 transition-colors truncate max-w-xs md:max-w-md"
                            title="Click để đổi tên"
                            onClick={() => handleRenameStart(doc.id, doc.filename)}
                          >
                            {doc.filename}
                          </span>
                        </div>
                      )}
                    </div>
                    
                    <div className="col-span-2">
                      <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-bold ${cfg.color}`}>
                        <span className={`w-1.5 h-1.5 rounded-full ${cfg.dot}`} />
                        {cfg.label}
                      </span>
                    </div>
                    
                    <div className="col-span-2 text-[10px] text-muted font-bold">
                      {formatDate(doc.created_at)}
                    </div>
                    
                    <div className="col-span-3 flex justify-end gap-1.5 pr-6">
                      {doc.status === "pending_review" && (
                        <Link
                          href={`/files/${doc.id}/review`}
                          className="p-1.5 hover:bg-emerald-500/10 dark:hover:bg-indigo-500/10 text-emerald-400 dark:text-indigo-400 rounded-xl hover:scale-105 active:scale-95 transition-all"
                          title="Review"
                        >
                          <Lock className="w-4 h-4" />
                        </Link>
                      )}
                      {doc.markdown_path && doc.status !== "pending" && doc.status !== "processing" && (
                        <Link
                          href={`/files/${doc.id}/review`}
                          className="p-1.5 hover:bg-amber-500/10 text-amber-500 rounded-xl hover:scale-105 active:scale-95 transition-all"
                          title="Chỉnh sửa Markdown"
                        >
                          <Edit2 className="w-4 h-4" />
                        </Link>
                      )}
                      {(doc.status === "processed" || doc.status === "vector_processed") && (
                        <Link
                          href={`/documents/${doc.id}/view`}
                          className="p-1.5 hover:bg-emerald-500/10 text-emerald-400 rounded-xl hover:scale-105 active:scale-95 transition-all"
                          title="Xem tài liệu"
                        >
                          <Eye className="w-4 h-4" />
                        </Link>
                      )}
                      <button
                        onClick={() => handleRenameStart(doc.id, doc.filename)}
                        className="p-1.5 hover:bg-emerald-500/10 dark:hover:bg-indigo-500/10 text-emerald-400 dark:text-indigo-400 rounded-xl hover:scale-105 active:scale-95 transition-all cursor-pointer border-none outline-none"
                        title="Đổi tên"
                      >
                        <Edit3 className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => handleDelete(doc.id, doc.filename)}
                        className="p-1.5 hover:bg-rose-500/10 text-rose-500 rounded-xl hover:scale-105 active:scale-95 transition-all cursor-pointer border-none outline-none"
                        title="Xóa"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Pagination Footer */}
            <div className="px-5 py-3.5 bg-secondary border-t border-theme flex items-center justify-between">
              <span className="text-[10px] text-muted font-bold">
                Hiển thị {docs.length} của {total} tài liệu
              </span>
              <Pagination page={page} total={total} pageSize={pageSize} onPageChange={setPage} />
            </div>
          </div>
        )}

        {/* Quick stats bottom area */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-8">
          
          <div className="rounded-2xl glass-card p-4 flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-emerald-500/10 dark:bg-indigo-500/10 text-emerald-400 dark:text-indigo-400 flex items-center justify-center">
              <HardDrive className="w-5 h-5" />
            </div>
            <div>
              <p className="text-[9px] uppercase font-black tracking-wider text-muted">Dung lượng sử dụng</p>
              <h4 className="text-xs font-black text-primary mt-0.5">1.2 GB / 5.0 GB</h4>
            </div>
          </div>

          <div className="rounded-2xl glass-card p-4 flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-emerald-550/10 text-emerald-400 flex items-center justify-center">
              <CheckCircle2 className="w-5 h-5" />
            </div>
            <div>
              <p className="text-[9px] uppercase font-black tracking-wider text-muted">Đã hoàn thành</p>
              <h4 className="text-xs font-black text-primary mt-0.5">{countProcessed} tệp tin</h4>
            </div>
          </div>

          <div className="rounded-2xl glass-card p-4 flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-amber-550/10 text-amber-400 flex items-center justify-center">
              <Clock className="w-5 h-5" />
            </div>
            <div>
              <p className="text-[9px] uppercase font-black tracking-wider text-muted">Đang chờ xử lý</p>
              <h4 className="text-xs font-black text-primary mt-0.5">{countPending} tệp tin</h4>
            </div>
          </div>

          <div className="rounded-2xl glass-card p-4 flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-rose-550/10 text-rose-450 flex items-center justify-center">
              <AlertCircle className="w-5 h-5" />
            </div>
            <div>
              <p className="text-[9px] uppercase font-black tracking-wider text-muted">Lỗi trích xuất</p>
              <h4 className="text-xs font-black text-primary mt-0.5">{countErrors} tệp tin</h4>
            </div>
          </div>

        </div>

      </div>
    </ProtectedRoute>
  );
}
