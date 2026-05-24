"use client";

import ProtectedRoute from "@/components/ProtectedRoute";
import { getPayload } from "@/lib/auth";

export default function StatsPage() {
  const payload = getPayload();
  const allowed = payload && (payload.role === "admin" || payload.role === "quan_ly");

  return (
    <ProtectedRoute>
      <section className="p-8">
        {allowed ? (
          <>
            <h1 className="text-2xl font-bold">Thống kê</h1>
            <p className="mt-4">Nội dung thống kê sẽ được triển khai ở đây.</p>
          </>
        ) : (
          <p className="text-center text-red-600">Bạn không có quyền truy cập trang này.</p>
        )}
      </section>
    </ProtectedRoute>
  );
}
