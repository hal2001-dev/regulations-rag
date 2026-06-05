"""[근거] 블록의 (doc_id, article_no) 가 실제 retrieved sources 안에 있는지 검증."""

from __future__ import annotations

import re

from packages.code.logger import get_logger
from packages.rag.state import QueryState

log = get_logger("packages.rag.nodes.citation_validator")

# [근거] 블록 추출 (다음 헤더 또는 EOF 까지)
_GE_BLOCK_RE = re.compile(r"\[근거\](.*?)(?=\n\[|\Z)", re.DOTALL)
# `[doc_id=12, 제5조] ...` / `[doc_id=12 | 제5조]` 두 형식 모두 수용
# LLM 이 prompt 의 콤마 대신 파이프를 쓰는 케이스가 흔함 (gpt-4o-mini 관찰)
_CITE_RE = re.compile(r"\[\s*doc_id\s*=\s*(\d+)\s*[,|]\s*([^\]]+?)\s*\]")


def _article_match(actual_no: str | None, cite_str: str) -> bool:
    """LLM 이 article_no 뒤에 title/한도 까지 붙이는 변종 모두 인정.

    - actual_no="제2조" + cite="제2조" → True
    - actual_no="제2조" + cite="제2조 직무" → True (한글 title prefix)
    - actual_no="제5조의2" + cite="제5조" → False (의2 빠짐)
    - actual_no="authority_rule#40" + cite="authority_rule#40 1억 이하" → True (M4 의 변종)
    """
    a = (actual_no or "").replace(" ", "")
    c = cite_str.replace(" ", "")
    if not a or not c:
        return False
    if a == c:
        return True
    if c.startswith(a):
        rest = c[len(a) :]
        if not rest:
            return True
        # "제2조의2" 의 "의2" 또는 article_no 가 부분 prefix 인 경우는 거부
        # actual_no 가 "조" 로 끝나는 한국어 조항 형식이면 — rest 가 숫자/의 로 시작하면 거부
        if a.endswith("조") and rest[0] in "0123456789의":
            return False
        return True
    return False


def citation_validator(state: QueryState) -> dict:
    draft = state.get("draft", "")
    sources = state.get("sources", [])
    src_by_doc: dict[int, list[str]] = {}
    for s in sources:
        src_by_doc.setdefault(int(s["doc_id"]), []).append(s.get("article_no") or "")

    m = _GE_BLOCK_RE.search(draft)
    if not m:
        log.warning("[근거] block missing")
        return {"citations_valid": [], "citation_valid_pct": 0.0}

    block = m.group(1)
    cites = _CITE_RE.findall(block)
    if not cites:
        log.warning("[근거] block has no parseable citations")
        return {"citations_valid": [], "citation_valid_pct": 0.0}

    valid = []
    for d, a in cites:
        d_int = int(d)
        cite_str = a.strip()
        candidates = src_by_doc.get(d_int, [])
        valid.append(any(_article_match(c, cite_str) for c in candidates))
    pct = sum(valid) / len(valid)
    log.info(
        "citation: {n} cited, valid={ok}/{tot} ({pct:.0%})",
        n=len(cites),
        ok=sum(valid),
        tot=len(valid),
        pct=pct,
    )
    return {"citations_valid": valid, "citation_valid_pct": pct}
