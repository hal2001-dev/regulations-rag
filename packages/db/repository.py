"""Thin repository helpers used by routers / worker.

Pattern: 모든 함수가 외부에서 받은 Session 으로 동작. commit 책임은 호출자.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from packages.db.models import Document, IngestJob


def get_document_by_hash(session: Session, content_hash: str) -> Document | None:
    stmt = select(Document).where(Document.content_hash == content_hash)
    return session.scalar(stmt)


def enqueue_ingest(
    session: Session,
    source_path: str,
    user_doc_type: str | None = None,
    force_ocr: bool = False,
) -> IngestJob:
    job = IngestJob(
        source_path=source_path,
        user_doc_type=user_doc_type,
        force_ocr=force_ocr,
        status="queued",
    )
    session.add(job)
    session.flush()  # job.id 채움 (commit 은 호출자)
    return job


def claim_next_job(session: Session, batch_size: int = 1) -> list[IngestJob]:
    """FOR UPDATE SKIP LOCKED 큐 폴링. running 으로 마킹하고 반환."""
    stmt = (
        select(IngestJob)
        .where(IngestJob.status == "queued")
        .order_by(IngestJob.created_at)
        .limit(batch_size)
        .with_for_update(skip_locked=True)
    )
    jobs = list(session.scalars(stmt))
    if not jobs:
        return []

    job_ids = [j.id for j in jobs]
    session.execute(
        update(IngestJob)
        .where(IngestJob.id.in_(job_ids))
        .values(status="running", started_at=datetime.now(UTC))
    )
    return jobs


def mark_job_done(session: Session, job_id: int, doc_id: int | None) -> None:
    session.execute(
        update(IngestJob)
        .where(IngestJob.id == job_id)
        .values(status="done", doc_id=doc_id, finished_at=datetime.now(UTC))
    )


def mark_job_failed(session: Session, job_id: int, error: str) -> None:
    session.execute(
        update(IngestJob)
        .where(IngestJob.id == job_id)
        .values(status="failed", error=error[:8000], finished_at=datetime.now(UTC))
    )
