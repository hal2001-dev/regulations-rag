# Wiki Index

**상태**: active
**마지막 업데이트**: 2026-06-08 (ISSUE-001 해결: 별표 청킹+linearization+reranker / clarifier.md 작성)

wiki 내 모든 페이지의 단일 카탈로그. 새로운 페이지를 추가할 때마다 본 index 도 함께 갱신할 것. 답변/탐색 시 가장 먼저 읽는다.

---

## 운영 (Operations)
- [log.md](log.md) — 작업 이력 (append-only, `## [YYYY-MM-DD] op | summary` 포맷)
- [changelog.md](changelog.md) — 버전별 변경 (TODO)

## 프로젝트 전체
- [overview.md](overview.md) — 현재 상태, 차별점, 진행률 한 눈에
- [roadmap.md](roadmap.md) — M1~M6 마일스톤 + KPI
- [glossary.md](glossary.md) — 규정 도메인(조/항/호/목, 위임전결) + RAG 기술(RRF, HyDE) 용어 사전
- [references.md](references.md) — 외부 참고 자료 (TODO)
- [security.md](security.md) — API 키 관리, PII 처리 (TODO)

## Architecture
- [architecture/decisions.md](architecture/decisions.md) — ADR (단일 collection, indexer 분리, LangGraph 채택 등 13개)
- [architecture/pipeline.md](architecture/pipeline.md) — LangGraph state machine 그래프 + ingestion flow
- [architecture/stack.md](architecture/stack.md) — 기술 스택 + 선택 이유

## Features
- [features/authority_matrix.md](features/authority_matrix.md) — ✅ active. 위임전결 SQL 정확 조회 (차별점 1). 현 데이터셋(4 PDF)에 282 rules 추출 완료 (2026-06-05, vision LLM)
- [features/citation.md](features/citation.md) — ★ heading_path 계층 인용 (차별점 2)
- [features/ingestion.md](features/ingestion.md) — Docling + regulation_parser (✅ M2 완료. 2026-06-08 별표 본문 경계 인식 추가 — [ISSUE-001](issues/resolved/ISSUE-001.md). 후속: 표 행단위 분할 + fallback chunker)
- [features/embedding.md](features/embedding.md) — ✅ M3, multilingual-e5-large + Qdrant/bm25 (ADR-014/015 로 대체 결정)
- [features/retrieval.md](features/retrieval.md) — ✅ M3 hybrid dense+sparse + RRF. **2026-06-08 cross-encoder reranker(bge-reranker-base) 연결 — 검색 정확도 핵심 ([ISSUE-001](issues/resolved/ISSUE-001.md))**
- [features/generation.md](features/generation.md) — ✅ M3, gpt-4o-mini stream + 5-block prompt + citation_validator
- [features/clarifier.md](features/clarifier.md) — ✅ M5, 4 패턴 LLM 감지 + interrupt_before + /query/resume
- [features/evaluation.md](features/evaluation.md) — ✅ M6, 30 golden queries + KPI 자동 측정 + ragas 옵션. baseline 기록.
- [features/answer_accuracy.md](features/answer_accuracy.md) — ★ 규정·제도 질의 정확도 확보 방법 (위험 5종 → 방어 6단계 플레이북 + 질문 작성 가이드)

## Data
- [data/spec.md](data/spec.md) — 현재 4 PDF 데이터셋 (2026-06-05 교체, 옛 17 PDF 는 ingest/temp 보관) + doc_type 분류
- [data/pipeline.md](data/pipeline.md) — 데이터 흐름 (TODO, M2)
- [data/quality.md](data/quality.md) — 품질 기준 + 검증 (TODO, M2)

## API
- [api/endpoints.md](api/endpoints.md) — ✅ M3 기준 (M4/M5 SSE 이벤트 `clarify`/`rewrite` + `POST /query/resume` 추가 반영 필요).

## Testing
- [testing/strategy.md](testing/strategy.md) — 테스트 전략 (TODO)
- [testing/cases.md](testing/cases.md) — 골든 쿼리 → `tests/e2e/golden_queries.yaml` 로 코드 측에 보관 (M6)

## Deployment
- [deployment/runbook.md](deployment/runbook.md) — 배포/롤백 절차 (TODO)
- [deployment/monitoring.md](deployment/monitoring.md) — 모니터링 지표 (TODO)

## Config
- [config/environments.md](config/environments.md) — dev/staging/prod (TODO)
- [config/dependencies.md](config/dependencies.md) — 라이브러리 버전 (TODO, M1 코드 작업 시)

## Onboarding
- [onboarding/setup.md](onboarding/setup.md) — 개발 환경 셋업 (TODO, M1 코드 작업 시)

## Troubleshooting
- [troubleshooting/common.md](troubleshooting/common.md) — ✅ 자주 발생하는 에러 4종 (별표 검색 실패 / 조문 흡수 / HTML entity / 포트 불일치)

## Meetings / Issues / Reviews
- `meetings/` — 회의록 (없음)
- `issues/open/` — (없음)
- [issues/resolved/ISSUE-001.md](issues/resolved/ISSUE-001.md) — ✅ resolved. 별표 거대 청크 검색 실패 → 별표 청킹 + linearization + HyDE 수정 + **reranker(결정타)** 로 해결 (2026-06-08)
- `reviews/patterns.md`, `reviews/PR-NNN.md` — 코드 리뷰 (없음)

---

## Raw 자료 (immutable, 수정 금지)
- [`../raw/requirements/PRD.md`](../raw/requirements/PRD.md) — Enterprise Policy RAG PRD 원본
- [`../raw/requirements/mvp_plan.md`](../raw/requirements/mvp_plan.md) — MVP 구현 계획 원본
- [`../raw/research/karpathy-llm-wiki.md`](../raw/research/karpathy-llm-wiki.md) — karpathy LLM Wiki gist 원문

---

## 출처
- 본 카탈로그 구조: [`project-wiki/CLAUDE.md`](../CLAUDE.md)
- 상위 계획: [`docs/mvp_plan.md`](../../docs/mvp_plan.md)
