"""Hybrid retrieval (dense + sparse) + Reciprocal Rank Fusion."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from qdrant_client.http import models as qm

from packages.code.logger import get_logger
from packages.rag.embeddings import embed_query_dense, embed_query_sparse
from packages.vectorstore.qdrant_store import search_dense, search_sparse

log = get_logger("packages.rag.retriever")


@dataclass
class Hit:
    article_id: int
    score: float
    payload: dict[str, Any]


def _to_hit(p: qm.ScoredPoint) -> Hit:
    return Hit(article_id=int(p.id), score=float(p.score), payload=dict(p.payload or {}))


def rrf_merge(
    *result_lists: list[Hit], k: int = 60, top_k: int = 20
) -> list[Hit]:
    """Reciprocal Rank Fusion. 각 list 안에서의 rank 기준 1/(k+rank) 합산."""
    scores: dict[int, float] = defaultdict(float)
    payload_map: dict[int, dict[str, Any]] = {}
    for results in result_lists:
        for rank, h in enumerate(results, start=1):
            scores[h.article_id] += 1.0 / (k + rank)
            payload_map.setdefault(h.article_id, h.payload)
    merged = [
        Hit(article_id=aid, score=s, payload=payload_map[aid])
        for aid, s in sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    ]
    return merged[:top_k]


def hybrid_search(
    question: str,
    top_k: int = 10,
    candidate_k: int = 30,
    payload_filter: dict[str, Any] | None = None,
) -> list[Hit]:
    """dense + sparse 각각 candidate_k 개 → RRF → top_k."""
    dense_vec = embed_query_dense(question)
    sparse_vec = embed_query_sparse(question)

    dense_hits = [
        _to_hit(p) for p in search_dense(dense_vec, limit=candidate_k, payload_filter=payload_filter)
    ]
    sparse_hits = [
        _to_hit(p)
        for p in search_sparse(
            sparse_vec.indices, sparse_vec.values, limit=candidate_k, payload_filter=payload_filter
        )
    ]
    merged = rrf_merge(dense_hits, sparse_hits, top_k=top_k)
    log.debug(
        "hybrid: dense={d} sparse={s} → merged={m} (top {k})",
        d=len(dense_hits),
        s=len(sparse_hits),
        m=len(merged),
        k=top_k,
    )
    return merged
