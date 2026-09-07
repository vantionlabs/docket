"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Composer } from "@/components/chat/composer";
import type { Thread } from "@/components/chat/thread-sidebar";
import { api } from "@/lib/api";

/**
 * New-chat landing. Creating the thread on the first message keeps
 * /threads free of empty ones.
 *
 * The suggestions are policy questions rather than generic prompts: this
 * chat is for interrogating the rules the pipeline decides against, and an
 * empty box with no starting point makes people ask it to summarise things
 * instead, which it is not for.
 */
const SUGGESTIONS = [
  "Who must approve an invoice of EUR 4,000 including VAT?",
  "When is a purchase order required?",
  "What happens to an invoice in a currency other than euro?",
  "Which suppliers are on the approved list?",
];

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

  function start(text: string) {
    const trimmed = text.trim();
    if (!trimmed || create.isPending) return;
    create.mutate(trimmed);
  }

  return (
    <div className="flex h-screen flex-col items-center justify-center px-6">
      <div className="w-full max-w-2xl">
        <h1 className="text-center text-2xl font-semibold tracking-tight">
          Ask your policy
        </h1>
        <p className="text-muted-foreground mt-2 text-center text-sm">
          Answers come from the documents you have uploaded, with the clause
          behind every claim. Anything that cannot be verified is not shown.
        </p>

        <div className="mt-8">
          <Composer
            autoFocus
            value={input}
            onChange={setInput}
            onSubmit={() => start(input)}
            busy={create.isPending}
            placeholder="Ask a question…"
          />
        </div>

        <div className="mt-4 flex flex-wrap justify-center gap-2">
          {SUGGESTIONS.map((suggestion) => (
            <button
              key={suggestion}
              onClick={() => start(suggestion)}
              disabled={create.isPending}
              className="bg-card text-muted-foreground hover:text-foreground hover:border-foreground/20 rounded-full border px-3 py-1.5 text-xs transition-colors disabled:opacity-50"
            >
              {suggestion}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
