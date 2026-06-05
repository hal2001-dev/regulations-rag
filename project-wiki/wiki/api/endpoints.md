# API Endpoints

**상태**: active
**마지막 업데이트**: 2026-05-27 (M3 완료, M4/M5/M6 진행 중 추가)
**관련 페이지**: [../features/generation.md](../features/generation.md), [../features/retrieval.md](../features/retrieval.md)

## Base
- 개발: `http://localhost:8001` (knowledge-rag 충돌 회피로 8001)
- Web 프록시: `http://localhost:3001/api/*` → `:8001/*` (`web/next.config.ts` rewrites)

## /health (GET)
M1 부팅 검증용. `{"status":"ok","db":"ok","service":"regulations-rag","version":"0.1.0"}`.

## /ingest (POST)
큐 enqueue. M2.
```json
{"source_path": "<서버 로컬 경로>", "user_doc_type": "policy?", "force_ocr": false}
→ 202 {"job_id":N, "status":"queued", ...}
```

## /jobs (GET)
ingest 잡 상태 조회. M2.
- `GET /jobs?limit=50` 최근 N개
- `GET /jobs?ids=1,2,3` 특정 id 들

## /documents (GET)
문서 list. M2. 페이지네이션/필터는 M6.

## /query (POST)
비-스트리밍 e2e (디버깅용). M3.
```json
{"question": "연차휴가 며칠?"} 
→ {
  "session_id":"...",
  "route":"policy",
  "draft":"[결론]...[근거]...",
  "citation_valid_pct":1.0,
  "sources":[{...}, ...],
  "timings":{"retriever":0.04, "generator":5.4}
}
```

## /query/stream (POST, SSE)
M3. LangGraph astream_events → SSE.

**요청 body**:
```json
{"question":"질문 문자열", "session_id":"<선택, 없으면 새 uuid>"}
```

**응답 이벤트**:

| event | data | 발생 시점 |
|---|---|---|
| `route` | `{"route":"policy|authority|manual|faq"}` | router_node 완료 |
| `sources` | `{"sources":[{article_id, doc_id, article_no, article_title, chapter, heading_path, body(≤600자), score}, ...8개]}` | retriever_node 완료 |
| `token` | `{"token":"청크"}` | gpt-4o-mini stream 청크마다 |
| `citation` | `{"valid_pct":0.0-1.0, "valid":[true,false,...]}` | citation_validator 완료 |
| `done` | `{"route":..., "citation_valid_pct":..., "session_id":..., "timings":{...}}` | 그래프 전체 종료 |
| `error` | `{"message":"..."}` | 예외 |

**multi-turn**: 같은 `session_id` 로 재호출하면 LangGraph PostgresSaver checkpoint 가 thread_id 별로 분리.

## /query/resume (POST)
M5 clarify resume 자리. 현재 501.

## /authority (POST/GET)
M4 직접 SQL 조회 자리. 현재 placeholder.

## /admin/* (POST/GET)
M6 reindex / upload UI. 현재 placeholder.

## 출처
- `docs/mvp_plan.md` §M3 Demo + §SSE 이벤트 명세
- `apps/routers/{query,ingest,jobs,documents,authority,admin}.py`
