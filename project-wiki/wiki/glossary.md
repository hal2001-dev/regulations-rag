# Glossary

**상태**: active
**마지막 업데이트**: 2026-05-27
**관련 페이지**: [features/authority_matrix.md](features/authority_matrix.md), [features/citation.md](features/citation.md), [architecture/pipeline.md](architecture/pipeline.md)

## 요약
두 영역으로 구성: **규정 도메인 용어** (조/항/호/목, 위임전결 등) + **RAG/검색 기술 용어** (RRF, HyDE, BM25 등). 새 용어 등장 시 본 페이지에 추가하고 관련 페이지에서 `[[glossary]]` 로 링크할 것.

---

## 규정 도메인

### 조항 구조 — 한국어 법규/규정의 표준 위계
**문서 → 편 → 장 → 절 → 관 → 조 → 항 → 호 → 목**

본 프로젝트가 다루는 깊이: `장(章) → 절(節) → 조(條) → 항(項) → 호(號) → 목(目)`.

| 단위 | 표기 | 예시 |
|---|---|---|
| 장 | `제N장` | `제2장 인사` |
| 절 | `제N절` | `제1절 채용` |
| 조 | `제N조` 또는 `제N조의M` | `제12조 (연차휴가)`, `제2조의2` |
| 항 | `①②③ … ⑳` (원숫자) | `① 직원은 …` |
| 호 | `1. 2. 3.` (아라비아) | `1. 본인 결혼 5일` |
| 목 | `가. 나. 다.` (한글) | `가. 부모 사망 5일` |

`제2조의2` 같은 **삽입조**(법령 개정 시 기존 조 번호 유지하며 사이에 삽입) 는 regex 에서 `(?:의\d+)?` 로 처리.

### 별표 / 별지 / 부칙
- **별표(別表)** `별표 1`, `별표 2` — 본문 뒤에 따라오는 표·서식
- **별지(別紙)** `별지 1` — 본문 뒤 첨부 서식
- **부칙(附則)** — 시행일/경과조치 등 본문 마지막 섹션. `effective_date` heuristic 추출.

본 프로젝트는 별표/별지를 `article_no='별표 N'` 으로 article 트리에 통합.

### 위임전결 (委任專決)
조직 내 의사결정 권한을 **상위 결재권자 → 하위자에게 위임**하여 결재 단계를 줄이는 제도. 일반적으로 표 형태 (`업무 × 결재권자 × 한도`) 로 규정.

| 용어 | 의미 |
|---|---|
| 결재권자 | 원래 결재해야 하는 자 (예: 대표이사) |
| 전결권자 | 위임 받아 단독으로 결재할 수 있는 자 (예: 본부장) |
| 한도 | 전결권자가 처리 가능한 상한 (금액 KRW 또는 비율 %) |
| 조건 | 한도 외 적용 조건 (예: 분기당 1회) |

본 프로젝트는 이를 `authority_rules` 테이블로 구조화 → SQL exact 조회. ([features/authority_matrix.md](features/authority_matrix.md))

### doc_type 분류 (7종)
| doc_type | 설명 | 예시 PDF |
|---|---|---|
| `authority_matrix` | 위임전결규정 | `사무위임전결규정.pdf` |
| `policy` | 일반 규정 | `인사관리규정.pdf`, `여비규정.pdf` |
| `manual` | 매뉴얼/가이드 | `자치법규업무매뉴얼.pdf` |
| `faq` | 100문답 형식 | `공무원여비100문100답.pdf` |
| `notice` | 한시/임시 공지 | (현재 17 PDF 에는 없음) |
| `guideline` | 가이드라인 | - |
| `template` | 서식 | - |

분류는 파일명 휴리스틱: `위임전결|직무권한` → authority_matrix, `매뉴얼|가이드` → manual, `100문` → faq, else → policy.

### heading_path
조항 위계의 직렬화. citation 의 source of truth. ([features/citation.md](features/citation.md))
```json
{ "doc_title": "인사관리규정", "chapter": "제2장 인사", "article": "제12조 (연차휴가)", "paragraph": "②" }
```
렌더링: `인사관리규정 > 제2장 인사 > 제12조 (연차휴가) > ②`

---

## RAG / 검색 기술

### Hybrid Search
**Dense (의미)** + **Sparse (키워드)** 검색을 결합하여 보완. 본 프로젝트는 bge-m3 dense + Qdrant/bm25 sparse.

