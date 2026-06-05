"""Article rows → 임베딩 + Qdrant upsert + articles.qdrant_point_id 갱신.

indexer_worker (새 PDF) 와 backfill 스크립트 (기존 PDF) 가 공유.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from packages.code.logger import get_logger
from packages.db.models import Article, Document
from packages.rag.embeddings import embed_documents_dense, embed_documents_sparse
from packages.vectorstore.qdrant_store import UpsertPoint, ensure_collection, upsert_points

log = get_logger("packages.rag.index_articles")


def _payload(doc: Document, art: Article) -> dict:
    return {
        "article_id": art.id,
        "doc_id": art.doc_id,
        "doc_type": doc.doc_type,
        "domain": doc.domain,
        "process": doc.process,
        "article_no": art.article_no,
        "chapter": art.chapter,
        "section": art.section,
        "article_title": art.article_title,
        "content_type": art.content_type,
        "heading_path": art.heading_path,
    }


def index_articles_for_doc(session: Session, doc_id: int, batch: int = 32) -> int:
    """doc_id 의 모든 article 을 dense+sparse 임베딩 후 Qdrant upsert.

    이미 인덱싱된 article (qdrant_point_id 채워짐) 도 다시 upsert (멱등).
    """
    doc = session.get(Document, doc_id)
    if doc is None:
        raise ValueError(f"doc_id={doc_id} not found")

    articles = session.scalars(
        select(Article).where(Article.doc_id == doc_id).order_by(Article.id)
    ).all()
    if not articles:
        log.info("doc_id={d} ({t}) has no articles — skip", d=doc_id, t=doc.title)
        return 0

    bodies = [a.body for a in articles]
    log.info(
        "Embedding doc_id={d} ({t}) → {n} articles",
        d=doc_id,
        t=doc.title,
        n=len(articles),
    )
    dense = embed_documents_dense(bodies)
    sparse = embed_documents_sparse(bodies)

    points = [
        UpsertPoint(
            article_id=a.id,
            dense=dv,
            sparse_indices=sv.indices,
            sparse_values=sv.values,
            payload=_payload(doc, a),
        )
        for a, dv, sv in zip(articles, dense, sparse)
    ]
    upsert_points(points, batch=batch)

    # articles.qdrant_point_id 갱신 (멱등; ID 가 article.id 와 같음 — 디버그/검증용 트래킹)
    for a in articles:
        a.qdrant_point_id = str(a.id)

    log.info("doc_id={d}: {n} points upserted", d=doc_id, n=len(points))
    return len(points)


def reset_doc_in_qdrant(session: Session, doc_id: int) -> None:
    """재인덱싱 시 stale point 정리 (없어도 idempotent)."""
    from packages.vectorstore.qdrant_store import delete_by_doc_id

    delete_by_doc_id(doc_id)
    arts = session.scalars(select(Article).where(Article.doc_id == doc_id)).all()
    for a in arts:
        a.qdrant_point_id = None


def ensure_index_ready() -> None:
    """프로세스 시작 시 한 번 호출 — Qdrant collection + schema 확인."""
    ensure_collection()
