import DocumentViewerClient from "./viewer-client";

type PageProps = {
  params: Promise<{
    doc_id: string;
  }>;
  searchParams: Promise<{
    highlight?: string;
  }>;
};

type DocumentMarkdownResponse = {
  doc_id: string;
  markdown: string;
};

export default async function DocumentViewPage({
  params,
  searchParams,
}: PageProps) {
  const { doc_id } = await params;
  const { highlight } = await searchParams;

  const res = await fetch(
    `http://127.0.0.1:8000/documents/${doc_id}/markdown`,
    {
      method: "GET",
      headers: {
        Accept: "application/json",
      },
      cache: "no-store",
    }
  );

  if (!res.ok) {
    return (
      <main className="min-h-screen flex items-center justify-center bg-white p-8">
        <p className="text-red-600 text-xl">
          Failed to load document
        </p>
      </main>
    );
  }

  const data = (await res.json()) as DocumentMarkdownResponse;

  return (
    <DocumentViewerClient
      markdown={data.markdown}
      highlight={highlight ?? ""}
      docId={doc_id}
    />
  );
}