### Dense Embedding
텍스트 → 고차원 벡터 (의미 유사). 본 프로젝트: **bge-m3** (한국어 검증, 로컬). cosine 유사도.

### Sparse Embedding / BM25
키워드 빈도 기반 retrieval. 정확한 용어 매칭에 강함 (예: 조 번호, 고유명사). 본 프로젝트: Qdrant 의 `Qdrant/bm25` + **Kiwi** 형태소 분석기 (N/V/SL/SN 필터링).

### Kiwi
한국어 형태소 분석기 (kiwipiepy). N=명사, V=동사, SL=영문, SN=숫자 등 품사 태그. BM25 토크나이저로 활용.

### RRF (Reciprocal Rank Fusion)
여러 검색 결과를 융합하는 방식. `score = Σ 1/(k + rank_i)`. 본 프로젝트는 (1) dense+sparse 융합, (2) 원본+HyDE+multi-query 결과 융합 두 곳에 사용.

### HyDE (Hypothetical Document Embedding)
질문 → LLM 으로 "가상의 정답 문서" 생성 → 그 텍스트를 추가 검색 쿼리로 사용. 한국어 규정 어휘 활성화에 효과. 본 프로젝트는 `query_rewriter` 노드 (M5).

### Multi-query
복합 의도 질문을 2-3개 sub-query 로 분해. 예: "승인 절차와 한도" → "결재 절차", "한도", "처리 시간". 본 프로젝트는 HyDE 와 함께 `query_rewriter` 에서 처리.

### Rerank
1차 retrieval top-K (예: 20) 를 reranker 로 재정렬해 top-N (예: 5) 선택. 본 프로젝트: **BGE-reranker-v2-m3** (MPS 가속).

### Chunk
RAG 의 검색/저장 단위. 본 프로젝트의 chunk 정책: **1 chunk = 1 제N조** (>800 token 시 항 분할). ([architecture/decisions.md](architecture/decisions.md) ADR-006)

### Breadcrumb
chunk 본문 앞에 prepend 되는 위계 경로 텍스트. 예: `인사관리규정 > 제2장 인사 > 제12조 (연차휴가)`. BM25 recall + chunk self-contained 목적.

### Payload (Qdrant)
vector 와 함께 저장되는 메타데이터 JSON. 본 프로젝트는 `{article_id, doc_type, domain, process, article_no}` 만 저장 (citation 은 Postgres 에서 재조회).

### Payload Index
Qdrant 가 payload 필드에 만드는 b-tree 유사 index. filter 가 O(log n) 가 되어 collection 분리와 동일 성능.

### Checkpointer (LangGraph)
그래프 실행 상태를 영속화하여 interrupt/resume 을 가능케 함. 본 프로젝트: `PostgresSaver`, `thread_id=session_id`.

### Interrupt (LangGraph)
그래프 실행 중 사용자 입력을 기다리며 정지. 본 프로젝트의 `clarifier` 노드가 4 ambiguity 패턴 감지 시 발동.

### Routing (graph)
조건부 edge 로 다음 노드 결정. 본 프로젝트: `router_node` 가 keyword regex 로 `authority`/`policy`/`manual`/`faq`/`notice` 분류 → `route=="authority"` 면 SQL lookup, else vector retriever.

### Citation
답변의 근거가 되는 source chunk 표시. 본 프로젝트는 `heading_path` 기반 (page 번호 X). ([features/citation.md](features/citation.md))

### Faithfulness
답변이 retrieved context 에 충실한가의 지표 (Ragas). 본 프로젝트 KPI: ≥0.95 (hallucination ≤5%).

### Ragas
RAG 평가 프레임워크. 본 프로젝트 사용 지표: `faithfulness`, `answer_relevancy`, `context_precision`, `citation_exact_match` (커스텀).

### SSE (Server-Sent Events)
서버 → 클라이언트 단방향 스트리밍. LangGraph token + 노드 진행 상태를 실시간 전달. 본 프로젝트 이벤트: `route`, `clarify`, `token`, `sources`, `warning`, `done`.

---

## 출처
- `docs/enterprise_policy_rag_prd_full.md`
- `docs/mvp_plan.md`
- 규정 위계: 행정안전부 자치법규 작성 매뉴얼 (`자치법규업무매뉴얼(2022년판)행정안전부.pdf`)
