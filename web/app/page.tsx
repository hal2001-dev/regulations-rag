import Link from "next/link";

export default function Home() {
  return (
    <main className="container mx-auto flex min-h-screen max-w-3xl flex-col gap-6 py-16">
      <header className="space-y-2">
        <p className="text-sm uppercase tracking-widest text-muted-foreground">
          M1 shell · 부팅 검증용
        </p>
        <h1 className="text-3xl font-semibold">regulations-rag</h1>
        <p className="text-muted-foreground">
          사내 규정 · 매뉴얼 · FAQ 17 PDF 를 통합 검색하는 한국어 Enterprise RAG.
          LangGraph state machine + Qdrant + Postgres 기반.
        </p>
      </header>

      <section className="rounded-lg border bg-muted/30 p-4 text-sm">
        <p className="font-medium">M1 상태</p>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-muted-foreground">
          <li>FastAPI <code className="font-mono">/health</code> · Postgres 7 테이블 · Qdrant healthy</li>
          <li>Indexer worker skeleton (큐 폴링만, M2 에서 Docling 연결)</li>
          <li>이 페이지 자체는 M5 (Chat UI) 까지 placeholder</li>
        </ul>
      </section>

      <nav className="flex flex-wrap gap-3">
        <Link
          href="/chat"
          className="rounded-md border bg-primary px-4 py-2 text-sm text-primary-foreground transition hover:opacity-90"
        >
          /chat →
        </Link>
        <Link
          href="/library"
          className="rounded-md border px-4 py-2 text-sm transition hover:bg-accent"
        >
          /library
        </Link>
        <Link
          href="/admin"
          className="rounded-md border px-4 py-2 text-sm transition hover:bg-accent"
        >
          /admin
        </Link>
        <a
          href="/api/health"
          className="rounded-md border px-4 py-2 text-sm transition hover:bg-accent"
        >
          /api/health
        </a>
      </nav>
    </main>
  );
}
