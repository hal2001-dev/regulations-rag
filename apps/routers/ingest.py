"""POST /ingest — 큐 enqueue."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from apps.dependencies import SessionDep
from packages.db.repository import enqueue_ingest
from packages.regulation_parser.doc_type_classifier import VALID_DOC_TYPES

router = APIRouter(prefix="/ingest", tags=["ingest"])


class IngestRequest(BaseModel):
    source_path: str = Field(..., description="서버 로컬 경로 (절대/상대)")
    user_doc_type: str | None = Field(
        default=None,
        description=f"명시적 doc_type 지정 (없으면 파일명 휴리스틱). valid: {sorted(VALID_DOC_TYPES)}",
    )
    force_ocr: bool = Field(default=False, description="macOS Vision OCR 강제 (스캔 PDF 용). M2 후속.")


class IngestResponse(BaseModel):
    job_id: int
    source_path: str
    status: str
    user_doc_type: str | None
    force_ocr: bool


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=IngestResponse)
def enqueue(req: IngestRequest, session: SessionDep) -> IngestResponse:
    src = Path(req.source_path)
    if not src.exists():
        raise HTTPException(
            status_code=400, detail=f"source_path not found on server: {src}"
        )
    if not src.is_file():
        raise HTTPException(status_code=400, detail=f"not a file: {src}")
    if req.user_doc_type and req.user_doc_type not in VALID_DOC_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"invalid user_doc_type={req.user_doc_type}, valid: {sorted(VALID_DOC_TYPES)}",
        )

    job = enqueue_ingest(
        session,
        source_path=str(src.resolve()),
        user_doc_type=req.user_doc_type,
        force_ocr=req.force_ocr,
    )
    session.commit()  # job.id 가 client 에 노출되니 즉시 영구화
    return IngestResponse(
        job_id=job.id,
        source_path=job.source_path,
        status=job.status,
        user_doc_type=job.user_doc_type,
        force_ocr=job.force_ocr,
    )
