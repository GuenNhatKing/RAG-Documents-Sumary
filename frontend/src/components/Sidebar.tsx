"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { getPayload } from "@/lib/auth";
import { MessageSquare, UploadCloud, FileText, Users, BarChart3, ChevronLeft, ChevronRight } from "lucide-react";

type MenuItem = {
  label: string;
  href: string;
  icon: React.ReactNode;
};

const getIconForHref = (href: string, size = 18) => {
  switch (href) {
    case "/chat": return <MessageSquare size={size} />;
    case "/upload": return <UploadCloud size={size} />;
    case "/files": return <FileText size={size} />;
    case "/users": return <Users size={size} />;
    case "/stats": return <BarChart3 size={size} />;
    default: return <FileText size={size} />;
  }
};

const roleMenus: Record<string, Omit<MenuItem, 'icon'>[]> = {
  nguoi_dung: [
    { label: "Hỏi đáp", href: "/chat" },
  ],
  can_bo: [
    { label: "Hỏi đáp", href: "/chat" },
    { label: "Upload", href: "/upload" },
    { label: "Tài liệu", href: "/files" },
  ],
  admin: [
    { label: "Hỏi đáp", href: "/chat" },
    { label: "Upload", href: "/upload" },
    { label: "Tài liệu", href: "/files" },
    { label: "Người dùng", href: "/users" },
    { label: "Thống kê", href: "/stats" },
  ],
};

export default function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const [role, setRole] = useState<string>("nguoi_dung");
  const pathname = usePathname();

  useEffect(() => {
    const payload = getPayload();
    setRole(payload?.role ?? "nguoi_dung");
  }, [pathname]);

  const menus: MenuItem[] = (roleMenus[role] ?? []).map(m => ({
    ...m,
    icon: getIconForHref(m.href)
  }));

  return (
    <aside
      className={`relative transition-all duration-300 ease-in-out flex flex-col bg-[#1a1f2e]/70 backdrop-blur-md border border-white/[0.06] rounded-xl m-3 ${
        collapsed ? "w-[60px]" : "w-56"
      }`}
    >
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="absolute -right-2.5 top-5 p-1 rounded-full bg-[#2a3148] border border-white/[0.08] text-slate-400 hover:text-indigo-400 hover:scale-105 transition-all focus:outline-none z-10 cursor-pointer"
        aria-label={collapsed ? "Mở rộng" : "Thu gọn"}
      >
        {collapsed ? <ChevronRight size={13} /> : <ChevronLeft size={13} />}
      </button>

      <div className="h-3" />

      <nav className="flex-1 overflow-y-auto py-3 px-2 space-y-1 scrollbar-none">
        {menus.map((item) => {
          const isActive = pathname === item.href;

          return (
            <Link
              key={item.href}
              href={item.href}
              title={collapsed ? item.label : undefined}
              className={`
                group flex items-center rounded-lg px-3 py-2.5 transition-all duration-200 cursor-pointer
                ${collapsed ? "justify-center" : "justify-start gap-3"}
                ${
                  isActive
                    ? "bg-gradient-to-r from-indigo-500/15 to-violet-500/15 text-indigo-300 font-medium border border-indigo-500/15"
                    : "text-slate-400 hover:text-slate-200 hover:bg-white/[0.04] font-medium"
                }
              `}
            >
              <div className={`${isActive ? "text-indigo-400" : "text-slate-400 group-hover:text-slate-200"} transition-colors duration-200`}>
                {item.icon}
              </div>

              {!collapsed && (
                <span className="whitespace-nowrap text-sm tracking-tight">
                  {item.label}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      {!collapsed && (
        <div className="p-2.5 m-2 rounded-lg bg-white/[0.02] border border-white/[0.04]">
          <p className="text-[9px] uppercase font-semibold text-center tracking-widest text-indigo-500/40">
            DocAI System
          </p>
        </div>
      )}
    </aside>
  );
}
