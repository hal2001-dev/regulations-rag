
# 사내 규정 RAG 시스템 PRD
## Enterprise Policy RAG Platform

---

# 1. 프로젝트 개요

## 프로젝트 목적

사내 규정, 업무 지침, 직무권한 규정, 운영 매뉴얼, FAQ 등을 통합 검색하고
자연어 질의응답이 가능한 Enterprise RAG 시스템 구축.

본 시스템은 단순 문서 검색이 아닌:

- 규정 기반 질의응답
- 승인 권한 확인
- 업무 절차 안내
- 근거 조항 citation
- 최신 규정 기반 응답

을 제공하는 것을 목표로 한다.

---

# 2. 핵심 목표

## Business Goal

- 사내 규정 검색 시간 단축
- 반복 문의 감소
- 업무 표준화
- 최신 규정 기반 응답 제공
- 승인 체계 명확화

## Technical Goal

- Hybrid Search 기반 Retrieval
- 문서 taxonomy 기반 검색
- Citation 기반 QA
- Hallucination 최소화
- Metadata 기반 Filtering

---

# 3. 주요 사용자

| 사용자 | 목적 |
|---|---|
| 일반 직원 | 규정 조회 |
| 팀장 | 승인 권한 확인 |
| 인사팀 | 인사 규정 대응 |
| 영업팀 | 할인/계약 기준 확인 |
| 보안팀 | 정책 확인 |
| 관리자 | 문서 관리 |

---

# 4. 지원 문서 유형

## Policy

- 인사규정
- 복무규정
- 영업규정
- 보안규정
- 구매규정
- 계약규정

## Authority Matrix

- 위임전결규정
- 직무권한 규정
- 승인 매트릭스

## Manual

- 업무 매뉴얼
- 시스템 사용 가이드
- SOP

## FAQ

- 자주 묻는 질문
- 사례 기반 문서

## Notice

- 공지사항
- 한시 정책

---

# 5. 문서 Taxonomy

## 목적

문서 성격에 따라 검색 전략과 retrieval 전략을 분리하기 위함.

## Taxonomy 구조

```text
doc_type
 ├─ policy
 ├─ authority_matrix
 ├─ guideline
 ├─ manual
 ├─ faq
 ├─ notice
 └─ template
```

## Domain

```text
- hr
- sales
- finance
- security
- procurement
- legal
- compliance
- it
```

## Process

```text
- leave
- attendance
- quotation
- contract
- discount_approval
- expense_claim
- payment
```

---

# 6. 문서 처리 파이프라인

```text
문서 업로드
    ↓
OCR / Parsing
    ↓
Markdown 변환
    ↓
문서 구조 분석
    ↓
taxonomy tagging
    ↓
metadata 생성
    ↓
chunk 생성
    ↓
embedding 생성
    ↓
vector db 저장
```

---

# 7. 문서 파싱 전략

## 지원 포맷

- PDF
- DOCX
- HWP
- XLSX
- PPTX
- Markdown

## OCR 대상

- 스캔 PDF
- 이미지 포함 문서
- 표 기반 문서

## 추천 OCR

- PaddleOCR
- Azure Document Intelligence
- Tesseract

---

# 8. Metadata 설계

## 공통 Metadata

```json
{
  "doc_id": "HR-POL-001",
  "document_name": "인사규정",
  "doc_type": "policy",
  "domain": "hr",
  "process": "leave",
  "version": "3.2",
  "effective_date": "2025-01-01",
  "status": "active",
  "department": "HR"
}
```

## 규정 Metadata

```json
{
  "chapter": "제2장 복무",
  "section": "제1절 근태",
  "article": "제12조",
  "paragraph": "②"
}
```

## 권한 규정 Metadata

```json
{
  "approval_role": "영업본부장",
  "approval_limit": "20%",
  "amount_limit": "5000만원"
}
```

---

# 9. Chunking 전략

## Policy

기본:

- 조(article) 단위 chunk

긴 조항:

- 항(paragraph) 단위 sub chunk

## Manual

- 업무 절차 단위
- 화면 단위
- 단계 단위

## FAQ

- Q/A 단위

## Authority Matrix

- 업무 + 승인권한 + 한도 기준

---

# 10. Retrieval 전략

## 검색 방식

Hybrid Search 사용.

```text
BM25 + Dense Embedding
```

## Query Routing

| 질문 유형 | 우선 검색 |
|---|---|
| 가능 여부 | policy |
| 승인권한 | authority_matrix |
| 처리 방법 | manual |
| 사례 질문 | faq |
| 한시 정책 | notice |

---

# 11. Vector DB 구조

