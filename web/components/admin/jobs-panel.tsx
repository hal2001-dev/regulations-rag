"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { enqueueIngest, fetchJobs, type JobItem } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Loader2, RotateCw } from "lucide-react";

const STATUS_CLASS: Record<JobItem["status"], string> = {
  queued: "text-muted-foreground",
  running: "text-primary",
  done: "text-emerald-600",
  failed: "text-destructive",
};

export function JobsPanel() {
  const [jobs, setJobs] = useState<JobItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [path, setPath] = useState("");
  const [docType, setDocType] = useState("");
  const [forceOcr, setForceOcr] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const refresh = async () => {
    setLoading(true);
    try {
      setJobs(await fetchJobs(30));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  useEffect(() => {
    if (!autoRefresh) return;
    const t = setInterval(refresh, 3000);
    return () => clearInterval(t);
  }, [autoRefresh]);

  const onEnqueue = async (e: React.FormEvent) => {
    e.preventDefault();
    const p = path.trim();
    if (!p || submitting) return;
    setSubmitting(true);
    try {
      const res = await enqueueIngest(p, docType || undefined, forceOcr);
      setToast(`enqueued job_id=${res.job_id}`);
      setPath("");
      setForceOcr(false);
      await refresh();
    } catch (err: unknown) {
      setToast(`enqueue 실패: ${String(err)}`);
    } finally {
      setSubmitting(false);
      setTimeout(() => setToast(null), 4000);
    }
  };

  const running = jobs.filter((j) => j.status === "running").length;
  const queued = jobs.filter((j) => j.status === "queued").length;

  return (
    <div className="space-y-4">
      <section className="space-y-2 rounded-md border bg-card p-3">
        <h2 className="text-sm font-semibold">새 문서 ingest</h2>
        <form onSubmit={onEnqueue} className="space-y-2">
          <Input
            value={path}
            onChange={(e) => setPath(e.target.value)}
            placeholder="서버 로컬 경로 (e.g. /Users/.../ingest/foo.pdf)"
            disabled={submitting}
          />
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={docType}
              onChange={(e) => setDocType(e.target.value)}
              className="h-10 rounded-md border border-input bg-background px-2 text-sm"
              disabled={submitting}
            >
              <option value="">doc_type 자동</option>
              {[
                "policy",
                "manual",
                "faq",
                "authority_matrix",
                "notice",
                "guideline",
                "template",
              ].map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
            <label className="flex items-center gap-1 text-xs">
              <input
                type="checkbox"
                checked={forceOcr}
                onChange={(e) => setForceOcr(e.target.checked)}
                disabled={submitting}
              />
              force OCR (스캔 PDF)
            </label>
            <Button type="submit" disabled={submitting || !path.trim()} size="sm">
              {submitting ? <Loader2 className="h-3 w-3 animate-spin" /> : "enqueue"}
            </Button>
          </div>
        </form>
      </section>

      <section className="space-y-2 rounded-md border bg-card p-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold">
            ingest jobs
            <span className="ml-2 text-xs font-normal text-muted-foreground">
              running {running} · queued {queued} · total {jobs.length}
            </span>
          </h2>
          <div className="flex items-center gap-2">
            <label className="flex items-center gap-1 text-xs text-muted-foreground">
              <input
                type="checkbox"
                checked={autoRefresh}
                onChange={(e) => setAutoRefresh(e.target.checked)}
              />
              auto
            </label>
            <Button variant="outline" size="icon" onClick={refresh} aria-label="새로고침">
              <RotateCw className={cn("h-4 w-4", loading && "animate-spin")} />
            </Button>
          </div>
        </div>

        <div className="max-h-[60vh] space-y-1 overflow-y-auto">
          {jobs.map((j) => (
            <div key={j.id} className="rounded-md border bg-muted/30 p-2 text-xs">
              <div className="flex items-baseline justify-between gap-2">
                <p className="line-clamp-1 font-mono">
                  #{j.id} · {j.source_path.split("/").slice(-1)[0]}
                </p>
                <span className={cn("shrink-0 font-mono uppercase", STATUS_CLASS[j.status])}>
                  {j.status}
                </span>
              </div>
              <div className="mt-1 flex flex-wrap gap-x-3 text-[10px] text-muted-foreground">
                {j.user_doc_type && <span>type: {j.user_doc_type}</span>}
                {j.force_ocr && <span>OCR</span>}
                {j.doc_id && <span>→ doc_id={j.doc_id}</span>}
                {j.finished_at && <span>{new Date(j.finished_at).toLocaleString("ko-KR")}</span>}
              </div>
              {j.error && (
                <p className="mt-1 line-clamp-2 text-[10px] text-destructive">{j.error}</p>
              )}
            </div>
          ))}
          {jobs.length === 0 && (
            <p className="px-2 py-6 text-center text-xs text-muted-foreground">jobs 없음</p>
          )}
        </div>
      </section>

      {toast && (
        <div className="fixed bottom-4 right-4 z-50 rounded-md border bg-card px-3 py-2 text-xs shadow-md">
          {toast}
        </div>
      )}
    </div>
  );
}
