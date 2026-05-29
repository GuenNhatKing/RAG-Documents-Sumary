"use client";

export default function AccessDeniedPage() {
  return (
    <section className="flex min-h-screen items-center justify-center bg-transparent">
      <div className="glass-panel p-8 rounded-3xl text-center max-w-sm w-full">
        <h1 className="mb-4 text-xl font-bold text-rose-500">403 – Truy cập bị từ chối</h1>
        <p className="mb-6 text-xs text-slate-400 font-medium">Bạn không có quyền xem trang này.</p>
        <a 
          href="/" 
          className="inline-block w-full px-5 py-2.5 rounded-xl border border-white/10 bg-white/5 hover:bg-white/10 hover:border-white/20 text-slate-300 font-bold transition-all duration-200 hover:-translate-y-0.5 active:scale-95 text-xs text-center"
        >
          Quay lại trang chủ
        </a>
      </div>
    </section>
  );
}
