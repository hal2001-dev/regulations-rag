# Roadmap

**상태**: active
**마지막 업데이트**: 2026-05-27
**관련 페이지**: [overview.md](overview.md), [architecture/pipeline.md](architecture/pipeline.md)

## 요약
M1~M6 의 6 마일스톤. 각 단계마다 **Demo**(수동 검증 가능) + **KPI**(정량 지표) 두 가지로 완료 정의. 일자는 풀타임 작업 기준 예상치.

---

## M1 — Skeleton + Wiki (1.5 일)

**Build**
- `docker-compose.yml` (qdrant + postgres)
- `apps/main.py` `/health`, `apps/config.py`, 빈 routers
- `packages/db/models.py` 전 테이블 + lifespan `create_all`
- `web/` shadcn init + `/chat` placeholder
- `.env.example`, `requirements.txt`
- **project-wiki 전체 스캐폴드** (CLAUDE.md + raw/ + wiki/ 초기 페이지 8개) — ✅ 2026-05-27 완료

**requirements.txt 핵심**: `langgraph`, `langgraph-checkpoint-postgres`, `langchain-core`, `langchain-openai`, `fastapi`, `uvicorn[standard]`, `sqlalchemy`, `psycopg[binary,pool]`, `qdrant-client`, `fastembed`, `kiwipiepy`, `docling`, `langchain-docling`, `pydantic-settings`, `ragas`, `httpx-sse`

**Demo**: `docker compose up` → `curl :8000/health` → `localhost:3000` shell. `cat project-wiki/wiki/overview.md` 가 PRD 요약 표시.

**KPI**: 두 프로세스 클린 부팅, Postgres 전 테이블 생성, wiki 초기 페이지 8개 작성 완료.

**현재 상태**: wiki 부분 ✅ / 코드 ❌

---

## M2 — Ingest + Structure Parser (3 일)

**Build**
- `packages/loaders/docling_loader.py`
- `packages/regulation_parser/{structure,article_chunker,doc_type_classifier}.py`
- `apps/indexer_worker.py` (FOR UPDATE SKIP LOCKED 큐 워커)
- `apps/routers/ingest.py`
- `scripts/bulk_ingest.py`

**Demo**: `python scripts/bulk_ingest.py ingest/*.pdf` → 17 job enqueue → worker drain → `SELECT doc_id, doc_type, chunk_count FROM documents` 17행. wiki `features/ingestion.md` + `data/spec.md` 갱신.

**KPI**: 17/17 인덱싱, `articles.article_no` non-null ≥14/17, 무작위 10 article 의 `heading_path` 수동 검증 통과.

---

## M3 — LangGraph Skeleton + Retrieval + Generator (3 일)

**Build**
- `packages/rag/state.py` (QueryState TypedDict)
- `packages/rag/checkpointer.py` (PostgresSaver)
- `packages/rag/nodes/{router_node,retriever_node,generator_node,citation_validator}.py`
- `packages/rag/{sparse,retriever,reranker}.py` 헬퍼
- `packages/rag/graph.py` (clarifier/rewriter 는 pass-through 더미)
- `apps/routers/query.py` SSE (`token`/`sources`/`done` 만 우선)
- `packages/vectorstore/qdrant_store.py`

**Demo**: `curl -N -X POST :8000/query/stream -d '{"question":"연차휴가 어떻게 신청하나요?"}'` → SSE 토큰 + `sources` + `done`. LangGraph checkpoint Postgres 테이블 자동 생성 확인.

**KPI**: 10 골든 policy 쿼리 중 top-1 정답 doc_id **8/10**, citation validator `[근거]` **90%+** 통과, 첫 토큰 **<1s**.

---

## M4 — Authority Lookup Node + Conditional Edge (2 일)

**Build**
- `packages/regulation_parser/authority_extractor.py`
- `packages/rag/nodes/authority_lookup_node.py`
- `graph.py` 에 `route=="authority"` 조건부 edge
- `apps/routers/authority.py` (REST 직접 조회용)
- 위임전결 2건 (`사무위임전결규정.pdf`, `신천초 위임전결규정...pdf`) 재인덱싱

**Demo**: `curl :8000/query/stream -d '{"question":"할인 30% 누가 승인?"}'` → `event: route data:{"route":"authority"}` → SQL 1-3행 → 토큰 스트리밍 "영업본부장 — 한도 30%/5천만원, 근거: 사무위임전결규정 제N조".

**KPI**: 5개 authority 쿼리에서 role/limit **exact match**, router accuracy **≥13/15**.

---

## M5 — Clarifier + Query Rewriter + Chat UI Multi-turn (3 일)

**Build**
- `packages/rag/nodes/{clarifier,query_rewriter}.py` (실제 구현으로 교체)
- `graph.py` 에 `clarifier` interrupt config (`interrupt_before=["clarify_pause"]`)
- `apps/routers/query.py` `clarify` 이벤트 송출 + `POST /query/resume`
- `web/app/chat/page.tsx`, `components/chat/{chat-stream,answer-blocks,citation-chip,quick-reply-chips,node-progress}.tsx`
- `web/lib/api.ts` (resume 클라이언트)
- `web/next.config.ts` `compress: false`

**Demo**: 브라우저 `/chat` 에 "그 규정 알려줘" → clarify question + chip → "회계규정" chip 클릭 → graph resume → 토큰 스트리밍 + citation.

**KPI**: 첫 토큰 **<1s**, 종단 **<3s**. 모호한 10개 쿼리 중 적절한 clarify 발동 **≥8/10**. clarify 후 resume 정상 동작 **100%**.

---

## M6 — Admin UI + Reindex + Ragas Eval (2 일)

**Build**
- `web/app/admin/*`, `web/app/library/page.tsx`
- `apps/routers/admin.py` (reindex = Qdrant chunk drop + 재 enqueue)
- `scripts/eval_ragas.py`
- `tests/e2e/golden_queries.yaml` (30 query × 3 doc_type × ~5 doc)

**Demo**: UI 업로드 → 진행도 → library 표시 → chunk preview → 강제 OCR 재색인. `python scripts/eval_ragas.py` 실행.

**KPI** (PRD §24):
- citation 정확도 **≥95%**
- 검색 성공 **≥85%**
- faithfulness **≥0.95**
- p95 **<3s**

---

## 누적 일정
| MS | 누적일수 | 비고 |
|---|---|---|
| M1 | 1.5 | wiki 부분 즉시 완료, 코드 스켈레톤 0.5-1일 |
| M2 | 4.5 | ingest 가 가장 무거움 |
| M3 | 7.5 | LangGraph 첫 등장 |
| M4 | 9.5 | authority 차별점 작동 |
| M5 | 12.5 | UI + clarify 완성 |
| M6 | 14.5 | KPI 측정 + admin |

## 출처
- `docs/mvp_plan.md` § Build Order
