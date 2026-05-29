"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import ProtectedRoute from "@/components/ProtectedRoute";
import { getPayload, API, getToken } from "@/lib/auth";
import { motion } from "framer-motion";
import {
  MessageSquare, UploadCloud, Folder, FileText, CheckCircle,
  TrendingUp, Sparkles, ArrowRight, BookOpen, Zap
} from "lucide-react";

type Stats = {
  totalDocs: number;
  processedDocs: number;
  totalSessions: number;
};

const container = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { staggerChildren: 0.08 } },
};

const item = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0, transition: { type: "spring", stiffness: 80, damping: 15 } },
};

export default function HomePage() {
  const [payload, setPayload] = useState<ReturnType<typeof getPayload>>(null);
  const [stats, setStats] = useState<Stats | null>(null);

  useEffect(() => {
    setPayload(getPayload());
  }, []);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    const headers = { Authorization: `Bearer ${token}` };

    Promise.all([
      fetch(`${API}/documents?page_size=1000`, { headers }).then((r) => (r.ok ? r.json() : { items: [] })),
      fetch(`${API}/chat/sessions`, { headers }).then((r) => r.ok ? r.json() : []),
    ])
      .then(([docs, sessions]) => {
        const docArr = Array.isArray(docs?.items) ? docs.items : Array.isArray(docs) ? docs : [];
        setStats({
          totalDocs: docs?.total ?? docArr.length,
          processedDocs: docArr.filter((d: Record<string, string>) => d.status === "processed").length,
          totalSessions: Array.isArray(sessions) ? sessions.length : 0,
        });
      })
      .catch(() => {});
  }, []);

  const role = payload?.role ?? "";
  const canUpload = role === "admin" || role === "can_bo";
  const displayName = payload?.sub ?? "bạn";

  const quickActions = [
    ...(canUpload
      ? [
          { href: "/upload", icon: UploadCloud, label: "Upload tài liệu", desc: "Tải lên PDF để phân tích", color: "from-violet-500 to-purple-600" },
          { href: "/files", icon: Folder, label: "Kho tài liệu", desc: "Quản lý & chỉnh sửa", color: "from-emerald-500 to-teal-600" },
        ]
      : []),
    { href: "/chat", icon: MessageSquare, label: "Hỏi đáp AI", desc: "Tra cứu thông tin thông minh", color: "from-blue-500 to-indigo-600" },
    ...(role === "admin" ? [{ href: "/stats", icon: TrendingUp, label: "Thống kê", desc: "Báo cáo chi tiết hệ thống", color: "from-amber-500 to-orange-600" }] : []),
  ];

  return (
    <ProtectedRoute>
      <motion.div variants={container} initial="hidden" animate="show" className="max-w-6xl mx-auto p-4 sm:p-8">
        <motion.div variants={item} className="mb-10">
          <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-indigo-600 via-purple-600 to-pink-500 p-8 sm:p-12">
            <div className="absolute top-0 right-0 w-64 h-64 bg-white/5 rounded-full blur-3xl -translate-y-1/2 translate-x-1/4" />
            <div className="absolute bottom-0 left-0 w-48 h-48 bg-black/10 rounded-full blur-2xl" />
            <div className="relative z-10">
              <div className="flex items-center gap-2 text-white/80 text-sm font-medium mb-3">
                <Sparkles size={16} />
                <span>Hệ thống tra cứu tài liệu thông minh</span>
              </div>
              <h1 className="text-3xl sm:text-5xl font-bold text-white mb-3 tracking-tight">
                Chào bạn, <span className="text-yellow-300">{displayName}</span>
              </h1>
              <p className="text-white/80 text-lg max-w-xl font-medium">
                Khai thác sức mạnh AI để phân tích, tra cứu và tổng hợp thông tin từ kho tài liệu của bạn.
              </p>
            </div>
          </div>
        </motion.div>

        {stats && (
          <motion.div variants={item} className="grid grid-cols-1 sm:grid-cols-3 gap-5 mb-10">
            {[
              { icon: FileText, label: "Tổng tài liệu", value: stats.totalDocs, color: "from-violet-500 to-purple-600" },
              { icon: CheckCircle, label: "Đã xử lý", value: stats.processedDocs, color: "from-emerald-500 to-teal-500" },
              { icon: MessageSquare, label: "Phiên chat", value: stats.totalSessions, color: "from-blue-500 to-indigo-500" },
            ].map((s, i) => (
              <div key={i} className="relative group">
                <div className="absolute inset-0 bg-gradient-to-br opacity-0 group-hover:opacity-100 transition-opacity duration-500 blur-xl"
                  style={{ background: `linear-gradient(135deg, ${s.color.replace("from-", "").split(" ")[0]}, ${s.color.replace("to-", "").split(" ")[0]})` }} />
                <div className="relative rounded-xl border border-white/10 bg-[#1e1e2d]/80 backdrop-blur-sm p-6 flex items-center gap-5 group-hover:-translate-y-1 transition-all duration-300">
                  <div className={`p-3.5 rounded-xl bg-gradient-to-br ${s.color} shadow-lg`}>
                    <s.icon size={24} className="text-white" />
                  </div>
                  <div>
                    <p className="text-3xl font-bold text-white">{s.value}</p>
                    <p className="text-sm text-slate-400 font-medium">{s.label}</p>
                  </div>
                </div>
              </div>
            ))}
          </motion.div>
        )}

        <motion.div variants={item}>
          <div className="flex items-center gap-3 mb-6">
            <div className="h-px flex-1 bg-gradient-to-r from-transparent via-white/10 to-transparent" />
            <h2 className="text-lg font-semibold text-slate-300 flex items-center gap-2">
              <Zap size={18} className="text-indigo-400" />
              Truy cập nhanh
            </h2>
            <div className="h-px flex-1 bg-gradient-to-r from-transparent via-white/10 to-transparent" />
          </div>

          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {quickActions.map((action, i) => (
              <Link key={i} href={action.href}>
                <div className="group relative cursor-pointer h-full">
                  <div className="absolute inset-0 rounded-xl bg-gradient-to-br opacity-0 group-hover:opacity-20 transition-opacity duration-500 blur-sm"
                    style={{ background: `linear-gradient(135deg, ${action.color.replace("from-", "").split(" ")[0]}, ${action.color.replace("to-", "").split(" ")[0]})` }} />
                  <div className="relative h-full rounded-xl border border-white/10 bg-[#1e1e2d]/60 backdrop-blur-sm p-6 flex flex-col gap-4 group-hover:-translate-y-1.5 group-hover:border-white/20 transition-all duration-300">
                    <div className={`p-3 w-fit rounded-xl bg-gradient-to-br ${action.color} shadow-lg group-hover:scale-110 transition-transform duration-300`}>
                      <action.icon size={22} className="text-white" />
                    </div>
                    <div className="flex-1">
                      <h3 className="font-semibold text-white mb-1.5 text-base">{action.label}</h3>
                      <p className="text-sm text-slate-500 leading-relaxed">{action.desc}</p>
                    </div>
                    <div className="flex items-center gap-1.5 text-xs font-medium text-indigo-400 opacity-0 group-hover:opacity-100 transition-opacity duration-300">
                      <span>Đi đến</span>
                      <ArrowRight size={14} />
                    </div>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        </motion.div>

        <motion.div variants={item} className="mt-10">
          <div className="rounded-xl border border-white/[0.05] bg-gradient-to-br from-white/[0.03] to-transparent p-6 sm:p-8">
            <div className="flex items-start gap-4">
              <div className="p-3 rounded-xl bg-gradient-to-br from-amber-500/20 to-orange-500/20 border border-amber-500/10 shrink-0">
                <BookOpen size={22} className="text-amber-400" />
              </div>
              <div>
                <h3 className="font-semibold text-white mb-2">Hướng dẫn nhanh</h3>
                <ul className="space-y-2 text-sm text-slate-400">
                  <li className="flex items-start gap-2">
                    <div className="w-1.5 h-1.5 rounded-full bg-indigo-500 mt-2 shrink-0" />
                    <span><strong className="text-slate-300">Upload</strong> — Tải file PDF lên hệ thống</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <div className="w-1.5 h-1.5 rounded-full bg-indigo-500 mt-2 shrink-0" />
                    <span><strong className="text-slate-300">Xử lý</strong> — OCR → Chuẩn hóa → Markdown → Cây ngữ nghĩa</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <div className="w-1.5 h-1.5 rounded-full bg-indigo-500 mt-2 shrink-0" />
                    <span><strong className="text-slate-300">Hỏi đáp</strong> — Đặt câu hỏi, AI trả lời dựa trên tài liệu</span>
                  </li>
                </ul>
              </div>
            </div>
          </div>
        </motion.div>
      </motion.div>
    </ProtectedRoute>
  );
}
