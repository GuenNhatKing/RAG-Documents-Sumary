"use client";

import { useCallback, useState, useEffect } from "react";
import { useDropzone } from "react-dropzone";
import axios from "axios";
import ProtectedRoute from "@/components/ProtectedRoute";
import { API, getToken } from "@/lib/auth";
import { CloudUpload, Eye, Check, RefreshCw, AlertTriangle, FileText, ChevronLeft, ArrowLeft } from "lucide-react";
import Link from "next/link";

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
  const [filename, setFilename] = useState("");
  const [errorMsg, setErrorMsg] = useState("");
  const [markdown, setMarkdown] = useState("");
  const [markdownLoading, setMarkdownLoading] = useState(false);
  const [showPdf, setShowPdf] = useState(false);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [pdfError, setPdfError] = useState("");

  const authHeaders = (): Record<string, string> => {
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
      const form = new FormData();
      form.append("file", file);
      const uploadRes = await axios.post(`${API}/upload`, form, {
        headers: { "Content-Type": "multipart/form-data", ...authHeaders() },
      });
      const id = uploadRes.data.id as string;
      setDocId(id);
      setFilename(file.name);

      setStatus("extracting");
      await axios.post(`${API}/documents/${id}/extract-text`, null, {
        headers: authHeaders(),
      });

      setStatus("generating_md");
      await axios.post(`${API}/documents/${id}/generate-md`, null, {
        headers: authHeaders(),
      });

      setStatus("pending_review");
      await loadMarkdown(id);
    } catch (e: any) {
      console.error(e);
      setErrorMsg(e?.response?.data?.detail || "Không thể tải lên hoặc xử lý tệp tin.");
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
      const res = await fetch(`${API}/documents/${docId}/raw`, {
        headers: authHeaders(),
      });
      if (!res.ok) throw new Error("Failed");
      const blob = await res.blob();
      setPdfUrl(URL.createObjectURL(blob));
    } catch {
      setPdfError("Không thể tải file PDF gốc.");
    } finally {
      setPdfLoading(false);
    }
  };

  const handleTogglePdf = () => {
    if (!showPdf) loadPdf();
    setShowPdf(!showPdf);
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
      setErrorMsg(e?.response?.data?.detail || "Xác nhận thất bại.");
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
    setFilename("");
    setErrorMsg("");
    setMarkdown("");
    setShowPdf(false);
    setPdfUrl(null);
  };

  return (
    <ProtectedRoute requiredRole={["admin", "can_bo"]}>
      <div className="flex-1 overflow-y-auto px-8 py-8 w-full max-w-6xl mx-auto select-none">
        
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center gap-3">
            <Link href="/files" className="p-2.5 bg-white/5 border border-white/10 rounded-xl hover:bg-white/10 hover:border-white/20 hover:scale-105 active:scale-95 transition-all text-slate-300 flex items-center justify-center cursor-pointer">
              <ArrowLeft className="w-4 h-4" />
            </Link>
            <div>
              <h1 className="text-3xl font-black text-neon-gradient tracking-tight">
                Tải Lên Tài Liệu
              </h1>
              <p className="text-xs text-slate-500 dark:text-slate-400 font-bold mt-0.5">
                Kéo thả file văn bản để trích xuất tri thức AI tự động.
              </p>
            </div>
          </div>
        </div>

        {/* Dropzone screen */}
        {status === "idle" && (
          <div
            {...getRootProps()}
            className={`w-full p-20 border-2 border-dashed rounded-3xl text-center cursor-pointer transition-all duration-500 bg-[#2a3148]/20 backdrop-blur-xl shadow-premium relative overflow-hidden group ${
              isDragActive 
                ? "border-[#c3c0ff] bg-[#c3c0ff]/10 scale-[1.005]" 
                : "border-white/10 hover:border-[#c3c0ff]/70"
            }`}
          >
            <input {...getInputProps()} />
            
            <div className="w-16 h-16 rounded-2xl bg-[#c3c0ff]/10 flex items-center justify-center mx-auto mb-6 text-[#c3c0ff] group-hover:scale-110 group-hover:rotate-3 transition-transform duration-300">
              <CloudUpload className="w-8 h-8" />
            </div>
            
            <h3 className="text-lg font-black text-slate-100">
              Kéo và thả tệp tin của bạn tại đây, hoặc click để chọn
            </h3>
            <p className="text-xs text-slate-400 mt-2 font-bold leading-normal">
              Chấp nhận định dạng .pdf và .md với kích thước tối đa 50MB
            </p>
          </div>
        )}

        {/* Loading Steps screen */}
        {(status === "pending" ||
          status === "extracting" ||
          status === "generating_md" ||
          status === "building_tree") && (
          <div className="mx-auto mt-12 text-center p-8 rounded-3xl glass-panel border border-white/15 shadow-2xl max-w-md w-full hover:shadow-neon-indigo transition-all duration-300">
            <div className="relative flex items-center justify-center w-12 h-12 mx-auto mb-6">
              <RefreshCw className="animate-spin h-7 w-7 text-indigo-400" />
            </div>
            
            <h3 className="text-base font-extrabold text-slate-100">
              {status === "pending" && "Đang tải tệp tin..."}
              {status === "extracting" && "Đang nhận dạng OCR..."}
              {status === "generating_md" && "Đang trích xuất cấu trúc Markdown..."}
              {status === "building_tree" && "Đang lập chỉ mục Vector RAG..."}
            </h3>
            <p className="text-[11px] text-slate-400 mt-2 font-bold leading-normal">
              Hệ thống AI đang phân tích dữ liệu. Vui lòng giữ trình duyệt mở.
            </p>
          </div>
        )}

        {/* Review markdown split screen */}
        {status === "pending_review" && (
          <div className="w-full animate-fade-in">
            <div className="glass-panel border border-white/15 p-6 rounded-3xl shadow-2xl backdrop-blur-xl space-y-6">
              {/* Header row */}
              <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-4 border-b border-white/10">
                <div>
                  <h2 className="text-xl font-black text-white">
                    Kiểm duyệt nội dung Markdown
                  </h2>
                  <p className="text-[10px] text-slate-450 mt-1 font-bold">
                    Tên file: <span className="text-indigo-500">{filename}</span>
                  </p>
                </div>
                
                <div className="flex flex-wrap gap-2.5">
                  <button
                    onClick={handleTogglePdf}
                    className={`px-4 py-2 rounded-xl text-xs font-bold flex items-center gap-1.5 transition-all duration-200 cursor-pointer active:scale-95 border ${
                      showPdf 
                        ? "bg-sky-500 text-white shadow-lg shadow-sky-500/25 border-sky-400/50" 
                        : "bg-sky-500/10 text-sky-300 border-sky-500/30 hover:bg-sky-500/20 hover:border-sky-400/50"
                    }`}
                  >
                    <Eye className="w-4 h-4" />
                    {showPdf ? "Ẩn PDF gốc" : "Xem PDF gốc"}
                  </button>
                  
                  <button
                    onClick={handleSaveMarkdown}
                    className="px-4 py-2 rounded-xl border border-amber-500/30 bg-amber-500/10 text-amber-300 hover:bg-amber-500/20 hover:border-amber-400/50 active:scale-95 text-xs font-bold transition-all duration-200 cursor-pointer"
                  >
                    Lưu tạm
                  </button>
                  
                  <button
                    onClick={handleConfirmMarkdown}
                    className="px-5 py-2 rounded-xl bg-gradient-to-r from-emerald-500 to-green-500 text-white text-xs font-extrabold shadow-lg shadow-emerald-500/25 hover:shadow-emerald-500/40 hover:from-emerald-400 hover:to-green-400 active:scale-95 transition-all duration-200 cursor-pointer"
                  >
                    Xác nhận & Cấu trúc
                  </button>
                </div>
              </div>

              {/* Textarea + PDF viewer */}
              <div className="flex flex-col lg:flex-row gap-6">
                <div className={showPdf ? "w-full lg:w-1/2" : "w-full"}>
                  {markdownLoading ? (
                    <div className="flex items-center justify-center h-48">
                      <RefreshCw className="animate-spin h-6 w-6 text-indigo-500" />
                    </div>
                  ) : (
                    <textarea
                      value={markdown}
                      onChange={(e) => setMarkdown(e.target.value)}
                      className="w-full h-[520px] p-4.5 rounded-2xl border border-white/15 bg-[#2a2a3d]/60 text-slate-100 font-mono text-xs resize-y shadow-inner transition-all duration-350 outline-none focus:border-indigo-500/40 focus:ring-4 focus:ring-indigo-500/15 leading-relaxed"
                      spellCheck={false}
                    />
                  )}
                </div>

                {showPdf && (
                  <div className="w-full lg:w-1/2 border border-white/15 rounded-2xl overflow-hidden flex flex-col bg-[#2a2a3d]/40 shadow-inner">
                    <div className="px-4 py-2.5 bg-[#2a2a3d]/60 border-b border-white/10 flex items-center justify-between">
                      <span className="text-[10px] uppercase font-black tracking-wider text-slate-300">PDF gốc đối chiếu</span>
                      {pdfUrl && (
                        <a
                          href={pdfUrl}
                          download={filename}
                          className="text-[10px] text-indigo-400 hover:text-indigo-300 font-bold hover:underline"
                        >
                          Tải PDF
                        </a>
                      )}
                    </div>
                    <div className="flex-1 min-h-[460px] relative bg-[#222840]/40">
                      {pdfLoading ? (
                        <p className="text-xs text-slate-400 p-4 font-bold">Đang tải tài liệu PDF...</p>
                      ) : pdfError ? (
                        <p className="text-xs text-rose-500 p-4 font-bold">{pdfError}</p>
                      ) : pdfUrl ? (
                        <object data={pdfUrl} type="application/pdf" className="w-full h-full absolute inset-0">
                          <p className="text-xs text-slate-500 p-4">
                            Không hỗ trợ xem trực tuyến.{" "}
                            <a href={pdfUrl} className="text-indigo-500 underline font-bold" download>
                              Nhấp vào đây để tải file PDF gốc
                            </a>
                          </p>
                        </object>
                      ) : null}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Success screen */}
        {status === "processed" && (
          <div className="mx-auto mt-12 text-center p-8 rounded-3xl glass-panel border border-white/15 shadow-2xl max-w-md w-full hover:shadow-neon-green transition-all duration-350">
            <div className="w-14 h-14 bg-emerald-500/10 text-emerald-500 rounded-full flex items-center justify-center mx-auto mb-5 shadow-md shadow-emerald-500/15">
              <Check className="w-7 h-7" />
            </div>
            
            <h2 className="text-emerald-400 text-xl font-black">
              Tài liệu đã lập chỉ mục!
            </h2>
            <p className="text-xs text-slate-400 text-center font-bold mt-2 leading-relaxed">
              Dữ liệu cấu trúc tri thức đã được thiết lập. Hãy bắt đầu hỏi đáp thông minh ngay bây giờ.
            </p>
            
            <div className="flex gap-3.5 mt-8 justify-center">
              <Link
                href={`/chat/${docId}`}
                className="px-5 py-2.5 btn-primary text-xs flex items-center justify-center"
              >
                Vào Hỏi Đáp
              </Link>
              <button
                onClick={resetUpload}
                className="px-5 py-2.5 rounded-xl border border-white/15 bg-white/5 hover:bg-white/10 hover:border-white/25 text-slate-200 text-xs font-bold transition-all duration-250 active:scale-95 cursor-pointer"
              >
                Tải tệp mới
              </button>
            </div>
          </div>
        )}

        {/* Error screen */}
        {status === "error" && (
          <div className="mx-auto mt-12 text-center p-8 rounded-3xl glass-panel border border-rose-500/20 shadow-2xl max-w-md w-full hover:shadow-neon-pink transition-all duration-350 animate-fade-in">
            <div className="w-12 h-12 bg-rose-500/10 text-rose-400 rounded-full flex items-center justify-center mx-auto mb-5">
              <AlertTriangle className="w-6 h-6" />
            </div>
            
            <h3 className="text-rose-400 font-black text-base">
              Xảy ra lỗi trong hệ thống
            </h3>
            
            <div className="mt-3.5 text-xs text-rose-400 font-semibold bg-rose-500/5 border border-rose-500/15 p-3 rounded-2xl leading-relaxed text-center">
              {errorMsg}
            </div>
            
            <button
              onClick={resetUpload}
              className="mt-6 w-full py-2.5 bg-rose-600 hover:bg-rose-500 text-white font-bold rounded-xl transition-all duration-200 active:scale-95 shadow-lg shadow-rose-500/15 cursor-pointer"
            >
              Thử lại
            </button>
          </div>
        )}
      </div>
    </ProtectedRoute>
  );
}
