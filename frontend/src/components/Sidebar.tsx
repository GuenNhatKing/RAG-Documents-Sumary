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
      className={`relative transition-all duration-300 ease-in-out flex flex-col bg-sidebar backdrop-blur-md border border-theme rounded-xl m-3 shadow-card ${
        collapsed ? "w-[60px]" : "w-56"
      }`}
    >
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="absolute -right-2.5 top-5 p-1 rounded-full bg-secondary border border-theme text-muted hover:text-emerald-500 dark:hover:text-indigo-500 hover:scale-105 transition-all focus:outline-none z-10 cursor-pointer"
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
                    ? "bg-sidebar-active text-emerald-600 dark:text-indigo-600 dark:text-emerald-300 dark:text-indigo-300 font-semibold border border-emerald-500/20 dark:border-indigo-500/20 dark:border-emerald-500/15 dark:border-indigo-500/15"
                    : "text-muted hover:text-primary hover:bg-sidebar-hover font-medium"
                }
              `}
            >
              <div className={`${isActive ? "text-emerald-500 dark:text-indigo-500 dark:text-emerald-400 dark:text-indigo-400" : "text-muted group-hover:text-primary"} transition-colors duration-200`}>
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
        <div className="p-2.5 m-2 rounded-lg bg-sidebar-active border border-emerald-500/15 dark:border-indigo-500/15">
          <p className="text-[9px] uppercase font-semibold text-center tracking-widest text-emerald-500/50 dark:text-indigo-500/50 dark:text-emerald-400/50 dark:text-indigo-400/50">
            DocAI System
          </p>
        </div>
      )}
    </aside>
  );
}
