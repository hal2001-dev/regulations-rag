# regulations-rag MVP 구현 계획

## Context

`/Users/hal2001/workspace/projects/personal/regulations-rag/` 는 사내 규정/매뉴얼/FAQ 를 통합 검색하는 한국어 Enterprise RAG 시스템이다. PRD(`docs/enterprise_policy_rag_prd_full.md`)는 hybrid search + 조항 단위 chunking + citation 기반 QA 를 명시한다.

현재 상태:
- `docs/enterprise_policy_rag_prd_full.md` — PRD 작성 완료
- `ingest/` — **파싱 대상 17개 PDF**(인사관리규정, 사무위임전결규정, 영업규정, 여비규정, 회계규정, 감사규정, 매뉴얼, FAQ 등)
- `project-wiki/` — 비어있음 (이번에 구축)
- 코드 없음

사용자 결정사항:
1. 형제 프로젝트 `knowledge-rag` 는 **참고만**, 새로 구현 (코드 직접 공유/모노레포 금지)
2. **Full-stack MVP**: Backend + Ingest + Next.js chat + Admin UI (PRD §22)
3. **인증 제외**(스키마에 `access_role` 필드만 placeholder)
4. **중점 영역**: 조/항 단위 정확 chunking + 계층적 citation, Authority Matrix 우선처리
5. **파싱 대상**: `./ingest/` 17개 PDF 전부
6. **project-wiki 구축**: karpathy "LLM Wiki" 패턴 (`https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f`) + knowledge-rag 의 wiki 구조 참고
7. **오케스트레이션**: **LangGraph** state machine 으로 구현 (imperative pipeline 대신)
8. **질문 구체화 (하이브리드)**:
   - 내부: HyDE/multi-query 로 retrieval 전 자동 확장 (사용자 비가시)
   - 외부: 모호하거나 정보 부족 시 `clarify` 노드에서 `interrupt()` → 사용자에게 역질문 → 답변 후 graph 재개

핵심 차별점(knowledge-rag 대비):
- 조 단위(`제N조`) + 항 단위(`①②`) 경계를 절대 안 자르는 **regulation structure parser**
- Authority Matrix 를 텍스트가 아닌 **구조화 테이블**(`authority_rules`)로 추출 → SQL 정확 조회
- Citation 포맷: `인사규정 > 제2장 > 제12조 > ②`(page 가 아닌 heading_path 기반)

---

## Architecture

### 디렉토리 레이아웃

