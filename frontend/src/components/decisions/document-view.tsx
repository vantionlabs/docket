"use client";

import { useEffect, useMemo, useRef } from "react";

/**
 * The document, with one field's source span highlighted.
 *
 * The span is matched the way the backend's verbatim check matches it:
 * whitespace-collapsed and case-insensitive, with nothing else normalized.
 * Doing it any other way would light up text the check would have rejected,
 * which is worse than highlighting nothing, because the whole point of this
 * pane is that a reviewer can trust what it shows them.
 */
export function DocumentView({
  text,
  highlight,
}: {
  text: string;
  highlight: string | null;
}) {
  const markRef = useRef<HTMLSpanElement>(null);

  const parts = useMemo(() => splitOnSpan(text, highlight), [text, highlight]);

  useEffect(() => {
    markRef.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [highlight]);

  return (
    <pre className="text-foreground/90 max-h-[calc(100vh-16rem)] overflow-auto rounded-lg border bg-card p-4 text-xs leading-relaxed whitespace-pre-wrap">
      {parts.before}
      {parts.match && (
        <span
          ref={markRef}
          className="rounded bg-amber-200 px-0.5 py-px text-amber-950 ring-1 ring-amber-400"
        >
          {parts.match}
        </span>
      )}
      {parts.after}
    </pre>
  );
}

/**
 * Find `span` inside `text` under the backend's normalization, and return
 * the original (un-normalized) slices around it.
 *
 * Matching happens on a normalized copy while an index map remembers where
 * each normalized character came from, so the highlight lands on the real
 * characters even when the document wraps mid-span.
 */
export function splitOnSpan(text: string, span: string | null) {
  if (!span?.trim()) return { before: text, match: "", after: "" };

  const { normalized, map } = normalizeWithMap(text);
  const target = normalizeWithMap(span).normalized;
  if (!target) return { before: text, match: "", after: "" };

  const at = normalized.indexOf(target);
  if (at === -1) return { before: text, match: "", after: "" };

  const start = map[at];
  const end = map[at + target.length - 1] + 1;
  return {
    before: text.slice(0, start),
    match: text.slice(start, end),
    after: text.slice(end),
  };
}

/**
 * Collapse runs of whitespace to one space and lowercase, keeping an index
 * back to the original string for every character emitted.
 */
function normalizeWithMap(input: string) {
  let normalized = "";
  const map: number[] = [];
  let pendingSpace = false;

  for (let i = 0; i < input.length; i++) {
    const char = input[i];
    if (/\s/.test(char)) {
      pendingSpace = normalized.length > 0;
      continue;
    }
    if (pendingSpace) {
      normalized += " ";
      map.push(i);
      pendingSpace = false;
    }
    normalized += char.toLowerCase();
    map.push(i);
  }
  return { normalized, map };
}
