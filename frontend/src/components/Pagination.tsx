"use client";

interface PaginationProps {
  page: number;
  total: number;
  pageSize: number;
  onPageChange: (page: number) => void;
}

export default function Pagination({ page, total, pageSize, onPageChange }: PaginationProps) {
  const totalPages = Math.ceil(total / pageSize);
  if (totalPages <= 1) return null;

  const pages: (number | "...")[] = [];
  for (let i = 1; i <= totalPages; i++) {
    if (i === 1 || i === totalPages || (i >= page - 1 && i <= page + 1)) {
      pages.push(i);
    } else if (pages[pages.length - 1] !== "...") {
      pages.push("...");
    }
  }

  return (
    <div className="flex items-center justify-center gap-1 mt-4">
      <button
        disabled={page <= 1}
        onClick={() => onPageChange(page - 1)}
        className="px-2 py-1 text-sm rounded border border-theme bg-secondary hover:bg-tertiary disabled:opacity-40 text-secondary"
      >
        &lt;
      </button>
      {pages.map((p, i) =>
        p === "..." ? (
          <span key={`dots-${i}`} className="px-2 text-muted text-sm">…</span>
        ) : (
          <button
            key={p}
            onClick={() => onPageChange(p)}
            className={`px-2.5 py-1 text-sm rounded border ${
              p === page
                ? "bg-emerald-500 dark:bg-indigo-500 text-white border-emerald-500 dark:border-indigo-500"
                : "border-theme bg-secondary hover:bg-tertiary text-secondary"
            }`}
          >
            {p}
          </button>
        )
      )}
      <button
        disabled={page >= totalPages}
        onClick={() => onPageChange(page + 1)}
        className="px-2 py-1 text-sm rounded border border-theme bg-secondary hover:bg-tertiary disabled:opacity-40 text-secondary"
      >
        &gt;
      </button>
      <span className="ml-3 text-xs text-muted">{total} kết quả</span>
    </div>
  );
}
