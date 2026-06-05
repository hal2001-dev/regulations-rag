import Link from "next/link";
import { JobsPanel } from "@/components/admin/jobs-panel";

export const dynamic = "force-dynamic";

export default function AdminPage() {
  return (
    <main className="container mx-auto max-w-3xl space-y-4 px-4 py-6">
      <header>
        <p className="text-xs uppercase tracking-widest text-muted-foreground">admin</p>
        <h1 className="text-xl font-semibold">인덱싱 관리</h1>
        <p className="text-xs text-muted-foreground">
          파일 ingest · 진행도 모니터링 · 실패 잡 확인. 라이브러리에서 개별 문서 재색인.
        </p>
        <nav className="mt-2 flex flex-wrap gap-3 text-xs">
          <Link href="/library" className="text-primary hover:underline">
            → /library
          </Link>
          <Link href="/chat" className="text-primary hover:underline">
            → /chat
          </Link>
        </nav>
      </header>
      <JobsPanel />
    </main>
  );
}
