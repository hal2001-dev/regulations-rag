# Embedding

**상태**: active
**마지막 업데이트**: 2026-05-27 (M3 완료)
**관련 페이지**: [retrieval.md](retrieval.md), [../architecture/decisions.md](../architecture/decisions.md)

## 요약
Dense: `intfloat/multilingual-e5-large` (1024-dim, fastembed) — 한국어 multilingual.
Sparse: `Qdrant/bm25` (fastembed 내장 BM25, 다국어 정규식 토크나이저).
원래 mvp_plan §177 의 결정은 BAAI/bge-m3 였지만 fastembed (0.7-0.8) 가 직접 지원하지 않아 변경 (ADR-? 참고).

## 인덱싱 통계 (2026-05-27)
- 17 docs / 1,461 articles → 1,461 Qdrant points
- backfill 시간: 253s (~5.8 points/s, M2 chunk → embed → upsert)
- 첫 호출 시 e5-large 모델 다운로드 약 ~2GB

## 코드 위치
- `packages/rag/embeddings.py` — fastembed wrapper. e5 family 의 `query: ` / `passage: ` prefix 적용.
- `packages/rag/index_articles.py` — Postgres articles → embedding → Qdrant upsert.
- `scripts/backfill_embeddings.py` — 기존 articles 일괄 backfill.
- `apps/indexer_worker.py` — 새 PDF 의 `_process_job` 끝에 `index_articles_for_doc(doc_id)` 호출.

## 한국어 quality 노트
- e5-large 가 한국어 multilingual 학습되어 동작은 하지만 ko-sroberta / KoSimCSE 같은 한국어 특화 모델보다 약함.
- BM25 (`Qdrant/bm25`) 가 한국어 형태소 분석 없이 단순 정규식 토큰 → 조사 분리 불완전. mvp_plan §415 의 Kiwi-BM25 가 이상적이나 kiwipiepy 가 Python 3.14 wheel 미제공 + 소스 빌드 실패.
- 후속 개선 옵션:
  1. .venv 를 Python 3.13 으로 재구성 → kiwipiepy 사용
  2. mecab / soynlp 기반 자체 BM25 인덱서
  3. ko-sroberta-multitask 등 한국어 dense 모델로 교체
  4. ColBERT (멀티벡터) 같은 latent retrieval

## 출처
- `docs/mvp_plan.md` §M3, §Ingestion Pipeline
- 2026-05-27 backfill 실측
