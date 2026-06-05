from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from packages.db.connection import Base

DOC_TYPES = ("policy", "authority_matrix", "manual", "faq", "notice", "guideline", "template")
EXTRACTION_QUALITIES = ("ok", "partial", "scan_only")
INGEST_STATUSES = ("queued", "running", "done", "failed")


def _in_clause(values: tuple[str, ...]) -> str:
    return "(" + ", ".join(f"'{v}'" for v in values) + ")"


class Document(Base):
    __tablename__ = "documents"

    doc_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    source_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_type: Mapped[str] = mapped_column(String(16), nullable=False, default="pdf")
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    doc_type: Mapped[str] = mapped_column(String(32), nullable=False)
    domain: Mapped[str | None] = mapped_column(String(64))
    process: Mapped[str | None] = mapped_column(String(64))
    version: Mapped[str | None] = mapped_column(String(32))
    effective_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    access_role: Mapped[str] = mapped_column(String(32), nullable=False, default="all")
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    extraction_quality: Mapped[str] = mapped_column(String(16), nullable=False, default="ok")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    articles: Mapped[list[Article]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    authority_rules: Mapped[list[AuthorityRule]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            f"doc_type IN {_in_clause(DOC_TYPES)}",
            name="ck_documents_doc_type",
        ),
        CheckConstraint(
            f"extraction_quality IN {_in_clause(EXTRACTION_QUALITIES)}",
            name="ck_documents_extraction_quality",
        ),
        Index("ix_documents_doc_type", "doc_type"),
        Index("ix_documents_domain", "domain"),
    )


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    doc_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("documents.doc_id", ondelete="CASCADE"), nullable=False
    )
    chapter: Mapped[str | None] = mapped_column(String(256))
    section: Mapped[str | None] = mapped_column(String(256))
    article_no: Mapped[str | None] = mapped_column(String(64))
    article_title: Mapped[str | None] = mapped_column(String(512))
    paragraph: Mapped[str | None] = mapped_column(String(8))
    item: Mapped[str | None] = mapped_column(String(16))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    heading_path: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    qdrant_point_id: Mapped[str | None] = mapped_column(String(64))
    page: Mapped[int | None] = mapped_column(Integer)
    content_type: Mapped[str] = mapped_column(String(32), nullable=False, default="article")

    document: Mapped[Document] = relationship(back_populates="articles")

    __table_args__ = (
        Index("ix_articles_doc_article_para", "doc_id", "article_no", "paragraph"),
        Index("ix_articles_heading_path", "heading_path", postgresql_using="gin"),
    )


class AuthorityRule(Base):
    __tablename__ = "authority_rules"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    doc_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("documents.doc_id", ondelete="CASCADE"), nullable=False
    )
    article_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("articles.id", ondelete="SET NULL")
    )
    process: Mapped[str] = mapped_column(String(64), nullable=False)
    task: Mapped[str | None] = mapped_column(String(256))
    approval_role: Mapped[str] = mapped_column(String(64), nullable=False)
    approval_limit_pct: Mapped[float | None] = mapped_column(Numeric(6, 3))
    amount_limit_krw: Mapped[int | None] = mapped_column(BigInteger)
    condition: Mapped[str | None] = mapped_column(Text)
    raw_row: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    source_page: Mapped[int | None] = mapped_column(Integer)
    confidence: Mapped[str] = mapped_column(String(16), nullable=False, default="ok")

    document: Mapped[Document] = relationship(back_populates="authority_rules")

    __table_args__ = (
        Index("ix_authority_process", "process"),
        Index("ix_authority_role", "approval_role"),
        Index("ix_authority_amount", "amount_limit_krw"),
    )


class IngestJob(Base):
    __tablename__ = "ingest_jobs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    user_doc_type: Mapped[str | None] = mapped_column(String(32))
    force_ocr: Mapped[bool] = mapped_column(nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    doc_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("documents.doc_id", ondelete="SET NULL")
    )
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            f"status IN {_in_clause(INGEST_STATUSES)}",
            name="ck_ingest_jobs_status",
        ),
        Index("ix_ingest_jobs_status_created", "status", "created_at"),
    )


class Conversation(Base):
    __tablename__ = "conversations"

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str | None] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("conversations.session_id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # user / assistant / system
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sources: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    route: Mapped[str | None] = mapped_column(String(32))
    citation_valid_pct: Mapped[float | None] = mapped_column(Numeric(5, 4))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    conversation: Mapped[Conversation] = relationship(back_populates="messages")

    __table_args__ = (Index("ix_messages_session_created", "session_id", "created_at"),)


class TaxonomyConfig(Base):
    """admin 에서 domain/process enum 편집. key='domain' / 'process' 등의 단일 row."""

    __tablename__ = "taxonomy_config"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    values: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("key", name="uq_taxonomy_config_key"),
    )
