"""위임전결 표 추출 — gpt-4o-mini **vision** (페이지 이미지 직접).

ADR-017: mvp_plan §M2.5 의 regex 추출은 PDF 표의 hierarchical/spanned 구조에서 동작 X
(1차 LLM text 시도 결과 177 rules 다 사장+amt=None). pypdfium2 로 페이지를 PNG 렌더 후
gpt-4o-mini 의 vision 입력으로 직접 표 셀 읽기. 비용 ~$0.01-0.05/PDF.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI

from apps.config import get_settings
from packages.code.logger import get_logger

log = get_logger("packages.regulation_parser.authority_extractor")


# ────────────────────────────────────────────────────────────────────
# 12-keyword process map (mvp_plan §M2.5 의 "12-keyword 맵")
# ────────────────────────────────────────────────────────────────────

PROCESS_TAXONOMY: dict[str, list[str]] = {
    "discount_approval": ["할인", "감면", "할인율"],
    "contract": ["계약", "공사", "용역", "제조", "물품계약"],
    "expense_claim": ["여비", "출장", "여비정산", "출장비"],
    "purchase": ["구매", "물품구매", "물품"],
    "approval_general": ["품의", "전결", "결재", "위임"],
    "personnel": ["임용", "휴가", "휴직", "인사", "채용", "복직"],
    "audit": ["감사"],
    "budget_execution": ["예산", "지출", "집행", "예산집행"],
    "report": ["보고"],
    "meeting": ["회의", "이사회"],
    "policy_management": ["규정", "정책", "방침"],
    "other": [],  # fallback
}

VALID_PROCESSES = set(PROCESS_TAXONOMY.keys())


# ────────────────────────────────────────────────────────────────────
# 추출 결과 dataclass
# ────────────────────────────────────────────────────────────────────


@dataclass
class ExtractedRule:
    process: str
    task: str
    approval_role: str
    amount_limit_krw: int | None
    approval_limit_pct: float | None
    condition: str | None
    raw_row: dict[str, Any] = field(default_factory=dict)
    source_page: int | None = None

    def is_valid(self) -> bool:
        if self.process not in VALID_PROCESSES:
            return False
        if not self.approval_role.strip():
            return False
        if not self.task.strip():
            return False
        if self.amount_limit_krw is not None and self.amount_limit_krw < 0:
            return False
        if self.approval_limit_pct is not None and not (0 <= self.approval_limit_pct <= 100):
            return False
        return True


# ────────────────────────────────────────────────────────────────────
# LLM prompt (vision)
# ────────────────────────────────────────────────────────────────────

_VISION_SYSTEM_PROMPT = """당신은 한국 사내 위임전결규정 PDF 페이지 이미지를 보고 표를 구조화 JSON 으로 추출하는 전문가입니다.

이미지에 위임전결 표가 있으면 그 표만 읽어서 다음 JSON 으로 반환:

{
  "has_table": true,
  "rules": [
    {
      "process": "discount_approval|contract|expense_claim|purchase|approval_general|personnel|audit|budget_execution|report|meeting|policy_management|other 중 하나",
      "task": "표의 행의 사무 내용 (한 줄 한국어)",
      "approval_role": "○ 표시된 결재권자 직위 (사장/본부장/부서장/팀장/시장/이사회 등 — 표 헤더의 정확한 값)",
      "amount_limit_krw": 50000000 같은 정수 (해당 행의 한도 금액, 없으면 null),
      "approval_limit_pct": 30.0 같은 실수 (해당 행의 한도 %, 없으면 null),
      "condition": "추가 조건 (없으면 null)"
    }
  ]
}

이미지에 위임전결 표가 없으면 (예: 부칙/본문/표지 페이지):
{"has_table": false, "rules": []}

규칙:
- ○ 표시 위치를 정확히 읽어 결재권자 열을 매칭. **사무별로 ○ 가 있는 각 결재권자마다 별도 rule** 을 만들어라. (예: 한 사무에 부서장/본부장/사장 ○ → 3 rules)
- "5천만 원" / "5,000만 원" / "50,000,000원" 모두 → amount_limit_krw=50000000.
- "1억" → 100000000, "1억 5천만" → 150000000.
- 한도 명시 안 된 일반 결재 (예: "이사회 운영") 도 포함 (amount=null, pct=null).
- task 는 표 안의 한국어 그대로. 영어 번역 X.
- 본문 일반 조항 (제N조) 무시. 별표/전결사항 표만.
- 표가 페이지를 걸쳐있어 행 일부만 보이면 보이는 만큼만 추출.
"""

# legacy (text-only, M4 1차 시도) 는 호환성 위해 남김
_SYSTEM_PROMPT = """당신은 한국 사내 위임전결규정 PDF 의 표를 구조화 JSON 으로 추출하는 전문가입니다.
입력은 Docling 으로 markdown 변환된 본문 (표 포함). 별표/사무위임 전결사항 표가 핵심.