```
regulations-rag/
├── apps/                              # FastAPI + indexer worker
│   ├── main.py                        # lifespan, CORS, routers
│   ├── config.py                      # pydantic-settings (env)
│   ├── dependencies.py
│   ├── indexer_worker.py              # FOR UPDATE SKIP LOCKED 큐 워커
│   └── routers/
│       ├── ingest.py                  # POST /ingest (enqueue)
│       ├── query.py                   # POST /query, /query/stream (SSE)
│       ├── documents.py               # GET /documents, /documents/{id}/chunks
│       ├── authority.py               # POST /authority/lookup
│       ├── jobs.py
│       └── admin.py
├── packages/
│   ├── code/{logger,models}.py
│   ├── db/{connection,models,repository}.py
│   ├── loaders/docling_loader.py
│   ├── regulation_parser/             # ★ 신규 (knowledge-rag 에 없음)
│   │   ├── structure.py               # 제N장/조/항/호/목 regex 파서
│   │   ├── article_chunker.py         # 조 단위 chunk + breadcrumb
│   │   ├── authority_extractor.py     # 위임전결 표 → authority_rules
│   │   └── doc_type_classifier.py     # 파일명 휴리스틱
│   ├── rag/                           # ★ LangGraph state machine
│   │   ├── graph.py                   # StateGraph 정의, compile, interrupt config
│   │   ├── state.py                   # QueryState TypedDict
│   │   ├── checkpointer.py            # PostgresSaver 설정
│   │   ├── nodes/
│   │   │   ├── clarifier.py           # ★ 모호성 감지 + 역질문 (interrupt)
│   │   │   ├── query_rewriter.py      # ★ HyDE / multi-query 확장
│   │   │   ├── router_node.py         # 쿼리 유형 → collection 우선순위
│   │   │   ├── retriever_node.py      # Qdrant hybrid + RRF + rerank
│   │   │   ├── authority_lookup_node.py  # ★ SQL 기반 정확 조회
│   │   │   ├── generator_node.py      # [결론]/[근거]/[절차]/[주의] 스트리밍
│   │   │   └── citation_validator.py  # ★ 근거-소스 매칭 검증
│   │   ├── retriever.py               # 하부 검색 헬퍼 (nodes/retriever_node 에서 사용)
│   │   ├── sparse.py                  # Kiwi + BM25
│   │   └── reranker.py                # BGE-reranker-v2-m3
│   ├── vectorstore/qdrant_store.py    # 단일 collection + payload filter
│   ├── llm/embeddings.py              # bge-m3 (fastembed)
│   └── jobs/queue.py
├── web/                               # Next.js 16 + Tailwind 4 + Shadcn
│   ├── next.config.ts                 # compress:false + /api/* rewrite
│   ├── app/
│   │   ├── layout.tsx, page.tsx       # / → /chat 리디렉션
│   │   ├── chat/page.tsx              # SSE streaming
│   │   ├── library/page.tsx           # taxonomy 필터
│   │   └── admin/{page,upload,documents/[id],taxonomy}/page.tsx
│   ├── components/chat/{chat-stream,answer-blocks,citation-chip}.tsx
│   ├── components/ui/                 # shadcn
│   └── lib/api.ts, types/api.ts       # openapi-fetch 자동생성
├── project-wiki/                      # ★ karpathy LLM Wiki 패턴
│   ├── CLAUDE.md                      # 스키마 + Operations (세션 시작 시 읽음)
│   ├── raw/                           # 원본 (수정 금지)
│   │   ├── requirements/              # PRD 사본
│   │   ├── research/                  # karpathy gist, 참고 자료
│   │   ├── meetings/, issues/, reviews/, data/
│   └── wiki/                          # LLM 이 관리하는 페이지
│       ├── index.md                   # 전체 카탈로그
│       ├── log.md                     # append-only 작업 이력
│       ├── overview.md                # 현재 상태
│       ├── roadmap.md                 # 마일스톤
│       ├── glossary.md                # 용어 (조/항/호/목, 위임전결, hybrid search, RRF 등)
│       ├── references.md              # karpathy gist, knowledge-rag ADR 링크
│       ├── architecture/
│       │   ├── decisions.md           # ADR(단일 collection, indexer worker 분리 등)
│       │   ├── pipeline.md            # ingest/query flow
│       │   └── stack.md               # 기술 스택 + 선택 이유
│       ├── features/
│       │   ├── ingestion.md, embedding.md
│       │   ├── retrieval.md, generation.md
│       │   ├── authority_matrix.md    # ★ 규정 도메인 특화
│       │   ├── citation.md            # ★ 계층 citation 정책
│       │   └── evaluation.md          # Ragas + 실험 누적
│       ├── data/{spec,pipeline,quality}.md  # 17개 PDF 스펙
│       ├── api/endpoints.md
│       ├── testing/{strategy,cases}.md
│       ├── deployment/{runbook,monitoring}.md
│       ├── onboarding/setup.md
│       ├── troubleshooting/common.md
│       ├── meetings/, issues/{open,resolved}/, reviews/
│       └── changelog.md, security.md
├── scripts/{bulk_ingest,rebuild_index,eval_ragas}.py
├── tests/
│   ├── regulation_parser/{test_structure,test_authority_extractor}.py
│   ├── rag/{test_router,test_citation_validator,test_authority_lookup}.py
│   └── e2e/{golden_queries.yaml,test_query_eval.py}
├── ingest/                            # ★ 17 PDF (기존)
├── data/                              # qdrant_storage, pg_data (gitignored)
├── docs/enterprise_policy_rag_prd_full.md
├── docker-compose.yml                 # qdrant + postgres
├── requirements.txt, .env.example
```

### 프로세스 모델
- Terminal 1: `uvicorn apps.main:app --port 8000` — 큐 enqueue 만
- Terminal 2: `python -m apps.indexer_worker` — Docling/embed/upsert 무거운 작업
- Docker: Qdrant + Postgres 만 (앱은 호스트 venv)
- 이유: Docling 파싱이 PDF 당 30–120s, FastAPI event loop 막으면 안 됨

---

## Data Model (PostgreSQL)

### `documents`
`doc_id`(PK), `title`, `source_path`, `file_type`, `content_hash`(sha256 unique, dedup), `doc_type`(CHECK in policy/authority_matrix/manual/faq/notice/guideline/template), `domain`, `process`, `version`, `effective_date`, `status`, `access_role`(default `'all'`, 미사용), `chunk_count`, `indexed_at`, `extraction_quality`(ok/partial/scan_only).

### `articles` — 조 단위 citation 의 source of truth
`id`(PK), `doc_id`(FK), `chapter`, `section`, `article_no`(text, `제2조의2` 대응), `article_title`, `paragraph`(①②), `item`(가/나/1./), `body`, `heading_path`(JSONB), `qdrant_point_id`, `page`, `content_type`.
Index: `(doc_id, article_no, paragraph)`, GIN on `heading_path`.
Qdrant payload 는 `article_id` 만 들고, citation 렌더 시 Postgres 에서 재조회 → 일관성 보장.

### `authority_rules` — Authority Matrix 구조화
`id`(PK), `doc_id`(FK), `article_id`(FK nullable), `process`(discount_approval/contract/expense_claim/...), `task`, `approval_role`, `approval_limit_pct`, `amount_limit_krw`, `condition`, `raw_row`(JSONB), `source_page`.
Index: `(process)`, `(approval_role)`, `(amount_limit_krw)`.
**핵심**: "할인 30% 누가 승인?" → `WHERE process='discount_approval' AND approval_limit_pct >= 30` SQL 직접 조회. LLM 은 결과 5행을 포맷만 함 → 한도 hallucination 차단.

