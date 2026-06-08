"""gpt-4o-mini streaming generator — [결론]/[근거]/[적용 조건]/[절차]/[주의] 5-block format."""

from __future__ import annotations

import time

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from apps.config import get_settings
from packages.code.logger import get_logger
from packages.rag.state import QueryState

log = get_logger("packages.rag.nodes.generator")


SYSTEM_PROMPT = """당신은 한국 사내 규정·매뉴얼 전문 어시스턴트입니다.
주어진 [컨텍스트] 의 조항만 근거로 답하세요. 컨텍스트에 없는 사실은 만들지 마세요.

## 답변 원칙 (중요)

1. **의미적 용어 매핑 허용**: 질문의 용어와 컨텍스트의 용어가 정확히 일치하지 않아도, 의미가 가까우면 (예: 사용자 "학생 폭언" ↔ 규정 "폭행·모욕", "연차" ↔ "연가") 컨텍스트의 정보를 활용해 답하세요. "정확히 그 단어가 없다"는 이유로 "내용 없음" 결론을 내리지 마세요.
2. **누락 금지**: 컨텍스트에 관련 절차·조치·한도·기한·역할 정보가 있으면 답변에 빠짐없이 반영하세요. 짧은 문장 1개로 끝내지 말고 컨텍스트의 핵심을 모두 옮겨 적으세요.
3. **다중 인용**: 컨텍스트 chunk 가 N개 주어졌을 때, 관련 있는 것은 최소 2개 (가능하면 3~5개) 를 [근거] 에 인용하세요.
4. **진짜 없을 때만 없음**: 컨텍스트 어디에도 관련 단서가 전혀 없을 때만 [결론] 에 "컨텍스트에 명시된 정보가 없습니다" 라고 쓰세요. 부분 정보라도 있으면 그것을 토대로 답하세요.

## 출력 형식

다음 다섯 블록을 순서대로, 각 블록의 헤더(`[결론]` 등)를 한 줄로 시작하세요.

[결론]
- 질문에 대한 직접적인 답을 1~3문장으로. 컨텍스트에 부분 정보만 있어도 그것을 토대로 답하세요.
[근거]
- 사용한 조항을 `[doc_id={숫자}, {조항}] {한 줄 요약}` 형식으로. 관련 있는 모든 sources 를 인용하세요 (최소 2개 권장).
- 컨텍스트에 명시된 doc_id 와 article_no 를 그대로 인용하세요. 추측 금지.
[적용 조건]
- 답이 성립하는 조건 (대상자·금액·기한 등) 이 있으면 적고, 없으면 "없음".
[절차]
- 실행 단계가 있으면 1·2·3 번호로 적고, 없으면 "없음".
[주의]
- 예외·기한·상위 규정 우선 등 사용자가 알아야 할 사항. 없으면 "없음".

## 예시

질문: "학생 폭언 어떻게 대응?"
컨텍스트에 "교원에 대한 폭행·모욕 등 침해행위 발생 시 즉시 보호조치를 하고 관할청에 보고" 가 있다면:
- ❌ 잘못된 답: "학생 폭언에 대한 절차가 명시되어 있지 않습니다."
- ✅ 올바른 답: [결론] 학생의 폭언은 규정상 '폭행·모욕 등 교육활동 침해행위' 에 해당하며, 즉시 보호조치를 시행하고 관할청에 보고해야 합니다.
"""


def _build_messages(
    question: str, sources: list[dict], history: list[dict] | None = None
) -> list:
    if not sources:
        ctx = "(컨텍스트 없음)"
    else:
        parts = []
        for s in sources[:8]:
            head = (
                f"doc_id={s['doc_id']} | {s.get('article_no') or '?'}"
                f" {s.get('article_title') or ''}".strip()
            )
            body = (s.get("body") or "").strip()
            parts.append(f"[{head}]\n{body}")
        ctx = "\n\n---\n\n".join(parts)
    msgs: list = [SystemMessage(content=SYSTEM_PROMPT)]
    # 이전 멀티턴 대화(최근 N turn) — 후속 질문의 지시어/맥락 이해용.
    for h in history or []:
        if h.get("role") == "user":
            msgs.append(HumanMessage(content=h["content"]))
        elif h.get("role") == "assistant":
            msgs.append(AIMessage(content=h["content"]))
    user = f"[컨텍스트]\n{ctx}\n\n[질문]\n{question}"
    msgs.append(HumanMessage(content=user))
    return msgs


_llm: ChatOpenAI | None = None


def _get_llm() -> ChatOpenAI:
    global _llm
    if _llm is None:
        s = get_settings()
        _llm = ChatOpenAI(
            model=s.llm_model,
            api_key=s.openai_api_key,
            streaming=True,
            temperature=0,
        )
    return _llm


async def generator_node(state: QueryState) -> dict:
    """LangGraph 가 outer astream_events 로 token chunk 를 자동 forward."""
    t0 = time.perf_counter()
    q = state.get("rewritten_question") or state["question"]
    sources = state.get("sources", [])

    msgs = _build_messages(q, sources, state.get("history"))
    llm = _get_llm()

    chunks: list[str] = []
    async for c in llm.astream(msgs):
        if c.content:
            chunks.append(c.content)
    draft = "".join(chunks)
    log.info(
        "generator: {n} sources → {ln} chars in {t:.2f}s",
        n=len(sources),
        ln=len(draft),
        t=time.perf_counter() - t0,
    )
    return {
        "draft": draft,
        "timings": {**state.get("timings", {}), "generator": time.perf_counter() - t0},
    }
