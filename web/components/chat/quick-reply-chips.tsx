"use client";

import { Button } from "@/components/ui/button";

export function QuickReplyChips({
  question,
  options,
  onPick,
  disabled,
}: {
  question: string;
  options: string[];
  onPick: (choice: string) => void;
  disabled?: boolean;
}) {
  return (
    <div className="rounded-lg border border-amber-200 bg-amber-50/60 p-3 text-sm dark:border-amber-500/30 dark:bg-amber-500/5">
      <p className="mb-2 font-medium text-amber-900 dark:text-amber-200">{question}</p>
      <div className="flex flex-wrap gap-2">
        {options.map((opt) => (
          <Button
            key={opt}
            size="sm"
            variant="outline"
            disabled={disabled}
            onClick={() => onPick(opt)}
          >
            {opt}
          </Button>
        ))}
      </div>
    </div>
  );
}
