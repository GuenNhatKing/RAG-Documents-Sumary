"use client";

import { useState, useEffect } from "react";
import ProtectedRoute from "@/components/ProtectedRoute";
import { getPayload } from "@/lib/auth";
import { getStats, StatsData } from "@/lib/stats";

const STATUS_LABELS: Record<string, string> = {
  pending: "Chờ xử lý",
  processing: "Đang xử lý",
  pending_review: "Chờ duyệt",
  processed: "Hoàn thành",
  error: "Lỗi",
};

const ROLE_LABELS: Record<string, string> = {
  admin: "Admin",
  can_bo: "Cán bộ",
  lanh_dao: "Lãnh đạo",
  nguoi_dung: "Người dùng",
};

export default function StatsPage() {
  const [allowed, setAllowed] = useState(false);
  const [checked, setChecked] = useState(false);
  const [stats, setStats] = useState<StatsData | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const payload = getPayload();
    const ok = !!payload && payload.role === "admin";
    setAllowed(ok);
    setChecked(true);
    if (ok) {
      getStats()
        .then(setStats)
        .catch(() => setError("Không thể tải dữ liệu thống kê."));
    }
  }, []);

  if (!checked) return null;

  return (
    <ProtectedRoute>
      <section className="p-8">
        {allowed ? (
          <>
            <h1 className="text-2xl font-bold mb-6">Thống kê hệ thống</h1>

            {error && (
              <p className="text-red-600 mb-4">{error}</p>
            )}

            {stats && (
              <div className="space-y-8">
                {/* Overview cards */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <Card label="Tổng tài liệu" value={stats.total_docs} />
                  <Card label="Tổng người dùng" value={stats.total_users} />
                  <Card label="Tổng phiên chat" value={stats.total_sessions} />
                  <Card label="Tổng câu hỏi" value={stats.total_questions} />
                </div>

                {/* Documents by status */}
                <div>
                  <h2 className="text-lg font-semibold mb-3">Tài liệu theo trạng thái</h2>
                  <div className="bg-white rounded-lg border border-gray-200 divide-y">
                    {Object.entries(stats.docs_by_status).map(([status, count]) => (
                      <div key={status} className="flex justify-between px-4 py-2.5">
                        <span className="text-gray-700">{STATUS_LABELS[status] || status}</span>
                        <span className="font-medium">{count}</span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Users by role */}
                <div>
                  <h2 className="text-lg font-semibold mb-3">Người dùng theo vai trò</h2>
                  <div className="bg-white rounded-lg border border-gray-200 divide-y">
                    {Object.entries(stats.users_by_role).map(([role, count]) => (
                      <div key={role} className="flex justify-between px-4 py-2.5">
                        <span className="text-gray-700">{ROLE_LABELS[role] || role}</span>
                        <span className="font-medium">{count}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </>
        ) : (
          <p className="text-center text-red-600">
            Bạn không có quyền truy cập trang này.
          </p>
        )}
      </section>
    </ProtectedRoute>
  );
}

function Card({ label, value }: { label: string; value: number }) {
  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4 text-center">
      <p className="text-2xl font-bold text-[#1f6f5f]">{value}</p>
      <p className="text-sm text-gray-500 mt-1">{label}</p>
    </div>
  );
}
