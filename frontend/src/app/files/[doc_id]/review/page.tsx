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
import { API, getToken } from "@/lib/auth";
import { ArrowLeft } from "lucide-react";

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
  const [showPdf, setShowPdf] = useState(false);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [pdfError, setPdfError] = useState("");

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

  // Cleanup PDF object URL on unmount
  useEffect(() => {
    return () => {
      if (pdfUrl) URL.revokeObjectURL(pdfUrl);
    };
  }, [pdfUrl]);

  const loadPdf = async () => {
    if (pdfUrl) return;
    setPdfLoading(true);
    setPdfError("");
    try {
      const token = getToken();
      const headers: Record<string, string> = token
        ? { Authorization: `Bearer ${token}` }
        : {};
      const res = await fetch(`${API}/documents/${docId}/raw`, { headers });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      setPdfUrl(URL.createObjectURL(blob));
    } catch {
      setPdfError("Không thể tải file PDF.");
    } finally {
      setPdfLoading(false);
    }
  };

  const handleTogglePdf = () => {
    if (!showPdf) {
      loadPdf();
    }
    setShowPdf(!showPdf);
  };

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
      <div className="min-h-[calc(100vh-64px)] flex flex-col py-8 max-w-6xl mx-auto px-4">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
          <div>
              <button
                onClick={() => router.push("/files")}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-theme bg-secondary hover:bg-tertiary hover:border-theme-accent text-secondary hover:text-primary transition-all text-xs font-bold cursor-pointer"
              >
                <ArrowLeft className="w-3.5 h-3.5" />
                Quay lại danh sách
              </button>
              <h1 className="text-3xl font-extrabold text-primary tracking-tight">
                Kiểm duyệt nội dung Markdown
              </h1>
              <p className="text-sm font-bold text-indigo-400 mt-1">
                Tên file: <span className="text-secondary">{filename}</span>
              </p>
          </div>
          {status === "ready" && (
            <div className="flex flex-wrap gap-2.5">
              <button
                onClick={handleTogglePdf}
                className={`inline-flex items-center gap-1.5 px-4 py-2.5 rounded-xl text-sm font-bold transition-all shadow-sm cursor-pointer border ${
                  showPdf
                    ? "bg-indigo-600 text-white shadow-indigo-500/20 hover:bg-indigo-500 border-indigo-500/30"
                    : "btn-accent-sky"
                }`}
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
                </svg>
                {showPdf ? "Ẩn PDF" : "Xem PDF gốc"}
              </button>
              <button
                onClick={handleSave}
                className="px-4 py-2.5 btn-accent-amber rounded-xl text-sm font-bold transition-all cursor-pointer"
              >
                Lưu lại
              </button>
              {docStatus === "pending_review" ? (
                <button
                  onClick={handleConfirm}
                  className="px-4 py-2.5 bg-gradient-to-r from-green-600 to-emerald-600 hover:from-green-500 hover:to-emerald-500 text-white rounded-xl text-sm font-bold shadow-md shadow-green-500/10 hover:shadow-lg transition-all cursor-pointer"
                >
                  Xác nhận & Tạo cây
                </button>
              ) : (
                <button
                  onClick={handleRebuild}
                  className="px-4 py-2.5 bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-50 hover:to-indigo-500 text-white rounded-xl text-sm font-bold shadow-md shadow-purple-500/10 hover:shadow-lg transition-all cursor-pointer"
                >
                  Lưu & Tạo lại cây
                </button>
              )}
            </div>
          )}
        </div>

        {status === "loading" && (
          <div className="flex-1 glass-panel p-8 flex flex-col items-center justify-center min-h-[400px] rounded-3xl">
            <div className="animate-spin h-8 w-8 border-4 border-indigo-600 border-t-transparent rounded-full mb-3" />
            <p className="text-muted font-medium">Đang tải nội dung…</p>
          </div>
        )}

        {(status === "saving" || status === "confirming") && (
          <div className="flex-1 glass-panel p-8 flex flex-col items-center justify-center min-h-[400px] rounded-3xl">
            <div className="animate-spin h-8 w-8 border-4 border-indigo-600 border-t-transparent rounded-full mb-3" />
            <p className="text-indigo-500 font-bold">
              {status === "saving"
                ? "Đang lưu chỉnh sửa..."
                : docStatus === "pending_review"
                  ? "Đang tạo cây ngữ nghĩa..."
                  : "Đang tạo lại cây ngữ nghĩa..."}
            </p>
          </div>
        )}

        {status === "done" && (
          <div className="flex-1 glass-panel p-8 flex flex-col items-center justify-center min-h-[400px] rounded-3xl">
            <div className="p-4 bg-green-500/10 text-green-600 rounded-full mb-4">
              <svg className="w-10 h-10" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <p className="text-primary text-xl font-extrabold mb-2">
              {docStatus === "pending_review"
                ? "Xác nhận thành công!"
                : "Cập nhật thành công!"}
            </p>
            <p className="text-muted font-medium text-sm max-w-sm mb-6">
              {docStatus === "pending_review"
                ? "Tài liệu đã được phân tích và sẵn sàng cho việc hỏi đáp ngữ cảnh chéo."
                : "Đã cập nhật Markdown và tạo lại cây ngữ nghĩa thành công!"}
            </p>
            <button
              onClick={() => router.push("/files")}
              className="px-6 py-3 rounded-xl border border-theme bg-secondary hover:bg-tertiary hover:border-theme-accent text-secondary font-bold hover:-translate-y-0.5 active:scale-95 transition-all text-sm cursor-pointer"
            >
              Quay lại danh sách
            </button>
          </div>
        )}

        {status === "error" && (
          <div className="flex-1 glass-panel p-8 flex flex-col items-center justify-center min-h-[400px] rounded-3xl">
            <div className="p-4 bg-rose-500/10 text-rose-600 dark:text-rose-400 rounded-full mb-4">
              <svg className="w-10 h-10" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            </div>
            <p className="text-primary text-xl font-extrabold mb-2">Đã có lỗi xảy ra</p>
            <p className="text-rose-500 font-semibold mb-6">{errorMsg}</p>
            <button
              onClick={() => router.push("/files")}
              className="px-5 py-2.5 rounded-xl border border-theme bg-secondary hover:bg-tertiary hover:border-theme-accent text-secondary font-bold hover:-translate-y-0.5 active:scale-95 transition-all text-sm cursor-pointer"
            >
              Quay lại
            </button>
          </div>
        )}

        {status === "ready" && (
          <div className="flex-1 flex flex-col md:flex-row gap-6 min-h-[500px]">
            <textarea
              value={markdown}
              onChange={(e) => setMarkdown(e.target.value)}
              className={`${showPdf ? "md:w-1/2" : "w-full"} p-5 border border-theme rounded-2xl bg-tertiary backdrop-blur-sm text-primary placeholder:text-muted shadow-inner font-mono text-sm resize-y focus:outline-none focus:ring-4 focus:ring-indigo-500/15 focus:border-indigo-500/40 transition-all`}
              spellCheck={false}
            />
            {showPdf && (
              <div className="md:w-1/2 rounded-2xl border border-theme bg-tertiary shadow-inner overflow-hidden flex flex-col">
                <div className="flex items-center justify-between px-4 py-2.5 bg-tertiary border-b border-theme">
                  <span className="text-xs font-bold text-secondary">PDF gốc</span>
                  {pdfUrl && (
                    <a
                      href={pdfUrl}
                      download={filename.replace(/\.[^.]+$/, ".pdf")}
                      className="text-xs font-bold text-indigo-400 hover:text-indigo-300 hover:underline"
                    >
                      Tải xuống
                    </a>
                  )}
                </div>
                <div className="flex-1">
                  {pdfLoading ? (
                    <div className="flex items-center justify-center h-full">
                      <div className="animate-spin h-6 w-6 border-4 border-indigo-600 border-t-transparent rounded-full" />
                    </div>
                  ) : pdfError ? (
                    <div className="flex items-center justify-center h-full">
                      <p className="text-sm font-semibold text-rose-500">{pdfError}</p>
                    </div>
                  ) : pdfUrl ? (
                    <object
                      data={pdfUrl}
                      type="application/pdf"
                      className="w-full h-full"
                    >
                      <div className="flex flex-col items-center justify-center h-full gap-2 p-4">
                        <p className="text-sm text-slate-500">Trình duyệt không hỗ trợ xem PDF trực tiếp.</p>
                        <a
                          href={pdfUrl}
                          download
                          className="text-sm px-4 py-2 bg-indigo-600 text-white rounded-xl font-semibold hover:bg-indigo-500"
                        >
                          Tải file PDF
                        </a>
                      </div>
                    </object>
                  ) : null}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </ProtectedRoute>
  );
}
