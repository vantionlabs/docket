"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";

import { api } from "@/lib/api";

export type DocumentItem = {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number | null;
  status: "pending_upload" | "uploaded" | "processing" | "ready" | "failed";
  error: string | null;
  created_at: string;
};

const BUSY = new Set(["pending_upload", "uploaded", "processing"]);
const POLL_MS = 2500;

/**
 * Documents list. TanStack Query polls while any document is still
 * processing (via a conditional refetchInterval) and stops once everything
 * is settled. Upload and delete are mutations that invalidate the list.
 */
export function useDocuments() {
  const qc = useQueryClient();

  const query = useQuery({
    queryKey: ["documents"],
    queryFn: () => api.get<DocumentItem[]>("/documents"),
    refetchInterval: (q) =>
      (q.state.data ?? []).some((d) => BUSY.has(d.status)) ? POLL_MS : false,
  });

  const invalidate = useCallback(
    () => qc.invalidateQueries({ queryKey: ["documents"] }),
    [qc],
  );

  const upload = useMutation({
    mutationFn: async (file: File) => {
      const { document_id, upload_url } = await api.post<{
        document_id: string;
        key: string;
        upload_url: string;
      }>("/documents/presign", {
        filename: file.name,
        content_type: file.type || "application/octet-stream",
        size_bytes: file.size,
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
    documents: query.data ?? [],
    isLoading: query.isLoading,
    upload: upload.mutateAsync,
    remove: remove.mutateAsync,
  };
}
