"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";

import { api } from "@/lib/api";

export type Collection = "policy" | "transactional";

export type DocumentItem = {
  id: string;
  collection: Collection;
  filename: string;
  content_type: string;
  size_bytes: number | null;
  status: "pending_upload" | "uploaded" | "processing" | "ready" | "failed";
  error: string | null;
  created_at: string;
};

const BUSY = new Set(["pending_upload", "uploaded", "processing"]);
const POLL_MS = 2500;

export type DocumentPage = {
  items: DocumentItem[];
  total: number;
  limit: number;
  offset: number;
};

/**
 * Documents list, paginated and filtered server-side.
 *
 * It used to fetch every document. At 5,000 that is a megabyte on the wire
 * and a browser laying out 5,000 nodes, which works fine on fixtures and
 * falls over on a real corpus.
 *
 * Polls while anything is still processing and stops once settled. Upload
 * and delete invalidate the list.
 */
export function useDocuments({
  collection,
  q = "",
  page = 0,
  pageSize = 25,
}: {
  collection?: Collection;
  q?: string;
  page?: number;
  pageSize?: number;
} = {}) {
  const qc = useQueryClient();

  const params = new URLSearchParams({
    limit: String(pageSize),
    offset: String(page * pageSize),
  });
  if (collection) params.set("collection", collection);
  if (q.trim()) params.set("q", q.trim());

  const query = useQuery({
    queryKey: ["documents", collection ?? "all", q.trim(), page, pageSize],
    queryFn: () => api.get<DocumentPage>(`/documents?${params}`),
    placeholderData: (previous) => previous,
    refetchInterval: (result) =>
      (result.state.data?.items ?? []).some((d) => BUSY.has(d.status))
        ? POLL_MS
        : false,
  });

  const invalidate = useCallback(() => {
    void qc.invalidateQueries({ queryKey: ["documents"] });
    void qc.invalidateQueries({ queryKey: ["documents-count"] });
    // A transactional upload becomes a decision, so the queue changes too.
    void qc.invalidateQueries({ queryKey: ["decisions"] });
  }, [qc]);

  const upload = useMutation({
    mutationFn: async ({
      file,
      collection: uploadCollection,
    }: {
      file: File;
      collection: Collection;
    }) => {
      const { document_id, upload_url } = await api.post<{
        document_id: string;
        key: string;
        upload_url: string;
      }>("/documents/presign", {
        filename: file.name,
        content_type: file.type || "application/octet-stream",
        size_bytes: file.size,
        collection: uploadCollection,
      });
      // Direct browser PUT to R2. Content-Type must match the presigned one.
      const put = await fetch(upload_url, {
        method: "PUT",
        headers: { "Content-Type": file.type || "application/octet-stream" },
        body: file,
      });
      if (!put.ok) throw new Error(`Upload failed (${put.status})`);
      await api.post(`/documents/${document_id}/confirm`);
    },
    onSuccess: invalidate,
  });

  const remove = useMutation({
    mutationFn: (id: string) => api.delete(`/documents/${id}`),
    onSuccess: invalidate,
  });

  return {
    documents: query.data?.items ?? [],
    total: query.data?.total ?? 0,
    pageSize,
    isLoading: query.isLoading,
    isFetching: query.isFetching,
    upload: upload.mutateAsync,
    remove: remove.mutateAsync,
  };
}

/** Counts per collection, for the tab labels. */
export function useDocumentCounts() {
  const policy = useQuery({
    queryKey: ["documents-count", "policy"],
    queryFn: () => api.get<DocumentPage>("/documents?collection=policy&limit=1"),
  });
  const transactional = useQuery({
    queryKey: ["documents-count", "transactional"],
    queryFn: () =>
      api.get<DocumentPage>("/documents?collection=transactional&limit=1"),
  });
  return {
    policy: policy.data?.total ?? 0,
    transactional: transactional.data?.total ?? 0,
  };
}
