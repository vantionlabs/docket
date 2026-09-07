"use client";

import { ArrowUp, Square } from "lucide-react";
import { useEffect, useRef } from "react";

/**
 * The prompt bar.
 *
 * Pattern from Beautiful UI (beautifului.dev, MIT, © 2026 Shane Levine),
 * implemented here rather than imported: the library is a showcase, not a
 * package.
 *
 * A textarea rather than an input, because questions about policy run to
 * two or three lines and a single-line box that scrolls sideways makes you
 * lose your place. Enter sends, Shift+Enter breaks the line, and it grows
 * to a ceiling rather than forever.
 */
export function Composer({
  value,
  onChange,
  onSubmit,
  onStop,
  busy,
  placeholder = "Ask a question…",
  autoFocus = false,
}: {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onStop?: () => void;
  busy: boolean;
  placeholder?: string;
  autoFocus?: boolean;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);

  // Grow with the content, up to a ceiling. Measured from a reset height so
  // deleting a line shrinks it back rather than leaving a hole.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [value]);

  const canSend = value.trim().length > 0 && !busy;

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        if (canSend) onSubmit();
      }}
      className="focus-within:ring-ring bg-card relative rounded-2xl border shadow-sm transition-shadow focus-within:ring-1"
    >
      <textarea
        ref={ref}
        rows={1}
        autoFocus={autoFocus}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            if (canSend) onSubmit();
          }
        }}
        placeholder={placeholder}
        className="placeholder:text-muted-foreground max-h-[200px] w-full resize-none bg-transparent px-4 py-3.5 pr-12 text-[15px] leading-relaxed focus:outline-none"
      />

      <div className="absolute right-2 bottom-2">
        {busy && onStop ? (
          <button
            type="button"
            onClick={onStop}
            aria-label="Stop generating"
            className="bg-foreground text-background flex size-8 items-center justify-center rounded-full transition-opacity hover:opacity-80"
          >
            <Square size={12} fill="currentColor" />
          </button>
        ) : (
          <button
            type="submit"
            disabled={!canSend}
            aria-label="Send"
            className="bg-foreground text-background flex size-8 items-center justify-center rounded-full transition-opacity disabled:opacity-25"
          >
            <ArrowUp size={16} />
          </button>
        )}
      </div>
    </form>
  );
}
