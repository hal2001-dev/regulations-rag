# Tech Stack

**상태**: active
**마지막 업데이트**: 2026-05-27
**관련 페이지**: [decisions.md](decisions.md), [pipeline.md](pipeline.md), [../config/dependencies.md](../config/dependencies.md)

## 요약
Python (FastAPI + LangGraph + Docling) backend + Next.js 16 (TS + Tailwind 4 + shadcn) frontend. Qdrant 단일 collection + Postgres (앱 데이터 + LangGraph checkpoint). 로컬 임베딩(bge-m3) + OpenAI gpt-4o-mini.

---

## Backend

| 영역 | 선택 | 이유 |
|---|---|---|
| Web framework | **FastAPI** + `uvicorn[standard]` | async + SSE 자연스러움, OpenAPI 자동생성 (web/types 자동) |
| Orchestration | **LangGraph** + `langgraph-checkpoint-postgres` | 조건부 edge, interrupt-based clarify, multi-turn resume (→ ADR-009) |
| LLM client | `langchain-openai` (gpt-4o-mini) | streaming 지원, JSON mode, 비용 저렴 (→ ADR-004) |
| DB ORM | `SQLAlchemy` + `psycopg[binary,pool]` | bulk insert 성능, JSONB 지원 |
| Vector store | `qdrant-client` (Qdrant) | sparse + dense 동시 지원, payload filter index, hybrid 네이티브 |
| Embedding | **bge-m3** via `fastembed` | 한국어 검증, 로컬 (PII/비용 0) (→ ADR-003) |
| Sparse | `Qdrant/bm25` + `kiwipiepy` (Kiwi) | 한국어 형태소 N/V/SL/SN 필터링 |
| Reranker | BGE-reranker-v2-m3 | top_n=5, MPS 가속 |
| PDF 파싱 | `docling` + `langchain-docling` | 표 추출 + OCR (macOS Vision lang=ko-KR) |
| Config | `pydantic-settings` | env-driven, type-safe |
| Eval | `ragas` | faithfulness, answer_relevancy, context_precision |
| SSE | `httpx-sse` (테스트 클라이언트) / FastAPI `StreamingResponse` | - |

## Frontend

| 영역 | 선택 | 이유 |
|---|---|---|
| Framework | **Next.js 16** (App Router) | RSC, streaming, /api rewrite |
| Styling | **Tailwind 4** + shadcn | 초기 속도, 디자인 토큰 |
| API client | `openapi-fetch` (자동생성) | FastAPI OpenAPI → TS 타입 |
| State | TanStack Query | SSE 친화, 캐시 |
| SSE 설정 | `next.config.ts` `compress:false` | gzip 이 SSE 버퍼링 (→ ADR/knowledge-rag ADR-038) |

## Infra

| 영역 | 선택 | 이유 |
|---|---|---|
| RDB | **Postgres** (docker) | 앱 데이터 + LangGraph checkpoint 통합 (→ ADR-010) |
| Vector store | **Qdrant** (docker) | 단일 collection, payload index (→ ADR-001) |
| Queue | Postgres `ingest_jobs` + `FOR UPDATE SKIP LOCKED` | 별도 브로커 X (운영 단순화) |
| Process model | FastAPI + indexer_worker 분리 (호스트 venv) | Docling 30-120s 차단 회피 (→ ADR-002) |
| OCR fallback | macOS Vision (Docling `OcrMacOptions`) | 무료, 한국어 양호 (→ ADR-008) |

## 디렉토리

```
regulations-rag/
├── apps/              FastAPI + indexer_worker
│   ├── main.py        lifespan, CORS, routers
│   ├── config.py      pydantic-settings
│   ├── indexer_worker.py
│   └── routers/       ingest, query, documents, authority, jobs, admin
├── packages/
│   ├── code/          logger, models
│   ├── db/            connection, models, repository
│   ├── loaders/       docling_loader
│   ├── regulation_parser/  ★ 신규 — structure, article_chunker, authority_extractor, doc_type_classifier
│   ├── rag/           ★ LangGraph — graph, state, checkpointer, nodes/, sparse, retriever, reranker
│   ├── vectorstore/   qdrant_store
│   ├── llm/           embeddings (bge-m3)
│   └── jobs/          queue
├── web/               Next.js 16 + Tailwind 4 + shadcn
│   ├── app/           layout, chat, library, admin/*
│   ├── components/    chat/*, ui/*
│   └── lib/api.ts     openapi-fetch
├── scripts/           bulk_ingest, rebuild_index, eval_ragas
├── tests/             regulation_parser/, rag/, e2e/
├── ingest/            17 PDF (원본)
├── data/              qdrant_storage, pg_data (gitignored)
├── docs/              PRD, MVP plan
├── docker-compose.yml qdrant + postgres
├── requirements.txt
└── .env.example
```

## 핵심 라이브러리 버전 (M1 시점 권장)
> **상태**: 미설치. `requirements.txt` 작성 시 최신 안정 버전 lock.

- `langgraph >=0.2`, `langgraph-checkpoint-postgres >=2`
- `langchain-core`, `langchain-openai` (LangGraph 와 호환 버전)
- `fastapi`, `uvicorn[standard]`
- `sqlalchemy >=2`, `psycopg[binary,pool] >=3`
- `qdrant-client`
- `fastembed` (bge-m3 포함)
- `kiwipiepy`
- `docling`, `langchain-docling`
- `pydantic-settings`
- `ragas`
- `httpx-sse`

## 환경 변수 (.env.example 항목)
- `OPENAI_API_KEY`
- `POSTGRES_URL` (예: `postgresql+psycopg://user:pw@localhost:5432/regulations`)
- `QDRANT_URL` (예: `http://localhost:6333`)
- `QDRANT_COLLECTION` (default `regulations`)
- `EMBEDDING_MODEL` (default `bge-m3`)
- `LLM_MODEL` (default `gpt-4o-mini`)
- `OCR_LANG` (default `ko-KR`)
- `INGEST_DIR` (default `./ingest`)

## 출처
- `docs/mvp_plan.md` § Architecture (디렉토리 레이아웃), § M1 (requirements.txt 핵심)
