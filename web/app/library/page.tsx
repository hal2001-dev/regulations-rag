import { DocumentList } from "@/components/library/document-list";

export const dynamic = "force-dynamic";

export default function LibraryPage() {
  return (
    <main className="container mx-auto max-w-6xl space-y-4 px-4 py-6">
      <header>
        <p className="text-xs uppercase tracking-widest text-muted-foreground">library</p>
        <h1 className="text-xl font-semibold">규정 문서 라이브러리</h1>
        <p className="text-xs text-muted-foreground">
          문서 + 추출된 조항 preview · 재색인 (선택 시 OCR 강제)
        </p>
      </header>
      <DocumentList />
    </main>
  );
}
