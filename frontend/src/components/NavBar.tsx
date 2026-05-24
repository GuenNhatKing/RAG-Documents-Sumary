"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { isAuthenticated, getPayload, clearToken } from "@/lib/auth";
import { useState, useEffect } from "react";

export default function NavBar() {
  const router = useRouter();

  const logout = () => {
    // Remove the JWT cookie
    clearToken();

    // Force a re‑render of all server‑side components that depend on auth state
    router.refresh();

    // Redirect to the login page
    router.replace("/login");
  };

  const [payload, setPayload] = useState(isAuthenticated() ? getPayload() : null);

  // Re‑check auth state periodically (e.g., every 500 ms) to pick up cookie changes
  useEffect(() => {
    const timer = setInterval(() => {
      const newPayload = isAuthenticated() ? getPayload() : null;
      setPayload((prev) => {
        // shallow compare to avoid unnecessary renders
        if (!prev && newPayload) return newPayload;
        if (prev && newPayload && prev.sub === newPayload.sub && prev.role === newPayload.role) return prev;
        return newPayload;
      });
    }, 500);
    return () => clearInterval(timer);
  }, []);


  return (
    <nav className="flex items-center justify-between bg-primary px-6 py-3 text-white">
      <Link href="/" className="font-semibold">
        Home
      </Link>
      <div className="flex items-center gap-4">
        {payload ? (
          <>
            <span>Hello, {payload.sub}</span>
            {payload.role === "admin" && (
              <Link href="/admin" className="underline">
                Admin
              </Link>
            )}
            {/* After logout the cookie is cleared and router.refresh() forces NavBar to re‑render,
                so the Logout button disappears on the next render. */}
            <button onClick={logout} className="underline">
              Đăng xuất
            </button>
          </>
        ) : (
          <>
            <Link href="/login" className="underline">
              Đăng nhập
            </Link>
            <Link href="/register" className="underline">
              Đăng ký
            </Link>
          </>
        )}
      </div>
    </nav>
  );
}
