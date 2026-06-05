"""Authority SQL exact 조회 노드.

질문에서 (process, amount, pct) 를 파싱하여 authority_rules 테이블 SQL 조회.
조회 결과를 generator 에게 컨텍스트로 전달 (state.sources 에 채움).
"""

from __future__ import annotations

import re
import time
from typing import Any

from sqlalchemy import select

from packages.code.logger import get_logger
from packages.db.connection import session_scope
from packages.db.models import AuthorityRule, Document
from packages.rag.state import QueryState, Source
from packages.regulation_parser.authority_extractor import PROCESS_TAXONOMY

log = get_logger("packages.rag.nodes.authority_lookup")


# ────────────────────────────────────────────────────────────────────
# 질문 파싱
# ────────────────────────────────────────────────────────────────────


def _parse_amount_krw(text: str) -> int | None:
    """한국어 금액 표기 → int (원 단위)."""
    # 1.5억 / 1억
    m = re.search(r"(\d+(?:\.\d+)?)\s*억", text)
    if m:
        return int(float(m.group(1)) * 100_000_000)
    # 5천만(원)
    m = re.search(r"(\d+(?:\.\d+)?)\s*천\s*만", text)
    if m:
        return int(float(m.group(1)) * 10_000_000)
    # 5백만(원)
    m = re.search(r"(\d+(?:\.\d+)?)\s*백\s*만", text)
    if m:
        return int(float(m.group(1)) * 1_000_000)
    # 5,000만원 / 5000 만원
    m = re.search(r"([\d,]+)\s*만\s*원?", text)
    if m:
        return int(m.group(1).replace(",", "")) * 10_000
    # 단순 N원
    m = re.search(r"([\d,]+)\s*원", text)
    if m:
        return int(m.group(1).replace(",", ""))
    return None


def _parse_pct(text: str) -> float | None:
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:%|퍼센트|프로)", text)
    if m:
        return float(m.group(1))
    return None


def _detect_process(text: str) -> str | None:
    """가장 먼저 매칭되는 process 키워드 반환. 없으면 None."""
    for proc, kws in PROCESS_TAXONOMY.items():
        if proc == "other":
            continue
        for kw in kws:
            if kw in text:
                return proc
    return None


# ────────────────────────────────────────────────────────────────────
# Node
# ────────────────────────────────────────────────────────────────────


def _serialize_rule(r: AuthorityRule, doc_title: str) -> Source:
    parts = [r.task or "(사무 미상)", f"→ {r.approval_role}"]
    if r.amount_limit_krw is not None:
        parts.append(f"금액 한도: {r.amount_limit_krw:,}원")
    if r.approval_limit_pct is not None:
        parts.append(f"비율 한도: {r.approval_limit_pct}%")
    if r.condition:
        parts.append(f"조건: {r.condition}")
    body = " | ".join(parts)
    breadcrumb = f"{doc_title} > authority_matrix > {r.process}"
    return Source(
        article_id=r.id,
        doc_id=r.doc_id,
        article_no=f"authority_rule#{r.id}",
        article_title=r.task[:80] if r.task else None,
        chapter=r.process,
        heading_path={
            "doc_title": doc_title,
            "process": r.process,
            "approval_role": r.approval_role,
            "amount_limit_krw": r.amount_limit_krw,
            "approval_limit_pct": r.approval_limit_pct,
        },
        body=f"{breadcrumb}\n\n{body}",
        score=1.0,  # SQL exact match
    )


def authority_lookup_node(state: QueryState) -> dict:
    """질문에서 (process, amount, pct) 파싱 → authority_rules SQL 조회."""
    t0 = time.perf_counter()
    q = state.get("rewritten_question") or state["question"]

    process = _detect_process(q)
    amount = _parse_amount_krw(q)
    pct = _parse_pct(q)

    log.info(
        "authority_lookup: q={q!r} → process={p}, amount={a}, pct={pc}",
        q=q[:60],
        p=process,
        a=amount,
        pc=pct,
    )

    with session_scope() as session:
        # amount/% 가 강한 신호라 그게 있으면 process 필터는 drop (process 가 "other" 로 매핑된 rules 도 포함).
        # process 만 있고 amount/% 없으면 process 필터만 적용.
        stmt = select(AuthorityRule, Document).join(
            Document, AuthorityRule.doc_id == Document.doc_id
        )
        if amount is None and pct is None and process and process != "other":
            stmt = stmt.where(AuthorityRule.process == process)
        if amount is not None:
            stmt = stmt.where(AuthorityRule.amount_limit_krw >= amount)
        if pct is not None:
            stmt = stmt.where(AuthorityRule.approval_limit_pct >= pct)

        # 가장 작은 한도 (가장 낮은 권한자) 가 정확한 답
        stmt = stmt.order_by(
            AuthorityRule.amount_limit_krw.asc().nullslast(),
            AuthorityRule.approval_limit_pct.asc().nullslast(),
        ).limit(20)

        rows = session.execute(stmt).all()

    sources: list[Source] = []
    for rule, doc in rows:
        sources.append(_serialize_rule(rule, doc.title))

    # SQL 0 결과 → hybrid retrieval fallback (route='authority' 라도 authority_matrix 만 검색)
    if not sources:
        log.info("authority_lookup: 0 rules matched — fallback to hybrid (filter=authority_matrix)")
        from packages.rag.retriever import hybrid_search

        hits = hybrid_search(q, top_k=10, candidate_k=30, payload_filter={"doc_type": ["authority_matrix"]})
        if hits:
            from sqlalchemy import select as _select

            from packages.db.models import Article

            ids = [h.article_id for h in hits]
            with session_scope() as session:
                rows2 = session.scalars(_select(Article).where(Article.id.in_(ids))).all()
                amap = {a.id: a for a in rows2}
            for h in hits:
                a = amap.get(h.article_id)
                if a is None:
                    continue
                sources.append(
                    Source(
                        article_id=a.id,
                        doc_id=a.doc_id,
                        article_no=a.article_no or "",
                        article_title=a.article_title,
                        chapter=a.chapter,
                        heading_path=a.heading_path or {},
                        body=a.body,
                        score=h.score,
                    )
                )
            log.info("authority fallback: {n} hits", n=len(sources))

    return {
        "sources": sources,
        "timings": {**state.get("timings", {}), "authority_lookup": time.perf_counter() - t0},
    }
