# Retrieval — Hybrid + RRF

**상태**: active
**마지막 업데이트**: 2026-05-27 (M3 완료)
**관련 페이지**: [embedding.md](embedding.md), [generation.md](generation.md), [citation.md](citation.md), [../architecture/pipeline.md](../architecture/pipeline.md)

## 요약
Dense (e5-large) + Sparse (BM25) 가 각각 Qdrant 에서 candidate_k=30 검색 → Reciprocal Rank Fusion (k=60) → top_k=10. payload filter 로 route 별 doc_type 제한.

## 흐름

```
question
  ↓
[router_node]  → route ∈ {policy, authority, manual, faq}
  ↓
[retriever_node]
  ├── embed_query_dense (e5 "query: " prefix) → search_dense (limit=30, filter=doc_type)
  └── embed_query_sparse (BM25) → search_sparse (limit=30, filter=doc_type)
       ↓
       rrf_merge (top_k=10)
       ↓
  Postgres articles.body 보강
  ↓
state.sources [{article_id, doc_id, article_no, chapter, heading_path, body, score}, ...]
```

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
- `packages/rag/nodes/retriever_node.py` — LangGraph 노드 + Postgres 보강
- `packages/vectorstore/qdrant_store.py` — `search_dense`, `search_sparse`

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
- Reranker (bge-reranker-v2-m3) 미연결 — 일단 RRF 만으로 충분, 후속.

## 출처
- `docs/mvp_plan.md` §M3, §Retrieval/QA, §11 (단일 collection)
