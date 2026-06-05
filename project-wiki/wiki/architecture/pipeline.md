# Pipelines (Ingest + Query)

**상태**: active
**마지막 업데이트**: 2026-05-27
**관련 페이지**: [decisions.md](decisions.md), [stack.md](stack.md), [../features/authority_matrix.md](../features/authority_matrix.md)

## 요약
두 개의 파이프라인.
- **Ingest 파이프라인**: PDF → Docling → regulation_parser → 임베딩 → Qdrant + Postgres. 별도 워커 프로세스.
- **Query 파이프라인**: LangGraph state machine. 7개 노드 + 조건부 edge + interrupt.

---

## Ingest 파이프라인

```
PDF
 │
 ▼
[doc_type 분류]                ← 파일명 휴리스틱
 │  위임전결|직무권한 → authority_matrix
 │  매뉴얼|가이드     → manual
 │  100문            → faq
 │  else             → policy
 ▼
[Docling 파싱]                 ← 1차 OCR off
 │  텍스트 <500 chars / 5+페이지
 │  → OcrMacOptions(lang=['ko-KR']) 재시도
 │  → extraction_quality='scan_only' 마킹
 ▼
[regulation_parser/structure.py]
 │  regex:
 │   CHAPTER = ^제\d+장\s+(.+)
 │   SECTION = ^제\d+절\s+(.+)
 │   ARTICLE = ^제\d+조(?:의\d+)?\s*(?:\(([^)]+)\))?
 │   PARA    = ^[①-⑳]
 │   ITEM_NUM= ^\d+\.\s
 │   ITEM_KOR= ^[가-힣]\.\s
 │   APPENDIX= ^별표\s*\d+|^별지\s*\d+
 │  → Chapter→Section→Article→Paragraph→Item 트리
 │  leaf = articles row
 ▼
[article_chunker.py]
 │  1 chunk = 1 제N조
 │  >800 token → ①②③ 단위 분할
 │  breadcrumb 본문 앞 prepend
 ▼
[authority_extractor.py]       ← doc_type=authority_matrix 만
 │  Docling 표 markdown → 헤더 매칭
 │  헤더: (업무|구분|항목) × (결재권자|승인자|전결권자) × (한도|금액|비율)
 │  금액 정규화 (\d[\d,]*)\s*(만원|억원|원)
 │  % 정규화 (\d+(?:\.\d+)?)\s*%
 │  process: 12-keyword 맵 inference
 │  → authority_rules row + Qdrant fallback chunk
 ▼
[임베딩 + 저장]
 │  bge-m3 dense (fastembed)
 │  Kiwi-BM25 sparse
 │  → Qdrant upsert
 │  SQLAlchemy bulk insert: articles + authority_rules
 │  1 문서 = 1 transaction
 │  content_hash dedup
 ▼
documents 테이블 chunk_count, indexed_at, extraction_quality 갱신
```

**프로세스 모델**
- Terminal 1: `uvicorn apps.main:app --port 8000` — 큐 enqueue 만
- Terminal 2: `python -m apps.indexer_worker` — Docling/embed/upsert 무거운 작업
- Docker: Qdrant + Postgres
- 이유: Docling 30-120s/PDF, FastAPI event loop 막으면 안 됨 (→ [decisions.md](decisions.md) ADR-002)

---

## Query 파이프라인 (LangGraph State Machine)

### 그래프

```
            START
              │
              ▼
       ┌────────────┐
       │ ingest_query│ 정규화, history attach
       └─────┬──────┘
             │
             ▼
       ┌────────────┐
       │  clarifier │ LLM small call
       └─────┬──────┘
             │
       needs_clarification ?
       ┌──────┴───────┐
       │ yes          │ no
       ▼              ▼
  ┌─────────┐   ┌──────────────┐
  │INTERRUPT│   │query_rewriter│ HyDE / multi-query
  │ 역질문  │   └──────┬───────┘
  │   END   │          │
  └─────────┘          ▼
   (resume →      ┌────────┐
    ingest_query) │ router │ regex → authority/policy/manual/faq
                  └───┬────┘
                      │
              route == "authority" ?
              ┌────────┴────────┐
              │ yes             │ no
              ▼                 ▼
      ┌───────────────┐   ┌──────────┐
      │ authority_    │   │retriever │ Qdrant hybrid + RRF + rerank
      │ lookup (SQL)  │   └────┬─────┘
      └───────┬───────┘        │
              │                │
              └────────┬───────┘
                       ▼
                 ┌──────────┐
                 │ generator│ LLM stream → [결론][근거][절차][주의]
                 └────┬─────┘
                      ▼
                 ┌──────────────────┐
                 │citation_validator│
                 └────┬─────────────┘
                      ▼
                    END
```

