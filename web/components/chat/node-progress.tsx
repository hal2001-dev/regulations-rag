"use client";

import { cn } from "@/lib/utils";
import { Check, Loader2 } from "lucide-react";

type Node = "clarifier" | "rewriter" | "router" | "retriever" | "generator" | "citation";

const LABEL: Record<Node, string> = {
  clarifier: "Clarify",
  rewriter: "HyDE",
  router: "Route",
  retriever: "Retrieve",
  generator: "Generate",
  citation: "Validate",
};

export type NodeStatus = "idle" | "active" | "done";

export function NodeProgress({
  status,
}: {
  status: Record<Node, NodeStatus>;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      {(Object.keys(LABEL) as Node[]).map((n) => {
        const s = status[n];
        return (
          <span
            key={n}
            className={cn(
              "inline-flex items-center gap-1 rounded-full border px-2 py-0.5",
              s === "active" && "border-primary text-primary",
              s === "done" && "border-emerald-500/40 text-emerald-600",
              s === "idle" && "border-border text-muted-foreground",
            )}
          >
            {s === "active" && <Loader2 className="h-3 w-3 animate-spin" />}
            {s === "done" && <Check className="h-3 w-3" />}
            {LABEL[n]}
          </span>
        );
      })}
    </div>
  );
}
