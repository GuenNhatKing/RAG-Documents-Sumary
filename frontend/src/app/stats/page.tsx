"use client";

import { useState, useEffect } from "react";
import ProtectedRoute from "@/components/ProtectedRoute";
import { getPayload } from "@/lib/auth";
import { getStats, StatsData } from "@/lib/stats";
import { FileText, Users as UsersIcon, ShieldAlert, Loader2 } from "lucide-react";
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
  nguoi_dung: "Người dùng",
};

const STATUS_COLORS: Record<string, string> = {
  pending: "#38bdf8",          // vibrant sky blue
  processing: "#fbbf24",       // vibrant amber
  pending_review: "#c084fc",   // vibrant purple
  processed: "#34d399",        // vibrant emerald
  error: "#f87171",            // vibrant red
};

const ROLE_COLORS: Record<string, string> = {
  admin: "#a855f7",            // purple
  can_bo: "#818cf8",           // indigo
  nguoi_dung: "#c3c0ff",       // soft lavender (Stitch primary)
};

const FEATURE_COLORS: Record<string, string> = {
  "Hỏi đáp": "#c3c0ff",
  "Hỏi tài liệu": "#34d399",
};

export default function StatsPage() {
  const [allowed, setAllowed] = useState(false);
  const [checked, setChecked] = useState(false);
  const [stats, setStats] = useState<StatsData | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const payload = getPayload();
    const ok = !!payload && payload.role === "admin";
    setAllowed(ok);
    setChecked(true);
    if (ok) {
      setLoading(true);
      getStats()
        .then(setStats)
        .catch(() => setError("Không thể tải dữ liệu thống kê."))
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
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
    <ProtectedRoute requiredRole="admin">
      <div className="flex-1 overflow-y-auto px-8 py-8 w-full max-w-6xl mx-auto select-none">
        
        {/* Header */}
        <div className="flex flex-col gap-1 mb-8">
          <h1 className="text-3xl font-black text-neon-gradient tracking-tight">
            Thống Kê Hệ Thống
          </h1>
          <p className="text-xs text-muted font-bold">
            Phân tích số liệu tài nguyên, lưu lượng truy cập và hoạt động hỏi đáp.
          </p>
        </div>

        {/* Access denied */}
        {!allowed && (
          <div className="bg-rose-500/10 border border-rose-500/20 text-rose-600 text-rose-500 text-xs font-bold rounded-2xl px-4 py-3 flex items-center gap-2">
            <ShieldAlert className="w-4 h-4 text-rose-500" />
            <span>Bạn không có quyền quản trị tối cao để xem báo cáo phân tích này.</span>
          </div>
        )}

        {/* System statistics */}
        {allowed && (
          <>
            {error && (
              <div className="bg-rose-500/10 border border-rose-500/20 text-rose-600 text-rose-500 text-xs font-bold rounded-2xl px-4 py-3 mb-5 flex items-center gap-2 animate-fade-in">
                <ShieldAlert className="w-4 h-4 text-rose-500" />
                <span>{error}</span>
              </div>
            )}

            {loading ? (
              <div className="flex items-center justify-center py-24 gap-3">
                <Loader2 className="animate-spin h-7 w-7 text-emerald-500 dark:text-indigo-500" />
                <span className="text-muted text-xs font-bold">Đang tải dữ liệu phân tích...</span>
              </div>
            ) : stats && (
              <div className="space-y-8 animate-fade-in">
                
                {/* Overview cards */}
                <div className="grid grid-cols-2 gap-6">
                  
                  <div className="glass-card rounded-2xl p-6 flex items-center gap-4 hover:-translate-y-0.5 transition-all duration-300">
                    <div className="w-12 h-12 rounded-2xl bg-emerald-500/10 dark:bg-indigo-500/10 text-emerald-500 dark:text-indigo-500 flex items-center justify-center">
                      <FileText className="w-6 h-6" />
                    </div>
                    <div>
                      <p className="text-[10px] uppercase font-black tracking-widest text-muted">Tổng tài liệu</p>
                      <h4 className="text-2xl font-black text-primary mt-1 leading-none">{stats.total_docs}</h4>
                    </div>
                  </div>

                  <div className="glass-card rounded-2xl p-6 flex items-center gap-4 hover:-translate-y-0.5 transition-all duration-300">
                    <div className="w-12 h-12 rounded-2xl bg-emerald-500/10 dark:bg-indigo-500/10 text-emerald-500 dark:text-indigo-500 flex items-center justify-center">
                      <UsersIcon className="w-6 h-6" />
                    </div>
                    <div>
                      <p className="text-[10px] uppercase font-black tracking-widest text-muted">Tổng người dùng</p>
                      <h4 className="text-2xl font-black text-primary mt-1 leading-none">{stats.total_users}</h4>
                    </div>
                  </div>

                </div>

                {/* Pie Charts block */}
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  
                  {/* Documents Status Donut */}
                  <div className="glass-card rounded-2xl p-6 flex flex-col">
                    <h3 className="text-sm font-bold text-primary mb-5 select-none">
                      Tài liệu theo trạng thái
                    </h3>
                    {docPieData.length > 0 ? (
                      <div className="flex-1 min-h-[280px]">
                        <ResponsiveContainer width="100%" height={280}>
                          <PieChart>
                            <Pie
                              data={docPieData}
                              cx="50%"
                              cy="50%"
                              innerRadius={60}
                              outerRadius={90}
                              paddingAngle={4}
                              dataKey="value"
                              label={({ cx, cy, midAngle, innerRadius, outerRadius, percent, name }: any) => {
                                const RADIAN = Math.PI / 180;
                                const radius = outerRadius + 22;
                                const x = cx + radius * Math.cos(-midAngle * RADIAN);
                                const y = cy + radius * Math.sin(-midAngle * RADIAN);
                                return (
                                  <text x={x} y={y} fill="var(--text-muted)" fontSize={10} fontWeight="bold" textAnchor={x > cx ? 'start' : 'end'} dominantBaseline="central">
                                    {`${name ?? ""} ${((percent ?? 0) * 100).toFixed(0)}%`}
                                  </text>
                                );
                              }}
                            >
                              {docPieData.map((entry, idx) => (
                                <Cell key={idx} fill={entry.color} />
                              ))}
                            </Pie>
                            <Tooltip contentStyle={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: "12px", color: "var(--text-primary)", fontSize: "11px" }} />
                            <Legend formatter={(value) => <span className="text-primary font-bold ml-1 text-[11px]">{value}</span>} />
                          </PieChart>
                        </ResponsiveContainer>
                      </div>
                    ) : (
                      <div className="flex-1 flex items-center justify-center text-muted text-xs font-bold py-12">
                        Chưa có dữ liệu thống kê.
                      </div>
                    )}
                  </div>

                  {/* Feature Usage Donut */}
                  <div className="glass-card rounded-2xl p-6 flex flex-col">
                    <h3 className="text-sm font-bold text-primary mb-5 select-none">
                      Chức năng được sử dụng
                    </h3>
                    {featurePieData.length > 0 ? (
                      <div className="flex-1 min-h-[280px]">
                        <ResponsiveContainer width="100%" height={280}>
                          <PieChart>
                            <Pie
                              data={featurePieData}
                              cx="50%"
                              cy="50%"
                              innerRadius={60}
                              outerRadius={90}
                              paddingAngle={4}
                              dataKey="value"
                              label={({ cx, cy, midAngle, innerRadius, outerRadius, percent, name }: any) => {
                                const RADIAN = Math.PI / 180;
                                const radius = outerRadius + 22;
                                const x = cx + radius * Math.cos(-midAngle * RADIAN);
                                const y = cy + radius * Math.sin(-midAngle * RADIAN);
                                return (
                                  <text x={x} y={y} fill="var(--text-muted)" fontSize={10} fontWeight="bold" textAnchor={x > cx ? 'start' : 'end'} dominantBaseline="central">
                                    {`${name ?? ""} ${((percent ?? 0) * 100).toFixed(0)}%`}
                                  </text>
                                );
                              }}
                            >
                              {featurePieData.map((entry, idx) => (
                                <Cell key={idx} fill={entry.color} />
                              ))}
                            </Pie>
                            <Tooltip contentStyle={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: "12px", color: "var(--text-primary)", fontSize: "11px" }} />
                            <Legend formatter={(value) => <span className="text-primary font-bold ml-1 text-[11px]">{value}</span>} />
                          </PieChart>
                        </ResponsiveContainer>
                      </div>
                    ) : (
                      <div className="flex-1 flex items-center justify-center text-muted text-xs font-bold py-12">
                        Chưa có dữ liệu thống kê.
                      </div>
                    )}
                  </div>

                </div>

                {/* Bar Charts block */}
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  
                  {/* Sessions by Role */}
                  <div className="glass-card rounded-2xl p-6 flex flex-col">
                    <h3 className="text-sm font-bold text-primary mb-5 select-none">
                      Phiên trò chuyện theo vai trò
                    </h3>
                    {sessionsByRoleData.length > 0 ? (
                      <div className="flex-1 min-h-[280px]">
                        <ResponsiveContainer width="100%" height={280}>
                          <BarChart data={sessionsByRoleData} barSize={32}>
                            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="rgba(255,255,255,0.06)" />
                            <XAxis dataKey="name" stroke="rgba(255, 255, 255, 0.15)" tick={{ fill: "var(--text-muted)", fontSize: 10, fontWeight: "600" }} />
                            <YAxis allowDecimals={false} stroke="rgba(255, 255, 255, 0.15)" tick={{ fill: "var(--text-muted)", fontSize: 10, fontWeight: "600" }} />
                            <Tooltip contentStyle={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: "12px", color: "var(--text-primary)", fontSize: "11px" }} />
                            <Bar dataKey="Số phiên" radius={[8, 8, 0, 0]}>
                              {sessionsByRoleData.map((entry, idx) => (
                                <Cell key={idx} fill={entry.fill} />
                              ))}
                            </Bar>
                          </BarChart>
                        </ResponsiveContainer>
                      </div>
                    ) : (
                      <div className="flex-1 flex items-center justify-center text-muted text-xs font-bold py-12">
                        Chưa có dữ liệu thống kê.
                      </div>
                    )}
                  </div>

                  {/* Questions by Role */}
                  <div className="glass-card rounded-2xl p-6 flex flex-col">
                    <h3 className="text-sm font-bold text-primary mb-5 select-none">
                      Số câu hỏi theo vai trò
                    </h3>
                    {questionsByRoleData.length > 0 ? (
                      <div className="flex-1 min-h-[280px]">
                        <ResponsiveContainer width="100%" height={280}>
                          <BarChart data={questionsByRoleData} barSize={32}>
                            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="rgba(255,255,255,0.06)" />
                            <XAxis dataKey="name" stroke="rgba(255, 255, 255, 0.15)" tick={{ fill: "var(--text-muted)", fontSize: 10, fontWeight: "600" }} />
                            <YAxis allowDecimals={false} stroke="rgba(255, 255, 255, 0.15)" tick={{ fill: "var(--text-muted)", fontSize: 10, fontWeight: "600" }} />
                            <Tooltip contentStyle={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: "12px", color: "var(--text-primary)", fontSize: "11px" }} />
                            <Bar dataKey="Câu hỏi" radius={[8, 8, 0, 0]}>
                              {questionsByRoleData.map((entry, idx) => (
                                <Cell key={idx} fill={entry.fill} />
                              ))}
                            </Bar>
                          </BarChart>
                        </ResponsiveContainer>
                      </div>
                    ) : (
                      <div className="flex-1 flex items-center justify-center text-muted text-xs font-bold py-12">
                        Chưa có dữ liệu thống kê.
                      </div>
                    )}
                  </div>

                </div>

              </div>
            )}
          </>
        )}

      </div>
    </ProtectedRoute>
  );
}