### 그 외
`ingest_jobs`(knowledge-rag 스키마 + `user_doc_type`, `force_ocr`), `conversations`/`messages`(`user_id` 없이 `session_id` 만), `taxonomy_config`(admin 에서 domain/process enum 편집).

### LangGraph checkpoint 테이블
`langgraph.checkpoints` 등은 **PostgresSaver 가 자체 마이그레이션**으로 생성 (`checkpointer.setup()` 1회 호출). 우리 ORM 모델에는 포함하지 않음. `thread_id = session_id` 로 묶어 multi-turn 재개 + clarify interrupt resume 지원.

---

## Ingestion Pipeline

1. **doc_type 분류**(파일명 휴리스틱): `위임전결|직무권한` → authority_matrix, `매뉴얼|가이드` → manual, `100문` → faq, else `policy`.
2. **Docling 파싱**: 1차 OCR off, 텍스트 <500 chars/5+페이지 → macOS Vision OCR(`OcrMacOptions(lang=['ko-KR'])`) 재시도, `extraction_quality='scan_only'` 마킹.
3. **regulation_parser/structure.py** regex (`packages/regulation_parser/structure.py`):
   ```
   CHAPTER  = r"^제\s*\d+\s*장\s+(.+)$"
   SECTION  = r"^제\s*\d+\s*절\s+(.+)$"
   ARTICLE  = r"^제\s*\d+\s*조(?:의\d+)?\s*(?:\(([^)]+)\))?"
   PARA     = r"^[①-⑳]"
   ITEM_NUM = r"^\d+\.\s"
   ITEM_KOR = r"^[가-힣]\.\s"
   APPENDIX = r"^별표\s*\d+|^별지\s*\d+"
   ```
   → Chapter→Section→Article→Paragraph→Item 트리, leaf 가 `articles` row.
4. **article_chunker.py**: 1 chunk = 1 `제N조` 기본, >800 token 이면 `①②③` 단위 분할, breadcrumb (`{doc_title} > {chapter} > {article_no} {title}`) 본문 앞에 prepend → BM25 recall + self-contained.
5. **authority_extractor.py**(`doc_type=authority_matrix` 만): Docling 표 markdown → 헤더 행 매칭(`업무|구분|항목` × `결재권자|승인자|전결권자` × `한도|금액|비율`) → 데이터 행 1개 = `authority_rules` 1행. 금액 정규화(`(\d[\d,]*)\s*(만원|억원|원)`), %(`(\d+(?:\.\d+)?)\s*%`), process 는 12-keyword 맵으로 inference. 동일 row 를 fuzzy fallback 용 chunk 로도 Qdrant 에 적재.
6. **임베딩 + 저장**: bge-m3 dense + Kiwi-BM25 sparse → Qdrant. SQLAlchemy bulk insert articles + authority_rules → Postgres. 문서 1개 = 1 transaction. `content_hash` dedup.

### 17개 PDF 분류(파싱 대상)
| File | doc_type |
|---|---|
| 사무위임전결규정.pdf | **authority_matrix** |
| 신천초 위임전결규정 제 4차 개정(20190308)-1.pdf | **authority_matrix** |
| 계약심사및기술심의업무처리시행내규_20260514.pdf | policy (내부 표 추출) |
| 31._회계규정_20191128.pdf, 내부회계관리규정.pdf, 인사관리규정.pdf, 영업규정.pdf, 여비규정.pdf, 감사규정.pdf, 경비업무규정.pdf, 상임이사및감사보수규정.pdf, 이사회내위원회운영규정.pdf | policy |
| 국립중앙도서관 규정집_2019.pdf | policy (다규정 모음) |
| 자치법규업무매뉴얼(2022년판)행정안전부.pdf, 건설공사 안전관리 매뉴얼(2024).pdf, 교육활동 보호 매뉴얼.pdf | manual |
| 공무원여비100문100답.pdf | **faq** |

---

## Retrieval / QA — LangGraph State Machine

### 그래프 구조

```
            START
              │
              ▼
       ┌────────────┐
       │ ingest_query│ (정규화, history attach)
       └─────┬──────┘
             │
             ▼
       ┌────────────┐
       │  clarifier │ (LLM small call: ambiguous? slot 부족?)
       └─────┬──────┘
             │
       needs_clarification ?
       ┌──────┴───────┐
       │ yes          │ no
       ▼              ▼
  ┌─────────┐   ┌──────────────┐
  │ INTERRUPT│   │query_rewriter│ (HyDE / multi-query)
  │ → 역질문 │   └──────┬───────┘
  │   END   │          │
  └─────────┘          ▼
   (user reply →   ┌────────┐
    resume from    │ router │ (regex → authority/policy/manual/faq)
    ingest_query)  └───┬────┘
                       │
              route == "authority" ?
              ┌────────┴────────┐
              │ yes             │ no
              ▼                 ▼
      ┌───────────────┐   ┌──────────┐
      │ authority_    │   │retriever │ (Qdrant hybrid + RRF + rerank)
      │ lookup (SQL)  │   └────┬─────┘
      └───────┬───────┘        │
              │                │
              └────────┬───────┘
                       ▼
                 ┌──────────┐
                 │ generator│ (LLM stream → [결론][근거][절차][주의])
                 └────┬─────┘
                      ▼
                 ┌──────────────────┐
                 │citation_validator│
                 └────┬─────────────┘
                      ▼
                    END
```

