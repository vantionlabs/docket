"use client";

import {
  ChevronLeft,
  ChevronRight,
  FileText,
  Scale,
  Search,
  Trash2,
  UploadCloud,
} from "lucide-react";
import { useCallback, useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  useDocumentCounts,
  useDocuments,
  type Collection,
  type DocumentItem,
} from "@/hooks/use-documents";

type BadgeVariant = React.ComponentProps<typeof Badge>["variant"];

const STATUS: Record<DocumentItem["status"], { label: string; variant: BadgeVariant }> = {
  pending_upload: { label: "Waiting for upload", variant: "secondary" },
  uploaded: { label: "Queued", variant: "warning" },
  processing: { label: "Processing", variant: "warning" },
  ready: { label: "Ready", variant: "success" },
  failed: { label: "Failed", variant: "destructive" },
};

/**
 * Documents, split by what they are FOR.
 *
 * The two collections are not a filing convenience, they are the product's
 * central distinction: policy documents are the rules, transactional ones
 * are judged against them, and retrieval keeps them apart so neither can be
 * mistaken for the other. Making that the page's structure means the upload
 * control has to say which kind you are adding, which is exactly the
 * question a user should be answering.
 *
 * Paginated because a real corpus has thousands of rows and the previous
 * version fetched and laid out every one of them.
 */
const TABS: { key: Collection; label: string; blurb: string; icon: React.ElementType }[] = [
  {
    key: "transactional",
    label: "To decide",
    blurb: "Invoices and other documents the pipeline checks against your policy.",
    icon: FileText,
  },
  {
    key: "policy",
    label: "Policy",
    blurb: "The written rules everything else is judged against.",
    icon: Scale,
  },
];

export default function DocumentsPage() {
  const [collection, setCollection] = useState<Collection>("transactional");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const counts = useDocumentCounts();
  const { documents, total, pageSize, isLoading, isFetching, upload, remove } =
    useDocuments({ collection, q: query, page });

  const tab = TABS.find((t) => t.key === collection)!;
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const from = total === 0 ? 0 : page * pageSize + 1;
  const to = Math.min(total, (page + 1) * pageSize);

  const handleFiles = useCallback(
    async (files: FileList | null) => {
      if (!files?.length) return;
      setError(null);
      try {
        for (const file of Array.from(files)) {
          await upload({ file, collection });
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : "Upload failed");
      }
    },
    [upload, collection],
  );

  function switchTo(next: Collection) {
    setCollection(next);
    setPage(0);
  }

  return (
    <div className="flex h-screen flex-col">
      <header className="shrink-0 border-b px-6 pt-5">
        <h1 className="text-lg font-semibold tracking-tight">Documents</h1>

        <nav className="mt-4 flex gap-1" aria-label="Document collections">
          {TABS.map((item) => {
            const active = item.key === collection;
            const count = counts[item.key];
            return (
              <button
                key={item.key}
                onClick={() => switchTo(item.key)}
                aria-current={active ? "page" : undefined}
                className={`-mb-px flex items-center gap-2 border-b-2 px-3 py-2 text-sm transition-colors ${
                  active
                    ? "border-foreground font-medium"
                    : "text-muted-foreground hover:text-foreground border-transparent"
                }`}
              >
                <item.icon size={14} />
                {item.label}
                <span className="text-muted-foreground tabular-nums">{count}</span>
              </button>
            );
          })}
        </nav>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl px-6 py-8">
          <p className="text-muted-foreground text-sm">{tab.blurb}</p>

          {/* Dropzone. Which collection it lands in follows the tab, so the
              choice is visible rather than hidden in a menu. */}
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
            className={`mt-5 flex cursor-pointer flex-col items-center gap-1.5 rounded-xl border-2 border-dashed px-6 py-8 transition-colors ${
              dragOver ? "border-foreground bg-accent/40" : "hover:border-foreground/30"
            }`}
          >
            <UploadCloud size={22} className="text-muted-foreground" />
            <p className="text-sm font-medium">
              Drop a {collection === "policy" ? "policy document" : "document to decide"} here
            </p>
            <p className="text-muted-foreground text-xs">
              .md · .txt · .pdf
              {collection === "transactional" && " — goes straight to the review queue"}
            </p>
            <input
              ref={fileInput}
              type="file"
              multiple
              accept=".md,.txt,.pdf,text/plain,text/markdown,application/pdf"
              className="hidden"
              onChange={(e) => void handleFiles(e.target.files)}
            />
          </div>
          {error && <p className="text-destructive mt-3 text-sm">{error}</p>}

          {/* Search + range. Both only appear when there is enough to need them. */}
          {(total > pageSize || query) && (
            <div className="mt-6 flex items-center gap-3">
              <div className="relative flex-1">
                <Search
                  size={14}
                  className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 -translate-y-1/2"
                />
                <Input
                  value={query}
                  onChange={(e) => {
                    setQuery(e.target.value);
                    setPage(0);
                  }}
                  placeholder="Search by filename…"
                  className="pl-9"
                />
              </div>
              <p className="text-muted-foreground shrink-0 text-xs tabular-nums">
                {from}–{to} of {total}
              </p>
            </div>
          )}

          <ul className="mt-4 divide-y border-y">
            {isLoading && (
              <li className="text-muted-foreground py-6 text-sm">Loading…</li>
            )}
            {!isLoading && documents.length === 0 && (
              <li className="text-muted-foreground py-8 text-sm">
                {query
                  ? `Nothing matching “${query}”.`
                  : collection === "policy"
                    ? "No policy yet. Upload the rules first; nothing can be decided without them."
                    : "Nothing here yet. Upload a document and it goes to the queue."}
              </li>
            )}
            {documents.map((doc) => (
              <li key={doc.id} className="group flex items-center gap-3 py-3">
                <FileText size={15} className="text-muted-foreground shrink-0" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{doc.filename}</p>
                  <p className="text-muted-foreground mt-0.5 text-xs">
                    {new Date(doc.created_at).toLocaleDateString()}
                    {doc.size_bytes ? ` · ${Math.round(doc.size_bytes / 1024)} kB` : ""}
                  </p>
                  {doc.status === "failed" && doc.error && (
                    <p className="text-destructive mt-0.5 truncate text-xs">{doc.error}</p>
                  )}
                </div>
                <Badge variant={STATUS[doc.status].variant}>
                  {STATUS[doc.status].label}
                </Badge>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => void remove(doc.id)}
                  aria-label={`Delete ${doc.filename}`}
                  className="text-muted-foreground hover:text-destructive size-7 opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100"
                >
                  <Trash2 size={14} />
                </Button>
              </li>
            ))}
          </ul>

          {pages > 1 && (
            <div className="mt-4 flex items-center justify-between">
              <Button
                variant="outline"
                size="sm"
                disabled={page === 0 || isFetching}
                onClick={() => setPage((p) => Math.max(0, p - 1))}
              >
                <ChevronLeft size={14} /> Previous
              </Button>
              <p className="text-muted-foreground text-xs tabular-nums">
                Page {page + 1} of {pages}
              </p>
              <Button
                variant="outline"
                size="sm"
                disabled={page + 1 >= pages || isFetching}
                onClick={() => setPage((p) => p + 1)}
              >
                Next <ChevronRight size={14} />
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
