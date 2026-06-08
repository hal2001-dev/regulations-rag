"""Indexer worker — `FOR UPDATE SKIP LOCKED` 큐 폴링 + Docling/parser/DB 적재.

M2:
- queued 잡 1개씩 claim → Docling 변환 → regulation_parser → SQLAlchemy bulk insert (documents + articles)
- content_hash 기반 dedup (이미 색인된 동일 파일은 skip + 기존 doc_id 로 mark_done)
- 실패 시 mark_job_failed + 다음 잡 계속

Qdrant upsert / 임베딩은 M3 retrieval 작업 시 본 파일에 추가.
"""

from __future__ import annotations

import hashlib
import signal
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from apps.config import get_settings
from packages.code.logger import get_logger
from packages.db.connection import Base, get_engine, session_scope
from packages.db.models import Article, Document
from packages.db.repository import (
    claim_next_job,
    get_document_by_hash,
    mark_job_done,
    mark_job_failed,
)
from packages.loaders.docling_loader import load_pdf_text
from packages.rag.index_articles import ensure_index_ready, index_articles_for_doc
from packages.regulation_parser.article_chunker import chunk_document
from packages.regulation_parser.authority_extractor import extract_authority_rules_from_pdf
from packages.regulation_parser.doc_type_classifier import classify, derive_title
from packages.regulation_parser.structure import parse_document

log = get_logger("apps.indexer_worker")

_should_stop = False


def _handle_signal(signum: int, _frame) -> None:
    global _should_stop
    log.info("Received signal {n} — stopping after current job.", n=signum)
    _should_stop = True


def _sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            buf = f.read(chunk)
            if not buf:
                break
            h.update(buf)
    return h.hexdigest()


def _process_job(job_id: int, source_path: str, user_doc_type: str | None) -> int:
    """1 job 의 변환·청킹·적재. 성공 시 doc_id 반환. 모든 예외는 호출자에게 전파."""
    src = Path(source_path)
    if not src.exists():
        raise FileNotFoundError(f"source_path 없음: {src}")

    content_hash = _sha256_file(src)

    # 1) dedup
    with session_scope() as s:
        existing = get_document_by_hash(s, content_hash)
        if existing:
            log.info(
                "Skip: already indexed (doc_id={d}, title={t})",
                d=existing.doc_id,
                t=existing.title,
            )
            return existing.doc_id

    # 2) doc_type + title
    doc_type = classify(src.name, user_doc_type)
    title = derive_title(src.name)
    log.info(
        "Job {jid}: {f} → doc_type={dt}, title={t}",
        jid=job_id,
        f=src.name,
        dt=doc_type,
        t=title,
    )

    # 3) Docling 변환 (~30~120s) — 정규화 markdown 을 data/parsed 에도 남김(디버깅/표 청킹 분석용)
    load = load_pdf_text(src, save_md_dir="data/parsed")

    # 4) parse + chunk
    articles = parse_document(load.text)
    chunks = chunk_document(title, articles)
    log.info(
        "Parsed: {n_art} articles → {n_chunk} chunks ({q})",
        n_art=len(articles),
        n_chunk=len(chunks),
        q=load.extraction_quality,
    )

    # 5) insert (1 docs = 1 transaction)
    with session_scope() as s:
        doc = Document(
            title=title,
            source_path=str(src.resolve()),
            file_type=src.suffix.lstrip(".") or "pdf",
            content_hash=content_hash,
            doc_type=doc_type,
            chunk_count=len(chunks),
            indexed_at=datetime.now(UTC),
            extraction_quality=load.extraction_quality,
        )
        s.add(doc)
        s.flush()  # doc.doc_id 확보

        for c in chunks:
            s.add(
                Article(
                    doc_id=doc.doc_id,
                    chapter=c.chapter,
                    section=c.section,
                    article_no=c.article_no,
                    article_title=c.article_title,
                    paragraph=c.paragraph,
                    body=c.body,
                    heading_path=c.heading_path,
                    content_type=c.content_type,
                )
            )
        new_doc_id = doc.doc_id

    # 6) embedding + Qdrant upsert (별도 트랜잭션 — 임베딩 시간 동안 락 잡지 않음)
    if chunks:
        with session_scope() as s:
            index_articles_for_doc(s, new_doc_id)

    # 7) authority_matrix doc 이면 LLM vision 으로 표 추출 → authority_rules insert
    if doc_type == "authority_matrix":
        log.info("doc_type=authority_matrix → vision LLM authority extraction (slow)")
        try:
            rules = extract_authority_rules_from_pdf(src)
        except Exception as e:  # noqa: BLE001
            log.exception("authority extraction failed for doc_id={d}: {e}", d=new_doc_id, e=e)
            rules = []
        if rules:
            from packages.db.models import AuthorityRule

            with session_scope() as s:
                for r in rules:
                    s.add(
                        AuthorityRule(
                            doc_id=new_doc_id,
                            process=r.process,
                            task=r.task,
                            approval_role=r.approval_role,
                            amount_limit_krw=r.amount_limit_krw,
                            approval_limit_pct=r.approval_limit_pct,
                            condition=r.condition,
                            raw_row=r.raw_row,
                            source_page=r.source_page,
                            confidence="ok",
                        )
                    )
            log.info("Inserted {n} authority_rules for doc_id={d}", n=len(rules), d=new_doc_id)

    return new_doc_id


def main() -> int:
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    settings = get_settings()
    log.info(
        "indexer_worker starting (poll={p}s, batch={b})",
        p=settings.indexer_poll_interval_sec,
        b=settings.indexer_batch_size,
    )

    engine = get_engine()
    Base.metadata.create_all(engine)
    log.info("DB schema ensured.")

    ensure_index_ready()
    log.info("Qdrant collection ensured.")

    while not _should_stop:
        try:
            with session_scope() as s:
                jobs = claim_next_job(s, settings.indexer_batch_size)

            if not jobs:
                time.sleep(settings.indexer_poll_interval_sec)
                continue

            for job in jobs:
                log.info("Claimed job id={id} path={p}", id=job.id, p=job.source_path)
                try:
                    doc_id = _process_job(job.id, job.source_path, job.user_doc_type)
                    with session_scope() as s:
                        mark_job_done(s, job.id, doc_id)
                    log.info("Job {id} done → doc_id={d}", id=job.id, d=doc_id)
                except Exception as e:
                    log.exception("Job {id} failed: {e}", id=job.id, e=e)
                    with session_scope() as s:
                        mark_job_failed(s, job.id, f"{type(e).__name__}: {e}")
        except Exception:
            log.exception("Worker loop error")
            time.sleep(settings.indexer_poll_interval_sec)

    log.info("indexer_worker stopped cleanly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
