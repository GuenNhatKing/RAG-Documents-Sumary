"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { setToken, API } from "@/lib/auth";
import { Sparkles, User, Lock, Eye, EyeOff, Check, ArrowRight } from "lucide-react";

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
    <section className="relative flex min-h-[calc(100vh-64px)] items-center justify-center py-12 px-4 overflow-hidden select-none">
      {/* Decorative blurs */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none -z-10">
        <div className="absolute top-[-8%] left-[-8%] w-[500px] h-[500px] bg-indigo-500/15 dark:bg-indigo-500/10 blur-[140px] rounded-full" />
        <div className="absolute bottom-[-8%] right-[-8%] w-[600px] h-[600px] bg-purple-500/15 dark:bg-purple-500/10 blur-[140px] rounded-full" />
        <div className="absolute top-[40%] left-[60%] w-[300px] h-[300px] bg-indigo-400/10 dark:bg-indigo-400/5 blur-[100px] rounded-full" />
      </div>

      <div className="relative w-full max-w-md">
        {/* Decorative top accent line */}
        <div className="absolute -top-px left-8 right-8 h-px bg-gradient-to-r from-transparent via-indigo-500/40 to-transparent" />

        <div className="relative rounded-3xl bg-card backdrop-blur-xl border border-theme shadow-card p-8 sm:p-10">
          {/* Branding */}
          <div className="flex flex-col items-center gap-4 mb-9">
            <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-white shadow-lg shadow-indigo-500/20 ring-1 ring-white/10 dark:ring-white/20">
              <Sparkles className="w-7 h-7" />
            </div>
            <div className="text-center space-y-1.5">
              <h1 className="text-3xl font-extrabold text-primary tracking-tight">
                RAG Summary
              </h1>
              <p className="text-sm text-muted font-medium">
                Chào mừng trở lại. Đăng nhập để tiếp tục.
              </p>
            </div>
          </div>

          {/* Form */}
          <form onSubmit={handle} className="space-y-5">
            <div className="space-y-1.5">
              <label className="text-xs font-bold text-secondary ml-1" htmlFor="username">
                Tên đăng nhập
              </label>
              <div className="relative group">
                <User className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted group-focus-within:text-indigo-500 transition-colors duration-200" />
                <input
                  id="username"
                  required
                  placeholder="Nhập tên người dùng"
                  className="w-full h-11 pl-10 pr-4 bg-secondary border border-theme hover:border-indigo-400/30 focus:border-indigo-500 rounded-xl text-sm text-primary placeholder-muted font-medium outline-none transition-all duration-200 focus:ring-[3px] focus:ring-indigo-500/15"
                  value={user.username}
                  onChange={e => setUser({ ...user, username: e.target.value })}
                  disabled={loading}
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-bold text-secondary ml-1" htmlFor="password">
                Mật khẩu
              </label>
              <div className="relative group">
                <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted group-focus-within:text-indigo-500 transition-colors duration-200" />
                <input
                  id="password"
                  required
                  type={showPassword ? "text" : "password"}
                  placeholder="••••••••"
                  className="w-full h-11 pl-10 pr-10 bg-secondary border border-theme hover:border-indigo-400/30 focus:border-indigo-500 rounded-xl text-sm text-primary placeholder-muted font-medium outline-none transition-all duration-200 focus:ring-[3px] focus:ring-indigo-500/15"
                  value={user.password}
                  onChange={e => setUser({ ...user, password: e.target.value })}
                  disabled={loading}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted hover:text-primary transition-colors cursor-pointer p-0.5"
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            {/* Remember & Forgot */}
            <div className="flex items-center justify-between">
              <label className="flex items-center gap-2.5 cursor-pointer group">
                <div className="relative flex items-center justify-center">
                  <input
                    type="checkbox"
                    checked={rememberMe}
                    onChange={(e) => setRememberMe(e.target.checked)}
                    className="peer sr-only"
                  />
                  <div className="w-[18px] h-[18px] rounded-md border border-theme bg-secondary peer-checked:bg-indigo-500 peer-checked:border-indigo-500 transition-all duration-200 flex items-center justify-center shadow-sm">
                    <Check className={`w-3 h-3 text-white transition-all duration-200 ${rememberMe ? "opacity-100 scale-100" : "opacity-0 scale-75"}`} />
                  </div>
                </div>
                <span className="text-xs font-semibold text-muted group-hover:text-primary transition-colors duration-200">
                  Ghi nhớ đăng nhập
                </span>
              </label>
              <a href="#" className="text-xs font-bold text-indigo-500 hover:text-indigo-600 dark:text-indigo-400 dark:hover:text-indigo-300 hover:underline transition-colors duration-200">
                Quên mật khẩu?
              </a>
            </div>

            {/* Error */}
            {error && (
              <div className="flex items-center gap-2.5 text-xs font-semibold text-rose-600 dark:text-rose-400 bg-rose-500/10 border border-rose-500/20 p-3 rounded-xl animate-fade-in">
                <div className="w-1.5 h-1.5 rounded-full bg-rose-500 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            {/* Submit */}
            <button
              type="submit"
              disabled={loading}
              className="relative w-full h-11 bg-gradient-to-r from-indigo-500 to-purple-600 hover:from-indigo-400 hover:to-purple-500 text-white font-bold text-sm rounded-xl shadow-lg shadow-indigo-500/20 hover:shadow-indigo-500/30 transition-all duration-300 hover:-translate-y-0.5 active:translate-y-0 active:scale-[0.98] focus:ring-[3px] focus:ring-indigo-500/25 outline-none cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:translate-y-0 disabled:hover:shadow-lg overflow-hidden group"
            >
              <span className="absolute inset-0 bg-white/10 opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
              <span className="relative flex items-center justify-center gap-2">
                {loading ? (
                  <>
                    <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    <span>Đang xử lý...</span>
                  </>
                ) : (
                  <>
                    <span>Đăng nhập</span>
                    <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform duration-200" />
                  </>
                )}
              </span>
            </button>
          </form>

          {/* Footer */}
          <div className="flex flex-col items-center gap-4 mt-8 pt-6 border-t border-theme">
            <p className="text-xs text-muted font-medium">
              Chưa có tài khoản?{" "}
              <a href="/register" className="font-bold text-indigo-500 hover:text-indigo-600 dark:text-indigo-400 dark:hover:text-indigo-300 hover:underline transition-colors duration-200">
                Đăng ký ngay
              </a>
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
