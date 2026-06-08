# Retrieval — Hybrid + RRF + Rerank

**상태**: active
**마지막 업데이트**: 2026-06-08 (cross-encoder reranker 연결 — [ISSUE-001](../issues/resolved/ISSUE-001.md))
**관련 페이지**: [embedding.md](embedding.md), [generation.md](generation.md), [citation.md](citation.md), [../architecture/pipeline.md](../architecture/pipeline.md), [../issues/resolved/ISSUE-001.md](../issues/resolved/ISSUE-001.md)

## 요약
Dense (e5-large) + Sparse (BM25) 가 각각 Qdrant 검색 → Reciprocal Rank Fusion (k=60) → 상위 `rerank_candidate_k=60` → **cross-encoder reranker (BAAI/bge-reranker-base)** 로 원질문과 1:1 재정렬 → top_k=10. payload filter 로 route 별 doc_type 제한.

> **reranker 가 검색 정확도의 핵심**이다. RRF 만으로는 e5 임베딩이 한국어 짧은 표 청크(별표 행)를 변별하지 못해, 의미상 정반대인 국내/국외 별표도 못 가렸다. cross-encoder 가 정답을 +3.5, 오답을 음수로 확실히 갈라 별표 검색을 해결했다. 상세 [ISSUE-001](../issues/resolved/ISSUE-001.md).

## 흐름

```
question
  ↓
[router_node]  → route ∈ {policy, authority, manual, faq}
  ↓
[retriever_node]
  ├── embed_query_dense (e5 "query: " prefix) → search_dense (limit=60, filter=doc_type)
  └── embed_query_sparse (BM25) → search_sparse (limit=60, filter=doc_type)
       ↓
       rrf_merge (top_k=rerank_candidate_k=60)
       ↓
  Postgres articles.body 보강
       ↓
  cross-encoder rerank (원질문 vs body, BAAI/bge-reranker-base) → 재정렬 → 상위 10
  ↓
state.sources [{..., score=rerank_score}, ...]
```

**rerank query 는 HyDE 가 아닌 원질문**을 쓴다 (cross-encoder 는 정밀 매칭이라 깨끗한 질의가 유리). `rerank_enabled=false` 면 RRF top_k=10 만 반환.

## Route → payload filter

| route | filter |
|---|---|
| policy | `doc_type IN ['policy']` |
| authority | `doc_type IN ['authority_matrix']` (M4 에서 SQL 직접조회로 교체) |
| manual | `doc_type IN ['manual']` |
| faq | none (faq doc_type 은 현재 0-chunk 라 필터 걸면 결과 0) |

**Fallback**: 필터 적용 결과가 0 hits 면 필터 해제 후 재검색 (`retriever_node._ROUTE_FILTER`).

## RRF 식
```
score(d) = Σ_{list ∈ {dense, sparse}} 1 / (k + rank_list(d))
k = 60 (Cormack et al. default)
```

각 리스트 내 rank 만 사용 — score 의 스케일 차이가 영향 없음.

## 코드 위치
- `packages/rag/retriever.py` — `hybrid_search`, `rrf_merge`
- `packages/rag/reranker.py` — `rerank_scores` (fastembed TextCrossEncoder)
- `packages/rag/nodes/retriever_node.py` — LangGraph 노드 + Postgres 보강 + rerank
- `packages/vectorstore/qdrant_store.py` — `search_dense`, `search_sparse`

## Reranker (2026-06-08 추가, ISSUE-001)
- 모델: **BAAI/bge-reranker-base** (`config.reranker_model`). 다국어 cross-encoder, fastembed `TextCrossEncoder` 로 ONNX 추론.
  - ⚠️ `BAAI/bge-reranker-v2-m3` 와 `jinaai/jina-reranker-v2-base-multilingual` 은 fastembed 에서 미지원/ONNX 파일 누락이라 base 로 확정.
- 설정: `rerank_enabled=true`, `rerank_candidate_k=60` (`.env` override 가능).
- **candidate_k=60 근거**: 별표가 9개로 늘며 정답 행 청크가 RRF 상위 30 밖으로 밀려 reranker 가 못 보는 회귀 발생 → 60 으로 넓혀 해결. 추가 비용은 rerank 추론 +193ms (30→60 docs, 218→411ms) 로 전체 응답(~15s)의 ~1.3% 라 무시 가능. 데이터셋이 커지면 재검토.
- 효과: "2호구분 일비" → 별표 2 행 청크 rerank +3.5 로 1위 (RRF 만으로는 top6 밖, 국외 별표 4 가 1위였음).

## M3 KPI 측정 (2026-05-27, 5 sample query)
| Q | route | top-1 doc | top-3 doc_ids | retr latency |
|---|---|---|---|---|
| 연차휴가 며칠 | policy | doc_id=17 (인사관리규정) ✓ | 17, 17, 3 | 600ms |
| 내부회계관리규정 제5조 | policy | doc_id=11 ✓ | 11, 11, 10 | 35ms |
| 출장 여비 일당 한도 | policy | doc_id=14 (여비규정) ✓ | 14, 14, 14 | 35ms |
| 감사 대상 | policy | doc_id=4 (감사규정) ✓ | 4, 4, 4 | 35ms |
| 이사회 위원회 종류 | policy | doc_id=16 ✓ | 16, 11, 16 | 35ms |

→ top-1 doc 정답 5/5. mvp_plan KPI **≥8/10** 충족 (10 query 풀셋은 M6 에서).

## 알려진 한계
- 첫 query 의 retr 600ms 는 e5 모델 lazy load (이후 ~35ms).
- 한국어 BM25 토큰화 불완전 (조사 분리 X). 향후 mecab/Kiwi 도입 필요.
- 동의어/축약어 약함 — "위임전결" vs "전결권자" 같은 변환 없음 (M5 의 HyDE 가 보강 목표).
- ~~Reranker 미연결~~ → **2026-06-08 연결 완료** (BAAI/bge-reranker-base, ISSUE-001).
- 한국어 표 청크의 dense 변별력 약함은 reranker 로 커버하나, 근본적으로 candidate_k 의존 — 컬렉션 확장 시 candidate_k 재조정 필요.

## 출처
- `docs/mvp_plan.md` §M3, §Retrieval/QA, §11 (단일 collection)
