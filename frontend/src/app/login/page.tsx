"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { setToken, API } from "@/lib/auth";
import { Sparkles, User, Lock, Eye, EyeOff, Check } from "lucide-react";

export default function LoginPage() {
  const [user, setUser] = useState({ username: "", password: "" });
  const [error, setError] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(false);
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  const handle = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await fetch(`${API}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(user),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? "Đăng nhập thất bại");
      setToken(data.access_token);
      router.refresh();
      router.push("/");
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="flex min-h-[calc(100vh-64px)] items-center justify-center py-12 px-4 relative overflow-hidden select-none">
      {/* Ambient Decorative Blurs */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none -z-10">
        <div className="absolute top-[-10%] left-[-10%] w-[500px] h-[500px] bg-indigo-500/10 dark:bg-indigo-600/8 blur-[120px] rounded-full" />
        <div className="absolute bottom-[-10%] right-[-10%] w-[600px] h-[600px] bg-purple-500/10 dark:bg-purple-650/8 blur-[120px] rounded-full" />
      </div>

      <div className="w-full max-w-md glass-panel p-8 rounded-3xl shadow-2xl z-10">
        {/* Branding & Logo */}
        <div className="flex flex-col items-center gap-3 mb-8">
          <div className="w-14 h-14 rounded-2xl bg-gradient-to-tr from-indigo-550 to-purple-550 flex items-center justify-center text-white shadow-lg shadow-indigo-500/20">
            <Sparkles className="w-6.5 h-6.5" />
          </div>
          <div className="text-center">
            <h1 className="text-3xl font-black text-neon-gradient tracking-tight">
              RAG Summary
            </h1>
            <p className="text-xs text-muted mt-1 font-bold">
              Chào mừng trở lại. Đăng nhập để tiếp tục.
            </p>
          </div>
        </div>

        {/* Form */}
        <form onSubmit={handle} className="space-y-5">
          {/* Username/Email Input */}
          <div className="space-y-1.5">
            <label className="text-xs font-bold text-muted ml-1" htmlFor="username">
              Tên đăng nhập
            </label>
            <div className="relative group">
              <User className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-muted group-focus-within:text-indigo-500 transition-colors" />
              <input
                id="username"
                required
                placeholder="Nhập tên người dùng"
                className="w-full bg-secondary/60 border border-theme rounded-2xl py-2.5 pl-11 pr-4 text-primary placeholder-muted text-xs shadow-soft transition-all duration-300 outline-none focus:border-indigo-500 focus:ring-4 focus:ring-indigo-500/10 font-semibold"
                value={user.username}
                onChange={e => setUser({ ...user, username: e.target.value })}
                disabled={loading}
              />
            </div>
          </div>

          {/* Password Input */}
          <div className="space-y-1.5">
            <label className="text-xs font-bold text-muted ml-1" htmlFor="password">
              Mật khẩu
            </label>
            <div className="relative group">
              <Lock className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-muted group-focus-within:text-indigo-500 transition-colors" />
              <input
                id="password"
                required
                type={showPassword ? "text" : "password"}
                placeholder="••••••••"
                className="w-full bg-secondary/60 border border-theme rounded-2xl py-2.5 pl-11 pr-11 text-primary placeholder-muted text-xs shadow-soft transition-all duration-300 outline-none focus:border-indigo-500 focus:ring-4 focus:ring-indigo-500/10 font-semibold"
                value={user.password}
                onChange={e => setUser({ ...user, password: e.target.value })}
                disabled={loading}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-4 top-1/2 -translate-y-1/2 text-muted hover:text-primary transition-colors cursor-pointer"
              >
                {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          {/* Remember & Forget */}
          <div className="flex items-center justify-between px-1">
            <label className="flex items-center gap-2 cursor-pointer group">
              <div className="relative">
                <input
                  type="checkbox"
                  checked={rememberMe}
                  onChange={(e) => setRememberMe(e.target.checked)}
                  className="peer sr-only"
                />
                <div className="w-4.5 h-4.5 rounded-lg border border-theme bg-secondary/40 peer-checked:bg-indigo-550 peer-checked:border-indigo-550 transition-all flex items-center justify-center">
                  <Check className="w-3 h-3 text-white opacity-0 peer-checked:opacity-100 transition-opacity" />
                </div>
              </div>
              <span className="text-[11px] text-muted font-bold group-hover:text-primary transition-colors">
                Ghi nhớ đăng nhập
              </span>
            </label>
            <a href="#" className="text-[11px] text-indigo-500 dark:text-indigo-400 font-bold hover:underline transition-colors">
              Quên mật khẩu?
            </a>
          </div>

          {/* Error Message */}
          {error && (
            <p className="text-xs text-rose-600 dark:text-rose-400 bg-rose-500/5 border border-rose-500/10 p-3 rounded-2xl leading-relaxed font-semibold">
              {error}
            </p>
          )}

          {/* Submit Button */}
          <button
            type="submit"
            disabled={loading}
            className="w-full bg-neon-gradient hover:bg-neon-hover text-white font-bold text-sm py-2.5 rounded-2xl shadow-lg shadow-indigo-500/15 hover:shadow-indigo-500/25 transition-all duration-300 hover:-translate-y-0.5 active:translate-y-0 active:scale-98 focus:ring-4 focus:ring-indigo-500/20 outline-none cursor-pointer disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {loading ? "Đang xử lý..." : "Đăng nhập"}
          </button>
        </form>

        {/* Footer */}
        <div className="flex flex-col items-center gap-4 mt-6 pt-5 border-t border-theme w-full text-center">
          <p className="text-xs text-muted font-medium">
            Chưa có tài khoản?{" "}
            <a href="/register" className="text-indigo-500 dark:text-indigo-400 font-extrabold hover:underline">
              Đăng ký ngay
            </a>
          </p>
        </div>
      </div>
    </section>
  );
}
