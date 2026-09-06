"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";

import type { Thread } from "@/components/chat/thread-sidebar";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";

/** New-chat landing: creating a thread on first message keeps /threads clean. */
export default function NewChatPage() {
  const router = useRouter();
  const qc = useQueryClient();
  const [input, setInput] = useState("");

  const create = useMutation({
    mutationFn: async (text: string) => ({
      thread: await api.post<Thread>("/threads"),
      text,
    }),
    onSuccess: ({ thread, text }) => {
      void qc.invalidateQueries({ queryKey: ["threads"] });
      // Hand the first message to the thread page via sessionStorage: the
      // chat page sends it on mount, so streaming starts immediately.
      sessionStorage.setItem(`pending-message-${thread.id}`, text);
      router.push(`/chat/${thread.id}`);
    },
  });

  function start(e: React.FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || create.isPending) return;
    create.mutate(text);
  }

  return (
    <div className="flex h-screen flex-col items-center justify-center px-6">
      <h1 className="text-2xl font-semibold tracking-tight">Ask your documents</h1>
      <p className="text-muted-foreground mt-2 max-w-md text-center text-sm">
        Answers are grounded in the documents you upload, with citations back
        to the source passage.
      </p>
      <form onSubmit={start} className="mt-8 flex w-full max-w-xl gap-2">
        <Input
          autoFocus
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask a question…"
          className="h-11 flex-1"
        />
        <Button type="submit" size="lg" disabled={create.isPending || !input.trim()}>
          Send
        </Button>
      </form>
    </div>
  );
}
