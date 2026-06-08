"""Thin repository helpers used by routers / worker.

Pattern: 모든 함수가 외부에서 받은 Session 으로 동작. commit 책임은 호출자.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from packages.db.models import Conversation, Document, IngestJob, Message


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


# ── 멀티턴 대화 (conversations / messages) ──────────────────────────


def get_recent_history(
    session: Session, session_id: str, limit_turns: int = 5
) -> list[dict[str, str]]:
    """session 의 최근 `limit_turns` turn(=user/assistant 메시지)을 시간순으로 반환.

    LLM 컨텍스트 주입용 — `[{"role": "user"|"assistant", "content": ...}, ...]`.
    현재 질문을 저장하기 *전에* 호출하므로 직전 대화까지만 담긴다.
    """
    rows = session.scalars(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.id.desc())
        .limit(limit_turns * 2)  # turn = user + assistant
    ).all()
    return [{"role": m.role, "content": m.content} for m in reversed(rows)]


def save_turn(
    session: Session,
    session_id: str,
    question: str,
    answer: str,
    route: str | None = None,
    citation_pct: float | None = None,
) -> None:
    """한 turn(user 질문 + assistant 답변)을 저장. conversation 없으면 생성. commit 은 호출자."""
    if session.get(Conversation, session_id) is None:
        session.add(Conversation(session_id=session_id, title=question[:256]))
    session.add(Message(session_id=session_id, role="user", content=question))
    session.add(
        Message(
            session_id=session_id,
            role="assistant",
            content=answer,
            route=route,
            citation_valid_pct=citation_pct,
        )
    )