### State (`packages/rag/state.py`)

```python
class QueryState(TypedDict, total=False):
    session_id: str
    original_query: str
    history: list[dict]                # 직전 대화 (multi-turn)
    clarifications: list[dict]          # [{q, a, asked_at}]
    needs_clarification: bool
    clarify_question: str | None
    rewritten_queries: list[str]        # HyDE 산출
    route: Literal["authority","policy","manual","faq","notice"]
    candidates: list[ScoredChunk]
    authority_rows: list[AuthorityRule]
    answer: str
    sources: list[Citation]
    citation_valid_pct: float
    warnings: list[str]
```

### Vector store — 1 collection + payload filter
17 문서 ~3000 chunk 규모에서 payload-indexed filter O(log n) 는 5 collection 분리와 동일 성능. 운영 부담 1/5. PRD §11 의 5 collection 은 strategy hint 로 해석. payload_indexes: `doc_id, doc_type, domain, process, article_no`.

### 노드별 책임

**1. `clarifier`** (`nodes/clarifier.py`)
- gpt-4o-mini 1회 호출, 시스템 프롬프트로 다음 4가지 ambiguity 패턴 체크:
  - **대상 모호**: "그 규정"(어느 규정?), 유사 명칭 다수("회계규정" vs "내부회계관리규정")
  - **Authority slot 부족**: 승인 질문인데 process 또는 amount/% 미명시 ("계약 누가 승인?" → 금액 범위 필요)
  - **시점 모호**: "최신 규정", "현재 시행 중인 것" (effective_date 명시 필요한 경우)
  - **범위 광범**: "휴가 알려줘"(연차/공가/병가 중 어떤?)
- 출력 schema: `{needs: bool, question: str|null, suggested_replies: list[str]}` (Quick reply chip 용)
- `needs=true` 시 그래프 `interrupt()` → FastAPI 가 SSE `clarify` 이벤트 송출 → END. 사용자 응답이 `POST /query/resume` 으로 들어오면 PostgresSaver checkpoint 에서 `ingest_query` 로 재진입 (응답을 `clarifications` 에 누적).
- 무한 루프 방지: `len(clarifications) >= 2` 면 강제 통과 (UX 가드).

**2. `query_rewriter`** (`nodes/query_rewriter.py`)
- 항상 실행, 사용자 비가시
- HyDE: "이 질문에 대한 가상의 규정 조항을 1-2문장으로 작성하라" → 그 텍스트를 추가 쿼리로 사용 (한국어 규정 어휘 활성화)
- Multi-query: 의도가 복합("승인 절차와 한도")이면 2-3개로 분해
- 출력: `rewritten_queries: [original, hyde_text, ...]` 모두 retriever 에 전달, RRF 로 융합

**3. `router_node`** — keyword-first
```python
RULES = [
  (r"누가\s*승인|결재권자|전결|승인\s*권한|한도|얼마까지", "authority"),
  (r"어떻게|절차|방법|단계|매뉴얼", "manual"),
  (r"가능|할\s*수\s*있|허용|되나요", "policy"),
  (r"FAQ|사례|예시|문답", "faq"),
  (r"공지|한시|임시", "notice"),
]
```
규제 무매칭 + 쿼리 >12 chars 시에만 LLM router fallback (비용 가드). `state.route` 에 1순위 저장. retriever 가 hits<2 or rerank<0.4 면 filter 해제 재검색 (LangGraph 조건부 edge 가 아닌 노드 내부 fallback).

**4. `retriever_node`**
- Dense: bge-m3 (cosine), Sparse: Qdrant `Qdrant/bm25` + Kiwi N/V/SL/SN 형태소
- `rewritten_queries` 각각 hybrid 검색 → 결과를 RRF 융합
- BGE-reranker-v2-m3 top_n=5
- payload filter: `doc_type = state.route`

**5. `authority_lookup_node`** (조건부 진입: `route == "authority"`)
```python
parsed = parse_authority_question(q + clarifications)
rows = db.query(AuthorityRule).filter(
    process == parsed.process,
    approval_limit_pct >= parsed.threshold_pct,
    amount_limit_krw >= parsed.amount_krw,
).order_by(approval_limit_pct).limit(5)
```
0 rows → `nodes/retriever_node` 로 우회 (authority Qdrant 청크 fallback) + warning 적재.

