"use client";

import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import axios from "axios";
import ProtectedRoute from "@/components/ProtectedRoute";
import { API, getToken } from "@/lib/auth";

type UploadStatus =
  | "idle"
  | "pending"
  | "extracting"
  | "generating_md"
  | "pending_review"
  | "building_tree"
  | "processed"
  | "error";

export default function UploadPage() {
  const [status, setStatus] = useState<UploadStatus>("idle");
  const [docId, setDocId] = useState("");
  const [errorMsg, setErrorMsg] = useState("");
  const [markdown, setMarkdown] = useState("");
  const [markdownLoading, setMarkdownLoading] = useState(false);

  const authHeaders = () => {
    const token = getToken();
    return token ? { Authorization: `Bearer ${token}` } : {};
  };

  const onDrop = useCallback(async (acceptedFiles: File[]) => {
    if (acceptedFiles.length === 0) return;
    const file = acceptedFiles[0];
    setStatus("pending");
    setErrorMsg("");
    setMarkdown("");

    try {
      // 1. Upload file
      const form = new FormData();
      form.append("file", file);
      const uploadRes = await axios.post(`${API}/upload`, form, {
        headers: { "Content-Type": "multipart/form-data", ...authHeaders() },
      });
      const id = uploadRes.data.id as string;
      setDocId(id);

      // 2. Extract text (OCR)
      setStatus("extracting");
      await axios.post(`${API}/documents/${id}/extract-text`, null, {
        headers: authHeaders(),
      });

      // 3. Generate markdown
      setStatus("generating_md");
      await axios.post(`${API}/documents/${id}/generate-md`, null, {
        headers: authHeaders(),
      });

      // 4. Load markdown for review
      setStatus("pending_review");
      await loadMarkdown(id);
    } catch (e: any) {
      console.error(e);
      setErrorMsg(e?.response?.data?.detail || "Upload failed");
      setStatus("error");
    }
  }, []);

  const loadMarkdown = async (id: string) => {
    setMarkdownLoading(true);
    try {
      const res = await axios.get(`${API}/documents/${id}/markdown`, {
        headers: authHeaders(),
      });
      setMarkdown(res.data.markdown);
    } catch (e: any) {
      console.error(e);
      setMarkdown("Không thể tải nội dung markdown.");
    } finally {
      setMarkdownLoading(false);
    }
  };

  const handleSaveMarkdown = async () => {
    if (!docId) return;
    try {
      await axios.patch(
        `${API}/documents/${docId}/markdown`,
        { markdown },
        { headers: authHeaders() }
      );
      alert("Đã lưu nội dung markdown!");
    } catch (e: any) {
      alert("Lưu thất bại: " + (e?.response?.data?.detail || e.message));
    }
  };

  const handleConfirmMarkdown = async () => {
    if (!docId) return;
    setStatus("building_tree");
    setErrorMsg("");
    try {
      await axios.patch(
        `${API}/documents/${docId}/markdown`,
        { markdown },
        { headers: authHeaders() }
      );
      await axios.post(`${API}/documents/${docId}/confirm-md`, null, {
        headers: authHeaders(),
      });
      setStatus("processed");
    } catch (e: any) {
      console.error(e);
      setErrorMsg(e?.response?.data?.detail || "Confirm failed");
      setStatus("error");
    }
  };

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    multiple: false,
    accept: { "application/pdf": [], "text/markdown": [] },
  });

  const resetUpload = () => {
    setStatus("idle");
    setDocId("");
    setErrorMsg("");
    setMarkdown("");
  };

  return (
    <ProtectedRoute requiredRole={["admin", "can_bo"]}>
      <div className="min-h-[calc(100vh-64px)] flex flex-col items-center p-8">
        <h1 className="text-3xl font-bold text-gray-800 mb-6">
          Upload Document
        </h1>

        {/* Dropzone */}
        {status === "idle" && (
          <div
            {...getRootProps()}
            className={`w-full max-w-4xl p-12 border-2 border-dashed rounded-lg text-center cursor-pointer transition-colors ${
              isDragActive ? "border-primary bg-primary/5" : "border-gray-300"
            }`}
          >
            <input {...getInputProps()} />
            <svg
              className="mx-auto mb-4 w-12 h-12 text-gray-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
              />
            </svg>
            <p className="text-lg text-gray-600">
              Drag & drop file PDF vào đây, hoặc click để chọn
            </p>
          </div>
        )}

        {/* Processing statuses */}
        {(status === "pending" ||
          status === "extracting" ||
          status === "generating_md" ||
          status === "building_tree") && (
          <div className="mt-6 text-center">
            <svg
              className="animate-spin h-8 w-8 text-primary mx-auto"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8v8H4z"
              />
            </svg>
            <p className="mt-2 text-primary">
              {status === "pending" && "Đang upload file…"}
              {status === "extracting" && "Đang trích xuất văn bản (OCR)…"}
              {status === "generating_md" && "Đang tạo Markdown…"}
              {status === "building_tree" && "Đang tạo cây ngữ nghĩa…"}
            </p>
          </div>
        )}

        {/* Review markdown */}
        {status === "pending_review" && (
          <div className="w-full max-w-4xl mt-4">
            <div className="bg-white rounded-lg shadow-md overflow-hidden">
              <div className="flex items-center justify-between px-4 py-3 bg-blue-50 border-b">
                <h2 className="text-lg font-semibold text-blue-800">
                  Xác nhận nội dung Markdown
                </h2>
                <div className="flex gap-2">
                  <button
                    onClick={handleSaveMarkdown}
                    className="px-4 py-2 bg-gray-200 text-gray-700 rounded hover:bg-gray-300 text-sm"
                  >
                    Lưu chỉnh sửa
                  </button>
                  <button
                    onClick={handleConfirmMarkdown}
                    className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 text-sm"
                  >
                    Xác nhận & Tạo cây
                  </button>
                </div>
              </div>
              <div className="p-4">
                {markdownLoading ? (
                  <p className="text-gray-500">Đang tải nội dung…</p>
                ) : (
                  <textarea
                    value={markdown}
                    onChange={(e) => setMarkdown(e.target.value)}
                    className="w-full h-[500px] p-4 border border-gray-300 rounded-lg font-mono text-sm resize-y focus:outline-none focus:ring-2 focus:ring-blue-500"
                    spellCheck={false}
                  />
                )}
              </div>
            </div>
          </div>
        )}

        {/* Success */}
        {status === "processed" && (
          <div className="mt-6 text-center">
            <p className="text-green-600 text-lg font-semibold">
              Tài liệu đã được xử lý thành công!
            </p>
            <div className="flex gap-4 mt-4 justify-center">
              <a
                href={`/chat/${docId}`}
                className="bg-primary text-white py-3 px-6 rounded-lg font-medium hover:bg-primary/90"
              >
                Vào Chat
              </a>
              <button
                onClick={resetUpload}
                className="py-3 px-6 bg-gray-200 text-gray-700 rounded-lg font-medium hover:bg-gray-300"
              >
                Upload tài liệu khác
              </button>
            </div>
          </div>
        )}

        {/* Error */}
        {status === "error" && (
          <div className="mt-6 text-center text-red-600">
            <p>{errorMsg}</p>
            <button
              onClick={resetUpload}
              className="mt-2 flex items-center gap-2 mx-auto bg-red-100 text-red-700 py-2 px-4 rounded hover:bg-red-200"
            >
              Thử lại
            </button>
          </div>
        )}
      </div>
    </ProtectedRoute>
  );
}
