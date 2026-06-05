"""Hybrid retrieval (dense+sparse RRF) → Postgres 에서 body 보강 → state.sources."""

from __future__ import annotations

import time

from sqlalchemy import select

from packages.code.logger import get_logger
from packages.db.connection import session_scope
from packages.db.models import Article
from packages.rag.retriever import hybrid_search
from packages.rag.state import QueryState, Source

log = get_logger("packages.rag.nodes.retriever")


# route → Qdrant payload filter (doc_type 가 0-chunk 인 doc_type 은 filter 안 거는 게 안전)
_ROUTE_FILTER = {
    "policy": {"doc_type": ["policy"]},
    "authority": {"doc_type": ["authority_matrix"]},
    "manual": {"doc_type": ["manual"]},
    "faq": None,  # faq doc_type 은 0-chunk 라 필터 걸면 결과 0. fallback 으로 전체.
}


def retriever_node(state: QueryState) -> dict:
    t0 = time.perf_counter()
    q = state.get("rewritten_question") or state["question"]
    route = state.get("route", "policy")
    payload_filter = _ROUTE_FILTER.get(route)

    hits = hybrid_search(q, top_k=10, candidate_k=30, payload_filter=payload_filter)
    if not hits:
        # route 필터로 0 이면 필터 해제 후 fallback
        log.info("Retrieval empty with filter={f} — falling back to no filter", f=payload_filter)
        hits = hybrid_search(q, top_k=10, candidate_k=30, payload_filter=None)

    if not hits:
        return {"sources": [], "timings": {**state.get("timings", {}), "retriever": time.perf_counter() - t0}}

    ids = [h.article_id for h in hits]
    with session_scope() as session:
        rows = session.scalars(select(Article).where(Article.id.in_(ids))).all()
        body_map = {r.id: r for r in rows}

    sources: list[Source] = []
    for h in hits:
        a = body_map.get(h.article_id)
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
    log.info(
        "retriever: route={r} hits={n} (filter={f})",
        r=route,
        n=len(sources),
        f=payload_filter,
    )
    return {
        "sources": sources,
        "timings": {**state.get("timings", {}), "retriever": time.perf_counter() - t0},
    }
