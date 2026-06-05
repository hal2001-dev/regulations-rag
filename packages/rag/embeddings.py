"""Dense (multilingual-e5-large) + Sparse (Qdrant/bm25) 임베딩 wrapper.

e5 family 는 "query: ..." / "passage: ..." prefix 가 필수.
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.config import get_settings
from packages.code.logger import get_logger

log = get_logger("packages.rag.embeddings")

_dense = None
_sparse = None


def _get_dense():
    global _dense
    if _dense is None:
        from fastembed import TextEmbedding

        s = get_settings()
        log.info("Loading dense model: {m}", m=s.embedding_model)
        _dense = TextEmbedding(model_name=s.embedding_model)
    return _dense


def _get_sparse():
    global _sparse
    if _sparse is None:
        from fastembed import SparseTextEmbedding

        s = get_settings()
        log.info("Loading sparse model: {m}", m=s.sparse_model)
        _sparse = SparseTextEmbedding(model_name=s.sparse_model)
    return _sparse


@dataclass
class SparseVector:
    indices: list[int]
    values: list[float]


def embed_documents_dense(texts: list[str]) -> list[list[float]]:
    """e5 의 passage prefix 적용 후 dense embed."""
    prefixed = [f"passage: {t}" for t in texts]
    model = _get_dense()
    return [list(v) for v in model.embed(prefixed)]


def embed_query_dense(text: str) -> list[float]:
    model = _get_dense()
    return list(next(iter(model.embed([f"query: {text}"]))))


def embed_documents_sparse(texts: list[str]) -> list[SparseVector]:
    model = _get_sparse()
    return [SparseVector(indices=list(v.indices), values=list(v.values)) for v in model.embed(texts)]


def embed_query_sparse(text: str) -> SparseVector:
    model = _get_sparse()
    v = next(iter(model.query_embed([text])))
    return SparseVector(indices=list(v.indices), values=list(v.values))


if __name__ == "__main__":
    # 다운로드 + smoke
    print("dense:", len(embed_query_dense("연차휴가 며칠?")))
    sv = embed_query_sparse("연차휴가 며칠?")
    print(f"sparse: {len(sv.indices)} nonzeros")
