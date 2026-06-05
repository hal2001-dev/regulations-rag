# Feature: Hierarchical Citation (heading_path 계층 인용)

**상태**: planned (구현 M3/M4)
**마지막 업데이트**: 2026-05-27
**관련 페이지**: [../architecture/decisions.md](../architecture/decisions.md) (ADR-006, ADR-007), [../architecture/pipeline.md](../architecture/pipeline.md), [authority_matrix.md](authority_matrix.md)

## 요약
Citation 을 page 번호가 아닌 **`{문서명} > {장} > {조} > {항}`** 형태의 `heading_path` 로 표시. 사용자가 답변의 근거를 조항 단위로 직접 인용 가능. PDF 재발간(페이지 번호 시프트) robust. KPI: citation 정확도 ≥95% 의 핵심.

## 왜 page 번호 인용은 부적합한가
- PDF 재발간 시 페이지 번호 시프트 → 인용 깨짐
- 조항이 페이지 경계에 걸치면 page 단독으로는 어느 조인지 불분명
- 사용자가 *원본* 인용을 다른 문서에 그대로 옮길 때 page 번호는 의미 없음 — `제12조 ②` 가 표준 인용 단위

## 핵심 — Postgres 가 source of truth

```
Qdrant payload: { article_id: 12345 }                    ← 가벼움
Postgres `articles` 테이블:                               ← citation 의 source of truth
  id=12345, doc_id=3, chapter='제2장 인사', section=NULL,
  article_no='제12조', article_title='연차휴가',
  paragraph='②', item=NULL,
  heading_path={chapter:'제2장 인사', article:'제12조 연차휴가', paragraph:'②'},
  qdrant_point_id='...', page=23
```

Render 시 Qdrant 결과의 `article_id` 로 Postgres 재조회 → 일관성 보장. Qdrant payload 가 stale 해도 citation 은 정확.

## heading_path 포맷

```json
{
  "doc_title": "인사관리규정",
  "chapter":   "제2장 인사",
  "section":   null,
  "article":   "제12조 (연차휴가)",
  "paragraph": "②",
  "item":      null
}
```

**렌더링**: `인사관리규정 > 제2장 인사 > 제12조 (연차휴가) > ②`

**CitationChip 클릭**: `/library/documents/{doc_id}?article=12` → 조 단위 본문 표시.

## chunk 경계 (ADR-006)
- 기본 1 chunk = 1 `제N조`
- >800 token → `①②③` (항) 단위 분할
- 항/호/목 중간 절단 금지 → citation 단위와 chunk 경계 **일치**
- breadcrumb (`{doc_title} > {chapter} > {article_no}`) 본문 앞 prepend → BM25 recall + self-contained chunk

## regex (`packages/regulation_parser/structure.py`)

```python
CHAPTER  = r"^제\s*\d+\s*장\s+(.+)$"
SECTION  = r"^제\s*\d+\s*절\s+(.+)$"
ARTICLE  = r"^제\s*\d+\s*조(?:의\d+)?\s*(?:\(([^)]+)\))?"   # 제2조의2 대응
PARA     = r"^[①-⑳]"
ITEM_NUM = r"^\d+\.\s"
ITEM_KOR = r"^[가-힣]\.\s"
APPENDIX = r"^별표\s*\d+|^별지\s*\d+"
```

엣지 케이스:
- `제2조의2` (삽입조) → `(?:의\d+)?` 처리
- `가목/나목/다목` → `ITEM_KOR`
- `①-⑳` → unicode range
- 별표/별지/부칙 → `article_no='별표 N'` 로 저장 (article 트리에 포함)
- 부칙 → `effective_date` heuristic 추출

## Citation Validator (`citation_validator.py`)

Generator 가 produce 한 `[근거]` 블록을 검증:
1. `[근거]` 블록에서 `(doc_id, article_no)` 추출
2. `state.sources` (retriever 가 적재한 후보) 와 매칭
3. 미매칭 `[결론]` 문장 → "근거 없음" 푸터 부착 (MVP 는 redaction 대신 경고로 측정)
4. `state.citation_valid_pct` 산출 → `query_logs` 적재

> **MVP 정책**: 검증 실패해도 답변 제거(redaction) 하지 않음. 경고만 부착하고 메트릭 누적. M6 Ragas eval 결과 보고 redaction 정책 도입 여부 결정.

## SSE 이벤트 (Frontend 렌더)
```
event: sources data: {
  "citations": [
    {
      "doc_id": 3,
      "article_no": "제12조",
      "heading_path": "인사관리규정 > 제2장 > 제12조 (연차휴가) > ②",
      "score": 0.87,
      "page": 23
    }
  ]
}
```

Frontend `<CitationChip>` 컴포넌트:
- 텍스트: heading_path
- 클릭 → `/library/documents/{doc_id}?article=12`
- 호버 → `[근거]` 본문 tooltip (M5/M6)

## KPI 측정 (M6 `eval_ragas.py`)
- `citation_exact_match`: `(doc_id, article_no, paragraph)` 모두 일치 → 95% 이상
- `tests/e2e/golden_queries.yaml` 30 쌍 기준

## 엣지 케이스 정리
| 케이스 | 처리 |
|---|---|
| `제2조의2` 삽입조 | regex `(?:의\d+)?` ✓ |
| `가목/나목/다목` | `ITEM_KOR` ✓ |
| `①-⑳` 항 마커 | unicode range ✓ |
| 별표/별지 | `article_no='별표 N'` 로 article 로 저장 |
| 부칙 | article 트리 포함 + `effective_date` heuristic |
| 교차참조 (`제5조 제2항 참조`) | MVP 는 텍스트만 저장, 그래프 해석 defer |
| 스캔 표 | OCR fallback (macOS Vision lang=ko-KR) → `extraction_quality='scan_only'` 마킹 |

## 다음 작업
1. M2 의 `structure.py` regex 작성 + 17 PDF 무작위 10 article 수동 검증
2. M3 의 retriever_node + citation_validator 구현
3. M6 의 `citation_exact_match` 측정값 본 페이지 append

## 출처
- `docs/mvp_plan.md` § Data Model (articles), § citation_validator, § Risks
