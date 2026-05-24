"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { setToken, API } from "@/lib/auth";

export default function LoginPage() {
  const [user, setUser] = useState({ username: "", password: "" });
  const [error, setError] = useState("");
  const router = useRouter();

  const handle = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      const res = await fetch(`${API}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(user),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? "Login failed");
      setToken(data.access_token);
      // Refresh the layout to re‑evaluate auth state, then go home
      router.refresh();
      router.push("/");
    } catch (err: any) {
      setError(err.message);
    }
  };

  return (
    <section className="flex min-h-screen items-center justify-center bg-bg-base">
      <form
        onSubmit={handle}
        className="w-full max-w-sm space-y-4 rounded-lg bg-white p-8 shadow-md"
      >
        <h2 className="mb-4 text-center text-2xl font-semibold text-text-main">
          Đăng nhập
        </h2>
        <input
          required
          placeholder="Tên người dùng"
          className="w-full rounded border p-2"
          value={user.username}
          onChange={e => setUser({ ...user, username: e.target.value })}
        />
        <input
          required
          type="password"
          placeholder="Mật khẩu"
          className="w-full rounded border p-2"
          value={user.password}
          onChange={e => setUser({ ...user, password: e.target.value })}
        />
        {error && <p className="text-sm text-red-600">{error}</p>}
        <button
          type="submit"
          className="w-full rounded bg-primary py-2 text-white hover:bg-primary/90"
        >
          Đăng nhập
        </button>
        <p className="text-center text-sm">
          Chưa có tài khoản?{' '}
          <a href="/register" className="text-primary underline">
            Đăng ký
          </a>
        </p>
      </form>
    </section>
  );
}
