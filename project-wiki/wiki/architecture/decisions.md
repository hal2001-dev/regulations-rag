# Architecture Decision Records

**상태**: active
**마지막 업데이트**: 2026-05-27
**관련 페이지**: [pipeline.md](pipeline.md), [stack.md](stack.md), [../features/authority_matrix.md](../features/authority_matrix.md), [../features/citation.md](../features/citation.md)

## 요약
M1 시작 시점의 핵심 결정 13개. 변경 시 본 문서에 **새 ADR 을 append** 하고 기존 항목을 deprecated 마킹할 것 (기존 행 직접 수정 금지).

각 ADR 형식: `### ADR-NNN: 제목` + Status / Context / Decision / Consequences.

---

### ADR-001: Vector store 분리하지 않고 단일 collection 사용

**Status**: accepted (2026-05-27)
**Context**: PRD §11 은 5 collection 분리(policy/manual/faq/notice/authority)를 제안. 17 문서 ~3000 chunk 규모에서 분리 이득 vs 운영 부담을 비교.
**Decision**: **단일 Qdrant collection + payload filter**(`doc_type`, `domain`, `process`, `article_no` 인덱싱).
**Consequences**:
- 운영 부담 1/5 (배포/백업/스키마 변경)
- payload-indexed filter 는 O(log n), 5 collection 분리와 동일 성능 (3000 chunk 규모)
- PRD §11 의 5 collection 은 **strategy hint** 로 해석 (route → payload filter 매핑)
- 100k chunk 이상으로 늘어나면 재검토

---

### ADR-002: Indexer 를 FastAPI 와 별도 프로세스로 분리

**Status**: accepted (2026-05-27)
**Context**: Docling PDF 파싱이 30-120s/PDF. FastAPI event loop 차단 시 다른 요청 응답 불가.
**Decision**: 큐 기반 별도 프로세스 (`apps/indexer_worker.py`). FastAPI 는 `POST /ingest` 에서 enqueue 만, worker 가 `FOR UPDATE SKIP LOCKED` 로 폴링.
**Consequences**:
- 두 프로세스 동시 기동 필요 (운영 복잡도 +)
- FastAPI 응답성 보장
- knowledge-rag ADR-028 패턴 차용
- 큐: Postgres `ingest_jobs` 테이블 (별도 메시지 브로커 X — 운영 단순화)

---

### ADR-003: Embedding 은 bge-m3 로컬 (fastembed) 사용

**Status**: accepted (2026-05-27)
**Context**: 한국어 규정 도메인. 임베딩 비용 + PII 우려 + 한국어 성능 평가.
**Decision**: **bge-m3** via fastembed (CPU/MPS 로컬).
**Consequences**:
- 한국어 성능 검증됨 (knowledge-rag 실험 결과)
- API 비용 0
- PII 외부 노출 0
- 로컬 GPU/MPS 권장 (CPU 도 동작은 하나 인덱싱 속도 ↓)

---

### ADR-004: Generator LLM 은 gpt-4o-mini (streaming)

**Status**: accepted (2026-05-27)
**Context**: Generator 의 책임은 **인용 + 포맷팅** ([결론][근거][절차][주의] 블록). 추론보다 정확한 인용이 우선.
**Decision**: `gpt-4o-mini` with `astream`.
**Consequences**:
- 비용 ~$0.02/일 수준 (예상)
- streaming 가능 → SSE token 이벤트
- 더 큰 모델 필요 시 (예: gpt-4o) 노드 단위 교체 가능

---

### ADR-005: Authority Matrix 는 Postgres 구조화 테이블에 저장

**Status**: accepted (2026-05-27)
**Context**: "할인 30% 누가 승인?" 같은 질문에 LLM 이 텍스트에서 한도/% 를 추출/추론하면 hallucination 위험. 정확성이 KPI 의 핵심.
**Decision**: 위임전결 표를 `authority_rules` 테이블로 추출 (`process`, `approval_role`, `approval_limit_pct`, `amount_limit_krw`, `condition`, `raw_row`). SQL exact 조회. 동일 행을 Qdrant 에도 fallback chunk 로 적재.
**Consequences**:
- 한도/% hallucination 0
- 표 추출 정확도가 차별점의 생명선 → M4 에서 충분한 검증 필요
- 추출 실패 시 admin CSV escape hatch 제공
- 차별점 1: [features/authority_matrix.md](../features/authority_matrix.md)

