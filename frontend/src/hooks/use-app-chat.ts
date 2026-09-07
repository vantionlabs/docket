"use client";

import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport } from "ai";
import { useMemo } from "react";

import type { Stage } from "@/components/chat/thinking-state";
import { API_URL } from "@/lib/api";

/**
 * Chat state + transport: the AI SDK's useChat wired to the FastAPI SSE
 * endpoint. `credentials: "include"` sends the httpOnly auth cookie with
 * the streaming request — no token in JS.
 *
 * Also surfaces the turn's stage. The backend emits one per phase
 * (`analyzing`, `verifying`, `retrying`, `streaming`) and the UI used to
 * discard all of it for a single "Thinking…". `retrying` is worth showing:
 * it means the answer failed grounding and the pipeline is going again,
 * which is a very different thing to be waiting for.
 */
export function useAppChat(threadId: string) {
  const transport = useMemo(
    () =>
      new DefaultChatTransport({
        api: `${API_URL}/chat/stream`,
        credentials: "include",
        body: { thread_id: threadId },
      }),
    [threadId],
  );

  const chat = useChat({ id: threadId, transport });

  // The latest stage on the last assistant message. Stages arrive as data
  // parts in order, so the last one is the current one.
  const stage = useMemo<Stage | null>(() => {
    const last = chat.messages.at(-1);
    if (!last || last.role !== "assistant") return null;
    const stages = last.parts
      .filter((part) => part.type === "data-status")
      .map((part) => (part as { data?: { stage?: string } }).data?.stage)
      .filter(Boolean) as Stage[];
    return stages.at(-1) ?? null;
  }, [chat.messages]);

  const busy = chat.status === "submitted" || chat.status === "streaming";

  // Which message is being written, for the streaming caret.
  const streamingId =
    chat.status === "streaming" && chat.messages.at(-1)?.role === "assistant"
      ? (chat.messages.at(-1)?.id ?? null)
      : null;

  return { ...chat, stage, busy, streamingId };
}
