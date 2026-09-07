"use client";

import { useQuery } from "@tanstack/react-query";
import { use, useEffect, useRef, useState } from "react";

import { Composer } from "@/components/chat/composer";
import { MessageList } from "@/components/chat/message-list";
import { ThinkingState } from "@/components/chat/thinking-state";
import { useAppChat } from "@/hooks/use-app-chat";
import { api } from "@/lib/api";

type StoredCitation = {
  citation_index: number;
  excerpt: string;
  filename: string;
  document_id: string;
  chunk_id: string;
};

type StoredMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: StoredCitation[];
};

export default function ChatThreadPage({
  params,
}: {
  params: Promise<{ threadId: string }>;
}) {
  const { threadId } = use(params);
  const { messages, sendMessage, setMessages, stage, busy, streamingId, stop } =
    useAppChat(threadId);
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const kickoffSent = useRef(false);

  // Persisted history is the source of truth for a thread's prior turns.
  // Refetch is disabled so it never clobbers the live streamed messages.
  const { data: history, isSuccess: historyLoaded } = useQuery({
    queryKey: ["messages", threadId],
    queryFn: () => api.get<StoredMessage[]>(`/threads/${threadId}/messages`),
    refetchOnMount: "always",
    staleTime: Infinity,
    gcTime: 0,
  });

  useEffect(() => {
    if (!history) return;
    setMessages(
      history.map((m) => ({
        id: m.id,
        role: m.role,
        parts: [
          { type: "text" as const, text: m.content },
          ...m.citations.map((c) => ({ type: "data-citation" as const, data: c })),
        ],
      })),
    );
  }, [history, setMessages]);

  useEffect(() => {
    if (!historyLoaded || kickoffSent.current) return;
    const pending = sessionStorage.getItem(`pending-message-${threadId}`);
    if (pending) {
      sessionStorage.removeItem(`pending-message-${threadId}`);
      kickoffSent.current = true;
      void sendMessage({ text: pending });
    }
  }, [historyLoaded, threadId, sendMessage]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  function onSubmit() {
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    void sendMessage({ text });
  }

  return (
    <div className="flex h-screen flex-col">
      <div className="min-h-0 flex-1 overflow-y-auto px-6 py-8">
        <div className="mx-auto max-w-2xl">
          {!historyLoaded ? (
            <p className="text-muted-foreground text-sm">Loading…</p>
          ) : (
            <MessageList messages={messages} streamingId={streamingId} />
          )}
          {busy && <ThinkingState stage={stage ?? "analyzing"} />}
          <div ref={bottomRef} />
        </div>
      </div>
      <div className="px-6 pb-6">
        <div className="mx-auto max-w-2xl">
          <Composer
            value={input}
            onChange={setInput}
            onSubmit={onSubmit}
            onStop={stop}
            busy={busy}
            placeholder="Ask a follow-up…"
          />
          <p className="text-muted-foreground mt-2 text-center text-[11px]">
            Answers are grounded in your documents. An answer that cannot be
            verified is not shown.
          </p>
        </div>
      </div>
    </div>
  );
}