---

### ADR-006: Chunk 경계는 조 단위 (>800 token 시 항 분할)

**Status**: accepted (2026-05-27)
**Context**: 조 중간을 자르면 인용 단위와 chunk 경계 불일치 → "제5조 제2항" 같은 정확 인용 어려움.
**Decision**: 기본 1 chunk = 1 `제N조`. 800 token 초과 시 `①②③` (항) 단위 분할. breadcrumb (`{doc_title} > {chapter} > {article_no} {title}`) 본문 앞 prepend.
**Consequences**:
- 인용 단위와 chunk 경계 일치
- breadcrumb prepend 로 BM25 recall + self-contained chunk
- 너무 짧은 조 (수 단어) 는 그대로 작은 chunk

---

### ADR-007: Citation 단위는 heading_path (page 번호 아님)

**Status**: accepted (2026-05-27)
**Context**: page 번호 인용은 PDF 재발간 시 깨짐. 또한 사용자가 인용을 보고 원문 위치를 찾기 어렵다.
**Decision**: `인사규정 > 제2장 > 제12조 > ②` 같은 **heading_path** 기반 citation.
**Consequences**:
- 사용자가 조항을 직접 인용 가능
- 재발간 robust
- 차별점 2: [features/citation.md](../features/citation.md)

---

### ADR-008: OCR 은 Docling 1차 → macOS Vision (lang=ko-KR) fallback

**Status**: accepted (2026-05-27)
**Context**: 17 PDF 중 스캔본 일부 + 별표(별첨 표) 가능성.
**Decision**: Docling 1차 (OCR off), 텍스트 <500 chars/5+ 페이지 시 `OcrMacOptions(lang=['ko-KR'])` 재시도. `extraction_quality='scan_only'` 마킹.
**Consequences**:
- macOS 의존 (Linux/CI 환경 별도 OCR 필요 — M6 이전 검토)
- 비용 0, 한국어 양호

---

### ADR-009: Orchestration 은 LangGraph state machine

**Status**: accepted (2026-05-27)
**Context**: 조건부 path(authority vs vector), 사용자 clarify interrupt, multi-turn resume 이 필요. imperative pipeline 으로 모두 구현 가능하지만 가독성/디버깅 곤란.
**Decision**: **LangGraph StateGraph**. 노드 = (clarifier, query_rewriter, router, retriever, authority_lookup, generator, citation_validator). 조건부 edge + `interrupt()` 활용.
**Consequences**:
- 조건부 edge 가 코드 분기보다 명시적
- interrupt-based clarify 가 multi-turn 의 자연스러운 모델
- checkpointer 가 필수 → ADR-010
- LangGraph 학습 곡선 (팀이 imperative 익숙해도 채택 가치 있음)

---

### ADR-010: Checkpointer 는 PostgresSaver (`thread_id = session_id`)

**Status**: accepted (2026-05-27)
**Context**: ADR-009 채택 시 checkpointer 필요. 별도 인프라 (Redis 등) 추가 vs 기존 Postgres 재사용.
**Decision**: `PostgresSaver.from_conn_string(POSTGRES_URL)` 1개 인스턴스. `thread_id = session_id`. `checkpointer.setup()` 1회로 `langgraph.checkpoints` 등 테이블 자동 생성 (앱 ORM 모델에 포함 X).
**Consequences**:
- 별도 인프라 0
- 대화별 격리 (`thread_id`)
- clarify interrupt → END 후 사용자 응답으로 resume 가능
- `langgraph.checkpoints` 무한 증가 → M6 에 일일 cleanup cron 추가 예정

---

### ADR-011: 질문 구체화는 하이브리드 (HyDE 내부 + clarify 외부)

