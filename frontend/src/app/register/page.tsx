"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { API } from "@/lib/auth";

export default function RegisterPage() {
  const [form, setForm] = useState({ username: "", password: "" });
  const [error, setError] = useState("");
  const router = useRouter();

  const handle = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    try {
      // Include default role required by backend
      const registerBody = { ...form, role: "nguoi_dung" };

      const res = await fetch(`${API}/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(registerBody),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? "Register failed");

      // Auto‑login after successful registration
      const loginRes = await fetch(`${API}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: form.username,
          password: form.password,
        }),
      });
      const loginData = await loginRes.json();
      if (!loginRes.ok) throw new Error(loginData.detail ?? "Login after register failed");
      localStorage.setItem("token", loginData.access_token);
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
          Đăng ký
        </h2>
        <input
          required
          placeholder="Tên người dùng"
          className="w-full rounded border p-2"
          value={form.username}
          onChange={e => setForm({ ...form, username: e.target.value })}
        />
        <input
          required
          type="password"
          placeholder="Mật khẩu"
          className="w-full rounded border p-2"
          value={form.password}
          onChange={e => setForm({ ...form, password: e.target.value })}
        />
        {error && <p className="text-sm text-red-600">{error}</p>}
        <button
          type="submit"
          className="w-full rounded bg-primary py-2 text-white hover:bg-primary/90"
        >
          Đăng ký
        </button>
        <p className="text-center text-sm">
          Đã có tài khoản?{' '}
          <a href="/login" className="text-primary underline">
            Đăng nhập
          </a>
        </p>
      </form>
    </section>
  );
}