출력 JSON 스키마 (반드시 `{"rules": [...]}` 형식):

{
  "rules": [
    {
      "process": "discount_approval|contract|expense_claim|purchase|approval_general|personnel|audit|budget_execution|report|meeting|policy_management|other 중 하나",
      "task": "표의 행 그대로의 사무 내용 (한 줄)",
      "approval_role": "결재권자 직위 (사장/본부장/부서장/팀장/시장/이사회 등 표 헤더의 값)",
      "amount_limit_krw": 50000000 같은 정수 (해당 행에 한도 금액이 있으면, 없으면 null),
      "approval_limit_pct": 30.0 같은 실수 (해당 행에 한도 % 가 있으면, 없으면 null),
      "condition": "조건이 명시되면 한 줄, 없으면 null"
    }
  ]
}

규칙:
- 표의 1 행에 ○ 표시가 여러 결재권자에 있으면, 한 행에 여러 rule 로 출력. (예: ○ 부서장 + ○ 본부장 + ○ 사장 = 3 rules with same task, different role)
- 동일 사무에 여러 한도 구간 (예: "1) 5천만원 이하, 2) 2천만원 이하") 이 있으면 각 구간을 별도 rule 로 출력.
- "5천만원" → 50000000, "1억원" → 100000000, "1억 5천만원" → 150000000.
- 한도 없는 일반 결재사항 (예: "이사회 운영") 도 포함 (amount=null, pct=null).
- 본문 일반 조항 (제N조) 은 무시. 별표/전결사항 표만.
- 최대 200 rules. 너무 많으면 금액/% 명시 rules 우선.
- task 는 표 안의 본래 한국어 문구 사용. 영어 번역 X.
"""


def _user_prompt(markdown_text: str, max_chars: int = 30000) -> str:
    truncated = markdown_text[:max_chars]
    suffix = f"\n\n(전체 {len(markdown_text):,} chars 중 {max_chars:,} 까지)" if len(markdown_text) > max_chars else ""
    return f"다음 위임전결규정 markdown 에서 rules JSON 을 추출하세요:\n\n{truncated}{suffix}"


# ────────────────────────────────────────────────────────────────────
# 추출 함수
# ────────────────────────────────────────────────────────────────────


_MAN_RE = re.compile(r"^(?:\s)*(\d[\d,]*)\s*(?:만원|만\s원)")  # 5,000 만원 등
_EOK_RE = re.compile(r"^(?:\s)*(\d[\d,]*)\s*억원?")            # 1억원, 1억
_WON_RE = re.compile(r"^(?:\s)*(\d[\d,]*)\s*원")               # 5천만원 등은 LLM 이 처리


def _normalize_amount(raw: Any) -> int | None:
    """LLM 이 반환한 amount_limit_krw 를 int 로. 문자열 들어와도 처리."""
    if raw is None:
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float):
        return int(raw)
    if isinstance(raw, str):
        s = raw.strip().replace(",", "")
        if not s:
            return None
        try:
            return int(s)
        except ValueError:
            pass
        # 한국어 단위 후처리
        if "억" in s:
            m = re.match(r"(\d+(?:\.\d+)?)\s*억", s)
            if m:
                return int(float(m.group(1)) * 100_000_000)
        if "만원" in s or "만 원" in s:
            m = re.match(r"(\d+(?:\.\d+)?)\s*만", s)
            if m:
                return int(float(m.group(1)) * 10_000)
    return None


def _normalize_pct(raw: Any) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str):
        s = raw.strip().rstrip("%").strip()
        try:
            return float(s)
        except ValueError:
            return None
    return None


def extract_authority_rules_from_pdf(pdf_path: str | "Path", start_page: int = 1, max_pages: int | None = None) -> list[ExtractedRule]:
    """pypdfium2 로 PDF 각 페이지를 PNG 렌더 → gpt-4o-mini vision 으로 표 추출.

    Args:
        pdf_path: PDF 경로
        start_page: 1-indexed, 표가 시작하는 페이지부터 (전체 = 1)
        max_pages: 최대 처리 페이지 수 (None = 전체)

    페이지마다 LLM 1회 호출. 비용 ~$0.0003/page (gpt-4o-mini vision low-res).
    """
    import base64
    import io
    from pathlib import Path

    import pypdfium2 as pdfium

    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(pdf_path)

    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)

    pdf = pdfium.PdfDocument(str(pdf_path))
    n_total = len(pdf)
    end_page = min(n_total, start_page - 1 + max_pages) if max_pages else n_total
    pages_to_process = range(start_page - 1, end_page)
    log.info(
        "Vision authority extract: {p} ({s}-{e} of {n})",
        p=pdf_path.name,
        s=start_page,
        e=end_page,
        n=n_total,
    )

    all_rules: list[ExtractedRule] = []
    pages_with_table = 0
    for idx in pages_to_process:
        page = pdf[idx]
        # 2x scale = ~144 DPI 정도. 위임전결 표는 텍스트 위주라 충분.
        pil_image = page.render(scale=2.0).to_pil()
        buf = io.BytesIO()
        pil_image.save(buf, format="PNG", optimize=True)
        img_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

        try:
            resp = client.chat.completions.create(
                model=settings.llm_model,
                messages=[
                    {"role": "system", "content": _VISION_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": f"위임전결규정 PDF, 페이지 {idx+1}/{n_total}. 표가 있으면 추출.",
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{img_b64}",
                                    "detail": "high",
                                },
                            },
                        ],
                    },
                ],
                temperature=0,
                response_format={"type": "json_object"},
            )
            raw_content = resp.choices[0].message.content or "{}"
            parsed = json.loads(raw_content)
        except Exception as e:  # noqa: BLE001
            log.warning("page {p} vision call failed: {e}", p=idx + 1, e=e)
            continue

        has_table = parsed.get("has_table", False)
        items = parsed.get("rules") or []
        if not items:
            continue
        pages_with_table += 1

        for item in items:
            if not isinstance(item, dict):
                continue
            proc = (item.get("process") or "other").strip()
            if proc not in VALID_PROCESSES:
                proc = "other"
            rule = ExtractedRule(
                process=proc,
                task=(item.get("task") or "").strip()[:256],
                approval_role=(item.get("approval_role") or "").strip()[:64],
                amount_limit_krw=_normalize_amount(item.get("amount_limit_krw")),
                approval_limit_pct=_normalize_pct(item.get("approval_limit_pct")),
                condition=(item.get("condition") or None),
                raw_row=item,
                source_page=idx + 1,
            )
            if rule.is_valid():
                all_rules.append(rule)

        log.info(
            "page {p}: has_table={ht} → {n} rules (cumulative {c})",
            p=idx + 1,
            ht=has_table,
            n=len(items),
            c=len(all_rules),
        )

    log.info(
        "Vision extract done: {n} rules across {pwt}/{tp} pages",
        n=len(all_rules),
        pwt=pages_with_table,
        tp=len(pages_to_process),
    )
    return all_rules


def extract_authority_rules(markdown_text: str, source_page: int | None = None) -> list[ExtractedRule]:
    """gpt-4o-mini 로 위임전결 표 → authority rules.

    실패 시 빈 리스트 반환 (예외 X).
    """
    if not markdown_text or len(markdown_text) < 100:
        return []

    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)

    log.info("LLM authority extraction: {n:,} chars → gpt-4o-mini", n=len(markdown_text))
    try:
        resp = client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _user_prompt(markdown_text)},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        raw_content = resp.choices[0].message.content or "{}"
        parsed = json.loads(raw_content)
    except Exception as e:  # noqa: BLE001
        log.exception("LLM extract failed: {e}", e=e)
        return []

    items = parsed.get("rules") or parsed.get("authority_rules") or []
    if not isinstance(items, list):
        log.warning("LLM returned non-list rules: {t}", t=type(items).__name__)
        return []

    rules: list[ExtractedRule] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        proc = (item.get("process") or "other").strip()
        if proc not in VALID_PROCESSES:
            proc = "other"
        rule = ExtractedRule(
            process=proc,
            task=(item.get("task") or "").strip()[:256],
            approval_role=(item.get("approval_role") or "").strip()[:64],
            amount_limit_krw=_normalize_amount(item.get("amount_limit_krw")),
            approval_limit_pct=_normalize_pct(item.get("approval_limit_pct")),
            condition=(item.get("condition") or None),
            raw_row=item,
            source_page=source_page,
        )
        if rule.is_valid():
            rules.append(rule)

    log.info(
        "LLM extract done: {valid}/{total} valid rules (model={m})",
        valid=len(rules),
        total=len(items),
        m=settings.llm_model,
    )
    return rules


# ────────────────────────────────────────────────────────────────────
# CLI smoke
# ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("usage: python -m packages.regulation_parser.authority_extractor <pdf_path> [start_page] [max_pages]")
        sys.exit(2)
    path = sys.argv[1]
    start = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    maxp = int(sys.argv[3]) if len(sys.argv) > 3 else None
    rules = extract_authority_rules_from_pdf(path, start_page=start, max_pages=maxp)
    print(f"\n=== Extracted {len(rules)} rules ===\n")
    for r in rules[:30]:
        amt = f"{r.amount_limit_krw:,}원" if r.amount_limit_krw else "-"
        pct = f"{r.approval_limit_pct:.1f}%" if r.approval_limit_pct else "-"
        print(f"  p={r.source_page:>2} [{r.process:<20}] {r.task[:40]:<40} → {r.approval_role:<6} (amt={amt}, pct={pct})")
    if len(rules) > 30:
        print(f"  ... ({len(rules)-30} more)")
