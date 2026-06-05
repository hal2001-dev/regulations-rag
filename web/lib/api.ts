/**
 * SSE 스트림 클라이언트 — /query/stream + /query/resume.
 *
 * 백엔드 이벤트:
 *  - clarify  : { question, options[], pattern, session_id }
 *  - rewrite  : { hyde }
 *  - route    : { route }
 *  - sources  : { sources[], via }
 *  - token    : { token } (generator 만)
 *  - citation : { valid_pct, valid[] }
 *  - done     : { route, citation_valid_pct, session_id, timings }
 *  - error    : { message }
 */

// `/api/*` 는 web/next.config.ts 의 rewrites 로 FastAPI(8001) 에 프록시됨.
// 외부 빌드에서 절대 URL 이 필요하면 NEXT_PUBLIC_API_URL 로 override.
export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "/api";

export type SseSource = {
  article_id?: number;
  doc_id?: number;
  article_no?: string;
  article_title?: string | null;
  chapter?: string | null;
  heading_path?: Record<string, unknown> | null;
  body?: string;
  score?: number;
};

export type SseEvent =
  | { type: "clarify"; question: string; options: string[]; pattern: string; session_id: string }
  | { type: "rewrite"; hyde: string }
  | { type: "route"; route: string }
  | { type: "sources"; sources: SseSource[]; via: string }
  | { type: "token"; token: string }
  | { type: "citation"; valid_pct: number; valid: boolean[] }
  | {
      type: "done";
      route: string | null;
      citation_valid_pct: number;
      session_id: string;
      timings: Record<string, number>;
    }
  | { type: "error"; message: string };

type StreamOpts = {
  signal?: AbortSignal;
  onEvent: (ev: SseEvent) => void;
};

async function readSse(resp: Response, opts: StreamOpts) {
  if (!resp.ok || !resp.body) {
    opts.onEvent({ type: "error", message: `HTTP ${resp.status}` });
    return;
  }
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });

    // SSE 는 "\n\n" 로 메시지 구분
    let idx: number;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const raw = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      parseSseBlock(raw, opts.onEvent);
    }
  }
  if (buf.trim()) parseSseBlock(buf, opts.onEvent);
}

function parseSseBlock(block: string, emit: (ev: SseEvent) => void) {
  const lines = block.split("\n");
  let event = "message";
  let dataStr = "";
  for (const line of lines) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataStr += line.slice(5).trim();
  }
  if (!dataStr) return;
  let payload: any;
  try {
    payload = JSON.parse(dataStr);
  } catch {
    return;
  }
  emit({ type: event as SseEvent["type"], ...payload });
}

export async function streamQuery(
  question: string,
  sessionId: string | null,
  opts: StreamOpts,
) {
  const resp = await fetch(`${API_BASE}/query/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, session_id: sessionId }),
    signal: opts.signal,
  });
  await readSse(resp, opts);
}

export async function resumeQuery(
  sessionId: string,
  choice: string,
  opts: StreamOpts,
) {
  const resp = await fetch(`${API_BASE}/query/resume`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, choice }),
    signal: opts.signal,
  });
  await readSse(resp, opts);
}

// ────────────────────────────────────────────────────────────────────
// Library / Admin REST
// ────────────────────────────────────────────────────────────────────

export type DocumentItem = {
  doc_id: number;
  title: string;
  doc_type: string;
  domain: string | null;
  chunk_count: number;
  status: string;
  extraction_quality: string;
  indexed_at: string | null;
};

export type ChunkItem = {
  id: number;
  chapter: string | null;
  article_no: string | null;
  article_title: string | null;
  paragraph: string | null;
  body: string;
  heading_path: Record<string, unknown> | null;
};

export type JobItem = {
  id: number;
  source_path: string;
  status: "queued" | "running" | "done" | "failed";
  doc_id: number | null;
  user_doc_type: string | null;
  force_ocr: boolean;
  error: string | null;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
};

async function jget<T>(path: string): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`GET ${path} → ${r.status}`);
  return r.json();
}

async function jpost<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
  if (!r.ok) {
    const txt = await r.text();
    throw new Error(`POST ${path} → ${r.status}: ${txt}`);
  }
  return r.json();
}

export async function fetchDocuments(docType?: string) {
  const qs = docType ? `?doc_type=${encodeURIComponent(docType)}` : "";
  const j = await jget<{ items: DocumentItem[] }>(`/documents${qs}`);
  return j.items;
}

export async function fetchChunks(
  docId: number,
  limit = 30,
  offset = 0,
): Promise<{
  doc_id: number;
  title: string;
  doc_type: string;
  total: number;
  offset: number;
  limit: number;
  items: ChunkItem[];
}> {
  return jget(`/documents/${docId}/chunks?limit=${limit}&offset=${offset}`);
}

export async function fetchJobs(limit = 30) {
  const j = await jget<{ items: JobItem[] }>(`/jobs?limit=${limit}`);
  return j.items;
}

export async function reindexDocument(
  docId: number,
  forceOcr = false,
): Promise<{ old_doc_id: number; source_path: string; new_job_id: number }> {
  return jpost(`/admin/reindex/${docId}`, { force_ocr: forceOcr });
}

export async function enqueueIngest(
  sourcePath: string,
  userDocType?: string,
  forceOcr = false,
): Promise<{ job_id: number; source_path: string; status: string }> {
  return jpost(`/ingest`, {
    source_path: sourcePath,
    user_doc_type: userDocType ?? null,
    force_ocr: forceOcr,
  });
}

// ────────────────────────────────────────────────────────────────────
// Shared formatters
// ────────────────────────────────────────────────────────────────────

export function formatHeadingPath(s: SseSource): string {
  const hp = (s.heading_path ?? {}) as Record<string, string>;
  const parts: string[] = [];
  // doc 이름이 source 에 직접 없고 doc_id 만 있을 수도 — 그땐 article_no/title 만 표시
  if (hp.doc_title) parts.push(String(hp.doc_title));
  if (hp.chapter || s.chapter) parts.push(String(hp.chapter ?? s.chapter));
  if (s.article_no) parts.push(`제${s.article_no}조`);
  if (s.article_title) parts.push(String(s.article_title));
  return parts.filter(Boolean).join(" > ");
}
