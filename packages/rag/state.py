"""LangGraph state — 모든 노드가 공유하는 dict-like state."""

from __future__ import annotations

from typing import Any, TypedDict


class Source(TypedDict, total=False):
    article_id: int
    doc_id: int
    article_no: str
    article_title: str | None
    chapter: str | None
    heading_path: dict[str, Any]
    body: str
    score: float


class Clarification(TypedDict, total=False):
    """clarifier 1회 호출 결과 (누적 가능)."""

    question: str  # 사용자에게 보여줄 질문
    options: list[str]  # 사용자가 선택할 chip
    pattern: str  # 발동 패턴: target_ambiguous / authority_slot / time_ambiguous / scope_wide
    user_choice: str | None  # resume 시 사용자 선택


class QueryState(TypedDict, total=False):
    """그래프 입력/출력 + 노드 간 전달.

    LangGraph 는 dict 의 키 단위로 merge — 새 키만 반환하면 그 키만 업데이트.
    """

    # 입력
    question: str
    session_id: str

    # M5 clarifier / rewriter
    needs_clarify: bool  # True 면 graph 가 interrupt
    clarify_question: str  # 사용자에게 보낼 질문
    clarify_options: list[str]  # chip 옵션
    clarify_pattern: str  # 발동 패턴
    clarifications: list[Clarification]  # 누적 (2회 후 강제 통과 — ADR-012)
    hyde_doc: str  # HyDE 가상 답변 (rewriter 가 생성)

    # 노드 출력
    route: str  # "policy" / "authority" / "manual" / "faq"
    rewritten_question: str  # rewriter 가 채움. M5: question + " " + hyde_doc.
    sources: list[Source]
    draft: str
    citations_valid: list[bool]
    citation_valid_pct: float

    # 에러/디버그
    errors: list[str]
    timings: dict[str, float]