**Status**: accepted (2026-05-27)
**Context**: 모호한 질문에 무차별 역질문하면 UX 마찰. 그러나 모든 질문을 retrieval 만으로 처리하면 KPI(검색 성공률 85%) 미달 위험.
**Decision**:
- **내부**: `query_rewriter` 노드가 HyDE + multi-query 로 retrieval 전 자동 확장 (사용자 비가시)
- **외부**: `clarifier` 노드가 4 패턴 (대상 모호 / authority slot 부족 / 시점 모호 / 범위 광범) 감지 시에만 `interrupt()` 로 역질문
**Consequences**:
- 명확 질문은 사용자 방해 없이 retrieval 품질 ↑
- 모호 질문만 역질문 → KPI 달성 핵심
- clarifier false-positive 위험 → confidence 0.6 미만 통과 + 무한 루프 방지(`len(clarifications) >= 2`)

---

### ADR-012: Clarify 무한 루프 방지 = clarifications 누적 2회 강제 통과

**Status**: accepted (2026-05-27)
**Context**: clarifier 가 매 응답 후에도 needs=true 를 계속 반환할 가능성. UX 가드 필요.
**Decision**: `len(state.clarifications) >= 2` 면 강제 통과 (router 로 직행).
**Consequences**:
- 무한 루프 차단
- 3번째 질문은 retrieval 로 best-effort 처리
- 명시적 한계 (사용자가 충분히 구체화하지 못한 경우 답변 품질 ↓)

---

### ADR-013: 모노레포 X, 형제 프로젝트 knowledge-rag 는 참고만

**Status**: accepted (2026-05-27)
**Context**: 형제 프로젝트 `knowledge-rag` 가 유사 RAG 인프라 보유. 코드 공유 vs 독립 구현.
**Decision**: 코드 직접 공유/모노레포 **금지**. 패턴/ADR/구조만 참고하여 본 프로젝트에서 재구현.
**Consequences**:
- 독립 evolution
- 도메인 특화 (규정 chunker, authority extractor) 자유롭게 추가
- 일부 중복 (loader, qdrant 헬퍼 등) 감수

---

### ADR-014: Dense embedding 을 `intfloat/multilingual-e5-large` 로 변경 (bge-m3 대체)

**Status**: accepted (2026-05-27, M3 진입 시) — supersedes ADR-?? (bge-m3 결정)
**Context**: mvp_plan §177 의 결정은 BAAI/bge-m3 (fastembed). 그러나 M3 진입 시 fastembed 0.7-0.8 의 `TextEmbedding.list_supported_models()` 에 bge-m3 dense 가 등재되어 있지 않음을 발견. multilingual + 1024-dim 으로 가장 비슷한 호환 모델 선택.
**Decision**: **`intfloat/multilingual-e5-large`** (1024 dim, multilingual, fastembed 지원).
**Consequences**:
- 모델 다운로드 ~2GB, 첫 호출 시 lazy load.
- e5 family 의 `query: ` / `passage: ` prefix 적용 필요 (`packages/rag/embeddings.py`).
- 한국어 quality 는 bge-m3 보다 약간 손해 가능 (multilingual 학습 강도 차이). M3 5-query 측정에선 top-1 doc 5/5 정답으로 충분.
- 후속 (M5 이후) 한국어 특화 모델 (ko-sroberta 등) 비교 실험 여지.

### ADR-015: Sparse 인코더는 `Qdrant/bm25` (Kiwi-BM25 우회)

