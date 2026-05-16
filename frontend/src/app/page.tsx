"use client";

import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import axios from "axios";
import { ArrowUpSquare, RefreshCcwIcon } from "lucide-react";
import { motion } from "framer-motion";

// UI color classes (Tailwind config should map these names)
const COLORS = {
  bgBase: "bg-bg-base",
  textMain: "text-text-main",
  primary: "bg-primary text-white",
  accent: "bg-accent text-white",
};

type UploadStatus = "idle" | "pending" | "processing" | "processed" | "error";

export default function UploadPage() {
  const [status, setStatus] = useState<UploadStatus>("idle");
  const [docId, setDocId] = useState<string>("");
  const [errorMsg, setErrorMsg] = useState<string>("");

  const onDrop = useCallback(async (acceptedFiles: File[]) => {
    if (acceptedFiles.length === 0) return;
    const file = acceptedFiles[0];
    setStatus("pending");
    setErrorMsg("");
    try {
      // 1️⃣ Upload file
      const form = new FormData();
      form.append("file", file);
      const uploadRes = await axios.post("http://localhost:8000/upload", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      const id = uploadRes.data.id as string;
      setDocId(id);

      setStatus("processing");
      // 2️⃣ Extract text
      await axios.post(`http://localhost:8000/documents/${id}/extract-text`);
      // 3️⃣ Build semantic tree
      await axios.post(`http://localhost:8000/documents/${id}/build-tree`);

      setStatus("processed");
    } catch (e: any) {
      console.error(e);
      setErrorMsg(e?.response?.data?.detail || "Upload failed");
      setStatus("error");
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    multiple: false,
    accept: { "application/pdf": [], "text/markdown": [] },
  });

  const retry = async () => {
    if (!docId) return;
    setStatus("processing");
    setErrorMsg("");
    try {
      await axios.post(`http://localhost:8000/documents/${docId}/extract-text`);
      await axios.post(`http://localhost:8000/documents/${docId}/build-tree`);
      setStatus("processed");
    } catch (e: any) {
      console.error(e);
      setErrorMsg(e?.response?.data?.detail || "Retry failed");
      setStatus("error");
    }
  };

  return (
    <div className={`${COLORS.bgBase} min-h-screen flex flex-col items-center p-8`}>
      <h1 className={`${COLORS.textMain} text-3xl font-bold mb-6`}>Upload Document</h1>
      <div
        {...getRootProps()}
        className={`w-full max-w-xl p-12 border-2 border-dashed rounded-lg text-center cursor-pointer transition-colors ${isDragActive ? "border-primary" : "border-gray-300"
          }`}
      >
        <input {...getInputProps()} />
        <ArrowUpSquare className="mx-auto mb-4" size={48} />
        <p className={`${COLORS.textMain} text-lg`}>Drag & drop a file here, or click to select</p>
      </div>

      {/* Status display */}
      {status !== "idle" && (
        <div className="mt-6 text-center">
          {status === "pending" && <p className="text-yellow-600">Uploading…</p>}
          {status === "processing" && (
            <div>
              <svg
                className="animate-spin h-8 w-8 text-primary mx-auto"
                xmlns="http://www.w3.org/2000/svg"
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

              <p className="mt-2 text-primary">Processing…</p>
            </div>
          )}
          {status === "processed" && <p className="text-green-600">Document processed successfully!</p>}
          {status === "error" && (
            <div className="text-red-600">
              <p>{errorMsg}</p>
              <button onClick={retry} className={`mt-2 flex items-center gap-2 ${COLORS.primary} py-2 px-4 rounded`}>
                <RefreshCcwIcon size={16} /> Retry
              </button>
            </div>
          )}
        </div>
      )}

      {/* Go to chat button */}
      {status === "processed" && (
        <a href={`/chat/${docId}`} className={`mt-8 ${COLORS.primary} py-3 px-6 rounded-lg font-medium transition-colors hover:bg-primary/90`}>Vào Chat</a>
      )}
    </div>
  );
}
