"""GET /documents, /documents/{id}/chunks — library 뷰."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from apps.dependencies import SessionDep
from packages.db.models import Article, Document

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("")
def list_documents(
    session: SessionDep,
    doc_type: str | None = Query(default=None, description="필터: policy/manual/faq/authority_matrix 등"),
) -> dict[str, list[dict]]:
    stmt = select(Document).order_by(Document.created_at.desc()).limit(200)
    if doc_type:
        stmt = stmt.where(Document.doc_type == doc_type)
    rows = session.scalars(stmt).all()
    return {
        "items": [
            {
                "doc_id": d.doc_id,
                "title": d.title,
                "doc_type": d.doc_type,
                "domain": d.domain,
                "chunk_count": d.chunk_count,
                "status": d.status,
                "extraction_quality": d.extraction_quality,
                "indexed_at": d.indexed_at.isoformat() if d.indexed_at else None,
            }
            for d in rows
        ]
    }


@router.get("/{doc_id}/chunks")
def list_chunks(
    doc_id: int,
    session: SessionDep,
    limit: int = Query(default=30, le=200),
    offset: int = 0,
) -> dict:
    doc = session.scalar(select(Document).where(Document.doc_id == doc_id))
    if not doc:
        raise HTTPException(status_code=404, detail=f"document {doc_id} 없음")

    stmt = (
        select(Article)
        .where(Article.doc_id == doc_id)
        .order_by(Article.id)
        .offset(offset)
        .limit(limit)
    )
    rows = session.scalars(stmt).all()
    return {
        "doc_id": doc_id,
        "title": doc.title,
        "doc_type": doc.doc_type,
        "total": doc.chunk_count,
        "offset": offset,
        "limit": limit,
        "items": [
            {
                "id": a.id,
                "chapter": a.chapter,
                "article_no": a.article_no,
                "article_title": a.article_title,
                "paragraph": a.paragraph,
                "body": a.body[:600],
                "heading_path": a.heading_path,
            }
            for a in rows
        ],
    }
