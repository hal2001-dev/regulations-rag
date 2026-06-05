"""Qdrant collection 헬퍼 — 단일 collection + payload filter (mvp_plan §11 결정).

Collection:
    - dense: 1024-dim cosine (multilingual-e5-large)
    - sparse: NamedSparseVector "bm25" (fastembed Qdrant/bm25)
    - payload indexed: doc_id, doc_type, domain, process, article_no
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from apps.config import get_settings
from packages.code.logger import get_logger

log = get_logger("packages.vectorstore.qdrant_store")

DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "bm25"


# ────────────────────────────────────────────────────────────────────
# Client
# ────────────────────────────────────────────────────────────────────


_client: QdrantClient | None = None


def get_client() -> QdrantClient:
    global _client
    if _client is None:
        s = get_settings()
        _client = QdrantClient(url=s.qdrant_url, timeout=30)
    return _client


# ────────────────────────────────────────────────────────────────────
# Schema
# ────────────────────────────────────────────────────────────────────


def ensure_collection() -> None:
    """Collection 없으면 생성, payload index 모두 보장."""
    s = get_settings()
    client = get_client()
    name = s.qdrant_collection

    cols = {c.name for c in client.get_collections().collections}
    if name not in cols:
        log.info("Creating Qdrant collection '{n}' (dim={d}, sparse=bm25)", n=name, d=s.embedding_dim)
        client.create_collection(
            collection_name=name,
            vectors_config={
                DENSE_VECTOR_NAME: qm.VectorParams(
                    size=s.embedding_dim, distance=qm.Distance.COSINE
                ),
            },
            sparse_vectors_config={
                SPARSE_VECTOR_NAME: qm.SparseVectorParams(
                    index=qm.SparseIndexParams(on_disk=False),
                )
            },
        )
    else:
        log.info("Qdrant collection '{n}' already exists", n=name)

    # payload indexes — idempotent (이미 있으면 무시)
    for field, schema in [
        ("doc_id", qm.PayloadSchemaType.INTEGER),
        ("doc_type", qm.PayloadSchemaType.KEYWORD),
        ("domain", qm.PayloadSchemaType.KEYWORD),
        ("process", qm.PayloadSchemaType.KEYWORD),
        ("article_no", qm.PayloadSchemaType.KEYWORD),
    ]:
        try:
            client.create_payload_index(
                collection_name=name, field_name=field, field_schema=schema
            )
        except Exception as e:  # noqa: BLE001
            # 이미 존재
            if "already exists" not in str(e).lower():
                log.debug("payload_index {f}: {e}", f=field, e=e)


# ────────────────────────────────────────────────────────────────────
# Upsert
# ────────────────────────────────────────────────────────────────────


@dataclass
class UpsertPoint:
    """Article → Qdrant point."""

    article_id: int  # used as point id
    dense: list[float]
    sparse_indices: list[int]
    sparse_values: list[float]
    payload: dict[str, Any]


def upsert_points(points: list[UpsertPoint], batch: int = 64) -> None:
    if not points:
        return
    s = get_settings()
    client = get_client()
    for i in range(0, len(points), batch):
        chunk = points[i : i + batch]
        client.upsert(
            collection_name=s.qdrant_collection,
            points=[
                qm.PointStruct(
                    id=p.article_id,
                    vector={
                        DENSE_VECTOR_NAME: p.dense,
                        SPARSE_VECTOR_NAME: qm.SparseVector(
                            indices=p.sparse_indices, values=p.sparse_values
                        ),
                    },
                    payload=p.payload,
                )
                for p in chunk
            ],
        )
    log.info("Upserted {n} points to '{c}'", n=len(points), c=s.qdrant_collection)


# ────────────────────────────────────────────────────────────────────
# Search
# ────────────────────────────────────────────────────────────────────


def search_dense(
    query_vector: list[float],
    limit: int = 20,
    payload_filter: dict[str, Any] | None = None,
) -> list[qm.ScoredPoint]:
    s = get_settings()
    client = get_client()
    f = _build_filter(payload_filter)
    res = client.query_points(
        collection_name=s.qdrant_collection,
        query=query_vector,
        using=DENSE_VECTOR_NAME,
        limit=limit,
        query_filter=f,
        with_payload=True,
    )
    return res.points


def search_sparse(
    indices: list[int],
    values: list[float],
    limit: int = 20,
    payload_filter: dict[str, Any] | None = None,
) -> list[qm.ScoredPoint]:
    s = get_settings()
    client = get_client()
    f = _build_filter(payload_filter)
    res = client.query_points(
        collection_name=s.qdrant_collection,
        query=qm.SparseVector(indices=indices, values=values),
        using=SPARSE_VECTOR_NAME,
        limit=limit,
        query_filter=f,
        with_payload=True,
    )
    return res.points


def _build_filter(payload_filter: dict[str, Any] | None) -> qm.Filter | None:
    if not payload_filter:
        return None
    must = []
    for k, v in payload_filter.items():
        if isinstance(v, list):
            must.append(qm.FieldCondition(key=k, match=qm.MatchAny(any=v)))
        else:
            must.append(qm.FieldCondition(key=k, match=qm.MatchValue(value=v)))
    return qm.Filter(must=must)


# ────────────────────────────────────────────────────────────────────
# Maintenance
# ────────────────────────────────────────────────────────────────────


def delete_by_doc_id(doc_id: int) -> None:
    """문서 재색인 / 삭제용."""
    s = get_settings()
    client = get_client()
    client.delete(
        collection_name=s.qdrant_collection,
        points_selector=qm.FilterSelector(
            filter=qm.Filter(
                must=[qm.FieldCondition(key="doc_id", match=qm.MatchValue(value=doc_id))]
            )
        ),
    )
