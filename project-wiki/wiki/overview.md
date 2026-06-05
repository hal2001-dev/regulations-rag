# Project Overview

**상태**: active
**마지막 업데이트**: 2026-06-05 (데이터셋 전면 교체 17→4 PDF 재색인)
**관련 페이지**: [roadmap.md](roadmap.md), [architecture/decisions.md](architecture/decisions.md), [features/authority_matrix.md](features/authority_matrix.md), [features/citation.md](features/citation.md), [data/spec.md](data/spec.md)

## 요약
사내 규정/매뉴얼/FAQ PDF 를 통합 검색하는 **한국어 Enterprise RAG** 시스템. Hybrid search + 조항 단위 chunking + 계층적 citation 으로 한도/% hallucination 을 차단하는 것이 목표. LangGraph state machine 으로 오케스트레이션. 시스템은 M1~M6 완료 상태이며, 2026-06-05 에 데이터셋을 17 PDF → 4 PDF(보험약관 2 + 공무원여비규정 + 사무위임전결규정)로 교체·재색인했다.

## 현재 데이터셋 (2026-06-05 재색인)
**4 docs / 579 articles / Qdrant 579 points** — 개인용자동차보험약관(303)·공무원여비규정(39)·레저보험약관(208)·사무위임전결규정(29), 전부 quality=ok. 상세는 [data/spec.md](data/spec.md).
- ✅ **authority_rules 282행** (사무위임전결규정) — 위임전결 SQL 조회 정상. (1차 시도는 OpenAI quota 실패 → 키 복구 후 `scripts/backfill_authority.py --doc-ids 4 --reset` 재실행으로 복구.)
- 옛 17 PDF 는 `ingest/temp/` 보관. 옛 golden 쿼리/eval 은 현 데이터셋과 불일치 → 재작성 필요.

## 현재 상태 (2026-05-27)

| 영역 | 상태 |
|---|---|
| PRD | ✅ 완료 (`docs/enterprise_policy_rag_prd_full.md`) |
| MVP 계획 | ✅ 완료 (`docs/mvp_plan.md`, 546 라인) |
| 17개 PDF 원본 | ✅ `ingest/` 디렉토리에 비치 |
| project-wiki 스키마 | ✅ `project-wiki/CLAUDE.md` |
| project-wiki 초기 페이지 | ✅ M1 wiki 스캐폴드 완료 |
| docker-compose / requirements.txt | ✅ postgres:16 (5433) + qdrant v1.12.4 (6433) healthy, `requirements-m1.txt` 별도 |
| 백엔드 코드 (apps/, packages/) | ✅ M1 스켈레톤 — `/health`, lifespan create_all, 6 router placeholder (501), indexer_worker 큐 폴링 |
| DB 7 테이블 | ✅ `documents/articles/authority_rules/ingest_jobs/conversations/messages/taxonomy_config` |
| Web UI (web/) | ✅ M1 shell — Next.js 15 + Tailwind v3 + shadcn-ready, `/` 홈 + `/chat` placeholder (실 UI 는 M5) |
| 17개 PDF 인덱싱 | ✅ M2 완료 — 17 docs / 1,461 articles, 15 docs with chunks (manual×1 + faq×1 = 0-chunk, 후속 fallback chunker 과제) |
| LangGraph state machine | ✅ M3 완료 — router → retriever → generator → citation_validator, AsyncPostgresSaver checkpoint |
| Qdrant 임베딩 (dense+sparse) | ✅ M3 — 1,461 points (multilingual-e5-large 1024d + Qdrant/bm25) |
| /query/stream SSE | ✅ M3 — token/sources/route/citation/done 5 이벤트 |
| Authority lookup (SQL exact) | ✅ M4 — 514 rules / vision LLM 추출 / conditional edge / KPI 통과 |
| Authority Matrix lookup | ✅ M4 |
| Chat clarify + rewriter + multi-turn UI | ✅ M5 — clarifier 4 패턴 / HyDE / interrupt_before + /query/resume / Next.js chat UI |
| Admin UI + Reindex | ✅ M6 — POST /admin/reindex/{doc_id} + /library chunk preview + /admin jobs panel |
| Eval 인프라 | ✅ M6 — 30 golden queries + `scripts/eval_ragas.py` (route/doc/citation/kw/latency + ragas 옵션) |
| KPI 목표 (PRD §24) | 🟡 route 92.3% ✅ / kw 83.3% ✅ · citation 69.2% ❌ / retrieval 68.2% ❌ / latency p95 16.4s ❌ — [ADR-019](architecture/decisions.md) carry-over |

