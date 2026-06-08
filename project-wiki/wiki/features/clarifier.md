# Clarifier — 모호 질문 역질문 (interrupt 기반)

**상태**: active
**마지막 업데이트**: 2026-06-08 (페이지 신규 — 기능은 M5 구현)
**관련 페이지**: [generation.md](generation.md), [retrieval.md](retrieval.md), [answer_accuracy.md](answer_accuracy.md), [../architecture/pipeline.md](../architecture/pipeline.md), [../architecture/decisions.md](../architecture/decisions.md)

## 요약
모호한 질문은 `clarifier` 노드가 LangGraph `interrupt` 로 그래프를 멈추고 사용자에게 역질문(+선택지 chip)을 보낸다. 명확한 질문은 그대로 통과한다. HyDE(내부 확장)와 clarify(외부 역질문)의 하이브리드 — 상세 [answer_accuracy.md](answer_accuracy.md).

## 4가지 clarify 패턴
| pattern | 발동 조건 | 예시 |
|---|---|---|
| `target_ambiguous` | 지시대명사만으로 대상 불명확 | "그 규정 알려줘", "이 사람 휴가" |
| `authority_slot` | 결재/승인 질문에 amount·process·role 슬롯 0개 | "결재 누가?" |
| `time_ambiguous` | 시점 지시어가 답의 핵심일 때 | "예전 기준", "최근에" |
| `scope_wide` | N개 문서를 통째로 요구 | "규정 전부 보여줘" |

## 발동 규칙 (보수적)
- LLM(gpt-4o-mini) structured JSON 으로 `should_clarify` / `confidence` / `pattern` / `options` 판정.
- **`should_clarify=true` + `confidence ≥ 0.7` + `options` 비어있지 않음** 일 때만 clarify (over-clarification 방지, ADR 참조).
- `MAX_CLARIFICATIONS = 2` (ADR-012) 초과 시 강제 통과 — 무한 역질문 방지.

## 그래프 흐름
```
START → clarifier → (needs_clarify ? clarify_pause : query_rewriter) → router → …
        interrupt_before=["clarify_pause"]   # clarify 시 그래프 일시 중단
```
- clarify 발생 → SSE `clarify` 이벤트(question/options/pattern/session_id) 송출 후 중단.
- 사용자 응답 → `POST /query/resume` → `apply_user_choice(state, choice)` 로 질문 보강 → `aupdate_state` → 그래프 재개.

## 코드 위치
- `packages/rag/nodes/clarifier_node.py` — 패턴 감지 + `apply_user_choice`
- `packages/rag/graph.py` — `interrupt_before=["clarify_pause"]`
- `apps/routers/query.py` — `clarify` SSE 이벤트 + `POST /query/resume`

## 출처
- `docs/mvp_plan.md` §M5, `packages/rag/nodes/clarifier_node.py`, [decisions.md](../architecture/decisions.md) ADR-012
