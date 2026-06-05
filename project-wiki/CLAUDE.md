# regulations-rag Project Wiki — Schema & Operations

이 파일은 LLM 이 프로젝트 위키를 어떻게 구축·유지할지 정의합니다.
**모든 세션 시작 시 이 파일을 먼저 읽고, `wiki/index.md` 와 `wiki/log.md` 최근 항목을 확인하세요.**

> Inspired by [karpathy's LLM Wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) — 3-layer 구조: **raw/** (immutable) / **wiki/** (LLM 관리) / **CLAUDE.md** (schema).

---

## 디렉토리 구조

```
project-wiki/
├── CLAUDE.md                       ← 이 파일 (스키마)
├── raw/                            ← 원본 (절대 수정 금지)
│   ├── requirements/               ← PRD, 기획서
│   ├── research/                   ← 참고 자료 (karpathy gist 등)
│   ├── meetings/                   ← 회의록 원문
│   ├── issues/                     ← 이슈 원문 (스택 트레이스 등)
│   ├── reviews/                    ← PR/코드 리뷰 원문
│   └── data/                       ← 샘플 데이터, 스펙 문서
└── wiki/
    ├── index.md                    ← 전체 페이지 카탈로그 (항상 최신 유지)
    ├── log.md                      ← 작업 이력 (append-only)
    ├── changelog.md                ← 버전별 변경 이력
    ├── overview.md                 ← 프로젝트 전체 요약 및 현재 상태
    ├── roadmap.md                  ← M1-M6 마일스톤
    ├── glossary.md                 ← 용어 사전 (규정 도메인 + RAG 기술)
    ├── references.md               ← 참고 자료 링크
    ├── security.md                 ← API 키 관리, 민감 데이터 처리
    ├── architecture/
    │   ├── decisions.md            ← ADR (Architecture Decision Records)
    │   ├── pipeline.md             ← LangGraph 그래프 + ingestion flow
    │   └── stack.md                ← 기술 스택 및 선택 이유
    ├── features/
    │   ├── ingestion.md            ← Docling + regulation_parser
    │   ├── embedding.md            ← bge-m3 + Kiwi-BM25
    │   ├── retrieval.md            ← Hybrid + RRF + rerank
    │   ├── generation.md           ← LLM prompt + [결론]/[근거] 포맷
    │   ├── authority_matrix.md     ← ★ 위임전결 SQL 조회 (차별점)
    │   ├── citation.md             ← ★ heading_path 계층 인용 (차별점)
    │   └── evaluation.md           ← Ragas + 실험 누적
    ├── data/
    │   ├── spec.md                 ← 17개 PDF 목록 + doc_type 분류
    │   ├── pipeline.md             ← 데이터 흐름 (수집 → 전처리 → 저장)
    │   └── quality.md              ← 데이터 품질 기준 및 검증
    ├── api/
    │   └── endpoints.md            ← FastAPI 엔드포인트 + SSE 이벤트 스펙
    ├── testing/
    │   ├── strategy.md             ← 테스트 전략
    │   └── cases.md                ← 골든 쿼리, 케이스
    ├── deployment/
    │   ├── runbook.md              ← 배포/롤백 절차
    │   └── monitoring.md           ← 모니터링 지표
    ├── config/
    │   ├── environments.md         ← dev/staging/prod
    │   └── dependencies.md         ← 라이브러리 버전 (LangGraph 등)
    ├── onboarding/
    │   └── setup.md                ← 개발 환경 셋업
    ├── troubleshooting/
    │   └── common.md               ← 자주 발생하는 에러 + 해결법
    ├── meetings/                   ← 회의록 요약 (YYYY-MM-DD-제목.md)
    ├── issues/
    │   ├── open/                   ← ISSUE-NNN.md
    │   └── resolved/
    └── reviews/
        ├── patterns.md             ← 반복 패턴 & 컨벤션
        └── PR-NNN.md
```

---

## 페이지 공통 형식

```markdown
# 페이지 제목

**상태**: [active|draft|deprecated]
**마지막 업데이트**: YYYY-MM-DD
**관련 페이지**: `다른 페이지 링크`

## 요약
(2~3줄 핵심 설명)

## 본문
...

## 출처
- raw/requirements/xxx.md
```

---

## 이슈 페이지 형식

```markdown
# ISSUE-NNN: 이슈 제목

**상태**: [open|in-progress|resolved]
**발생일**: YYYY-MM-DD
**해결일**: YYYY-MM-DD
**관련 기능**: `features/xxx.md`

## 증상
## 원인 분석
## 해결 방법
## 재발 방지
```

---

## PR 리뷰 페이지 형식

```markdown
# PR-NNN: 제목

**날짜**: YYYY-MM-DD
**리뷰어**:
**상태**: [open|approved|changes-requested|merged]
**관련 기능**: `features/xxx.md`

## 변경 내용
## 리뷰 의견
- [ ] 지적 사항
- [x] 해결됨: 지적 사항
## 반영된 결정
```

---

## 회의록 페이지 형식

```markdown
# YYYY-MM-DD: 회의 제목

**참석자**:
**관련 페이지**: `xxx.md`

## 논의 내용
## 결정 사항
- 결정 1 → [decisions.md](wiki/architecture/decisions.md) 반영 필요
## 액션 아이템
- [ ] 담당자: 할 일 (기한)
## 다음 회의
```

---

## ADR 형식 (decisions.md)

```markdown
## ADR-NNN: 결정 제목

**일자**: YYYY-MM-DD
**상태**: [proposed|accepted|deprecated|superseded by ADR-XXX]

### 배경
### 결정
### 대안
### 결과
```

---

## Operations

### 1. Ingest (새 정보 추가)

새 소스(기획서, 회의록, 이슈 등)가 생겼을 때:

1. 원본을 `raw/` 적절한 폴더에 저장
2. 핵심 내용 논의
3. 관련 wiki 페이지 업데이트 또는 신규 생성
4. `wiki/index.md` 갱신
5. `wiki/log.md` 에 항목 추가:
   ```
   ## [YYYY-MM-DD] ingest | 제목
   - 영향받은 페이지: xxx.md, yyy.md
   - 주요 변경: 한 줄 요약
   ```
6. `wiki/overview.md` 진행 상황 업데이트

**하나의 소스가 여러 페이지에 영향을 줄 수 있음. 모두 업데이트할 것.**

### 2. Query (질문에 답변)

1. `wiki/index.md` 먼저 확인
2. 관련 페이지 읽기
3. 답변 생성 + 출처 명시
4. 답변이 새로운 인사이트라면 wiki 페이지로 저장 제안

### 3. Issue 등록 / 해결

등록 시:
1. `raw/issues/ISSUE-NNN-제목.md` 저장
2. `wiki/issues/open/ISSUE-NNN.md` 생성
3. 관련 feature 페이지 cross-link 추가
4. 반복 가능성 있으면 `wiki/troubleshooting/common.md` 에도 추가

해결 시:
1. `wiki/issues/open/` → `wiki/issues/resolved/` 이동
2. 해결 방법 및 재발 방지 추가
3. `wiki/troubleshooting/common.md` 업데이트

### 4. 코드 리뷰

1. `raw/reviews/PR-NNN-제목.md` 저장
2. `wiki/reviews/PR-NNN.md` 생성
3. 설계 결정 → `wiki/architecture/decisions.md` 반영
4. 반복 패턴 → `wiki/reviews/patterns.md` 누적
5. `wiki/log.md` 업데이트

### 5. 회의

1. `raw/meetings/YYYY-MM-DD-제목.md` 저장
2. `wiki/meetings/YYYY-MM-DD-제목.md` 요약 생성
3. 결정 사항 → `wiki/architecture/decisions.md` 반영
4. 액션 아이템 → `wiki/overview.md` 할 일 목록 반영
5. 로드맵 변경 시 → `wiki/roadmap.md` 업데이트

### 6. 릴리즈 / 버전 업

1. `wiki/changelog.md` 항목 추가
2. `wiki/overview.md` 진행 상황 업데이트
3. `wiki/roadmap.md` 완료 항목 체크
4. `wiki/config/dependencies.md` 버전 업데이트

### 7. Lint (건강 체크)

`"wiki lint 해줘"` 실행 시:

- [ ] open 이슈 중 실제 해결된 것은 없는가
- [ ] overview.md 진행 상황이 최신인가
- [ ] decisions.md 결정이 실제 구현과 일치하는가
- [ ] 링크가 끊어진 페이지는 없는가
- [ ] 고아 페이지(inbound link 없는 페이지)는 없는가
- [ ] 아직 페이지가 없는 중요 개념은 없는가
- [ ] troubleshooting 에 없는 반복 이슈는 없는가
- [ ] roadmap 마일스톤 날짜가 지났는데 미완료인 항목은 없는가
- [ ] security.md 의 API 키/민감 정보 관리 지침이 최신인가
- [ ] dependencies.md 버전이 실제 코드와 일치하는가
- [ ] glossary.md 에 없는 새 용어가 본문에 등장하지 않는가

---

## regulations-rag 도메인 특화 규칙

### 규정 파싱 결정 변경 시
조/항/호/목 파싱 규칙(`regulation_parser/structure.py`)이 바뀌면 반드시:
- `wiki/features/ingestion.md` regex 표 갱신
- `wiki/data/quality.md` 추출 품질 기준 재검토
- `wiki/data/spec.md` 의 17 PDF 분류 영향 여부 확인

### Authority Matrix 추출 결과 기록
새 위임전결 문서 추가 또는 추출 정확도 변경 시:
- `wiki/features/authority_matrix.md` 에 추출 row 수, confidence 분포 기록
- 실패 케이스 → `wiki/issues/open/` 등록

### Citation 정책 변경 시
heading_path 포맷(`인사규정 > 제2장 > 제12조 > ②`) 변경은 frontend 영향:
- `wiki/features/citation.md` 갱신
- `wiki/api/endpoints.md` SSE `sources` 이벤트 스펙 갱신
- ADR 항목 작성

### LangGraph 노드 추가/변경 시
- `wiki/architecture/pipeline.md` 그래프 다이어그램 갱신
- `wiki/features/` 해당 노드 페이지 갱신
- State 필드 변경 시 모든 노드 영향 검토

### 실험 결과 기록 (RAG 공통)
임베딩 모델, chunk size, retrieval 전략 변경 시:

```markdown
## 실험 YYYY-MM-DD: 변경 내용 요약
- 변경: chunk_size 512 → 256
- 이유: 긴 청크에서 관련 없는 내용 포함 문제
- 결과: precision +8%, recall -2%
- 결론: 유지 / 롤백 / 추가 실험 필요
```

`wiki/features/evaluation.md` 에 누적 기록.

### 성능 지표 추적
`wiki/features/evaluation.md` 에 항상 최신 지표 유지:
- Retrieval: Precision@K, Recall@K, Hit@3, MRR
- Generation: faithfulness, answer_relevancy, citation_exact_match
- 시스템: TTFT(첫 토큰), end-to-end p95 latency, 인덱싱 속도

### KPI 목표 (PRD §24)
| 지표 | 목표 |
|---|---|
| 검색 성공률 | 85% 이상 |
| Citation 정확도 | 95% 이상 |
| Hallucination 비율 | 5% 이하 |
| 응답 시간 (p95) | 3초 이하 |

---

## 진행 상태 레이블

| 레이블 | 의미 |
|--------|------|
| `todo` | 구현 예정 |
| `in-progress` | 개발 중 |
| `done` | 완료 |
| `blocked` | 다른 이슈/결정으로 막힘 |
| `experimental` | 실험적, 미확정 |
| `deprecated` | 더 이상 사용 안 함 |
| `needs-review` | 리뷰 필요 |

---

## 세션 시작 루틴

매 세션 시작 시 반드시:
1. 이 파일(CLAUDE.md) 읽기
2. `wiki/log.md` 최근 5개 항목 확인
3. `wiki/issues/open/` 확인
4. `wiki/overview.md` 현재 상태 확인
5. 사용자에게 브리핑 후 작업 시작
