"use client";

import { useQuery } from "@tanstack/react-query";
import { use, useEffect, useRef, useState } from "react";

import { MessageList } from "@/components/chat/message-list";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
  const { messages, sendMessage, status, setMessages } = useAppChat(threadId);
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

  const busy = status === "submitted" || status === "streaming";

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
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
            <MessageList messages={messages} />
          )}
          {busy && <p className="text-muted-foreground mt-4 text-sm">Thinking…</p>}
          <div ref={bottomRef} />
        </div>
      </div>
      <div className="border-t px-6 py-4">
        <form onSubmit={onSubmit} className="mx-auto flex max-w-2xl gap-2">
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask a follow-up…"
            className="h-11 flex-1"
          />
          <Button type="submit" size="lg" disabled={busy || !input.trim()}>
            Send
          </Button>
        </form>
      </div>
    </div>
  );
}
