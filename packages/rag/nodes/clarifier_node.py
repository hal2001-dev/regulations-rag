"""Clarifier — 모호한 질문 감지 + 사용자 chip 옵션 생성.

4 패턴 (mvp_plan §M5):
1. target_ambiguous  — "그 규정", "이 사람" 처럼 대상 불명확
2. authority_slot   — authority 질문인데 process/amount/role 정보 부족
3. time_ambiguous   — "예전", "최근" 처럼 시점 모호
4. scope_wide       — "전부 알려줘", "다 보여줘" 처럼 광범

ADR-012: 동일 세션 clarifications 누적 2회 후 강제 통과 (UX 가드).
"""

from __future__ import annotations

import json
import time

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from apps.config import get_settings
from packages.code.logger import get_logger
from packages.rag.state import Clarification, QueryState

log = get_logger("packages.rag.nodes.clarifier")

MAX_CLARIFICATIONS = 2  # ADR-012

_SYSTEM_PROMPT = """당신은 한국 사내 규정 RAG 시스템의 clarifier 입니다.
사용자 질문이 retrieval/SQL 조회에 충분히 구체적인지 판단하고, 정말로 모호할 때만 chip 옵션을 제공하세요.
대부분의 질문은 그대로 통과시키세요 (false-positive 가 사용자 경험을 크게 해칩니다).

⚠️ [이전 대화] 가 주어지면 먼저 그 맥락으로 질문을 해석하세요. 후속/지시어 질문("방금 그거", "그럼 식비는?", "내가 뭘 물었지?")이 이전 대화로 **자연스럽게 풀리면 should_clarify=false** 로 통과시키세요 (대상이 이미 대화에 있으므로 모호하지 않음).

다음 4 패턴 중 하나에 명백히 해당할 때만 clarify, 그 외는 모두 통과:

1. target_ambiguous — 지시 대명사만으로 대상이 안 잡힘 ("그 규정 알려줘", "이 사람 휴가", "거기 한도")
2. authority_slot — 결재/승인 질문에 amount(금액)·process(업무)·role(직위) 중 식별 가능한 슬롯이 0개
   예 NEED: "결재 누가?", "한도가 얼마?"
   예 PASS: "3천만원 계약 누가 결재?", "할인 30% 누구 승인?", "복리후생비 본부장 한도?"
3. time_ambiguous — "예전", "최근", "그때" 등 시점 지시어가 답변의 핵심일 때만
4. scope_wide — "규정 다 보여줘", "전부 알려줘" 처럼 N개 문서를 통째로 요구

출력 JSON (반드시 이 형식):
{
  "should_clarify": true | false,
  "confidence": 0.0~1.0 (clarify 필요성에 대한 확신도),
  "pattern": "target_ambiguous|authority_slot|time_ambiguous|scope_wide|none",
  "question": "사용자에게 보낼 한국어 질문 (clarify 시)",
  "options": ["chip1", "chip2", "chip3"] (3-5개, clarify 시)
}

명확한 질문 예시 (모두 should_clarify=false):
- "내부회계관리규정 제5조 내용은?"
- "연차휴가 어떻게 신청하나요?"
- "3천만원 계약 누가 결재?" (금액+프로세스 슬롯 채워짐)
- "출장비 한도 알려줘" (프로세스 명시)
- "신천초 위임전결 5천만원 한도" (문서명+금액)

규칙:
- 명백히 모호한 경우에만 should_clarify=true, confidence ≥ 0.7
- 약간 모호하지만 retrieval 로 답이 나올 가능성이 있으면 통과 (보수적)
- options 는 우리 PDF 카테고리에서 골라: 회계규정/여비규정/인사관리규정/내부회계관리규정/정보보안규정/위임전결/취업규칙/복리후생/계약관리/안전관리
- 한국어로 question 작성
"""


_llm: ChatOpenAI | None = None


def _get_llm() -> ChatOpenAI:
    global _llm
    if _llm is None:
        s = get_settings()
        _llm = ChatOpenAI(
            model=s.llm_model,
            api_key=s.openai_api_key,
            temperature=0,
            model_kwargs={"response_format": {"type": "json_object"}},
        )
    return _llm


