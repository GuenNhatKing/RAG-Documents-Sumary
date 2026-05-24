"use client";

export default function AccessDeniedPage() {
  return (
    <section className="flex min-h-screen items-center justify-center bg-bg-base">
      <div className="rounded bg-white p-8 shadow-md text-center">
        <h1 className="mb-4 text-2xl font-bold text-red-600">403 – Truy cập bị từ chối</h1>
        <p className="mb-4">Bạn không có quyền xem trang này.</p>
        <a href="/" className="text-primary underline">
          Quay lại trang chủ
        </a>
      </div>
    </section>
  );
}