### State 정의 (`packages/rag/state.py`)

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

### 노드별 책임

| 노드 | 책임 | 모델/도구 | 출력 |
|---|---|---|---|
| `ingest_query` | 쿼리 정규화, history attach | - | `original_query`, `history` |
| `clarifier` | 4 패턴 ambiguity 감지 | gpt-4o-mini (JSON mode) | `needs_clarification`, `clarify_question` |
| `query_rewriter` | HyDE + multi-query 확장 | gpt-4o-mini | `rewritten_queries[]` |
| `router` | regex keyword-first, 무매칭+12자+ 시 LLM fallback | regex / gpt-4o-mini | `route` |
| `authority_lookup` | SQL exact 조회 (process/threshold) | Postgres | `authority_rows` |
| `retriever` | Hybrid (dense+sparse) + RRF + BGE-reranker | bge-m3, Kiwi-BM25, BGE-reranker-v2-m3 | `candidates[]` |
| `generator` | [결론][근거][절차][주의] 스트리밍 | gpt-4o-mini `astream` | `answer` (stream), `sources` |
| `citation_validator` | (doc_id, article_no) 매칭 검증 | - | `citation_valid_pct`, `warnings` |

### 4 ambiguity 패턴 (clarifier 발동 조건)
1. **대상 모호**: "그 규정"(어느 규정?), 유사 명칭 다수("회계규정" vs "내부회계관리규정")
2. **Authority slot 부족**: 승인 질문인데 process 또는 amount/% 미명시
3. **시점 모호**: "최신 규정", "현재 시행 중인 것" (effective_date 필요)
4. **범위 광범**: "휴가 알려줘"(연차/공가/병가 중 어떤?)

### Router regex
```python
RULES = [
  (r"누가\s*승인|결재권자|전결|승인\s*권한|한도|얼마까지", "authority"),
  (r"어떻게|절차|방법|단계|매뉴얼", "manual"),
  (r"가능|할\s*수\s*있|허용|되나요", "policy"),
  (r"FAQ|사례|예시|문답", "faq"),
  (r"공지|한시|임시", "notice"),
]
```

### Latency Budget (PRD §19 — 3s 종단)

| Stage | Budget |
|---|---|
| ingest_query / router (regex) | <10ms |
| clarifier (gpt-4o-mini JSON) | ~300ms (clear 통과 시) |
| query_rewriter (HyDE, mini) | ~250ms |
| retriever (hybrid k=20) | ~150ms |
| reranker (BGE-v2-m3, MPS) | ~400ms |
| generator (stream, first token) | ~600ms |
| citation_validator | ~50ms |
| **종단(first token)** | **~1.5s**, 전체 답변 <3s |

### Checkpoint / Multi-turn
- `PostgresSaver.from_conn_string(POSTGRES_URL)` 1 instance
- `thread_id = session_id` (대화별 격리)
- 사용 시점:
  1. clarify interrupt → END 후 사용자 응답으로 resume
  2. 동일 session 의 후속 질문에서 직전 sources/clarifications 참조

### SSE 이벤트 (LangGraph → FastAPI 변환)
```
event: route        data: {"route":"authority"}
event: clarify      data: {"question":"...", "suggested_replies":["...","..."]}
event: token        data: {"text":"…"}
event: sources      data: {"citations":[{doc_id,article_no,heading_path,score},...]}
event: warning      data: {"message":"근거 없음 결론 1건"}
event: done         data: {"citation_valid_pct":0.94}
```
LangGraph `astream_events` 사용 → token / interrupt 가 같은 stream → FastAPI 가 type 분기.

## 출처
- `docs/mvp_plan.md` § Ingestion Pipeline, § Retrieval / QA
