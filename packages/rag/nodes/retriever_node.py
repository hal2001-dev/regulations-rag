"""Hybrid retrieval (dense+sparse RRF) → Postgres 에서 body 보강 → state.sources."""

from __future__ import annotations

import time

from sqlalchemy import select

from apps.config import get_settings
from packages.code.logger import get_logger
from packages.db.connection import session_scope
from packages.db.models import Article
from packages.rag.reranker import rerank_scores
from packages.rag.retriever import hybrid_search
from packages.rag.state import QueryState, Source

log = get_logger("packages.rag.nodes.retriever")

TOP_K = 10


# route → Qdrant payload filter (doc_type 가 0-chunk 인 doc_type 은 filter 안 거는 게 안전)
_ROUTE_FILTER = {
    "policy": {"doc_type": ["policy"]},
    "authority": {"doc_type": ["authority_matrix"]},
    "manual": {"doc_type": ["manual"]},
    "faq": None,  # faq doc_type 은 0-chunk 라 필터 걸면 결과 0. fallback 으로 전체.
}


def retriever_node(state: QueryState) -> dict:
    t0 = time.perf_counter()
    settings = get_settings()
    q = state.get("rewritten_question") or state["question"]
    route = state.get("route", "policy")
    payload_filter = _ROUTE_FILTER.get(route)

    # rerank 시 RRF 후보를 더 넓게 받는다 (rerank_candidate_k), 아니면 top_k 만.
    fetch_k = settings.rerank_candidate_k if settings.rerank_enabled else TOP_K
    hits = hybrid_search(q, top_k=fetch_k, candidate_k=max(fetch_k, 30), payload_filter=payload_filter)
    if not hits:
        # route 필터로 0 이면 필터 해제 후 fallback
        log.info("Retrieval empty with filter={f} — falling back to no filter", f=payload_filter)
        hits = hybrid_search(q, top_k=fetch_k, candidate_k=max(fetch_k, 30), payload_filter=None)

    if not hits:
        return {"sources": [], "timings": {**state.get("timings", {}), "retriever": time.perf_counter() - t0}}

    ids = [h.article_id for h in hits]
    with session_scope() as session:
        rows = session.scalars(select(Article).where(Article.id.in_(ids))).all()
        body_map = {r.id: r for r in rows}

    # body 가 있는 hit 만 (순서 유지)
    cand = [h for h in hits if h.article_id in body_map]

    # ── Cross-encoder rerank: RRF 후보를 원질문과 1:1 정밀 비교 후 재정렬 ──
    # rerank query 는 HyDE 가 아닌 '원질문' 사용 (cross-encoder 는 정밀 매칭이라 깨끗한 질의가 유리).
    rerank_score: dict[int, float] = {}
    if settings.rerank_enabled and len(cand) > 1:
        docs = [body_map[h.article_id].body for h in cand]
        try:
            scores = rerank_scores(state["question"], docs)
            scored = sorted(zip(cand, scores), key=lambda x: x[1], reverse=True)
            cand = [h for h, _ in scored]
            rerank_score = {h.article_id: sc for h, sc in scored}
        except Exception as e:  # noqa: BLE001
            log.warning("rerank failed: {e} — RRF 순위 유지", e=e)

    cand = cand[:TOP_K]

    sources: list[Source] = []
    for h in cand:
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
                score=rerank_score.get(h.article_id, h.score),
            )
        )
    log.info(
        "retriever: route={r} hits={n} (filter={f}, rerank={rr})",
        r=route,
        n=len(sources),
        f=payload_filter,
        rr=settings.rerank_enabled,
    )
    return {
        "sources": sources,
        "timings": {**state.get("timings", {}), "retriever": time.perf_counter() - t0},
    }
