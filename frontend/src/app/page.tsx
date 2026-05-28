"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import ProtectedRoute from "@/components/ProtectedRoute";
import { getPayload, API, getToken } from "@/lib/auth";

type Stats = {
  totalDocs: number;
  processedDocs: number;
  totalSessions: number;
};

export default function HomePage() {
  const [payload, setPayload] = useState<ReturnType<typeof getPayload>>(null);
  const [stats, setStats] = useState<Stats | null>(null);

  useEffect(() => {
    setPayload(getPayload());
  }, []);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    const headers = { Authorization: `Bearer ${token}` };

    Promise.all([
      fetch(`${API}/documents`, { headers }).then((r) => (r.ok ? r.json() : [])),
      fetch(`${API}/chat/sessions`, { headers }).then((r) =>
        r.ok ? r.json() : []
      ),
    ])
      .then(([docs, sessions]) => {
        const docArr = Array.isArray(docs) ? docs : [];
        setStats({
          totalDocs: docArr.length,
          processedDocs: docArr.filter((d: any) => d.status === "processed")
            .length,
          totalSessions: Array.isArray(sessions) ? sessions.length : 0,
        });
      })
      .catch(() => {});
  }, []);

  const role = payload?.role ?? "";
  const canUpload = role === "admin" || role === "can_bo";
  const displayName = payload?.sub ?? "bạn";

  return (
    <ProtectedRoute>
      <div className="max-w-4xl mx-auto py-10 px-4">
        {/* Welcome */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-800">
            Xin chào, {displayName}!
          </h1>
          <p className="text-gray-500 mt-1">
            Hệ thống hỏi đáp tài liệu thông minh
          </p>
        </div>

        {/* Stats */}
        {stats && (
          <div className="grid grid-cols-3 gap-4 mb-8">
            <div className="bg-white rounded-lg border border-gray-200 p-4 text-center">
              <p className="text-2xl font-bold text-primary">{stats.totalDocs}</p>
              <p className="text-sm text-gray-500">Tổng tài liệu</p>
            </div>
            <div className="bg-white rounded-lg border border-gray-200 p-4 text-center">
              <p className="text-2xl font-bold text-green-600">
                {stats.processedDocs}
              </p>
              <p className="text-sm text-gray-500">Sẵn sàng</p>
            </div>
            <div className="bg-white rounded-lg border border-gray-200 p-4 text-center">
              <p className="text-2xl font-bold text-blue-600">
                {stats.totalSessions}
              </p>
              <p className="text-sm text-gray-500">Phiên trò chuyện</p>
            </div>
          </div>
        )}

        {/* Quick actions */}
        <div className="grid gap-4 sm:grid-cols-2">
          <Link
            href="/chat"
            className="flex items-center gap-4 bg-white rounded-lg border border-gray-200 p-5 hover:border-primary hover:shadow-md transition-all"
          >
            <div className="p-3 bg-blue-100 rounded-lg">
              <svg
                className="w-6 h-6 text-blue-600"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
                />
              </svg>
            </div>
            <div>
              <h3 className="font-semibold text-gray-800">Hỏi đáp</h3>
              <p className="text-sm text-gray-500">
                Chat với tài liệu hoặc tìm kiếm
              </p>
            </div>
          </Link>

          {canUpload && (
            <Link
              href="/upload"
              className="flex items-center gap-4 bg-white rounded-lg border border-gray-200 p-5 hover:border-primary hover:shadow-md transition-all"
            >
              <div className="p-3 bg-green-100 rounded-lg">
                <svg
                  className="w-6 h-6 text-green-600"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
                  />
                </svg>
              </div>
              <div>
                <h3 className="font-semibold text-gray-800">Upload tài liệu</h3>
                <p className="text-sm text-gray-500">
                  Tải lên và xử lý tài liệu mới
                </p>
              </div>
            </Link>
          )}

          {role === "admin" && (
            <Link
              href="/stats"
              className="flex items-center gap-4 bg-white rounded-lg border border-gray-200 p-5 hover:border-primary hover:shadow-md transition-all"
            >
              <div className="p-3 bg-purple-100 rounded-lg">
                <svg
                  className="w-6 h-6 text-purple-600"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
                  />
                </svg>
              </div>
              <div>
                <h3 className="font-semibold text-gray-800">Thống kê</h3>
                <p className="text-sm text-gray-500">
                  Xem báo cáo và phân tích
                </p>
              </div>
            </Link>
          )}

          {canUpload && (
            <Link
              href="/files"
              className="flex items-center gap-4 bg-white rounded-lg border border-gray-200 p-5 hover:border-primary hover:shadow-md transition-all"
            >
              <div className="p-3 bg-orange-100 rounded-lg">
                <svg
                  className="w-6 h-6 text-orange-600"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"
                  />
                </svg>
              </div>
              <div>
                <h3 className="font-semibold text-gray-800">Quản lý tài liệu</h3>
                <p className="text-sm text-gray-500">
                  Xem và quản lý tất cả tài liệu
                </p>
              </div>
            </Link>
          )}
        </div>
      </div>
    </ProtectedRoute>
  );
}
