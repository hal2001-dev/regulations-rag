import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "regulations-rag",
  description: "사내 규정/매뉴얼/FAQ 한국어 Enterprise RAG",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ko">
      <body className="min-h-screen bg-background text-foreground antialiased">
        {children}
      </body>
    </html>
  );
}
