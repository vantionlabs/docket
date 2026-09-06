"use client";

import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport } from "ai";
import { useMemo } from "react";

import { API_URL } from "@/lib/api";

/**
 * Chat state + transport: the AI SDK's useChat wired to the FastAPI SSE
 * endpoint. `credentials: "include"` sends the httpOnly auth cookie with
 * the streaming request — no token in JS.
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

  return useChat({ id: threadId, transport });
}