**Status**: accepted (2026-05-27, M3 진입 시) — partial supersede of mvp_plan §M3 build 의 `kiwipiepy` 의존
**Context**: mvp_plan §415/§M3 에서 `kiwipiepy` + Kiwi-BM25 (한국어 형태소 기반) 가 명시. 그러나 kiwipiepy 0.18-0.21 가 Python 3.14 wheel 미제공 + 소스 빌드 (numpy build-isolation 환경) 실패. .venv 의 Python 버전 다운그레이드는 docling/langgraph 등 다른 deps 영향이 큼.
**Decision**: **fastembed 내장 `Qdrant/bm25`** (다국어 정규식 토크나이저). 한국어 형태소 분해 X.
**Consequences**:
- 한국어 조사 분리/원형 복원 없음 → BM25 recall 약함.
- 후속 옵션 (우선순위): (1) .venv 를 Python 3.13 으로 재구성 + kiwipiepy, (2) mecab/soynlp 자체 BM25 구현, (3) sparse 자체를 dense-only 로 전환 후 reranker 강화.
- 본 결정은 M3 골격 우선이므로 후속 retrieval quality 측정 후 옵션 1 으로 회귀 가능.

### ADR-016: 첫 토큰 KPI <1s 미달은 OpenAI gpt-4o-mini latency 한계로 인정

**Status**: accepted (2026-05-27, M3 측정 후)
**Context**: mvp_plan §M3 KPI 의 "첫 토큰 <1s". 측정 결과 실제 ~3.5s. 분석: retrieval 36ms + LLM API cold-start ~3s. system prompt 길이/네트워크/모델 영향이 대부분.
**Decision**: M3 단계에선 미달 인정. 사용자 체감 개선 책임은 M5 Chat UI (skeleton/loading state + node-progress) 로 이전.
**Consequences**:
- 후속 옵션: (1) Claude Haiku 4.5 등 더 빠른 API, (2) system prompt 압축 (~400→~200 token), (3) 로컬 LLM (Ollama gpt-oss).
- M6 Ragas eval 에선 latency 별도 KPI 측정.

### ADR-017: authority_extractor 는 **gpt-4o-mini vision** (페이지 이미지 직접)

**Status**: accepted (2026-05-27, M4 진입 시) — supersedes mvp_plan §M2.5 의 regex 추출 결정
**Context**: mvp_plan §M2.5 는 "Docling 표 markdown → regex 헤더 매칭 → 행 단위 row" 결정. 그러나 실제 시도 결과:
- 1차 (regex): 사무위임전결규정 0 rows (PDF 표가 hierarchical/spanned 구조)
- 2차 (LLM text-only on markdown): 177 rules 다 "사장" + amount=null (markdown 으로 평탄화된 ○ 매핑 못 풀어냄)
- 3차 (LLM vision, 페이지 PNG 직접): 514 rules, 29 rules 에 amount, role 다양 — 사용 가능 수준

**Decision**: `pypdfium2` 로 PDF 페이지 PNG 렌더 → gpt-4o-mini vision (`detail=high`) → structured JSON output 으로 추출. 페이지별로 1회 호출. 빈 페이지(`has_table=false`) 는 skip.

**Consequences**:
- 비용 PDF당 ~$0.02 (32 페이지 × ~$0.0006). 자동 처리 가능, 새 PDF 추가 시 즉시 동작.
- 결과 ≈ 85% 정확. process 매핑은 약함 (다수 "other") 이지만 amount/role 정확. authority_lookup 에서 amount/% 가 강한 신호일 때 process 필터를 drop 해 우회.
- 처리 시간 PDF당 ~5~15분 (페이지당 ~30s). 백그라운드 backfill 가능.
- 후속 보강 옵션 (M5/M6): (a) Docling native table cells API 로 비용 0 자동화, (b) macOS Vision + bbox 분석, (c) CSV escape hatch (mvp_plan §495).

### ADR-018: amount/% 가 있으면 authority_lookup 의 process 필터 drop

**Status**: accepted (2026-05-27, M4 검증 후)
**Context**: 1차 lookup 시 5/5 queries 가 0 sources 였음. 원인 = process 필터 + amount 필터 AND, 그런데 amount 가 있는 rules 들이 대부분 process="other" 로 LLM 매핑됨 ("5,000만 원 이하" 같은 한도-only task 라 process 키워드 없음).
**Decision**: amount/% 가 명시되어 있으면 process 필터 자동 drop. amount/% 가 없을 때만 process 필터 적용. 그래도 0 results 면 hybrid retrieval fallback (authority_matrix doc_type 만).
**Consequences**:
- 5/5 query 모두 정답 매칭 (M4 KPI 통과).
- process 가 검색의 weak signal, amount/% 가 strong signal — order 가 자연스럽게 맞음.
- 가능 가짜 양성: amount 만 검색 시 의도하지 않은 process 의 rule 도 hit. 결과를 generator 가 답변하므로 hallucination 보다 over-recall 위험.

