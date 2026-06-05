"use client";

import { Button } from "@/components/ui/button";
import { Scale, ScrollText, FileText } from "lucide-react";

type Group = {
  label: string;
  icon: React.ReactNode;
  prompts: string[];
};

const GROUPS: Group[] = [
  {
    label: "정책·규정",
    icon: <ScrollText className="h-3.5 w-3.5" />,
    prompts: [
      "연차휴가 어떻게 신청하나요?",
      "내부회계관리규정 제5조 내용은?",
      "여비규정 일비 기준이 어떻게 돼?",
    ],
  },
  {
    label: "위임전결",
    icon: <Scale className="h-3.5 w-3.5" />,
    prompts: [
      "3천만원 계약 누가 결재하나요?",
      "5천만원 한도 결재권자",
      "사무위임전결 부서장 한도",
    ],
  },
  {
    label: "매뉴얼",
    icon: <FileText className="h-3.5 w-3.5" />,
    prompts: [
      "자치법규 입법 절차를 단계별로 설명",
      "교육활동 보호 매뉴얼에서 학생 폭언 대응 절차",
    ],
  },
];

export function StarterChips({
  onPick,
  disabled,
}: {
  onPick: (question: string) => void;
  disabled?: boolean;
}) {
  return (
    <div className="w-full max-w-2xl space-y-4">
      <div className="text-center">
        <p className="text-sm font-medium">사내 규정·매뉴얼·위임전결을 물어보세요</p>
        <p className="mt-1 text-xs text-muted-foreground">
          아래 예시를 클릭하거나, 직접 질문을 입력하세요.
        </p>
      </div>

      <div className="space-y-3">
        {GROUPS.map((g) => (
          <div key={g.label} className="space-y-1.5">
            <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
              {g.icon}
              {g.label}
            </div>
            <div className="flex flex-wrap gap-1.5">
              {g.prompts.map((p) => (
                <Button
                  key={p}
                  size="sm"
                  variant="outline"
                  disabled={disabled}
                  onClick={() => onPick(p)}
                  className="h-auto whitespace-normal px-2.5 py-1.5 text-left text-xs font-normal"
                >
                  {p}
                </Button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
