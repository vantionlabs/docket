"use client";

import type { UIMessage } from "ai";
import { FileText } from "lucide-react";
import { useState } from "react";

/**
 * Messages, with the evidence attached.
 *
 * Streaming text and context-card patterns from Beautiful UI
 * (beautifului.dev, MIT, © 2026 Shane Levine), implemented here rather
 * than imported: the library is a showcase, not a package.
 *
 * The rule this screen follows is the same one the decision detail screen
 * follows: a claim and the words behind it should be one click apart.
 * Hovering a [n] marker lights up the source it came from, so checking an
 * answer does not mean re-reading the documents.
 */

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

/** Inline [n] markers become chips that highlight their source on hover. */
function AssistantText({
  text,
  streaming,
  active,
  onHover,
}: {
  text: string;
  streaming: boolean;
  active: number | null;
  onHover: (index: number | null) => void;
}) {
  const segments = text.split(/(\[\d+\])/g);
  return (
    <p className="text-[15px] leading-relaxed whitespace-pre-wrap">
      {segments.map((segment, i) => {
        const marker = segment.match(/^\[(\d+)\]$/);
        if (!marker) return <span key={i}>{segment}</span>;
        const index = Number(marker[1]);
        return (
          <sup key={i}>
            <button
              onMouseEnter={() => onHover(index)}
              onMouseLeave={() => onHover(null)}
              onFocus={() => onHover(index)}
              onBlur={() => onHover(null)}
              aria-label={`Source ${index}`}
              className={`mx-0.5 inline-flex h-4 min-w-4 items-center justify-center rounded px-1 text-[10px] font-semibold transition-colors ${
                active === index
                  ? "bg-amber-400 text-amber-950"
                  : "bg-foreground text-background"
              }`}
            >
              {index}
            </button>
          </sup>
        );
      })}
      {streaming && (
        <span
          aria-hidden
          className="bg-foreground ml-0.5 inline-block h-[1.1em] w-[2px] translate-y-[2px] animate-pulse"
        />
      )}
    </p>
  );
}

function ContextCards({
  citations,
  active,
  onHover,
}: {
  citations: Citation[];
  active: number | null;
  onHover: (index: number | null) => void;
}) {
  return (
    <div className="mt-4 space-y-1.5">
      <p className="text-muted-foreground text-[11px] font-medium tracking-wide uppercase">
        Sources
      </p>
      {citations.map((citation) => (
        <div
          key={citation.citation_index}
          onMouseEnter={() => onHover(citation.citation_index)}
          onMouseLeave={() => onHover(null)}
          className={`rounded-lg border p-2.5 transition-colors ${
            active === citation.citation_index
              ? "border-amber-300 bg-amber-50"
              : "bg-card"
          }`}
        >
          <p className="flex items-center gap-1.5 text-xs font-medium">
            <span
              className={`inline-flex h-4 min-w-4 items-center justify-center rounded px-1 text-[10px] font-semibold ${
                active === citation.citation_index
                  ? "bg-amber-400 text-amber-950"
                  : "bg-muted text-muted-foreground"
              }`}
            >
              {citation.citation_index}
            </span>
            <FileText size={11} className="text-muted-foreground shrink-0" />
            <span className="truncate">{citation.filename}</span>
          </p>
          <blockquote className="text-muted-foreground mt-1.5 border-l-2 pl-2 text-xs leading-relaxed">
            {citation.excerpt}
          </blockquote>
        </div>
      ))}
    </div>
  );
}

export function MessageList({
  messages,
  streamingId,
}: {
  messages: UIMessage[];
  /** Id of the message currently being written, for the caret. */
  streamingId?: string | null;
}) {
  const [active, setActive] = useState<number | null>(null);

  return (
    <div className="flex flex-col gap-8">
      {messages.map((message) => {
        const text = textOf(message);

        if (message.role === "user") {
          return (
            <div key={message.id} className="flex justify-end">
              <div className="bg-foreground text-background max-w-[80%] rounded-2xl px-4 py-2.5 text-[15px]">
                {text}
              </div>
            </div>
          );
        }

        const citations = citationsOf(message);
        return (
          <div key={message.id} className="max-w-[90%]">
            <AssistantText
              text={text}
              streaming={message.id === streamingId}
              active={active}
              onHover={setActive}
            />
            {citations.length > 0 && (
              <ContextCards
                citations={citations}
                active={active}
                onHover={setActive}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
