"""Admin routes — reindex + taxonomy + authority CSV escape hatch (M6).

Reindex 정책:
- Qdrant 의 해당 doc_id 포인트 삭제
- documents row 삭제 (CASCADE 로 articles + authority_rules 정리)
- 새 ingest_job enqueue (force_ocr 옵션)
- worker 가 picking 하면서 신선한 색인 재생성

content_hash UNIQUE 제약 때문에 같은 파일이라도 row 가 남아 있으면 dedup 으로 skip 됨 — 그래서 row 자체를 지움.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from apps.dependencies import SessionDep
from packages.code.logger import get_logger
from packages.db.models import Document
from packages.db.repository import enqueue_ingest
from packages.vectorstore.qdrant_store import delete_by_doc_id

log = get_logger("apps.routers.admin")
router = APIRouter(prefix="/admin", tags=["admin"])


class ReindexRequest(BaseModel):
    force_ocr: bool = Field(default=False, description="macOS Vision OCR 강제 재추출")


class ReindexResponse(BaseModel):
    old_doc_id: int
    source_path: str
    new_job_id: int


@router.post("/reindex/{doc_id}", response_model=ReindexResponse)
def reindex(doc_id: int, req: ReindexRequest, session: SessionDep) -> ReindexResponse:
    doc = session.scalar(select(Document).where(Document.doc_id == doc_id))
    if not doc:
        raise HTTPException(status_code=404, detail=f"document {doc_id} 없음")

    source_path = doc.source_path
    doc_type = doc.doc_type
    if not Path(source_path).exists():
        raise HTTPException(
            status_code=400,
            detail=f"원본 파일이 사라짐: {source_path}",
        )

    try:
        delete_by_doc_id(doc_id)
    except Exception as e:  # noqa: BLE001
        log.exception("Qdrant delete failed for doc_id={d}: {e}", d=doc_id, e=e)

    session.delete(doc)
    session.flush()

    job = enqueue_ingest(
        session,
        source_path=source_path,
        user_doc_type=doc_type,
        force_ocr=req.force_ocr,
    )
    session.commit()

    log.info(
        "Reindex queued: doc_id={d} → job_id={j} (force_ocr={f})",
        d=doc_id,
        j=job.id,
        f=req.force_ocr,
    )
    return ReindexResponse(
        old_doc_id=doc_id, source_path=source_path, new_job_id=job.id
    )
