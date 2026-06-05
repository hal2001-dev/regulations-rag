"""GET /jobs — ingest_jobs 상태 조회 (전체 최신 N개 또는 ids 필터)."""

from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import select

from apps.dependencies import SessionDep
from packages.db.models import IngestJob

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _serialize(j: IngestJob) -> dict:
    return {
        "id": j.id,
        "source_path": j.source_path,
        "status": j.status,
        "doc_id": j.doc_id,
        "user_doc_type": j.user_doc_type,
        "force_ocr": j.force_ocr,
        "error": j.error,
        "created_at": j.created_at.isoformat() if j.created_at else None,
        "started_at": j.started_at.isoformat() if j.started_at else None,
        "finished_at": j.finished_at.isoformat() if j.finished_at else None,
    }


@router.get("")
def list_jobs(
    session: SessionDep,
    ids: str | None = Query(default=None, description="콤마 구분 job id 목록"),
    limit: int = 50,
) -> dict[str, list[dict]]:
    if ids:
        try:
            id_list = [int(x) for x in ids.split(",") if x.strip()]
        except ValueError:
            id_list = []
        stmt = select(IngestJob).where(IngestJob.id.in_(id_list)).order_by(IngestJob.id)
    else:
        stmt = select(IngestJob).order_by(IngestJob.created_at.desc()).limit(limit)
    rows = session.scalars(stmt).all()
    return {"items": [_serialize(j) for j in rows]}