## Collection 분리

```text
policy_index
manual_index
authority_index
faq_index
notice_index
```

## 추천 Vector DB

- Qdrant
- Weaviate
- OpenSearch
- Elasticsearch

---

# 12. Embedding 전략

## 추천 모델

- bge-m3
- multilingual-e5-large
- text-embedding-3-large

## 한국어 문서 특성

반드시 Hybrid Search 사용.

이유:

- exact keyword 많음
- 조항 번호 검색 많음
- 승인권한 검색 많음

---

# 13. 시스템 프롬프트 정책

## 핵심 원칙

- 검색 문서 기반 답변만 허용
- 검색되지 않은 정보 추론 금지
- citation 없는 답변 금지
- 규정 우선 원칙 적용
- 권한 질문은 authority_matrix 우선
- 방법 질문은 manual 우선

## 충돌 처리

우선순위:

```text
policy
→ authority_matrix
→ guideline
→ manual
→ faq
→ notice
```

---

# 14. 응답 포맷

```text
[결론]

[근거]
- 문서명
- 조항
- 내용

[적용 조건]

[절차]

[주의]
```

## 예시

```text
[결론]
연차휴가는 가능합니다.

[근거]
인사규정 제12조 제2항에 따르면
연차휴가는 부서장 승인을 받아 사용할 수 있습니다.

[절차]
HR 시스템에서 신청 후 승인 요청.

[주의]
긴급 휴가는 별도 승인 필요.
```

---

# 15. Citation 정책

## Citation 형식

```text
인사규정 > 제2장 복무 > 제12조 > ②
```

## 필수 항목

- 문서명
- 조항
- 시행일
- 버전

---

# 16. 권한 관리

## Access Control

- RBAC
- 부서별 접근 제한
- 문서 등급 제한
- SSO 연동

## Security Level

```text
public
internal
confidential
restricted
```

---

# 17. 관리자 기능

## 문서 관리

- 업로드
- 수정
- 폐기
- 버전 관리

## 시스템 관리

- taxonomy 수정
- metadata 수정
- chunk 재생성
- embedding 재생성
- index rebuild

## 모니터링

- 검색 로그
- 실패 질문
- retrieval 정확도
- hallucination 비율

---

# 18. 검색 로그 분석

## 수집 항목

- 질문
- 검색 결과
- 선택 문서
- 응답 성공 여부
- 사용자 피드백

## 활용 목적

- taxonomy 개선
- retrieval 개선
- FAQ 생성
- prompt tuning

---

# 19. 비기능 요구사항

## 성능

| 항목 | 목표 |
|---|---|
| 검색 응답 | 3초 이내 |
| 업로드 처리 | 1분 이내 |
| chunk 생성 | 비동기 |

## 안정성

- 재색인 가능
- embedding 재생성 가능
- chunk 재생성 가능

---

# 20. 기술 스택

## Frontend

- Next.js
- TypeScript
- Tailwind
- Shadcn UI

## Backend

- FastAPI
- NestJS

## RAG Stack

- LangChain
- LlamaIndex
- Docling
- Unstructured

## Storage

- PostgreSQL
- Redis
- Qdrant

---

# 21. 관리자 UI 요구사항

## Dashboard

- 업로드 현황
- 문서 통계
- 검색 성공률
- 인기 질문

## 문서 관리 화면

- taxonomy 수정
- metadata 수정
- 문서 상태 변경
- chunk 미리보기

---

# 22. MVP 범위

## 포함

- 문서 업로드
- OCR
- taxonomy tagging
- Hybrid Search
- Citation QA
- 관리자 화면

## 제외

- Workflow automation
- 음성 인터페이스
- 자동 규정 비교
- 다국어 지원

---

# 23. 향후 확장

- Slack 연동
- Teams 연동
- 사내 그룹웨어 연동
- 결재 시스템 연동
- 권한 자동 판별
- AI Workflow Recommendation

---

# 24. 성공 KPI

| KPI | 목표 |
|---|---|
| 검색 성공률 | 85% 이상 |
| Citation 정확도 | 95% 이상 |
| Hallucination 비율 | 5% 이하 |
| 응답 시간 | 3초 이하 |
| 반복 문의 감소 | 30% 이상 |

---

# 25. 핵심 설계 원칙

```text
1. 규정을 구조화된 지식으로 관리한다
2. taxonomy 기반 retrieval 수행
3. 문서 유형별 retrieval 분리
4. 최신성 관리 우선
5. citation 없는 답변 금지
6. semantic search만 의존하지 않는다
7. hybrid retrieval 사용
8. 권한 규정 우선 처리
```
