"use client";

import { useState, useEffect } from "react";
import ProtectedRoute from "@/components/ProtectedRoute";
import { getPayload } from "@/lib/auth";
import { getStats, StatsData } from "@/lib/stats";
import {
  PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend,
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
} from "recharts";

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

const STATUS_COLORS: Record<string, string> = {
  pending: "#94a3b8",
  processing: "#60a5fa",
  pending_review: "#fbbf24",
  processed: "#34d399",
  error: "#f87171",
};

const ROLE_COLORS: Record<string, string> = {
  admin: "#8b5cf6",
  can_bo: "#3b82f6",
  lanh_dao: "#f59e0b",
  nguoi_dung: "#6b7280",
};

const FEATURE_COLORS: Record<string, string> = {
  "Hỏi đáp": "#3b82f6",
  "Hỏi tài liệu": "#10b981",
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

  const docPieData = stats
    ? Object.entries(stats.docs_by_status)
        .filter(([, v]) => v > 0)
        .map(([k, v]) => ({ name: STATUS_LABELS[k] ?? k, value: v, color: STATUS_COLORS[k] ?? "#94a3b8" }))
    : [];

  const featurePieData = stats
    ? Object.entries(stats.feature_usage)
        .filter(([, v]) => v > 0)
        .map(([k, v]) => ({ name: k, value: v, color: FEATURE_COLORS[k] ?? "#6b7280" }))
    : [];

  const sessionsByRoleData = stats
    ? Object.entries(stats.sessions_by_role).map(([k, v]) => ({
        name: ROLE_LABELS[k] ?? k,
        "Số phiên": v,
        fill: ROLE_COLORS[k] ?? "#6b7280",
      }))
    : [];

  const questionsByRoleData = stats
    ? Object.entries(stats.questions_by_role).map(([k, v]) => ({
        name: ROLE_LABELS[k] ?? k,
        "Câu hỏi": v,
        fill: ROLE_COLORS[k] ?? "#6b7280",
      }))
    : [];

  return (
    <ProtectedRoute>
      <section className="p-8">
        {!allowed ? (
          <p className="text-center text-red-600">Bạn không có quyền truy cập trang này.</p>
        ) : (
          <>
            <h1 className="text-2xl font-bold mb-6">Thống kê hệ thống</h1>

            {error && <p className="text-red-600 mb-4">{error}</p>}

            {stats && (
              <div className="space-y-8">
                {/* Overview cards */}
                <div className="grid grid-cols-2 gap-4">
                  <Card label="Tổng tài liệu" value={stats.total_docs} icon="📄" />
                  <Card label="Tổng người dùng" value={stats.total_users} icon="👥" />
                </div>

                {/* Row 1: Pie charts */}
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  {/* Pie chart — Documents by status */}
                  <div className="bg-white rounded-lg border border-gray-200 p-5">
                    <h2 className="text-lg font-semibold mb-4">Tài liệu theo trạng thái</h2>
                    {docPieData.length > 0 ? (
                      <ResponsiveContainer width="100%" height={280}>
                        <PieChart>
                          <Pie
                            data={docPieData}
                            cx="50%"
                            cy="50%"
                            innerRadius={55}
                            outerRadius={95}
                            paddingAngle={3}
                            dataKey="value"
                            label={({ name, percent }: { name?: string; percent?: number }) =>
                              `${name ?? ""} ${((percent ?? 0) * 100).toFixed(0)}%`
                            }
                          >
                            {docPieData.map((entry, i) => (
                              <Cell key={i} fill={entry.color} />
                            ))}
                          </Pie>
                          <Tooltip />
                          <Legend />
                        </PieChart>
                      </ResponsiveContainer>
                    ) : (
                      <p className="text-gray-400 text-center py-12">Chưa có dữ liệu</p>
                    )}
                  </div>

                  {/* Pie chart — Feature usage */}
                  <div className="bg-white rounded-lg border border-gray-200 p-5">
                    <h2 className="text-lg font-semibold mb-4">Chức năng sử dụng</h2>
                    {featurePieData.length > 0 ? (
                      <ResponsiveContainer width="100%" height={280}>
                        <PieChart>
                          <Pie
                            data={featurePieData}
                            cx="50%"
                            cy="50%"
                            innerRadius={55}
                            outerRadius={95}
                            paddingAngle={3}
                            dataKey="value"
                            label={({ name, percent }: { name?: string; percent?: number }) =>
                              `${name ?? ""} ${((percent ?? 0) * 100).toFixed(0)}%`
                            }
                          >
                            {featurePieData.map((entry, i) => (
                              <Cell key={i} fill={entry.color} />
                            ))}
                          </Pie>
                          <Tooltip />
                          <Legend />
                        </PieChart>
                      </ResponsiveContainer>
                    ) : (
                      <p className="text-gray-400 text-center py-12">Chưa có dữ liệu</p>
                    )}
                  </div>
                </div>

                {/* Row 2: Bar charts by role */}
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  {/* Bar chart — Sessions by role */}
                  <div className="bg-white rounded-lg border border-gray-200 p-5">
                    <h2 className="text-lg font-semibold mb-4">Phiên trao đổi theo vai trò</h2>
                    {sessionsByRoleData.length > 0 ? (
                      <ResponsiveContainer width="100%" height={280}>
                        <BarChart data={sessionsByRoleData} barSize={40}>
                          <CartesianGrid strokeDasharray="3 3" vertical={false} />
                          <XAxis dataKey="name" />
                          <YAxis allowDecimals={false} />
                          <Tooltip />
                          <Bar dataKey="Số phiên" radius={[6, 6, 0, 0]}>
                            {sessionsByRoleData.map((entry, i) => (
                              <Cell key={i} fill={entry.fill} />
                            ))}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    ) : (
                      <p className="text-gray-400 text-center py-12">Chưa có dữ liệu</p>
                    )}
                  </div>

                  {/* Bar chart — Questions by role */}
                  <div className="bg-white rounded-lg border border-gray-200 p-5">
                    <h2 className="text-lg font-semibold mb-4">Câu hỏi theo vai trò</h2>
                    {questionsByRoleData.length > 0 ? (
                      <ResponsiveContainer width="100%" height={280}>
                        <BarChart data={questionsByRoleData} barSize={40}>
                          <CartesianGrid strokeDasharray="3 3" vertical={false} />
                          <XAxis dataKey="name" />
                          <YAxis allowDecimals={false} />
                          <Tooltip />
                          <Bar dataKey="Câu hỏi" radius={[6, 6, 0, 0]}>
                            {questionsByRoleData.map((entry, i) => (
                              <Cell key={i} fill={entry.fill} />
                            ))}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    ) : (
                      <p className="text-gray-400 text-center py-12">Chưa có dữ liệu</p>
                    )}
                  </div>
                </div>
              </div>
            )}
          </>
        )}
      </section>
    </ProtectedRoute>
  );
}

function Card({ label, value, icon }: { label: string; value: number; icon: string }) {
  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4 flex items-center gap-3">
      <span className="text-2xl">{icon}</span>
      <div>
        <p className="text-2xl font-bold text-[#1f6f5f]">{value}</p>
        <p className="text-sm text-gray-500">{label}</p>
      </div>
    </div>
  );
}
