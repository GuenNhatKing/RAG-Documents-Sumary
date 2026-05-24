"use client";

import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import axios from "axios";
import { ArrowUpSquare, RefreshCcwIcon } from "lucide-react";
import { motion } from "framer-motion";

const COLORS = {
  bgBase: "bg-bg-base",
  textMain: "text-text-main",
  primary: "bg-primary text-white",
  accent: "bg-accent text-white",
};

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
  const [docId, setDocId] = useState<string>("");
  const [errorMsg, setErrorMsg] = useState<string>("");
  const [markdown, setMarkdown] = useState<string>("");
  const [markdownLoading, setMarkdownLoading] = useState(false);

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
      const uploadRes = await axios.post("http://localhost:8000/upload", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      const id = uploadRes.data.id as string;
      setDocId(id);

      // 2. Extract text (OCR)
      setStatus("extracting");
      await axios.post(`http://localhost:8000/documents/${id}/extract-text`);

      // 3. Generate markdown (DỪNG ở đây — chờ review)
      setStatus("generating_md");
      await axios.post(`http://localhost:8000/documents/${id}/generate-md`);

      // 4. Load markdown để review
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
      const res = await axios.get(`http://localhost:8000/documents/${id}/markdown`);
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
      await axios.patch(`http://localhost:8000/documents/${docId}/markdown`, {
        markdown,
      });
      alert("Đã lưu nội dung markdown!");
    } catch (e: any) {
      console.error(e);
      alert("Lưu thất bại: " + (e?.response?.data?.detail || e.message));
    }
  };

  const handleConfirmMarkdown = async () => {
    if (!docId) return;
    setStatus("building_tree");
    setErrorMsg("");
    try {
      // Lưu markdown trước
      await axios.patch(`http://localhost:8000/documents/${docId}/markdown`, {
        markdown,
      });
      // Confirm → build semantic tree
      await axios.post(`http://localhost:8000/documents/${docId}/confirm-md`);
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
    <div className={`${COLORS.bgBase} min-h-screen flex flex-col items-center p-8`}>
      <h1 className={`${COLORS.textMain} text-3xl font-bold mb-6`}>
        Upload Document
      </h1>

      {/* Dropzone - chỉ hiện khi idle */}
      {status === "idle" && (
        <div
          {...getRootProps()}
          className={`w-full max-w-4xl p-12 border-2 border-dashed rounded-lg text-center cursor-pointer transition-colors ${
            isDragActive ? "border-primary" : "border-gray-300"
          }`}
        >
          <input {...getInputProps()} />
          <ArrowUpSquare className="mx-auto mb-4" size={48} />
          <p className={`${COLORS.textMain} text-lg`}>
            Drag & drop file PDF vào đây, hoặc click để chọn
          </p>
        </div>
      )}

      {/* Processing statuses */}
      {status === "pending" && (
        <p className="text-yellow-600 mt-4">Đang upload file…</p>
      )}
      {status === "extracting" && (
        <div className="mt-4 text-center">
          <svg
            className="animate-spin h-8 w-8 text-primary mx-auto"
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
          </svg>
          <p className="mt-2 text-primary">Đang trích xuất văn bản (OCR)…</p>
        </div>
      )}
      {status === "generating_md" && (
        <div className="mt-4 text-center">
          <svg
            className="animate-spin h-8 w-8 text-primary mx-auto"
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
          </svg>
          <p className="mt-2 text-primary">Đang tạo Markdown…</p>
        </div>
      )}
      {status === "building_tree" && (
        <div className="mt-4 text-center">
          <svg
            className="animate-spin h-8 w-8 text-primary mx-auto"
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
          </svg>
          <p className="mt-2 text-primary">Đang tạo cây ngữ nghĩa…</p>
        </div>
      )}

      {/* REVIEW SECTION - cán bộ xem và sửa .md */}
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
                  className="px-4 py-2 bg-gray-200 text-gray-700 rounded hover:bg-gray-300 transition-colors text-sm"
                >
                  Lưu chỉnh sửa
                </button>
                <button
                  onClick={handleConfirmMarkdown}
                  className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 transition-colors text-sm"
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
          <div className="flex gap-4 mt-4">
            <a
              href={`/chat/${docId}`}
              className={`${COLORS.primary} py-3 px-6 rounded-lg font-medium transition-colors hover:bg-primary/90`}
            >
              Vào Chat
            </a>
            <button
              onClick={resetUpload}
              className="py-3 px-6 bg-gray-200 text-gray-700 rounded-lg font-medium hover:bg-gray-300 transition-colors"
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
            <RefreshCcwIcon size={16} /> Thử lại
          </button>
        </div>
      )}
    </div>
  );
}
