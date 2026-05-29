"use client";

import { usePathname } from "next/navigation";
import Sidebar from "@/components/Sidebar";

export default function ClientLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isChatRoute = pathname === "/chat" || pathname.startsWith("/chat/");
  const isAuthRoute = pathname === "/login" || pathname === "/register";

  if (isAuthRoute) {
    return <main className="flex-1 overflow-y-auto">{children}</main>;
  }

  if (isChatRoute) {
    return (
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <main className="flex-1 overflow-hidden flex flex-col min-w-0">
          {children}
        </main>
      </div>
    );
  }

  return (
    <div className="flex flex-1 overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-6 md:p-8">
        <div className="mx-auto max-w-7xl w-full">
          {children}
        </div>
      </main>
    </div>
  );
}