진행률: **M1~M6 완료.** 17 PDF / 1,461 articles + 514 authority_rules + clarifier + Chat UI + Admin/Library + 자동 KPI 측정. KPI 4종 미달은 ADR-019 로 후속 작업 명시. 전체 ~100% (post-MVP 튜닝 단계).

## 핵심 차별점 (knowledge-rag 대비)

1. **Regulation structure parser** — 조(`제N조`) + 항(`①②`) 경계를 절대 자르지 않는 chunker. 인용 단위와 chunk 경계 일치.
2. **Authority Matrix 구조화** — 위임전결을 텍스트가 아닌 `authority_rules` 테이블로 추출 → SQL exact 조회. "할인 30% 누가 승인?" → `WHERE approval_limit_pct >= 30` 으로 한도 hallucination 0.
3. **Citation 포맷** — page number 가 아닌 `인사규정 > 제2장 > 제12조 > ②` (heading_path 기반). 사용자가 조항을 직접 인용 가능.
4. **LangGraph + interrupt-based clarify** — 모호한 질문은 `clarifier` 노드가 `interrupt()` 로 역질문, 명확한 질문은 그대로 통과. HyDE 내부 확장과 외부 clarify 의 하이브리드.

## 데이터 규모 (2026-06-05 현재)
- 4 PDF / 579 article chunk (조 단위, breadcrumb prepend) + 282 authority_rules — 상세 [data/spec.md](data/spec.md)
- Vector store: 단일 Qdrant collection `regulations` + payload filter, 579 points (dense 1024d + bm25 sparse)
- (옛 17 PDF 데이터셋: 1,461 articles / 514 authority_rules — `ingest/temp/` 보관, 비활성)

## KPI 목표 (PRD §24)
- citation 정확도 ≥95%
- 검색 성공 ≥85% (top-1 doc_id 일치)
- faithfulness ≥0.95 (hallucination ≤5%)
- 첫 토큰 <1s, 종단 <3s (p95)

## 사용자 결정사항 (변경 불가)
1. 형제 프로젝트 `knowledge-rag` 는 **참고만** (코드 직접 공유/모노레포 금지)
2. **Full-stack MVP** (Backend + Ingest + Next.js chat + Admin UI)
3. **인증 제외** (스키마에 `access_role` placeholder 만)
4. **17개 PDF 전부** 파싱 대상
5. **LangGraph** state machine (imperative pipeline 아님)
6. **하이브리드 질문 구체화** (HyDE 내부 + clarify 외부)

## 다음 액션 (post-MVP, KPI 보강)
1. **Citation 보강** (현재 69.2% → 목표 ≥95%)
   - generator prompt 에 `[근거]` 블록 필수 강제 + few-shot 예시
   - article_no 표기 표준화 (P01/P02/P05/P14 같이 사용자 친화 답변에 article_no 누락된 케이스)
2. **Retrieval top-1 보강** (현재 68.2% → 목표 ≥85%)
   - golden truth 의 `expected_doc_id` 단일 → `acceptable_doc_ids[]` 다중 허용
   - manual route boost — M02/M03 같은 매뉴얼 쿼리가 policy 로 misroute
   - 한국어 sparse 보강 (mecab / Python 3.13 + kiwipiepy)
3. **Latency 개선** (현재 first-token p95 10.8s → ≤1s)
   - clarifier prefilter (명확 query 는 LLM skip)
   - HyDE → dense embedding 대체 (LLM 1회 절약)
   - Claude Haiku 또는 prompt 압축
4. **M4 후속**:
   - authority hierarchical row 처리
   - process 매핑 정확도 (지금 "other" 89%)
   - admin CSV escape hatch (`POST /authority/csv`)
5. **이월 (M2 후속)**: manual/faq fallback chunker (0-chunk 2 docs)
6. **ragas baseline** — `python scripts/eval_ragas.py --ragas` 1회 측정해서 faithfulness/answer_relevancy 기준점 잡기

## 출처
- `docs/enterprise_policy_rag_prd_full.md`
- `docs/mvp_plan.md`
- `project-wiki/CLAUDE.md`
