"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import { formatHeadingPath, type SseSource } from "@/lib/api";

export function CitationChip({ source, idx }: { source: SseSource; idx: number }) {
  const [open, setOpen] = useState(false);
  const label = formatHeadingPath(source) || `근거 ${idx + 1}`;
  return (
    <div className="rounded-md border bg-muted/30 text-xs">
      <button
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "flex w-full items-center justify-between gap-2 px-3 py-2 text-left",
          "hover:bg-accent hover:text-accent-foreground",
        )}
      >
        <span className="line-clamp-1 font-medium">
          [{idx + 1}] {label}
        </span>
        {typeof source.score === "number" && (
          <span className="shrink-0 font-mono text-muted-foreground">
            {source.score.toFixed(3)}
          </span>
        )}
      </button>
      {open && source.body && (
        <pre className="border-t bg-background px-3 py-2 font-mono text-[11px] leading-snug whitespace-pre-wrap break-words text-muted-foreground">
          {source.body}
        </pre>
      )}
    </div>
  );
}
