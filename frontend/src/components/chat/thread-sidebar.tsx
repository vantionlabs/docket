"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";

export type Thread = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
};

export function ThreadSidebar({ activePath }: { activePath: string }) {
  const router = useRouter();
  const qc = useQueryClient();

  const { data: threads = [] } = useQuery({
    queryKey: ["threads"],
    queryFn: () => api.get<Thread[]>("/threads"),
  });

  const create = useMutation({
    mutationFn: () => api.post<Thread>("/threads"),
    onSuccess: (thread) => {
      void qc.invalidateQueries({ queryKey: ["threads"] });
      router.push(`/chat/${thread.id}`);
    },
  });

  const remove = useMutation({
    mutationFn: (id: string) => api.delete(`/threads/${id}`),
    onSuccess: (_data, id) => {
      void qc.invalidateQueries({ queryKey: ["threads"] });
      if (activePath === `/chat/${id}`) router.push("/");
    },
  });

  return (
    <div className="flex flex-col gap-1">
      <Button
        variant="outline"
        size="sm"
        onClick={() => create.mutate()}
        disabled={create.isPending}
        className="mb-2 justify-start"
      >
        <Plus size={14} /> New chat
      </Button>
      {threads.map((t) => {
        const href = `/chat/${t.id}`;
        const active = activePath === href;
        return (
          <div key={t.id} className="group flex items-center">
            <Link
              href={href}
              className={`min-w-0 flex-1 truncate rounded-lg px-2 py-1.5 text-sm transition-colors ${
                active ? "bg-accent font-medium" : "text-muted-foreground hover:bg-accent/50"
              }`}
            >
              {t.title || "New chat"}
            </Link>
            <button
              onClick={() => remove.mutate(t.id)}
              aria-label="Delete thread"
              className="text-muted-foreground hover:text-destructive hidden shrink-0 p-1 group-hover:block"
            >
              <Trash2 size={13} />
            </button>
          </div>
        );
      })}
    </div>
  );
}
