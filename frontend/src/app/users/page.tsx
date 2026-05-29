"use client";

import { useState, useEffect } from "react";
import ProtectedRoute from "@/components/ProtectedRoute";
import { getUsers, updateUserRole, UserItem } from "@/lib/users";
import Pagination from "@/components/Pagination";
import { Users, ShieldAlert, Loader2 } from "lucide-react";

const ROLE_LABELS: Record<string, string> = {
  admin: "Admin",
  can_bo: "Cán bộ",
  nguoi_dung: "Người dùng",
};

export default function UsersPage() {
  const [users, setUsers] = useState<UserItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [updating, setUpdating] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const pageSize = 15;

  const loadUsers = async (p: number) => {
    try {
      setLoading(true);
      const data = await getUsers(p, pageSize);
      setUsers(data.items ?? []);
      setTotal(data.total ?? 0);
    } catch {
      setError("Không thể tải danh sách người dùng.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadUsers(page);
  }, [page]);

  const handleRoleChange = async (user: UserItem, newRole: string) => {
    if (newRole === user.role) return;
    setUpdating(user.id);
    setError("");
    try {
      await updateUserRole(user.id, newRole);
      await loadUsers(page);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Lỗi cập nhật vai trò.");
    } finally {
      setUpdating(null);
    }
  };

  return (
    <ProtectedRoute requiredRole="admin">
      <div className="flex-1 overflow-y-auto px-8 py-8 w-full max-w-4xl mx-auto select-none font-sans">
        
        {/* Header Toolbar */}
        <div className="flex flex-col gap-1 mb-8">
          <h1 className="text-3xl font-outfit font-bold text-neon-gradient tracking-tight">
            Quản Lý Người Dùng
          </h1>
          <p className="text-xs text-slate-400 font-medium">
            Quản lý quyền hạn truy cập của cán bộ và thành viên trong hệ thống.
          </p>
        </div>

        {/* Error notification */}
        {error && (
          <div className="bg-rose-500/10 border border-rose-500/20 text-rose-455 text-xs font-bold rounded-2xl px-4 py-3 mb-5 flex items-center gap-2 animate-pulse">
            <ShieldAlert className="w-4 h-4 text-rose-500" />
            <span>{error}</span>
          </div>
        )}

        {/* User table grid */}
        {loading ? (
          <div className="flex items-center justify-center py-24 gap-3">
            <Loader2 className="animate-spin h-7 w-7 text-indigo-400" />
            <span className="text-slate-400 text-xs font-bold">Đang tải danh sách thành viên...</span>
          </div>
        ) : (
          <div className="glass-panel rounded-2xl overflow-hidden shadow-2xl flex flex-col w-full">
            {/* Table Header */}
            <div className="grid grid-cols-12 gap-4 px-6 py-3.5 bg-white/5 border-b border-white/10 select-none">
              <div className="col-span-5 text-[10px] uppercase font-black tracking-widest text-slate-400">Tên đăng nhập</div>
              <div className="col-span-3 text-[10px] uppercase font-black tracking-widest text-slate-400">Vai trò hiện tại</div>
              <div className="col-span-4 text-[10px] uppercase font-black tracking-widest text-slate-400 text-right pr-6">Cập nhật vai trò</div>
            </div>

            {/* Table Body */}
            <div className="flex-1 overflow-y-auto divide-y divide-white/5 bg-[#2a3148]/10 max-h-[calc(100vh-320px)] scrollbar-thin">
              {users.map((user) => (
                <div
                  key={user.id}
                  className="grid grid-cols-12 gap-4 px-6 py-4 items-center glass-card hover:z-10 group"
                >
                  <div className="col-span-5 font-bold text-slate-200 text-xs flex items-center gap-2">
                    <Users className="w-4 h-4 text-indigo-400" />
                    <span>{user.username}</span>
                  </div>
                  
                  <div className="col-span-3">
                    <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold ${
                      user.role === "admin"
                        ? "bg-purple-500/10 text-purple-400 border border-purple-500/20"
                        : user.role === "can_bo"
                          ? "bg-indigo-500/10 text-indigo-400 border border-indigo-500/20"
                          : "bg-slate-500/10 text-slate-400 border border-slate-500/20"
                    }`}>
                      <span className={`w-1.5 h-1.5 rounded-full ${
                        user.role === "admin" ? "bg-purple-500" : user.role === "can_bo" ? "bg-indigo-500" : "bg-slate-400"
                      }`} />
                      {ROLE_LABELS[user.role] ?? user.role}
                    </span>
                  </div>

                  <div className="col-span-4 flex justify-end pr-6">
                    {user.role === "admin" ? (
                      <span className="text-[10px] text-slate-400 font-bold bg-[#222840]/60 px-2.5 py-1 rounded-lg select-none">
                        Quản trị viên tối cao
                      </span>
                    ) : (
                      <select
                        value={user.role}
                        disabled={updating === user.id}
                        onChange={(e) => handleRoleChange(user, e.target.value)}
                        className="w-full max-w-[160px] px-3.5 py-1.5 rounded-xl border border-white/10 bg-[#222840]/60 text-slate-100 text-xs font-bold shadow-soft transition-all duration-300 outline-none focus:border-indigo-500 focus:ring-4 focus:ring-indigo-500/10 disabled:opacity-50 cursor-pointer"
                      >
                        <option value="nguoi_dung" className="bg-[#2a3148] text-slate-100">Người dùng</option>
                        <option value="can_bo" className="bg-[#2a3148] text-slate-100">Cán bộ</option>
                      </select>
                    )}
                  </div>
                </div>
              ))}
            </div>

            {/* Pagination Footer */}
            <div className="px-5 py-3.5 bg-white/5 border-t border-white/10 flex items-center justify-between">
              <span className="text-[10px] text-slate-400 font-bold">
                Hiển thị {users.length} của {total} người dùng
              </span>
              <Pagination page={page} total={total} pageSize={pageSize} onPageChange={setPage} />
            </div>
          </div>
        )}

      </div>
    </ProtectedRoute>
  );
}
