# Data Spec — 현재 데이터셋 (4 PDF)

**상태**: active
**마지막 업데이트**: 2026-06-05 (데이터셋 전면 교체)
**관련 페이지**: [../features/authority_matrix.md](../features/authority_matrix.md), [../features/citation.md](../features/citation.md), [../glossary.md](../glossary.md)

## 요약
`./ingest/` 루트에 비치된 **4개 PDF** 가 현재 색인 대상. doc_type 은 파일명 휴리스틱(`doc_type_classifier.py`) 으로 자동 분류. 2026-06-05 에 기존 17 PDF 데이터셋을 전부 삭제하고 본 4개로 재색인했다.

> **이전 17 PDF 데이터셋**은 `ingest/temp/` 로 이동되어 보관 중 (색인 대상 아님). 이전 측정값/golden 쿼리(`tests/e2e/golden_queries.yaml`) 는 옛 데이터셋 기준이라 현 데이터셋과 맞지 않음 — eval 재작성 필요.

## 현재 4개 PDF 표

| doc_id | 파일명 | doc_type | 비고 |
|---|---|---|---|
| 1 | `개인용자동차보험약관.pdf` (19MB) | policy | 168 page, Docling 변환 ~60s |
| 2 | `공무원여비규정.pdf` | policy | 22 page |
| 3 | `레저보험약관.pdf` | policy | 90 page |
| 4 | `사무위임전결규정.pdf` | **authority_matrix** | ★ 위임전결 — authority_rules 282행 추출 완료 (2026-06-05) |

**분류 분포**: policy 3 / authority_matrix 1 = 4. (보험약관 도메인 2 + 여비 1 + 위임전결 1)

## doc_type 분류 휴리스틱 (`doc_type_classifier.py`)

```python
def classify(filename: str) -> str:
    if re.search(r"위임전결|직무권한", filename):
        return "authority_matrix"
    if re.search(r"매뉴얼|가이드", filename):
        return "manual"
    if re.search(r"100문|문답|FAQ", filename, re.IGNORECASE):
        return "faq"
    return "policy"
```

→ 보험약관·여비규정은 키워드 미매칭으로 policy, 사무위임전결규정은 `위임전결` 매칭으로 authority_matrix. admin UI 에서 `user_doc_type` 으로 override 가능.

## 측정 결과 (2026-06-05 재색인)

| doc_id | title | doc_type | chunk_count | quality | 비고 |
|---|---|---|---|---|---|
| 1 | 개인용자동차보험약관 | policy | 303 | ok | 274,270 chars / 168 page / 114 articles → 303 chunks |
| 2 | 공무원여비규정 | policy | 39 | ok | 25,411 chars / 22 page |
| 3 | 레저보험약관 | policy | 208 | ok | 112,186 chars / 90 page |
| 4 | 사무위임전결규정 | authority_matrix | 29 | ok | 36,043 chars / 32 page. chunk 29 + authority_rules 282행 |

**합계**: 4 docs / 579 articles / Qdrant 579 points / 4 docs with chunks (zero-chunk 없음). authority_rules 282행 (doc_id=4).

## authority_rules 추출 (2026-06-05)
사무위임전결규정(doc_id=4) vision 추출 → **282 rules** (19/32 페이지에 표, amount 18 / % 0). 위임전결 SQL 정확 조회(차별점 1) 정상 동작.
> 1차 재색인 때는 OpenAI `429 insufficient_quota` 로 0행 실패 → 키 결제 정상화 후 `scripts/backfill_authority.py --doc-ids 4 --reset` 로 복구. 상세는 [../features/authority_matrix.md](../features/authority_matrix.md).

## 후속 (현 데이터셋 기준)
1. **golden 쿼리 / eval 재작성**: `tests/e2e/golden_queries.yaml` 은 옛 17 PDF 기준. 보험약관·여비·위임전결 도메인 쿼리로 교체 필요.
2. 0-chunk 문서 없음 — 이번 데이터셋엔 manual/faq fallback chunker 이슈 해당 없음.

## 출처
- `/Users/hal2001/workspace/projects/personal/regulations-rag/ingest/` 실제 파일 목록 (2026-06-05 ls)
- 2026-06-05 재색인 worker 로그 + `documents`/`articles` 테이블 + Qdrant `regulations` collection 측정
