"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { getPayload } from "@/lib/auth";

type MenuItem = {
  label: string;
  href: string;
};

const roleMenus: Record<string, MenuItem[]> = {
  nguoi_dung: [
    { label: "Hỏi đáp", href: "/chat" },
  ],
  can_bo: [
    { label: "Hỏi đáp", href: "/chat" },
    { label: "Upload tài liệu", href: "/upload" },
    { label: "Quản lý tài liệu", href: "/files" },
  ],
  admin: [
    { label: "Hỏi đáp", href: "/chat" },
    { label: "Upload tài liệu", href: "/upload" },
    { label: "Quản lý tài liệu", href: "/files" },
    { label: "Quản lý người dùng", href: "/users" },
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

  const menus = roleMenus[role] ?? [];

  return (
    <aside
      className={`h-full transition-all duration-300 ease-in-out flex flex-col shadow-sm border-r border-[#6fcf97]/40 bg-white ${
        collapsed ? "w-20" : "w-64"
      }`}
    >
      {/* Header & Toggle Button */}
      <div className="flex items-center justify-between p-4 border-b border-[#6fcf97]/20">
        {!collapsed && (
          <span className="font-bold text-[#1f6f5f] text-lg tracking-wide truncate">
            Hệ Thống
          </span>
        )}
        <button
          onClick={() => setCollapsed(!collapsed)}
          className={`p-1.5 rounded-md text-[#2fa084] hover:bg-[#2fa084]/10 transition-colors focus:outline-none focus:ring-2 focus:ring-[#6fcf97]/50 ${
            collapsed ? "mx-auto" : ""
          }`}
          aria-label={collapsed ? "Mở rộng sidebar" : "Thu gọn sidebar"}
        >
          {collapsed ? (
            // Icon Menu / Expand
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          ) : (
            // Icon Close / Collapse
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 19l-7-7 7-7m8 14l-7-7 7-7" />
            </svg>
          )}
        </button>
      </div>

      {/* Menu items */}
      <nav className="flex-1 overflow-y-auto py-5 px-3 space-y-2">
        {menus.map((item) => {
          const isActive = pathname === item.href;

          return (
            <Link
              key={item.href}
              href={item.href}
              title={collapsed ? item.label : undefined}
              className={`
                flex items-center rounded-lg px-3 py-2.5 transition-all duration-200
                ${collapsed ? "justify-center" : "justify-start"}
                ${
                  isActive
                    ? "bg-[#2fa084] text-white shadow-md shadow-[#2fa084]/30"
                    : "text-[#1f6f5f] hover:bg-[#6fcf97]/15 hover:text-[#1f6f5f]"
                }
              `}
            >
              {collapsed ? (
                <span className="font-bold text-lg leading-none">
                  {item.label.charAt(0)}
                </span>
              ) : (
                <span className="font-medium whitespace-nowrap">
                  {item.label}
                </span>
              )}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}