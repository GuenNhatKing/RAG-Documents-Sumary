"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import ProtectedRoute from "@/components/ProtectedRoute";
import { getDocuments, deleteDocument, renameDocument, type DocumentItem } from "@/lib/documents";
import Pagination from "@/components/Pagination";

const statusConfig: Record<string, { label: string; color: string }> = {
  pending: { label: "Chờ xử lý", color: "bg-gray-100 text-gray-600" },
  processing: { label: "Đang xử lý", color: "bg-yellow-100 text-yellow-700" },
  pending_review: { label: "Chờ review", color: "bg-blue-100 text-blue-700" },
  processed: { label: "Hoàn thành", color: "bg-green-100 text-green-700" },
  error: { label: "Lỗi", color: "bg-red-100 text-red-700" },
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
    const data = await getDocuments(p, pageSize);
    setDocs(data.items);
    setTotal(data.total);
    setLoading(false);
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
      return new Date(iso).toLocaleDateString("vi-VN", {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return iso;
    }
  };

  return (
    <ProtectedRoute requiredRole={["admin", "can_bo"]}>
      <div className="min-h-[calc(100vh-64px)] p-8">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold text-gray-800">Quản lý tài liệu</h1>
          <Link
            href="/upload"
            className="px-4 py-2 bg-[#2fa084] text-white rounded-lg hover:bg-[#2fa084]/90 text-sm font-medium"
          >
            + Upload mới
          </Link>
        </div>

        {loading ? (
          <p className="text-gray-500">Đang tải danh sách tài liệu…</p>
        ) : docs.length === 0 ? (
          <div className="text-center py-16 text-gray-400">
            <p className="text-lg">Chưa có tài liệu nào.</p>
          </div>
        ) : (
          <div className="bg-white rounded-lg shadow overflow-hidden">
            <table className="w-full text-left">
              <thead className="bg-gray-50 border-b">
                <tr>
                  <th className="px-4 py-3 text-sm font-medium text-gray-600">Tên file</th>
                  <th className="px-4 py-3 text-sm font-medium text-gray-600 w-32">Trạng thái</th>
                  <th className="px-4 py-3 text-sm font-medium text-gray-600 w-44">Ngày tạo</th>
                  <th className="px-4 py-3 text-sm font-medium text-gray-600 w-48">Thao tác</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {docs.map((doc) => {
                  const cfg = statusConfig[doc.status] ?? statusConfig.pending;
                  return (
                    <tr key={doc.id} className="hover:bg-gray-50 transition-colors">
                      <td className="px-4 py-3 text-sm text-gray-800">
                        {editingId === doc.id ? (
                          <input
                            type="text"
                            value={editingName}
                            onChange={(e) => setEditingName(e.target.value)}
                            onKeyDown={(e) => handleRenameKeyDown(e, doc.id)}
                            onBlur={() => handleRenameSave(doc.id)}
                            className="w-full px-2 py-1 border border-blue-400 rounded text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                            autoFocus
                          />
                        ) : (
                          <span
                            className="cursor-pointer hover:text-blue-600 truncate max-w-xs inline-block"
                            title="Nhấp để đổi tên"
                            onClick={() => handleRenameStart(doc.id, doc.filename)}
                          >
                            {doc.filename}
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${cfg.color}`}
                        >
                          {cfg.label}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-500">
                        {formatDate(doc.created_at)}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex gap-2">
                          {doc.status === "pending_review" && (
                            <Link
                              href={`/files/${doc.id}/review`}
                              className="px-3 py-1 bg-blue-50 text-blue-700 rounded text-xs hover:bg-blue-100"
                            >
                              Review
                            </Link>
                          )}
                          {doc.markdown_path && doc.status !== "pending" && doc.status !== "processing" && (
                            <Link
                              href={`/files/${doc.id}/review`}
                              className="px-3 py-1 bg-yellow-50 text-yellow-700 rounded text-xs hover:bg-yellow-100"
                            >
                              Sửa
                            </Link>
                          )}
                          {doc.status === "processed" && (
                            <Link
                              href={`/documents/${doc.id}/view`}
                              className="px-3 py-1 bg-green-50 text-green-700 rounded text-xs hover:bg-green-100"
                            >
                              Xem
                            </Link>
                          )}
                          <button
                            onClick={() => handleRenameStart(doc.id, doc.filename)}
                            className="px-3 py-1 bg-gray-100 text-gray-600 rounded text-xs hover:bg-gray-200"
                          >
                            Đổi tên
                          </button>
                          <button
                            onClick={() => handleDelete(doc.id, doc.filename)}
                            className="px-3 py-1 bg-red-50 text-red-600 rounded text-xs hover:bg-red-100"
                          >
                            Xóa
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        <Pagination page={page} total={total} pageSize={pageSize} onPageChange={setPage} />
      </div>
    </ProtectedRoute>
  );
}