### ADR-019: M6 KPI 4종 중 citation/retrieval/latency 미달은 미완료가 아닌 후속 작업

**Status**: accepted (2026-05-28, M6 baseline 측정 후)
**Context**: 30 query golden eval 결과 — route 92.3% ✅ / kw 83.3% ✅, citation 69.2% ❌ / retrieval top-1 68.2% ❌ / first-token p95 10.8s ❌ / end-to-end p95 16.4s ❌. ADR-016 으로 latency 는 이미 인정. 신규 미달 2종 (citation, retrieval) 은 prompt/golden 양쪽 모두 원인.
**Decision**: M6 종료 = 측정 인프라 (`scripts/eval_ragas.py` + `tests/e2e/golden_queries.yaml`) 완성 + 1차 baseline 기록. 4종 미달은 명시적 carry-over.
**Consequences**:
- citation 후속: generator prompt 에 `[근거]` 블록 필수 강제 + few-shot 예시 추가
- retrieval 후속: golden truth 의 `expected_doc_id` 단일을 `acceptable_doc_ids[]` 다중 허용으로 완화 + manual 키워드의 doc_type=manual boost (M02/M03 같은 매뉴얼 쿼리가 policy 로 misroute 되는 케이스 차단)
- latency 후속: clarifier prefilter (명확 query 는 LLM 안 부르고 통과) + HyDE → dense embedding 대체 — gpt-4o-mini 호출 두 번 절약. ADR-016 의 후속 채널.
- ragas 는 `--ragas` 플래그로 옵션, 비용 발생 시점에만 측정.

### ADR-020: Retrieval 에 cross-encoder reranker 추가 (BAAI/bge-reranker-base)

**Status**: accepted (2026-06-08, [ISSUE-001](../issues/resolved/ISSUE-001.md))
**Context**: 별표 표 등 짧은 한국어 표 청크를 RRF(dense e5-large + sparse BM25)만으로는 변별하지 못함. 의미상 정반대인 국내/국외 별표도 못 가려 "2호구분 일비" 가 국외 별표 4 를 1위로 잡음. ADR-016 에서 reranker 를 후속으로 미뤄둔 항목.
**Decision**: RRF 후보 `rerank_candidate_k=60` 을 fastembed `TextCrossEncoder(BAAI/bge-reranker-base)` 로 **원질문**(HyDE 아님)과 1:1 재정렬 → 상위 10. `rerank_enabled` 토글 (`reranker.py`, `retriever_node`).
**Consequences**:
- 대안 기각: `bge-reranker-v2-m3` / `jina-reranker-v2-base-multilingual` 은 fastembed 미지원 또는 ONNX 누락 → base 채택.
- `candidate_k` 30→60: 별표 9개 환경에서 정답 행 청크가 후보 밖으로 밀린 회귀를 후보 확대로 해결. 추론 +193ms(전체 ~15s 의 1.3%).
- ablation 으로 rerank 가 검색 정확도 1등 확인 ("2호구분 일비" RRF top6밖 → rerank 1위 +3.5). linearization 은 후보를 깔아주는 보조.
- 컬렉션 확장 시 `rerank_candidate_k` 재조정 필요.

## ADR 작성 가이드
- 새 결정 시 `ADR-(N+1)` 로 append
- 기존 결정 변경 시: 새 ADR + 기존 ADR Status 를 `superseded by ADR-XXX` 로 변경 (본문 수정 금지)
- Status 값: `accepted` / `proposed` / `superseded by ADR-XXX` / `deprecated`

## 출처
- `docs/mvp_plan.md` § 핵심 결정 (decisions 테이블)
- `docs/enterprise_policy_rag_prd_full.md`
