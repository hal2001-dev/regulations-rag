"""Cross-encoder reranker (fastembed TextCrossEncoder).

dense+sparse RRF 가 뽑은 후보를 query 와 1:1 로 정밀 비교해 재정렬한다.
e5 dense 의 한국어 표/짧은 문장 변별력 약점을 보완 (ISSUE-001 retrieval).
"""

from __future__ import annotations

from apps.config import get_settings
from packages.code.logger import get_logger

log = get_logger("packages.rag.reranker")

_reranker = None


def _get_reranker():
    global _reranker
    if _reranker is None:
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        s = get_settings()
        log.info("Loading reranker model: {m}", m=s.reranker_model)
        _reranker = TextCrossEncoder(model_name=s.reranker_model)
    return _reranker


def rerank_scores(query: str, documents: list[str]) -> list[float]:
    """query vs 각 document 의 cross-encoder 적합도 점수 (입력 순서 정렬)."""
    if not documents:
        return []
    model = _get_reranker()
    return [float(s) for s in model.rerank(query, documents)]
