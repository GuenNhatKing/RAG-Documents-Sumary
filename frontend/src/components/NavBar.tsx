"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { isAuthenticated, getPayload, clearToken } from "@/lib/auth";
import { useState, useEffect } from "react";
import { LogOut, User, Sparkles, Sun, Moon } from "lucide-react";
import { useTheme } from "@/lib/theme";

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

  const { theme, toggle } = useTheme();

  return (
    <nav className="sticky top-0 z-50 flex items-center justify-between px-5 sm:px-8 py-3.5 bg-nav backdrop-blur-xl border-b border-theme-light transition-all duration-300">
      <Link href="/" className="flex items-center gap-2.5 font-semibold text-base tracking-tight select-none group">
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-violet-600 flex items-center justify-center shadow-lg shadow-indigo-500/20 group-hover:scale-105 transition-transform duration-200">
          <span className="text-white text-sm font-bold">R</span>
        </div>
        <div className="flex items-baseline gap-1.5">
          <span className="text-nav-title font-semibold">DocAI</span>
              <span className="text-[10px] font-medium text-indigo-500/70 dark:text-indigo-400/80 hidden sm:inline">v2.0</span>
        </div>
      </Link>

      <div className="flex items-center gap-3">
        <button
          onClick={toggle}
          className="p-2 rounded-lg text-muted hover:text-indigo-400 hover:bg-tertiary border border-transparent hover:border-theme-light transition-all duration-200 cursor-pointer"
          title={theme === "dark" ? "Chế độ sáng" : "Chế độ tối"}
        >
          {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
        </button>

        {payload ? (
          <>
            <div className="flex items-center gap-2 px-3.5 py-1.5 rounded-lg bg-sidebar-hover border border-theme text-sm font-medium text-primary">
              <User size={14} className="text-indigo-500 dark:text-indigo-400" />
              <span className="text-primary font-semibold">{payload.sub}</span>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 font-bold uppercase tracking-wider">
                {payload.role === "admin" ? "Admin" : payload.role === "can_bo" ? "Cán bộ" : "User"}
              </span>
            </div>

            <button
              onClick={logout}
              className="flex items-center gap-1.5 text-sm font-medium text-muted hover:text-red-400 border border-transparent hover:border-red-500/20 rounded-lg px-3 py-1.5 hover:bg-red-500/5 transition-all duration-200 cursor-pointer"
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
              className="px-4 py-2 text-sm font-semibold text-primary hover:text-indigo-600 dark:hover:text-indigo-400 bg-secondary hover:bg-sidebar-hover border border-theme rounded-lg transition-all duration-200"
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
