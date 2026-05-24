"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import ProtectedRoute from "@/components/ProtectedRoute";
import { getPayload, API } from "@/lib/auth";

export default function UploadPage() {
  const [file, setFile] = useState<File | null>(null);
  const [message, setMessage] = useState("");
  const router = useRouter();

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return setMessage("Chọn tệp tin trước");
    const token = localStorage.getItem("token");
    if (!token) return router.replace("/login");

    const form = new FormData();
    form.append("file", file);

    try {
      const res = await fetch(`${API}/files/upload`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: form,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? "Upload failed");
      setMessage("Tải lên thành công");
    } catch (err: any) {
      setMessage(err.message);
    }
  };

  const payload = getPayload();
  const allowed = payload && (payload.role === "admin" || payload.role === "can_bo");

  return (
    <ProtectedRoute>
      <section className="flex min-h-screen items-center justify-center bg-bg-base">
        {allowed ? (
          <form onSubmit={handleUpload} className="w-full max-w-md space-y-4 rounded-lg bg-white p-8 shadow-md">
            <h2 className="mb-4 text-center text-2xl font-semibold text-text-main">Upload tài liệu</h2>
            <input
              type="file"
              required
              onChange={e => setFile(e.target.files?.[0] ?? null)}
              className="w-full"
            />
            <button type="submit" className="w-full rounded bg-primary py-2 text-white hover:bg-primary/90">
              Tải lên
            </button>
            {message && <p className="mt-2 text-sm text-gray-700">{message}</p>}
          </form>
        ) : (
          <p className="text-center text-red-600">Bạn không có quyền tải lên tài liệu.</p>
        )}
      </section>
    </ProtectedRoute>
  );
}
