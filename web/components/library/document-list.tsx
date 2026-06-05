"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  fetchChunks,
  fetchDocuments,
  reindexDocument,
  type ChunkItem,
  type DocumentItem,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { Loader2, RotateCw, Search } from "lucide-react";

const DOC_TYPE_OPTIONS = [
  "",
  "policy",
  "manual",
  "faq",
  "authority_matrix",
  "notice",
  "guideline",
  "template",
];

export function DocumentList() {
  const [docs, setDocs] = useState<DocumentItem[]>([]);
  const [filter, setFilter] = useState<string>("");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<DocumentItem | null>(null);
  const [chunks, setChunks] = useState<ChunkItem[]>([]);
  const [chunkInfo, setChunkInfo] = useState<{ total: number; offset: number; limit: number } | null>(null);
  const [loadingDocs, setLoadingDocs] = useState(true);
  const [loadingChunks, setLoadingChunks] = useState(false);
  const [reindexing, setReindexing] = useState<number | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const refreshDocs = async () => {
    setLoadingDocs(true);
    try {
      const items = await fetchDocuments(filter || undefined);
      setDocs(items);
    } finally {
      setLoadingDocs(false);
    }
  };

  useEffect(() => {
    refreshDocs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filter]);

  const onSelect = async (d: DocumentItem) => {
    setSelected(d);
    setLoadingChunks(true);
    try {
      const c = await fetchChunks(d.doc_id, 30, 0);
      setChunks(c.items);
      setChunkInfo({ total: c.total, offset: c.offset, limit: c.limit });
    } finally {
      setLoadingChunks(false);
    }
  };

  const onReindex = async (d: DocumentItem, forceOcr: boolean) => {
    if (!confirm(`"${d.title}" 재색인할까요?${forceOcr ? " (OCR 강제)" : ""}`)) return;
    setReindexing(d.doc_id);
    try {
      const res = await reindexDocument(d.doc_id, forceOcr);
      setToast(`재색인 enqueued — old=${res.old_doc_id} → job=${res.new_job_id}`);
      setSelected(null);
      setChunks([]);
      setTimeout(() => setToast(null), 4000);
      await refreshDocs();
    } catch (e: unknown) {
      setToast(`reindex 실패: ${String(e)}`);
    } finally {
      setReindexing(null);
    }
  };

  const visible = docs.filter((d) =>
    query ? d.title.toLowerCase().includes(query.toLowerCase()) : true,
  );

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-[1fr_1.2fr]">
      <section className="space-y-3">
        <div className="flex flex-wrap gap-2">
          <div className="relative flex-1 min-w-[180px]">
            <Search className="absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="문서 제목 검색"
              className="pl-8"
            />
          </div>
          <select
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="h-10 rounded-md border border-input bg-background px-2 text-sm"
          >
            {DOC_TYPE_OPTIONS.map((o) => (
              <option key={o} value={o}>
                {o || "(전체)"}
              </option>
            ))}
          </select>
          <Button variant="outline" size="icon" onClick={refreshDocs} aria-label="새로고침">
            <RotateCw className={cn("h-4 w-4", loadingDocs && "animate-spin")} />
          </Button>
        </div>

        <div className="text-xs text-muted-foreground">
          {loadingDocs ? "로딩…" : `${visible.length}/${docs.length} docs`}
        </div>

        <div className="max-h-[70vh] space-y-1 overflow-y-auto rounded-md border bg-card p-2">
          {visible.map((d) => {
            const active = selected?.doc_id === d.doc_id;
            return (
              <button
                key={d.doc_id}
                onClick={() => onSelect(d)}
                className={cn(
                  "block w-full rounded-md border p-2 text-left text-xs transition",
                  active
                    ? "border-primary bg-primary/5"
                    : "border-transparent hover:border-border hover:bg-accent",
                )}
              >
                <div className="flex items-baseline justify-between gap-2">
                  <p className="line-clamp-1 font-medium">{d.title}</p>
                  <span className="shrink-0 font-mono text-[10px] text-muted-foreground">
                    #{d.doc_id}
                  </span>
                </div>
                <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[10px] text-muted-foreground">
                  <span>{d.doc_type}</span>
                  <span>chunks {d.chunk_count}</span>
                  <span>{d.extraction_quality}</span>
                </div>
              </button>
            );
          })}
          {visible.length === 0 && !loadingDocs && (
            <p className="px-2 py-4 text-center text-xs text-muted-foreground">없음</p>
          )}
        </div>
      </section>

      <section className="space-y-3 rounded-md border bg-card p-3">
        {!selected && (
          <p className="py-12 text-center text-sm text-muted-foreground">
            왼쪽에서 문서를 선택하면 chunk preview 가 나타납니다.
          </p>
        )}
        {selected && (
          <>
            <header className="space-y-1">
              <p className="text-xs text-muted-foreground">
                #{selected.doc_id} · {selected.doc_type} · chunks {selected.chunk_count}
              </p>
              <h2 className="text-sm font-semibold">{selected.title}</h2>
              <div className="flex flex-wrap gap-2 pt-1">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => onReindex(selected, false)}
                  disabled={reindexing === selected.doc_id}
                >
                  {reindexing === selected.doc_id ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : (
                    <RotateCw className="h-3 w-3" />
                  )}
                  재색인
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => onReindex(selected, true)}
                  disabled={reindexing === selected.doc_id}
                >
                  재색인 + OCR
                </Button>
              </div>
            </header>

            <div className="text-[10px] uppercase tracking-widest text-muted-foreground">
              chunk preview
              {chunkInfo && (
                <span className="ml-2 font-mono normal-case text-foreground">
                  {chunkInfo.offset}–{chunkInfo.offset + chunks.length} / {chunkInfo.total}
                </span>
              )}
            </div>

            <div className="max-h-[60vh] space-y-2 overflow-y-auto pr-1">
              {loadingChunks && (
                <p className="text-xs text-muted-foreground">로딩…</p>
              )}
              {chunks.map((c) => (
                <div key={c.id} className="rounded-md border bg-muted/30 p-2 text-xs">
                  <p className="font-mono text-[10px] text-muted-foreground">
                    {c.chapter ? `${c.chapter} · ` : ""}
                    {c.article_no ?? "—"}
                    {c.article_title ? ` · ${c.article_title}` : ""}
                    {c.paragraph ? ` · ${c.paragraph}` : ""}
                  </p>
                  <p className="mt-1 whitespace-pre-wrap break-words leading-snug">
                    {c.body}
                  </p>
                </div>
              ))}
              {chunks.length === 0 && !loadingChunks && (
                <p className="text-xs text-muted-foreground italic">청크 없음.</p>
              )}
            </div>
          </>
        )}
      </section>

      {toast && (
        <div className="fixed bottom-4 right-4 z-50 rounded-md border bg-card px-3 py-2 text-xs shadow-md">
          {toast}
        </div>
      )}
    </div>
  );
}
