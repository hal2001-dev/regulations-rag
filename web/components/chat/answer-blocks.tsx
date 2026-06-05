"use client";

import { cn } from "@/lib/utils";

/**
 * 답변 본문을 [결론]/[근거] 헤더로 분리해 시각적으로 강조.
 * 모르겠으면 그냥 plain text 로 표시.
 */
export function AnswerBlocks({ text }: { text: string }) {
  if (!text) {
    return (
      <p className="text-sm text-muted-foreground italic">답변 생성 중…</p>
    );
  }

  // [결론] / [근거] 헤더 분리
  const sections = splitSections(text);
  if (sections.length === 0) {
    return <Plain text={text} />;
  }

  return (
    <div className="space-y-3">
      {sections.map((sec, i) => (
        <div
          key={i}
          className={cn(
            "rounded-md border p-3 text-sm",
            sec.tag === "결론" && "border-primary/30 bg-primary/5",
            sec.tag === "근거" && "border-emerald-500/30 bg-emerald-500/5",
            !sec.tag && "border-border bg-muted/30",
          )}
        >
          {sec.tag && (
            <p
              className={cn(
                "mb-1 text-[10px] font-semibold uppercase tracking-widest",
                sec.tag === "결론" && "text-primary",
                sec.tag === "근거" && "text-emerald-700 dark:text-emerald-300",
              )}
            >
              [{sec.tag}]
            </p>
          )}
          <Plain text={sec.body} />
        </div>
      ))}
    </div>
  );
}

function Plain({ text }: { text: string }) {
  return <p className="whitespace-pre-wrap break-words leading-relaxed">{text}</p>;
}

type Section = { tag: "결론" | "근거" | null; body: string };

function splitSections(text: string): Section[] {
  const re = /\[(결론|근거)\]/g;
  const matches = [...text.matchAll(re)];
  if (matches.length === 0) return [];

  const out: Section[] = [];
  // prefix before first tag
  if (matches[0].index! > 0) {
    const pre = text.slice(0, matches[0].index!).trim();
    if (pre) out.push({ tag: null, body: pre });
  }
  for (let i = 0; i < matches.length; i++) {
    const tag = matches[i][1] as "결론" | "근거";
    const start = matches[i].index! + matches[i][0].length;
    const end = i + 1 < matches.length ? matches[i + 1].index! : text.length;
    const body = text.slice(start, end).trim();
    out.push({ tag, body });
  }
  return out;
}