**6. `generator_node`** — streaming
- gpt-4o-mini, `astream` 토큰 방출 → FastAPI 가 SSE `token` 이벤트로 전달
- Prompt 는 `[결론]/[근거]/[적용 조건]/[절차]/[주의]` 블록 포맷 강제
- Authority 경로일 때는 `authority_rows` 만 컨텍스트로 받아 한도/% 그대로 인용하도록 제약

**7. `citation_validator`**
- `[근거]` 블록의 `(doc_id, article_no)` 추출 → `state.sources` 매칭 확인
- 미매칭 `[결론]` 문장 → "근거 없음" 푸터 부착 (MVP 는 redaction 대신 경고로 측정 우선)
- `state.citation_valid_pct` 산출 → `query_logs` 적재

### Latency budget (PRD §19, 3s 종단)
| Stage | Budget |
|---|---|
| ingest_query / router (regex) | <10ms |
| clarifier (gpt-4o-mini, JSON mode) | ~300ms (clear 통과 시) |
| query_rewriter (HyDE, mini) | ~250ms |
| retriever (hybrid k=20) | ~150ms |
| reranker (BGE-v2-m3, MPS) | ~400ms |
| generator (stream, first token) | ~600ms |
| citation_validator | ~50ms |
| **종단(first token)** | **~1.5s**, 전체 답변 <3s |

### Checkpointing
- `PostgresSaver.from_conn_string(POSTGRES_URL)` 1개 인스턴스, `graph.compile(checkpointer=saver, interrupt_before=["clarifier_interrupt"])`.
- `thread_id = session_id` (대화별 격리)
- 사용 시점:
  1. clarify interrupt → END 후 사용자 응답으로 resume
  2. 동일 session 의 후속 질문에서 직전 sources/clarifications 참조

---

## Frontend (Next.js + Shadcn)

### SSE 이벤트 타입 (LangGraph 다중 노드 출력)
```
event: route        data: {"route":"authority"}                # router_node 결과
event: clarify      data: {"question":"...", "suggested_replies":["...","..."]}
event: token        data: {"text":"…"}                          # generator 스트리밍
event: sources      data: {"citations":[{doc_id,article_no,heading_path,score},...]}
event: warning      data: {"message":"근거 없음 결론 1건"}
event: done         data: {"citation_valid_pct":0.94}
```

### Pages
- `/chat`: TanStack Query → `POST /api/query/stream` SSE
  - `clarify` 수신 시 답변 영역에 질문 버블 + `<QuickReplyChips>` 렌더 (사용자 클릭 또는 자유 입력)
  - 응답 후 `POST /api/query/resume` (session_id + answer) → graph resume → 다시 토큰 스트리밍
  - `route` 이벤트로 UI 상단에 "Authority Matrix 조회 중..." 같은 상태 표시
  - `token` 누적 → client-side regex(`^\[(결론|근거|적용 조건|절차|주의)\]$`)로 블록 분리 → `<AnswerBlocks>` 컬러 카드 + `<CitationChip>`(`인사규정 > 제2장 > 제12조 > ②`, 클릭 → `/library/documents/{id}?article=N`)
- `/library`: `GET /documents` 페이지네이션, `doc_type/domain/process/status` 필터, 행 클릭 → article 리스트 drawer.
- `/admin/upload`: 다파일 드롭존, `doc_type`/`domain` override → `POST /ingest`(multipart).
- `/admin/documents/[id]`: chunk preview, "Reindex" → `POST /admin/reindex/{doc_id}`.
- `/admin/taxonomy`: domain/process enum 편집(`taxonomy_config` table).
- `/admin/graph-traces` (선택): LangGraph 노드별 latency/입출력 디버그 뷰 (M6 에 포함).

### Components 추가
- `<QuickReplyChips replies={...}>` — clarify 응답 chip
- `<NodeProgress route={...}>` — 현재 실행 중인 노드 표시
- 기존 `<AnswerBlocks>`, `<CitationChip>` 유지

### SSE 주의
`next.config.ts` 에 `compress: false` 필수 (gzip 이 SSE 버퍼링 → knowledge-rag ADR-038).

---

## Project Wiki (karpathy LLM Wiki 패턴)

