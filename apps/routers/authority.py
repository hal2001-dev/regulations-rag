"""GET /authority — authority_rules 직접 SQL 조회 (admin/디버깅).

LangGraph 의 authority_lookup_node 와 동일 로직을 REST 로 노출.
M6 의 admin UI 가 이걸 사용.
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from apps.dependencies import SessionDep
from packages.db.models import AuthorityRule, Document

router = APIRouter(prefix="/authority", tags=["authority"])


def _serialize(r: AuthorityRule, doc: Document) -> dict:
    return {
        "id": r.id,
        "doc_id": r.doc_id,
        "doc_title": doc.title,
        "process": r.process,
        "task": r.task,
        "approval_role": r.approval_role,
        "amount_limit_krw": r.amount_limit_krw,
        "approval_limit_pct": float(r.approval_limit_pct) if r.approval_limit_pct is not None else None,
        "condition": r.condition,
        "source_page": r.source_page,
        "confidence": r.confidence,
    }


@router.get("")
def search_rules(
    session: SessionDep,
    process: str | None = Query(default=None, description="discount_approval/contract/expense_claim/..."),
    amount: int | None = Query(default=None, description="KRW. 이 금액 이상 결재 가능한 rules"),
    pct: float | None = Query(default=None, description="0-100. 이 % 이상 결재 가능한 rules"),
    role: str | None = Query(default=None, description="결재권자 직위 exact (사장/본부장/...)"),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    """authority_rules 필터 조회.

    예:
        GET /authority?process=contract&amount=50000000   → 5천만원 계약 결재 가능 rules
        GET /authority?process=discount_approval&pct=30   → 30% 할인 결재 가능 rules
        GET /authority?role=사장                          → 사장 결재 rules 전체
    """
    stmt = select(AuthorityRule, Document).join(Document, AuthorityRule.doc_id == Document.doc_id)
    if process:
        stmt = stmt.where(AuthorityRule.process == process)
    if amount is not None:
        stmt = stmt.where(AuthorityRule.amount_limit_krw >= amount)
    if pct is not None:
        stmt = stmt.where(AuthorityRule.approval_limit_pct >= pct)
    if role:
        stmt = stmt.where(AuthorityRule.approval_role == role)

    stmt = stmt.order_by(
        AuthorityRule.amount_limit_krw.asc().nullslast(),
        AuthorityRule.approval_limit_pct.asc().nullslast(),
    ).limit(limit)

    rows = session.execute(stmt).all()
    return {
        "items": [_serialize(r, d) for r, d in rows],
        "count": len(rows),
        "filter": {
            "process": process,
            "amount_krw": amount,
            "pct": pct,
            "role": role,
        },
    }


@router.get("/processes")
def list_processes(session: SessionDep) -> dict:
    """process distinct + 카운트 — admin overview."""
    rows = session.execute(
        select(AuthorityRule.process, func.count().label("n"))
        .group_by(AuthorityRule.process)
        .order_by(func.count().desc())
    ).all()
    return {"items": [{"process": p, "count": n} for p, n in rows]}


@router.get("/roles")
def list_roles(session: SessionDep) -> dict:
    """approval_role distinct + 카운트."""
    rows = session.execute(
        select(AuthorityRule.approval_role, func.count().label("n"))
        .group_by(AuthorityRule.approval_role)
        .order_by(func.count().desc())
    ).all()
    return {"items": [{"role": r, "count": n} for r, n in rows]}
