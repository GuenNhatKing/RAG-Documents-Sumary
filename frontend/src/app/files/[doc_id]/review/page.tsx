"use client";

import { useEffect, useState } from "react";
import { useRouter, useParams } from "next/navigation";
import ProtectedRoute from "@/components/ProtectedRoute";
import {
  getDocumentDetail,
  getDocumentMarkdown,
  saveDocumentMarkdown,
  confirmDocumentMd,
} from "@/lib/documents";

type Status = "loading" | "ready" | "saving" | "confirming" | "done" | "error";

export default function ReviewPage() {
  const router = useRouter();
  const params = useParams<{ doc_id: string }>();
  const docId = params.doc_id;

  const [markdown, setMarkdown] = useState("");
  const [filename, setFilename] = useState("");
  const [docStatus, setDocStatus] = useState("");
  const [status, setStatus] = useState<Status>("loading");
  const [errorMsg, setErrorMsg] = useState("");

  useEffect(() => {
    async function load() {
      const doc = await getDocumentDetail(docId);
      if (!doc) {
        setErrorMsg("Không tìm thấy tài liệu.");
        setStatus("error");
        return;
      }
      if (!doc.markdown_path) {
        setErrorMsg("Tài liệu chưa có nội dung Markdown.");
        setStatus("error");
        return;
      }
      setFilename(doc.filename);
      setDocStatus(doc.status);
      const md = await getDocumentMarkdown(docId);
      if (md === null) {
        setErrorMsg("Không thể tải nội dung Markdown.");
        setStatus("error");
        return;
      }
      setMarkdown(md);
      setStatus("ready");
    }
    load();
  }, [docId, router]);

  const handleSave = async () => {
    setStatus("saving");
    const ok = await saveDocumentMarkdown(docId, markdown);
    if (ok) {
      alert("Đã lưu chỉnh sửa!");
      setStatus("ready");
    } else {
      setErrorMsg("Lưu thất bại.");
      setStatus("error");
    }
  };

  const handleConfirm = async () => {
    setStatus("confirming");
    setErrorMsg("");
    // Save first, then confirm
    const saved = await saveDocumentMarkdown(docId, markdown);
    if (!saved) {
      setErrorMsg("Lưu thất bại.");
      setStatus("error");
      return;
    }
    const confirmed = await confirmDocumentMd(docId);
    if (confirmed) {
      setStatus("done");
    } else {
      setErrorMsg("Xác nhận thất bại.");
      setStatus("error");
    }
  };

  const handleRebuild = async () => {
    setStatus("confirming");
    setErrorMsg("");
    const saved = await saveDocumentMarkdown(docId, markdown);
    if (!saved) {
      setErrorMsg("Lưu thất bại.");
      setStatus("error");
      return;
    }
    const confirmed = await confirmDocumentMd(docId);
    if (confirmed) {
      setStatus("done");
    } else {
      setErrorMsg("Tạo lại cây thất bại.");
      setStatus("error");
    }
  };

  return (
    <ProtectedRoute requiredRole={["admin", "can_bo"]}>
      <div className="min-h-[calc(100vh-64px)] flex flex-col p-8">
        <div className="flex items-center justify-between mb-4">
          <div>
            <button
              onClick={() => router.push("/files")}
              className="text-sm text-[#2fa084] hover:underline mb-1 inline-block"
            >
              &larr; Quay lại danh sách
            </button>
            <h1 className="text-2xl font-bold text-gray-800">
              {docStatus === "pending_review" ? "Review" : "Sửa"} Markdown: {filename}
            </h1>
          </div>
          {status === "ready" && (
            <div className="flex gap-2">
              <button
                onClick={handleSave}
                className="px-4 py-2 bg-gray-200 text-gray-700 rounded hover:bg-gray-300 text-sm"
              >
                Lưu chỉnh sửa
              </button>
              {docStatus === "pending_review" ? (
                <button
                  onClick={handleConfirm}
                  className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 text-sm"
                >
                  Xác nhận & Tạo cây
                </button>
              ) : (
                <button
                  onClick={handleRebuild}
                  className="px-4 py-2 bg-purple-600 text-white rounded hover:bg-purple-700 text-sm"
                >
                  Lưu & Tạo lại cây
                </button>
              )}
            </div>
          )}
        </div>

        {status === "loading" && (
          <div className="flex-1 flex items-center justify-center">
            <p className="text-gray-500">Đang tải nội dung…</p>
          </div>
        )}

        {(status === "saving" || status === "confirming") && (
          <div className="flex-1 flex items-center justify-center">
            <p className="text-primary">
              {status === "saving"
                ? "Đang lưu…"
                : docStatus === "pending_review"
                  ? "Đang tạo cây ngữ nghĩa…"
                  : "Đang tạo lại cây ngữ nghĩa…"}
            </p>
          </div>
        )}

        {status === "done" && (
          <div className="flex-1 flex flex-col items-center justify-center gap-4">
            <p className="text-green-600 text-lg font-semibold">
              {docStatus === "pending_review"
                ? "Tài liệu đã được xử lý thành công!"
                : "Đã cập nhật Markdown và tạo lại cây thành công!"}
            </p>
            <button
              onClick={() => router.push("/files")}
              className="px-6 py-2 bg-[#2fa084] text-white rounded-lg hover:bg-[#2fa084]/90"
            >
              Quay lại danh sách
            </button>
          </div>
        )}

        {status === "error" && (
          <div className="flex-1 flex flex-col items-center justify-center gap-4">
            <p className="text-red-600">{errorMsg}</p>
            <button
              onClick={() => router.push("/files")}
              className="px-6 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300"
            >
              Quay lại
            </button>
          </div>
        )}

        {status === "ready" && (
          <textarea
            value={markdown}
            onChange={(e) => setMarkdown(e.target.value)}
            className="flex-1 min-h-[400px] w-full p-4 border border-gray-300 rounded-lg font-mono text-sm resize-y focus:outline-none focus:ring-2 focus:ring-[#2fa084]"
            spellCheck={false}
          />
        )}
      </div>
    </ProtectedRoute>
  );
}