### 구축 시점: M1 (스켈레톤과 동시)
karpathy 패턴 3-layer: **raw/** (immutable 원본) / **wiki/** (LLM 관리) / **CLAUDE.md** (스키마). knowledge-rag 의 `project-wiki/CLAUDE.md` 구조를 그대로 가져오되 RAG 도메인 페이지(`features/authority_matrix.md`, `features/citation.md`) 추가.

### 세션 시작 루틴 (`project-wiki/CLAUDE.md` 에 명시)
1. `project-wiki/CLAUDE.md` 읽기
2. `wiki/log.md` 최근 5개 항목
3. `wiki/issues/open/` 확인
4. `wiki/overview.md` 현재 상태
5. 사용자 브리핑 후 작업

### Operations (wiki/CLAUDE.md 에서 정의)
- **Ingest** (새 정보): raw/ 저장 → 관련 wiki 페이지 갱신 → `index.md` 갱신 → `log.md` append → `overview.md` 진행상황
- **Query** (질문 응답): `index.md` → 관련 페이지 → 답변 + 출처. 새 인사이트는 wiki 페이지로 저장 제안
- **Lint** ("wiki lint 해줘"): open issue 실제 해결 여부 / overview 최신성 / decisions 구현 일치 / 깨진 링크 / orphan 페이지 / roadmap 지연 / dependencies 버전 / glossary 누락 용어 등 체크리스트

### 초기 채워야 할 페이지 (M1 종료 시점)
- `raw/requirements/PRD.md` ← PRD 사본
- `raw/research/karpathy-llm-wiki.md` ← gist 요약
- `wiki/overview.md` ← 본 plan 요약
- `wiki/roadmap.md` ← M1~M6 마일스톤
- `wiki/architecture/{decisions,pipeline,stack}.md` ← 단일 collection, indexer 분리, bge-m3 결정 등 ADR 첫 글
- `wiki/glossary.md` ← 조/항/호/목, 위임전결, hybrid search, RRF, BM25, breadcrumb 용어
- `wiki/data/spec.md` ← 17 PDF 분류표
- `wiki/features/{authority_matrix,citation}.md` ← 차별점 설명

이후 M2~M6 진행 시 각 단계 결정/실험을 wiki 에 누적.

---

## Build Order — 6 Milestones

### M1 — Skeleton + Wiki (1.5 일)
**Build**: `docker-compose.yml`(qdrant+postgres), `apps/main.py` `/health`, `apps/config.py`, 빈 routers, `packages/db/models.py` 전 테이블 + lifespan `create_all`, `web/` shadcn init + `/chat` placeholder, `.env.example`, **project-wiki/ 전체 스캐폴드 (CLAUDE.md + raw/ + wiki/ 초기 페이지 8개)**.
`requirements.txt` 핵심: `langgraph`, `langgraph-checkpoint-postgres`, `langchain-core`, `langchain-openai`, `fastapi`, `uvicorn[standard]`, `sqlalchemy`, `psycopg[binary,pool]`, `qdrant-client`, `fastembed`, `kiwipiepy`, `docling`, `langchain-docling`, `pydantic-settings`, `ragas`, `httpx-sse`.
**Demo**: `docker compose up` → `curl :8000/health` → `localhost:3000` shell. `cat project-wiki/wiki/overview.md` 가 PRD 요약 표시.
**KPI**: 두 프로세스 클린 부팅, Postgres 전 테이블 생성, wiki 초기 페이지 8개 작성 완료.

### M2 — Ingest + Structure Parser (3 일)
**Build**: `packages/loaders/docling_loader.py`, `packages/regulation_parser/{structure,article_chunker,doc_type_classifier}.py`, `apps/indexer_worker.py`, `apps/routers/ingest.py`, `scripts/bulk_ingest.py`.
**Demo**: `python scripts/bulk_ingest.py ingest/*.pdf` → 17 job enqueue → worker drain → `SELECT doc_id, doc_type, chunk_count FROM documents` 17행. wiki 에 `features/ingestion.md` + `data/spec.md` 갱신.
**KPI**: 17/17 인덱싱, `articles.article_no` non-null ≥14/17, 무작위 10 article 의 `heading_path` 수동 검증 통과.

### M3 — LangGraph Skeleton + Retrieval + Generator (3 일)
**Build**:
- `packages/rag/state.py` (QueryState TypedDict)
- `packages/rag/checkpointer.py` (PostgresSaver)
- `packages/rag/nodes/{router_node,retriever_node,generator_node,citation_validator}.py`
- `packages/rag/{sparse,retriever,reranker}.py` 헬퍼
- `packages/rag/graph.py` (clarifier/rewriter 자리는 pass-through 더미)
- `apps/routers/query.py` SSE (`token`/`sources`/`done` 이벤트만 우선)
- `packages/vectorstore/qdrant_store.py`

**Demo**: `curl -N -X POST :8000/query/stream -d '{"question":"연차휴가 어떻게 신청하나요?"}'` → SSE 토큰 + `sources` + `done`. LangGraph checkpoint Postgres 테이블 자동 생성 확인. wiki `architecture/pipeline.md` 그래프 다이어그램 + `features/retrieval.md`.
**KPI**: 10 골든 policy 쿼리 중 top-1 정답 doc_id 8/10, citation validator `[근거]` 90%+ 통과, 첫 토큰 <1s.

### M4 — Authority Lookup Node + Conditional Edge (2 일)
**Build**: `packages/regulation_parser/authority_extractor.py`, `packages/rag/nodes/authority_lookup_node.py`, `graph.py` 에 `route=="authority"` 조건부 edge, `apps/routers/authority.py`(REST 직접 조회용), 위임전결 2건 재인덱싱.
**Demo**: `curl :8000/query/stream -d '{"question":"할인 30% 누가 승인?"}'` → `event: route data:{"route":"authority"}` → SQL 1-3행 → 토큰 스트리밍 "영업본부장 — 한도 30%/5천만원, 근거: 사무위임전결규정 제N조". wiki `features/authority_matrix.md`.
**KPI**: 5개 authority 쿼리에서 role/limit exact match, router accuracy ≥13/15.

### M5 — Clarifier + Query Rewriter + Chat UI Multi-turn (3 일)
**Build**:
- `packages/rag/nodes/{clarifier,query_rewriter}.py` (실제 구현으로 교체)
- `graph.py` 에 `clarifier` interrupt config (`interrupt_before=["clarify_pause"]`)
- `apps/routers/query.py` `clarify` 이벤트 송출 + `POST /query/resume` 엔드포인트
- `web/app/chat/page.tsx`, `components/chat/{chat-stream,answer-blocks,citation-chip,quick-reply-chips,node-progress}.tsx`
- `web/lib/api.ts` (resume 클라이언트)
- `web/next.config.ts compress:false`

**Demo**: 브라우저 `/chat` 에 "그 규정 알려줘" 입력 → clarify question + chip 표시 → "회계규정" chip 클릭 → 그래프 resume → 토큰 스트리밍 + citation. HyDE 효과 측정: 동일 쿼리에서 rewriter on/off 시 hit@3 차이 wiki `features/evaluation.md` 기록.
**KPI**: 첫 토큰 <1s, 종단 <3s. 모호한 10개 쿼리 중 적절한 clarify 발동 ≥8/10. clarify 후 resume 정상 동작 100%.

### M6 — Admin UI + Reindex + Ragas Eval (2 일)
**Build**: `web/app/admin/*`, `apps/routers/admin.py`(reindex = Qdrant chunk drop + 재 enqueue), `web/app/library/page.tsx`, `scripts/eval_ragas.py`, `tests/e2e/golden_queries.yaml`(30 query × 3 doc_type × ~5 doc).
**Demo**: UI 업로드 → 진행도 → library 표시 → chunk preview → 강제 OCR 재색인. `python scripts/eval_ragas.py` 실행.
**KPI** (PRD §24): citation 정확도 ≥95%, 검색 성공 ≥85%, faithfulness ≥0.95 (hallucination ≤5%), p95 <3s. wiki `features/evaluation.md` 결과 누적.

---

## 핵심 결정 (decisions.md 첫 항목들)

| 결정 | 선택 | 이유 |
|---|---|---|
| Vector store 분리 | 단일 collection + payload filter | 17 문서 규모에서 분리 이득 없음, 운영 단순화 |
| Indexer 분리 | 별도 프로세스 (knowledge-rag ADR-028) | Docling 30-120s 가 FastAPI 막음 |
| Embedding | bge-m3 (fastembed 로컬) | 한국어 검증, API 비용 0, PII 우려 0 |
| LLM | gpt-4o-mini (streaming) | 인용 + 포맷 위주 task 에 충분, $0.02/일 수준 |
| Authority 저장 | Postgres 구조화 테이블 (+ Qdrant fallback) | SQL exact 조회로 한도/% hallucination 차단 |
| Chunking | 조 단위 + 800 token 초과 시 항 분할 | 인용 단위와 chunk 경계 일치 |
| Citation 단위 | heading_path 기반 (page 아님) | 사용자가 조항을 직접 인용 가능 |
| OCR | Docling 1차 → macOS Vision (lang=ko-KR) | 무료, 한국어 양호. 별표/스캔표 fallback 만 필요 |
| Orchestration | **LangGraph state machine** | 조건부 edge(authority vs vector path), interrupt-based 사용자 clarify, multi-turn resume 이 imperative pipeline 대비 자연스러움 |
| Checkpointer | **PostgresSaver** (이미 Postgres 사용 중) | 별도 인프라 불필요, `thread_id=session_id` 로 대화 격리 |
| 질문 구체화 | **하이브리드** (HyDE 내부 + clarify 노드 외부) | 명확 질문은 사용자 방해 없이 retrieval 품질↑, 모호 질문만 역질문 → KPI(검색 성공률 85%) 달성 핵심 |
| Clarify 발동 조건 | 4 패턴 (대상 모호 / authority slot 부족 / 시점 모호 / 범위 광범) | 무차별 clarify 는 UX 마찰. 4 패턴으로 좁혀 false-positive 최소화 |
| Clarify 무한 루프 | `len(clarifications) >= 2` 시 강제 통과 | UX 가드 |

---

## Risks & Open Questions

| 항목 | MVP 처리 |
|---|---|
| `제2조의2`(삽입조) | regex `제\d+조(?:의\d+)?` 처리 ✓ |
| `가목/나목/다목` | `ITEM_KOR` regex ✓ |
| `①-⑳` 항 마커 | regex ✓ |
| 별표/별지/부칙 | article 로 저장(`article_no='별표 N'`), 표는 Docling 추출. 부칙 → `effective_date` heuristic |
| 교차참조(`제5조 제2항 참조`) | 텍스트만 저장, 그래프 해석 defer |
| 스캔 authority 표 | OCR fallback → 0 rows 시 `confidence='low'` + admin 배너 + CSV 업로드 escape hatch(`POST /admin/authority_rules/{doc_id}/csv`) |
| Citation 95% 측정 | `tests/e2e/golden_queries.yaml` 30 쌍 × `eval_ragas.py` 의 `citation_exact_match` 메트릭 |
| Clarify false-positive | clarifier 출력에 `confidence` 점수 → 0.6 미만이면 통과. 골든셋에 명확/모호 쌍 30개 두고 precision/recall 측정 |
| LangGraph checkpoint 누적 | `langgraph.checkpoints` 테이블 무한 증가 가능. M6 에 `DELETE FROM ... WHERE created_at < NOW() - INTERVAL '30 days'` 일일 cron (또는 launchd) |
| Streaming + interrupt 동시 처리 | LangGraph `astream_events` 사용 → token 이벤트와 interrupt 이벤트가 같은 stream 으로 들어옴 → FastAPI 가 type 분기해 SSE 다른 event 이름으로 송출 |
| Resume thread 충돌 | 동일 `session_id` 로 동시 요청 시 checkpoint race. M5 에서 `POST /query/stream` 시 `SELECT ... FOR UPDATE` advisory lock 또는 큐잉. MVP 는 한 탭 가정. |

---

## Verification (E2E)

```bash
# 1. Up
docker compose up -d
uvicorn apps.main:app --port 8000 &
python -m apps.indexer_worker &

# 2. Bulk ingest
python scripts/bulk_ingest.py ingest/*.pdf
# wait SELECT count(*) FROM ingest_jobs WHERE status='done' = 17

# 3. 10 representative queries (tests/e2e/golden_queries.yaml)
```

| # | 질문 | Routed | Expected citation |
|---|---|---|---|
| 1 | 연차휴가 며칠까지 쓸 수 있나요? | policy | 인사관리규정 > 제N조 |
| 2 | 출장 여비 일당 한도는? | policy | 여비규정 > 제N조 |
| 3 | 공무원 여비 100문답 식비 정산 사례 | faq | 공무원여비100문100답 > 문 N |
| 4 | 할인 30% 누가 승인하나요? | authority | `authority_rules`: discount_approval ≥30 |
| 5 | 5천만원 계약은 누가 결재? | authority | `authority_rules`: amount≥50000000 |
| 6 | 건설공사 안전관리 점검 절차 | manual | 안전관리 매뉴얼 > 장 > 절 |
| 7 | 교육활동 침해 시 대응 방법 | manual | 교육활동 보호 매뉴얼 > 장 > 절 |
| 8 | 내부회계관리규정 제5조 내용 | policy | 내부회계관리규정 > 제5조 (exact) |
| 9 | 감사 대상은 누구인가? | policy | 감사규정 > 제N조 |
| 10 | 이사회 위원회 종류 | policy | 이사회내위원회운영규정 > 제N조 |

Pass 기준: router 정확, top-1 doc_id 일치, 4·5번은 role+amount exact match. Ragas faithfulness ≥0.95 / answer_relevancy ≥0.85 / context_precision ≥0.80 / citation_exact_match ≥0.95. p95 latency ≤3s.

---

## Critical Files (구현 시 핵심)
- `packages/regulation_parser/structure.py` — 조/항/호/목 파싱의 핵심
- `packages/regulation_parser/authority_extractor.py` — Authority Matrix 추출
- `packages/db/models.py` — `articles` + `authority_rules` 스키마
- `packages/rag/graph.py` — LangGraph 정의 + interrupt 설정 (전체 흐름)
- `packages/rag/state.py` — QueryState TypedDict (모든 노드 공유)
- `packages/rag/checkpointer.py` — PostgresSaver (multi-turn resume 의 기반)
- `packages/rag/nodes/clarifier.py` — 4 패턴 ambiguity 감지 (검색 성공률 KPI 핵심)
- `packages/rag/nodes/query_rewriter.py` — HyDE / multi-query (내부 retrieval 품질)
- `packages/rag/nodes/authority_lookup_node.py` — SQL exact 조회
- `packages/rag/nodes/citation_validator.py` — 95% citation 정확도 핵심
- `apps/routers/query.py` — SSE 이벤트 분기 (token/clarify/route/sources/done)
- `project-wiki/CLAUDE.md` — 세션 시작 루틴 + Operations 정의
- `web/next.config.ts` — `compress: false` SSE gotcha
- `web/app/chat/page.tsx` + `components/chat/quick-reply-chips.tsx` — clarify resume UX
- `tests/e2e/golden_queries.yaml` — KPI 측정의 단일 source of truth (clarify 명확/모호 쌍 포함)
