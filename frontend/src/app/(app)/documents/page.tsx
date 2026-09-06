"use client";

import { FileText, Trash2, UploadCloud } from "lucide-react";
import { useCallback, useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useDocuments, type DocumentItem } from "@/hooks/use-documents";

type BadgeVariant = React.ComponentProps<typeof Badge>["variant"];

const STATUS_VARIANT: Record<DocumentItem["status"], BadgeVariant> = {
  pending_upload: "secondary",
  uploaded: "warning",
  processing: "warning",
  ready: "success",
  failed: "destructive",
};

export default function DocumentsPage() {
  const { documents, isLoading, upload, remove } = useDocuments();
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const handleFiles = useCallback(
    async (files: FileList | null) => {
      if (!files?.length) return;
      setError(null);
      try {
        for (const file of Array.from(files)) {
          await upload(file);
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : "Upload failed");
      }
    },
    [upload],
  );

  return (
    <div className="mx-auto max-w-3xl px-6 py-12">
      <h1 className="text-xl font-semibold tracking-tight">Documents</h1>
      <p className="mt-1 text-sm text-neutral-500">
        Markdown, text, and PDF. Uploads go straight to storage; processing
        runs in the background and the status updates here.
      </p>

      {/* Dropzone */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          void handleFiles(e.dataTransfer.files);
        }}
        onClick={() => fileInput.current?.click()}
        className={`mt-8 flex cursor-pointer flex-col items-center gap-2 rounded-2xl border-2 border-dashed px-6 py-12 transition-colors ${
          dragOver ? "border-neutral-900 bg-neutral-50" : "border-neutral-300"
        }`}
      >
        <UploadCloud size={28} className="text-neutral-400" />
        <p className="text-sm font-medium">Drop files here or click to browse</p>
        <p className="text-xs text-neutral-400">.md · .txt · .pdf</p>
        <input
          ref={fileInput}
          type="file"
          multiple
          accept=".md,.txt,.pdf,text/plain,text/markdown,application/pdf"
          className="hidden"
          onChange={(e) => void handleFiles(e.target.files)}
        />
      </div>
      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}

      {/* List */}
      <ul className="mt-8 divide-y divide-neutral-100 border-y border-neutral-100">
        {isLoading && (
          <li className="py-6 text-sm text-neutral-400">Loading…</li>
        )}
        {!isLoading && documents.length === 0 && (
          <li className="py-6 text-sm text-neutral-400">
            No documents yet. Upload one to start asking questions.
          </li>
        )}
        {documents.map((doc) => (
          <li key={doc.id} className="group flex items-center gap-3 py-3.5">
            <FileText size={16} className="shrink-0 text-neutral-400" />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">{doc.filename}</p>
              {doc.status === "failed" && doc.error && (
                <p className="text-destructive truncate text-xs">{doc.error}</p>
              )}
            </div>
            <Badge variant={STATUS_VARIANT[doc.status]}>{doc.status}</Badge>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => void remove(doc.id)}
              aria-label="Delete document"
              className="text-muted-foreground hover:text-destructive hidden size-7 group-hover:flex"
            >
              <Trash2 size={14} />
            </Button>
          </li>
        ))}
      </ul>
    </div>
  );
}
