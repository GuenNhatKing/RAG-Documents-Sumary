"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { isAuthenticated, getPayload, clearToken } from "@/lib/auth";
import { useState, useEffect } from "react";
import { LogOut, User, Sparkles } from "lucide-react";

export default function NavBar() {
  const router = useRouter();

  const logout = () => {
    clearToken();
    router.refresh();
    router.replace("/login");
  };

  const [payload, setPayload] = useState<ReturnType<typeof getPayload>>(null);

  useEffect(() => {
    const check = () => {
      const newPayload = isAuthenticated() ? getPayload() : null;
      setPayload((prev) => {
        if (!prev && newPayload) return newPayload;
        if (prev && newPayload && prev.sub === newPayload.sub && prev.role === newPayload.role) return prev;
        return newPayload;
      });
    };
    check();
    const timer = setInterval(check, 500);
    return () => clearInterval(timer);
  }, []);

  return (
    <nav className="sticky top-0 z-50 flex items-center justify-between px-5 sm:px-8 py-3.5 bg-[#0b0d12]/85 backdrop-blur-xl border-b border-white/[0.04] transition-all duration-300">
      <Link href="/" className="flex items-center gap-2.5 font-semibold text-base tracking-tight select-none group">
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center shadow-lg shadow-indigo-500/20 group-hover:scale-105 transition-transform duration-200">
          <span className="text-white text-sm font-bold">R</span>
        </div>
        <div className="flex items-baseline gap-1.5">
          <span className="text-white font-semibold">DocAI</span>
          <span className="text-[10px] font-medium text-indigo-400/60 hidden sm:inline">v2.0</span>
        </div>
      </Link>

      <div className="flex items-center gap-3">
        {payload ? (
          <>
            <div className="flex items-center gap-2 px-3.5 py-1.5 rounded-lg bg-white/[0.04] border border-white/[0.06] text-sm font-medium text-slate-300">
              <User size={14} className="text-indigo-400" />
              <span>{payload.sub}</span>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-indigo-500/10 text-indigo-400 font-medium uppercase tracking-wider">
                {payload.role === "admin" ? "Admin" : payload.role === "can_bo" ? "Cán bộ" : "User"}
              </span>
            </div>

            <button
              onClick={logout}
              className="flex items-center gap-1.5 text-sm font-medium text-slate-500 hover:text-red-400 border border-transparent hover:border-red-500/20 rounded-lg px-3 py-1.5 hover:bg-red-500/5 transition-all duration-200 cursor-pointer"
              title="Đăng xuất"
            >
              <LogOut size={15} />
              <span className="hidden sm:inline">Đăng xuất</span>
            </button>
          </>
        ) : (
          <div className="flex items-center gap-2">
            <Link
              href="/login"
              className="px-4 py-2 text-sm font-medium text-slate-300 hover:text-white hover:bg-white/[0.04] border border-white/[0.06] rounded-lg transition-all duration-200"
            >
              Đăng nhập
            </Link>
            <Link
              href="/register"
              className="px-4 py-2 text-sm font-semibold bg-gradient-to-r from-indigo-500 to-violet-600 hover:shadow-lg hover:shadow-indigo-500/25 text-white rounded-lg transition-all duration-200"
            >
              Đăng ký
            </Link>
          </div>
        )}
      </div>
    </nav>
  );
}
