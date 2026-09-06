"use client";

import type { UIMessage } from "ai";

export type Citation = {
  citation_index: number;
  excerpt: string;
  filename: string;
  document_id: string;
  chunk_id: string;
};

function citationsOf(message: UIMessage): Citation[] {
  return message.parts
    .filter((p) => p.type === "data-citation")
    .map((p) => (p as { data: Citation }).data)
    .sort((a, b) => a.citation_index - b.citation_index);
}

function textOf(message: UIMessage): string {
  return message.parts
    .filter((p) => p.type === "text")
    .map((p) => (p as { text: string }).text)
    .join("");
}

/** Inline [n] markers become superscript chips; the sources list sits under the answer. */
function AssistantText({ text }: { text: string }) {
  const segments = text.split(/(\[\d+\])/g);
  return (
    <p className="whitespace-pre-wrap text-[15px] leading-relaxed">
      {segments.map((seg, i) => {
        const m = seg.match(/^\[(\d+)\]$/);
        if (!m) return <span key={i}>{seg}</span>;
        return (
          <sup
            key={i}
            className="mx-0.5 inline-flex h-4 min-w-4 items-center justify-center rounded bg-neutral-900 px-1 text-[10px] font-semibold text-white"
          >
            {m[1]}
          </sup>
        );
      })}
    </p>
  );
}

export function MessageList({ messages }: { messages: UIMessage[] }) {
  return (
    <div className="flex flex-col gap-6">
      {messages.map((message) => {
        const text = textOf(message);
        if (message.role === "user") {
          return (
            <div key={message.id} className="flex justify-end">
              <div className="max-w-[80%] rounded-2xl bg-neutral-900 px-4 py-2.5 text-[15px] text-white">
                {text}
              </div>
            </div>
          );
        }
        const citations = citationsOf(message);
        return (
          <div key={message.id} className="max-w-[90%]">
            <AssistantText text={text} />
            {citations.length > 0 && (
              <div className="mt-3 flex flex-col gap-1.5 border-t border-neutral-100 pt-3">
                {citations.map((c) => (
                  <details key={c.citation_index} className="group">
                    <summary className="flex cursor-pointer list-none items-center gap-2 text-xs text-neutral-500 hover:text-neutral-900">
                      <span className="inline-flex h-4 min-w-4 items-center justify-center rounded bg-neutral-200 px-1 text-[10px] font-semibold text-neutral-700">
                        {c.citation_index}
                      </span>
                      <span className="truncate font-medium">{c.filename}</span>
                    </summary>
                    <blockquote className="mt-1.5 border-l-0 rounded-lg bg-neutral-50 px-3 py-2 text-xs leading-relaxed text-neutral-600">
                      {c.excerpt}
                    </blockquote>
                  </details>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
