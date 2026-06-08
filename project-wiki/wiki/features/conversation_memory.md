# Conversation Memory — 멀티턴 대화 참조 (최근 5턴)

**상태**: active
**마지막 업데이트**: 2026-06-08 (신규)
**관련 페이지**: [clarifier.md](clarifier.md), [retrieval.md](retrieval.md), [generation.md](generation.md), [../architecture/pipeline.md](../architecture/pipeline.md), [../api/endpoints.md](../api/endpoints.md)

## 요약
같은 `session_id` 안에서 **최근 5 turn(user/assistant)** 을 참조해 후속 질문을 처리한다. 두 축으로 동작:
1. **대화 메모리** — "방금 무엇을 물어봤나" 처럼 이전 대화를 기억해 답변.
2. **맥락 기반 재검색** — "그럼 식비는?" 처럼 생략된 대상·조건을 이전 대화에서 복원해 **검색까지** 연결.

> 이전에는 `conversations`/`messages` 테이블만 있고 저장·참조 로직이 전혀 없어, 각 질문이 독립 처리됐다. 이 기능으로 멀티턴이 실제 동작한다.

## 흐름
```
POST /query/stream {question, session_id}
  ↓
get_recent_history(session_id, limit_turns=5)  → state.history [{role, content}, …]
  ↓
[clarifier]  history 참조 → 후속/지시어 질문이면 clarify 안 하고 통과
[rewriter]   history 로 생략 맥락 복원 → HyDE 키워드 확장 (검색 query 보강)
[generator]  history 를 Human/AI 메시지로 프롬프트에 주입 → 맥락 있는 답변
  ↓
턴 완료(needs_clarify=false) → save_turn: user 질문 + assistant 답변 저장
  (clarify 대기 중엔 미저장, /query/resume 완료 시 저장)
```

## 컴포넌트
| 위치 | 역할 |
|---|---|
| `repository.save_turn` | conversation upsert + user/assistant 메시지 저장 |
| `repository.get_recent_history` | 최근 `limit_turns`×2 메시지를 시간순 반환 |
| `state.QueryState.history` | `list[{role, content}]` — 노드 간 전달 |
| `query.py` `_persist_turn` / `HISTORY_TURNS=5` | 로드 + 저장 오케스트레이션 |
| `clarifier_node` | history 로 후속 질문 통과 (역질문 억제) |
| `query_rewriter_node` | history 로 HyDE 맥락 복원 (검색 보강) |
| `generator_node` | history 를 LLM 메시지로 주입 |

## 검증 (2026-06-08)
| turn | 질문 | 결과 |
|---|---|---|
| Q1 | "공무원여비규정 국내 여비 지급표 제2호 일비 금액" | "1일당 25,000원" |
| Q2 | "방금 내가 무엇을 물어봤나요?" | 이전 질문 정확히 기억 ✅ |
| Q2' | "그럼 식비는?" | HyDE 가 "국내 출장 2호 식비" 로 복원 → 별표 2 식비 행 검색 → "1일당 25,000원" ✅ |

## 한계 / 후속
- **reranker 는 원질문 사용** — `retriever_node` 의 rerank 쿼리는 `state["question"]`(원문, 예: "그럼 식비는?"). 후보는 rewriter 가 맥락으로 끌어오지만, rerank 점수 변별은 원질문 기준이라 약할 수 있음. 필요 시 rerank 도 복원된 질문 사용으로 확장.
- **clarifier 과민**(ADR-019 carry-over) — 명확한 첫 질문도 가끔 clarify. 멀티턴과 무관한 별개 이슈.
- **history 는 generator/clarifier/rewriter 만 사용** — router/authority_lookup 은 미사용.
- 요약/압축 없이 원문 5턴 주입 — 길어지면 토큰 비용↑ (현재 turn 당 150자 truncate).

## 출처
- `packages/db/repository.py`, `packages/rag/state.py`, `apps/routers/query.py`
- `packages/rag/nodes/{clarifier,query_rewriter,generator}_node.py`
- 2026-06-08 멀티턴 e2e 검증
