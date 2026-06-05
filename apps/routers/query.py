"""POST /query, /query/stream (SSE), /query/resume — LangGraph 호출 + clarify interrupt 지원."""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from packages.code.logger import get_logger
from packages.rag.graph import build_graph
from packages.rag.nodes.clarifier_node import apply_user_choice

log = get_logger("apps.routers.query")
router = APIRouter(prefix="/query", tags=["query"])


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    session_id: str | None = Field(default=None, description="multi-turn 식별자. 없으면 새 uuid.")


class ResumeRequest(BaseModel):
    session_id: str = Field(..., description="clarify 시 받은 session_id")
    choice: str = Field(..., min_length=1, max_length=500, description="사용자가 chip 또는 자유 입력한 선택")


def _sse(event: str, data: dict[str, Any] | list[Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _trim_source(src: dict[str, Any], max_body: int = 600) -> dict[str, Any]:
    body = (src.get("body") or "")[:max_body]
    return {
        "article_id": src.get("article_id"),
        "doc_id": src.get("doc_id"),
        "article_no": src.get("article_no"),
        "article_title": src.get("article_title"),
        "chapter": src.get("chapter"),
        "heading_path": src.get("heading_path"),
        "body": body,
        "score": src.get("score"),
    }


async def _astream_state(g, inputs: dict | None, config: dict):
    """그래프 astream_events 를 돌면서 SSE 이벤트 yield.

    interrupt 발생 시 (clarify 필요) → 'clarify' event 송출 후 종료.
    """
    final_state: dict[str, Any] = {}

    async for ev in g.astream_events(inputs, config=config, version="v2"):
        kind = ev.get("event")
        name = ev.get("name", "")

        if kind == "on_chat_model_stream":
            # generator 노드의 LLM 출력만 SSE token 으로 흘림.
            # clarifier/rewriter 의 LLM 호출도 같은 이벤트를 발생시키므로 langgraph_node 로 필터.
            meta = ev.get("metadata") or {}
            if meta.get("langgraph_node") != "generator":
                continue
            chunk = ev["data"].get("chunk")
            tok = getattr(chunk, "content", "") if chunk else ""
            if tok:
                yield _sse("token", {"token": tok})
            continue

        if kind != "on_chain_end":
            continue

        output = ev["data"].get("output") or {}
        if name == "clarifier":
            # clarify 가 필요한 경우, 사용자에게 question + options 전달
            if output.get("needs_clarify"):
                yield _sse(
                    "clarify",
                    {
                        "question": output.get("clarify_question"),
                        "options": output.get("clarify_options", []),
                        "pattern": output.get("clarify_pattern"),
                        "session_id": config["configurable"]["thread_id"],
                    },
                )
        elif name == "query_rewriter":
            hyde = output.get("hyde_doc")
            if hyde:
                yield _sse("rewrite", {"hyde": hyde[:200]})
        elif name == "router":
            yield _sse("route", {"route": output.get("route")})
        elif name == "retriever" or name == "authority_lookup":
            srcs = output.get("sources") or []
            yield _sse(
                "sources",
                {"sources": [_trim_source(s) for s in srcs[:8]], "via": name},
            )
        elif name == "citation_validator":
            yield _sse(
                "citation",
                {
                    "valid_pct": output.get("citation_valid_pct", 0.0),
                    "valid": output.get("citations_valid", []),
                },
            )
        elif name == "LangGraph":
            final_state = output
            yield _sse(
                "done",
                {
                    "route": output.get("route"),
                    "citation_valid_pct": output.get("citation_valid_pct", 0.0),
                    "session_id": config["configurable"]["thread_id"],
                    "timings": output.get("timings", {}),
                },
            )


@router.post("/stream")
async def stream_query(req: QueryRequest) -> StreamingResponse:
    g = await build_graph()
    session_id = req.session_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": session_id}}
    inputs = {"question": req.question, "session_id": session_id}

    async def event_stream():
        try:
            async for chunk in _astream_state(g, inputs, config):
                yield chunk
        except Exception as e:  # noqa: BLE001
            log.exception("/query/stream error: {e}", e=e)
            yield _sse("error", {"message": str(e)})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/resume")
async def resume_query(req: ResumeRequest) -> StreamingResponse:
    """clarify 응답 받아서 그래프 resume 후 SSE 스트림 재개."""
    g = await build_graph()
    config = {"configurable": {"thread_id": req.session_id}}

    # 현재 state 조회
    snapshot = await g.aget_state(config)
    if snapshot is None or not snapshot.values:
        raise HTTPException(status_code=404, detail=f"세션 {req.session_id} state 없음")
    if not snapshot.values.get("needs_clarify"):
        raise HTTPException(status_code=400, detail="이 세션은 clarify 대기 상태가 아닙니다")

    # user_choice 반영 + clarifications append + needs_clarify 해제
    updates = apply_user_choice(snapshot.values, req.choice)
    await g.aupdate_state(config, updates)
    log.info(
        "resume session={s}, choice={c!r}, enriched_q={q!r}",
        s=req.session_id,
        c=req.choice,
        q=updates["question"][:60],
    )

    async def event_stream():
        try:
            # inputs=None → 저장된 state 에서 다음 노드 (clarify_pause) 부터 진행
            async for chunk in _astream_state(g, None, config):
                yield chunk
        except Exception as e:  # noqa: BLE001
            log.exception("/query/resume error: {e}", e=e)
            yield _sse("error", {"message": str(e)})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("")
async def query_once(req: QueryRequest) -> dict[str, Any]:
    """비-스트리밍 디버깅용. interrupt 시 clarify 정보 반환."""
    g = await build_graph()
    session_id = req.session_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": session_id}}

    await g.ainvoke({"question": req.question, "session_id": session_id}, config=config)
    snapshot = await g.aget_state(config)
    s = snapshot.values if snapshot else {}

    if s.get("needs_clarify"):
        return {
            "session_id": session_id,
            "status": "clarify",
            "clarify_question": s.get("clarify_question"),
            "clarify_options": s.get("clarify_options", []),
            "clarify_pattern": s.get("clarify_pattern"),
        }
    return {
        "session_id": session_id,
        "status": "complete",
        "route": s.get("route"),
        "draft": s.get("draft"),
        "hyde": (s.get("hyde_doc") or "")[:200],
        "citation_valid_pct": s.get("citation_valid_pct"),
        "sources": [_trim_source(x) for x in (s.get("sources") or [])[:8]],
        "timings": s.get("timings", {}),
    }
