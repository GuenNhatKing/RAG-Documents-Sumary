"use client";

import { useState, useEffect } from "react";
import ProtectedRoute from "@/components/ProtectedRoute";
import { getUsers, updateUserRole, UserItem } from "@/lib/users";

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

  const loadUsers = async () => {
    try {
      setLoading(true);
      setUsers(await getUsers());
    } catch {
      setError("Không thể tải danh sách người dùng.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadUsers();
  }, []);

  const handleRoleChange = async (user: UserItem, newRole: string) => {
    if (newRole === user.role) return;
    setUpdating(user.id);
    setError("");
    try {
      await updateUserRole(user.id, newRole);
      await loadUsers();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Lỗi cập nhật vai trò.");
    } finally {
      setUpdating(null);
    }
  };

  return (
    <ProtectedRoute requiredRole="admin">
      <section className="p-8 max-w-3xl mx-auto">
        <h1 className="text-2xl font-bold mb-6">Quản lý người dùng</h1>

        {error && <p className="text-red-600 mb-4">{error}</p>}

        {loading ? (
          <p className="text-gray-500">Đang tải...</p>
        ) : (
          <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
            <table className="w-full text-left">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="px-4 py-3 text-sm font-medium text-gray-600">Tên đăng nhập</th>
                  <th className="px-4 py-3 text-sm font-medium text-gray-600">Vai trò hiện tại</th>
                  <th className="px-4 py-3 text-sm font-medium text-gray-600">Đổi vai trò</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {users.map((user) => (
                  <tr key={user.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 text-gray-900">{user.username}</td>
                    <td className="px-4 py-3">
                      <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${
                        user.role === "admin"
                          ? "bg-purple-100 text-purple-700"
                          : user.role === "can_bo"
                            ? "bg-blue-100 text-blue-700"
                            : "bg-gray-100 text-gray-700"
                      }`}>
                        {ROLE_LABELS[user.role] ?? user.role}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      {user.role === "admin" ? (
                        <span className="text-xs text-gray-400">Không thể thay đổi</span>
                      ) : (
                        <select
                          value={user.role}
                          disabled={updating === user.id}
                          onChange={(e) => handleRoleChange(user, e.target.value)}
                          className="border border-gray-300 rounded px-2 py-1 text-sm bg-white disabled:opacity-50"
                        >
                          <option value="nguoi_dung">Người dùng</option>
                          <option value="can_bo">Cán bộ</option>
                        </select>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </ProtectedRoute>
  );
}
