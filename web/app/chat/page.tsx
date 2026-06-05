import { ChatStream } from "@/components/chat/chat-stream";

export const dynamic = "force-dynamic";

export default function ChatPage() {
  return (
    <main className="container mx-auto flex h-screen max-w-3xl flex-col gap-4 py-6">
      <header>
        <p className="text-xs uppercase tracking-widest text-muted-foreground">
          regulations-rag
        </p>
        <h1 className="text-xl font-semibold">사내 규정 챗봇</h1>
        <p className="text-xs text-muted-foreground">
          LangGraph clarifier · HyDE · hybrid retrieval · authority SQL · streaming.
        </p>
      </header>
      <div className="min-h-0 flex-1">
        <ChatStream />
      </div>
    </main>
  );
}