def clarifier_node(state: QueryState) -> dict:
    """모호 감지 + clarify question/options 채우기.

    이미 누적 clarifications ≥ MAX 면 강제 통과 (needs_clarify=False).
    """
    t0 = time.perf_counter()
    q = state["question"]
    clarify_hist = state.get("clarifications", [])
    conv_hist = state.get("history", [])  # 멀티턴 대화 (user/assistant)

    # UX 가드: 누적 한계 도달 시 강제 통과
    if len(clarify_hist) >= MAX_CLARIFICATIONS:
        log.info("clarifications limit reached ({n}) — bypass", n=len(clarify_hist))
        return {
            "needs_clarify": False,
            "timings": {**state.get("timings", {}), "clarifier": time.perf_counter() - t0},
        }

    parts = [f"질문: {q}"]
    # 멀티턴 대화 — 후속/지시어 질문이 이전 맥락으로 풀리면 clarify 불필요.
    if conv_hist:
        convo = "\n".join(
            f"- {h.get('role')}: {(h.get('content') or '')[:150]}" for h in conv_hist[-6:]
        )
        parts.append(f"\n[이전 대화 (이 맥락으로 해소되면 clarify 하지 말 것)]\n{convo}")
    # clarify 누적 (같은 turn 의 이전 역질문)
    if clarify_hist:
        ctx = "\n".join(
            f"- 이전 clarify: {c.get('question','')} → 선택: {c.get('user_choice','')}"
            for c in clarify_hist
        )
        parts.append(f"\n[이전 clarify]\n{ctx}")
    user = "\n".join(parts)

    try:
        resp = _get_llm().invoke(
            [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=user)],
        )
        parsed = json.loads(resp.content or "{}")
    except Exception as e:  # noqa: BLE001
        log.warning("clarifier LLM failed: {e} — bypass", e=e)
        return {
            "needs_clarify": False,
            "timings": {**state.get("timings", {}), "clarifier": time.perf_counter() - t0},
        }

    should = bool(parsed.get("should_clarify", False))
    confidence = float(parsed.get("confidence", 0.0))
    pattern = parsed.get("pattern", "none")
    cq = parsed.get("question", "")
    options = parsed.get("options") or []

    # confidence ≥ 0.7 + should_clarify=True + options 비어있지 않음 (보수적 임계)
    if not (should and confidence >= 0.7 and cq and options):
        log.info(
            "clarifier: pass (should={s}, conf={c:.2f}, pattern={p})",
            s=should,
            c=confidence,
            p=pattern,
        )
        return {
            "needs_clarify": False,
            "timings": {**state.get("timings", {}), "clarifier": time.perf_counter() - t0},
        }

    log.info(
        "clarifier: NEED (pattern={p}, conf={c:.2f}, q={q!r}, options={o})",
        p=pattern,
        c=confidence,
        q=cq[:40],
        o=options[:5],
    )
    return {
        "needs_clarify": True,
        "clarify_question": cq,
        "clarify_options": options[:5],
        "clarify_pattern": pattern,
        "timings": {**state.get("timings", {}), "clarifier": time.perf_counter() - t0},
    }


def apply_user_choice(state: QueryState, user_choice: str) -> dict:
    """/query/resume 호출 시 클라이언트가 보낸 선택을 state 에 반영.

    이전 clarify question + user_choice 를 clarifications 에 append + question 자체에 합쳐
    rewriter/router 가 보강된 질문으로 진행하게 한다.
    """
    new_history: list[Clarification] = list(state.get("clarifications") or [])
    last = Clarification(
        question=state.get("clarify_question", ""),
        options=state.get("clarify_options", []),
        pattern=state.get("clarify_pattern", ""),
        user_choice=user_choice,
    )
    new_history.append(last)

    # question 보강: 원본 + " (clarify: " + 선택 + ")"
    enriched = f"{state['question']} (관련: {user_choice})"

    return {
        "question": enriched,
        "clarifications": new_history,
        "needs_clarify": False,
        # clarify 관련 일회성 필드 비워 다음 round 영향 X
        "clarify_question": "",
        "clarify_options": [],
        "clarify_pattern": "",
    }
