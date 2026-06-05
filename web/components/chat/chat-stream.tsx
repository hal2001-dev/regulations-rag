"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { resumeQuery, streamQuery, type SseEvent, type SseSource } from "@/lib/api";
import { Send } from "lucide-react";
import { AnswerBlocks } from "./answer-blocks";
import { CitationChip } from "./citation-chip";
import { NodeProgress, type NodeStatus } from "./node-progress";
import { QuickReplyChips } from "./quick-reply-chips";
import { StarterChips } from "./starter-chips";

type Turn = {
  id: string;
  question: string;
  answer: string;
  sources: SseSource[];
  clarify?: { question: string; options: string[]; pattern: string };
  citationPct?: number;
  route?: string | null;
  hyde?: string;
  status: Record<NodeName, NodeStatus>;
  timings?: Record<string, number>;
  error?: string;
  awaitingResume?: boolean;
};

type NodeName = "clarifier" | "rewriter" | "router" | "retriever" | "generator" | "citation";

function newId(): string {
  // crypto.randomUUID 는 secure context (https/localhost) 에서만 동작 — LAN IP 접속 대비 fallback.
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

const INITIAL_STATUS: Record<NodeName, NodeStatus> = {
  clarifier: "idle",
  rewriter: "idle",
  router: "idle",
  retriever: "idle",
  generator: "idle",
  citation: "idle",
};

export function ChatStream() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns]);

  const updateLast = (patch: Partial<Turn>) =>
    setTurns((prev) => {
      if (prev.length === 0) return prev;
      const last = prev[prev.length - 1];
      return [...prev.slice(0, -1), { ...last, ...patch }];
    });

  const patchLastStatus = (node: NodeName, s: NodeStatus) =>
    setTurns((prev) => {
      if (prev.length === 0) return prev;
      const last = prev[prev.length - 1];
      return [
        ...prev.slice(0, -1),
        { ...last, status: { ...last.status, [node]: s } },
      ];
    });

  const handleEvent = (ev: SseEvent) => {
    switch (ev.type) {
      case "clarify":
        setSessionId(ev.session_id);
        patchLastStatus("clarifier", "done");
        updateLast({
          clarify: { question: ev.question, options: ev.options, pattern: ev.pattern },
          awaitingResume: true,
        });
        break;
      case "rewrite":
        patchLastStatus("clarifier", "done");
        patchLastStatus("rewriter", "done");
        updateLast({ hyde: ev.hyde });
        break;
      case "route":
        patchLastStatus("router", "done");
        updateLast({ route: ev.route });
        if (ev.route === "authority") patchLastStatus("retriever", "active");
        else patchLastStatus("retriever", "active");
        break;
      case "sources":
        patchLastStatus("retriever", "done");
        patchLastStatus("generator", "active");
        updateLast({ sources: ev.sources });
        break;
      case "token":
        setTurns((prev) => {
          if (prev.length === 0) return prev;
          const last = prev[prev.length - 1];
          return [
            ...prev.slice(0, -1),
            { ...last, answer: last.answer + ev.token },
          ];
        });
        break;
      case "citation":
        patchLastStatus("generator", "done");
        patchLastStatus("citation", "done");
        updateLast({ citationPct: ev.valid_pct });
        break;
      case "done":
        setSessionId(ev.session_id);
        updateLast({ timings: ev.timings, route: ev.route ?? null });
        break;
      case "error":
        updateLast({ error: ev.message });
        break;
    }
  };

  const startTurn = async (question: string) => {
    const turn: Turn = {
      id: newId(),
      question,
      answer: "",
      sources: [],
      status: { ...INITIAL_STATUS, clarifier: "active" },
    };
    setTurns((prev) => [...prev, turn]);
    setBusy(true);
    try {
      await streamQuery(question, sessionId, { onEvent: handleEvent });
    } catch (e: unknown) {
      updateLast({ error: String(e) });
    } finally {
      setBusy(false);
    }
  };

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const q = draft.trim();
    if (!q || busy) return;
    setDraft("");
    await startTurn(q);
  };

  const onPickChip = async (choice: string) => {
    if (!sessionId || busy) return;
    setBusy(true);
    updateLast({ awaitingResume: false });
    patchLastStatus("clarifier", "done");
    patchLastStatus("rewriter", "active");
    try {
      await resumeQuery(sessionId, choice, { onEvent: handleEvent });
    } catch (e: unknown) {
      updateLast({ error: String(e) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex h-full flex-col gap-4">
      <div className="flex-1 space-y-6 overflow-y-auto rounded-lg border bg-card p-4">
        {turns.length === 0 && (
          <div className="flex h-full items-center justify-center px-2">
            <StarterChips onPick={startTurn} disabled={busy} />
          </div>
        )}
        {turns.map((t) => (
          <article key={t.id} className="space-y-3">
            <div className="rounded-md bg-muted/40 p-3 text-sm">
              <p className="text-xs font-semibold text-muted-foreground">질문</p>
              <p className="mt-1">{t.question}</p>
            </div>

            <NodeProgress status={t.status} />

            {t.route && (
              <p className="text-xs text-muted-foreground">
                route: <code className="font-mono">{t.route}</code>
                {t.hyde && (
                  <>
                    {" "}· HyDE 확장 <span className="opacity-70">({t.hyde.length} chars)</span>
                  </>
                )}
              </p>
            )}

            {t.clarify && t.awaitingResume && (
              <QuickReplyChips
                question={t.clarify.question}
                options={t.clarify.options}
                onPick={onPickChip}
                disabled={busy}
              />
            )}

            {(t.answer || (!t.clarify && !t.error)) && <AnswerBlocks text={t.answer} />}

            {t.sources.length > 0 && (
              <div className="space-y-1">
                <p className="text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
                  근거 ({t.sources.length})
                  {typeof t.citationPct === "number" && (
                    <span className="ml-2 font-mono normal-case text-foreground">
                      valid {(t.citationPct * 100).toFixed(0)}%
                    </span>
                  )}
                </p>
                <div className="grid gap-1.5">
                  {t.sources.map((s, i) => (
                    <CitationChip key={`${t.id}-${i}`} source={s} idx={i} />
                  ))}
                </div>
              </div>
            )}

            {t.error && (
              <div className="rounded-md border border-destructive/50 bg-destructive/10 p-2 text-xs text-destructive">
                error: {t.error}
              </div>
            )}
          </article>
        ))}
        <div ref={bottomRef} />
      </div>

      <form onSubmit={onSubmit} className="flex items-center gap-2">
        <Input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={busy ? "답변 받는 중…" : "질문을 입력하세요"}
          disabled={busy}
          autoFocus
        />
        <Button type="submit" disabled={busy || !draft.trim()} size="icon" aria-label="전송">
          <Send className="h-4 w-4" />
        </Button>
      </form>
    </div>
  );
}
