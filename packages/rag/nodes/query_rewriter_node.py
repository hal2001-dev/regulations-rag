"""Query rewriter — HyDE (Hypothetical Document Embeddings).

LLM 이 질문에 답을 가상으로 작성 → 그 가상 답변과 원본 질문을 합쳐 retrieval 의 query 로 사용.
한국어 retrieval 의 동의어/조사 약점 보완 (예: "연차" → "연차휴가 며칠 ...").

clarifier 가 needs_clarify=True 이면 graph 에서 우회되므로, 이 노드는 명확한 질문만 받음.
authority route 는 SQL exact 라 HyDE 효과 적음 → 일단 모든 query 에 적용 (간단), 후속 최적화.
"""

from __future__ import annotations

import time

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from apps.config import get_settings
from packages.code.logger import get_logger
from packages.rag.state import QueryState

log = get_logger("packages.rag.nodes.query_rewriter")


_SYSTEM_PROMPT = """당신은 한국 사내 규정 검색을 위한 HyDE 도우미입니다.
사용자 질문의 답이 담겨 있을 법한 짧은 가상 답변(1-2문장)을 작성합니다.
목적은 '사실 진술'이 아니라 '검색 키워드 확장' 입니다.

규칙:
- 한국어, 규정 문체로 작성.
- 질문의 핵심 명사를 동의어·관련어로 확장한다 (예: "일비" → "일비, 1일당 정액, 출장 일당").
- 답이 담길 법한 자료의 '명칭·유형'을 일반적으로 언급한다 (예: "지급표", "구분표", "별표", "기준표", "정액표").
- ⚠️ 조문·별표 '번호'(제N조, 별표 N)를 모르면 절대 지어내지 말 것. 확신 없는 번호는 쓰지 않는다.
- ⚠️ 구체적 금액·수치를 단정하지 말 것.
- 답변만 출력 (헤더/설명/JSON 없이).
"""


_llm: ChatOpenAI | None = None


def _get_llm() -> ChatOpenAI:
    global _llm
    if _llm is None:
        s = get_settings()
        _llm = ChatOpenAI(
            model=s.llm_model,
            api_key=s.openai_api_key,
            temperature=0.0,  # 환각(틀린 조항번호) 최소화
            max_tokens=160,
        )
    return _llm


def query_rewriter_node(state: QueryState) -> dict:
    """원본 질문 + HyDE 가상 답변 = rewritten_question."""
    t0 = time.perf_counter()
    q = state["question"]

    try:
        resp = _get_llm().invoke(
            [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=q)],
        )
        hyde = (resp.content or "").strip()
    except Exception as e:  # noqa: BLE001
        log.warning("HyDE LLM failed: {e} — fallback to original", e=e)
        return {
            "rewritten_question": q,
            "hyde_doc": "",
            "timings": {**state.get("timings", {}), "rewriter": time.perf_counter() - t0},
        }

    if not hyde:
        return {
            "rewritten_question": q,
            "hyde_doc": "",
            "timings": {**state.get("timings", {}), "rewriter": time.perf_counter() - t0},
        }

    rewritten = f"{q}\n\n{hyde}"
    log.info(
        "HyDE: original {oq} chars → rewritten {rq} chars (hyde={h} chars)",
        oq=len(q),
        rq=len(rewritten),
        h=len(hyde),
    )
    return {
        "rewritten_question": rewritten,
        "hyde_doc": hyde,
        "timings": {**state.get("timings", {}), "rewriter": time.perf_counter() - t0},
    }
