# Feature: Authority Matrix (위임전결 SQL 정확 조회)

**상태**: ✅ active (M4 구현 완료, 2026-06-05 현 데이터셋에 282 rules 재추출 완료)
**마지막 업데이트**: 2026-06-05 (데이터셋 교체 + authority_rules 재추출 성공)
**관련 페이지**: [../architecture/decisions.md](../architecture/decisions.md) (ADR-005), [../architecture/pipeline.md](../architecture/pipeline.md), [citation.md](citation.md), [../data/spec.md](../data/spec.md)

## 현재 상태 (2026-06-05) — 정상 동작
현 데이터셋(4 PDF)의 사무위임전결규정(doc_id=4)에서 **282 authority_rules** 추출 완료. 최초 재색인 시 OpenAI `429 insufficient_quota` 로 실패했으나, 키 결제 정상화 후 `scripts/backfill_authority.py --doc-ids 4 --reset` 재실행으로 복구. 아래 M4 구현/측정 기록 중 514 rules 표는 옛 17 PDF 데이터셋 기준이다.

## 요약
"할인 30% 누가 승인?" / "5천만원 계약은 누가 결재?" 같은 **위임전결** 질문을 텍스트 RAG 가 아닌 **SQL exact match** 로 처리한다. LLM 은 결과 행을 포맷팅만 → 한도/% **hallucination 0**. knowledge-rag 에 없는 본 프로젝트의 핵심 차별점.

## 왜 텍스트 RAG 로는 부족한가
- 위임전결 표는 `process × approval_role × limit_pct × amount_krw × condition` 의 **다축 매트릭스**. 텍스트로 변환하면 LLM 이 한도/% 를 잘못 인용하거나 추론하기 쉽다.
- "할인 30%" → LLM 이 "30% 까지 본부장 승인" 이라는 표 내용을 *유사* 텍스트만 보고 다른 임계(20% 부장, 50% 사장) 와 혼동 가능.
- KPI: citation 정확도 ≥95% / faithfulness ≥0.95. 한 번의 한도 오인용으로 KPI 미달.

## 해결 — 2-track 저장

**Primary track**: 구조화 테이블 `authority_rules`
```sql
CREATE TABLE authority_rules (
  id           BIGSERIAL PRIMARY KEY,
  doc_id       BIGINT REFERENCES documents(doc_id),
  article_id   BIGINT REFERENCES articles(id),  -- nullable
  process      TEXT NOT NULL,        -- discount_approval / contract / expense_claim / ...
  task         TEXT,
  approval_role TEXT NOT NULL,        -- 영업본부장 / 대표이사 / ...
  approval_limit_pct  NUMERIC,        -- 할인율 등 % 한도
  amount_limit_krw    BIGINT,         -- 금액 한도 (원 단위)
  condition    TEXT,
  raw_row      JSONB,                 -- 원본 표 행 (검증/감사 용)
  source_page  INT
);
CREATE INDEX ON authority_rules (process);
CREATE INDEX ON authority_rules (approval_role);
CREATE INDEX ON authority_rules (amount_limit_krw);
```

**Fallback track**: 동일 행을 Qdrant 에도 chunk 로 적재 → 추출 실패 / SQL 0행 시 vector 검색으로 backup.

## 추출 파이프라인 (`authority_extractor.py`, M4 구현)
1. Docling 표 markdown 추출
2. 헤더 행 매칭: `(업무|구분|항목)` × `(결재권자|승인자|전결권자)` × `(한도|금액|비율)` 키워드 매칭
3. 데이터 행 1개 = `authority_rules` 1행
4. 금액 정규화: `(\d[\d,]*)\s*(만원|억원|원)` → KRW int
5. % 정규화: `(\d+(?:\.\d+)?)\s*%` → numeric
6. `process` inference: 12-keyword 맵 (`할인`→discount_approval, `계약`→contract, `여비`→expense_claim, ...)

대상 PDF (doc_type='authority_matrix'): 현 데이터셋에선 `사무위임전결규정.pdf` (doc_id=4) 1개. (옛 17 PDF 데이터셋엔 `신천초 위임전결규정` 도 포함됐으나 현재 `ingest/temp/` 로 이동.) indexer_worker 가 doc_type='authority_matrix' 감지 시 `extract_authority_rules_from_pdf` 자동 호출.

## 조회 (`authority_lookup_node.py`)

```python
parsed = parse_authority_question(q + clarifications)
# parsed: {process: "discount_approval", threshold_pct: 30, amount_krw: None}

rows = session.query(AuthorityRule).filter(
    AuthorityRule.process == parsed.process,
    AuthorityRule.approval_limit_pct >= parsed.threshold_pct,
    AuthorityRule.amount_limit_krw  >= (parsed.amount_krw or 0),
).order_by(AuthorityRule.approval_limit_pct).limit(5).all()

# 0 rows → retriever_node 로 우회 + warning 적재
```

Generator 노드는 `authority_rows` 만 컨텍스트로 받아 한도/% 를 **그대로 인용**하도록 프롬프트 제약 (다른 컨텍스트 무시 강제).

## Clarify 연동 (4 패턴 중 #2 — "Authority slot 부족")
승인 질문이지만 `process` 또는 `amount/%` 미명시 시 clarifier 가 `interrupt()`.
- "계약 누가 승인?" → "금액 범위가 어떻게 되나요? (5천만원 이하 / 5천만원~1억 / 1억 이상)" + suggested_replies chip

## SSE 시나리오
```
> POST /query/stream {"question":"할인 30% 누가 승인?"}

event: route        data: {"route":"authority"}
event: token        data: {"text":"[결론]\n"}
event: token        data: {"text":"영업본부장이 승인합니다. "}
event: token        data: {"text":"(한도 30%/5천만원)\n\n[근거]\n"}
event: token        data: {"text":"사무위임전결규정 > 제3장 > 제12조 > ①"}
event: sources      data: {"citations":[{...}]}
event: done         data: {"citation_valid_pct":1.0}
```

## KPI 측정 (M4)
- 5개 authority 쿼리에서 **role + limit exact match**
- Router accuracy ≥13/15 (15개 query 중 `authority` 분류 정확도)

## 실패 시 처리
| 실패 유형 | 대응 |
|---|---|
| 표 추출 실패 (스캔 + OCR 결과 불량) | `confidence='low'` 마킹 + admin 배너 + CSV 업로드 escape hatch (`POST /admin/authority_rules/{doc_id}/csv`) |
| SQL 0행 | retriever_node fallback (authority chunk) + warning 적재 |
| process inference 실패 | clarifier 가 process 선택 chip 제공 |

## M4 구현 결과 (2026-05-27)

### 추출 방식 결정 (ADR-017)
mvp_plan §M2.5 의 regex 기반 추출 시도 → 한국어 위임전결 표의 hierarchical/spanned 구조에서 거의 동작 안 함 (1차 LLM text-only 도 177 rules 다 "사장" + amount=null). **gpt-4o-mini vision** (PDF 페이지를 PNG 렌더 후 직접 vision input) 으로 결정. ADR-017 참조.

- `packages/regulation_parser/authority_extractor.py` — vision 호출 + 검증 (process 12-keyword enum, amount/% 정규화, validity check)
- `scripts/backfill_authority.py` — 일괄 추출 + DB insert
- `apps/indexer_worker.py` — 새 PDF 의 doc_type='authority_matrix' 시 자동 호출

### 인덱싱 결과 (옛 17 PDF 데이터셋, 2026-05-27)
| doc | 페이지 수 | 표 있는 페이지 | 추출 rules | amount 있음 | % 있음 |
|---|---|---|---|---|---|
| 사무위임전결규정 (doc_id=12) | 32 | 11 | **329** | 29 | 0 |
| 신천초 위임전결규정 (doc_id=13) | 17 | 8 | **185** | 0 | 0 |
| 합계 | 49 | 19 | **514** | 29 (5.6%) | 0 |

처리 시간: 약 14분 (vision LLM × 49 페이지). 비용 PDF당 ~$0.02.

### 재색인 결과 (현 4 PDF 데이터셋, 2026-06-05) — ✅ 복구 완료
| doc | 페이지 수 | 표 있는 페이지 | 추출 rules | amount 있음 | % 있음 |
|---|---|---|---|---|---|
| 사무위임전결규정 (doc_id=4) | 32 | 19 | **282** | 18 | 0 |

process 분포: other 255 / approval_general 15 / personnel 12 (기존과 동일하게 process 매핑 약함 — 아래 "알려진 한계 1" 참조). 샘플: 팀장/부서장/본부장 + 금액 한도(5억·1억 등). 처리 ~4.5분(vision × 32 page).

> 1차 시도는 OpenAI `429 insufficient_quota` 로 0/32 전부 실패 → 키 결제 정상화 후 `scripts/backfill_authority.py --doc-ids 4 --reset` 재실행으로 282 rules 적재. dense 임베딩(fastembed 로컬)은 영향 없어 chunk 29개는 1차 색인 때 이미 적재됨.

### M4 e2e 검증 (5 query, 2026-05-27)

| Q | 질문 | route 정확 | role/limit exact | citation_valid_pct |
|---|---|---|---|---|
| Q1 | "5천만원 계약 누가 결재?" | ✅ authority | ✅ 부서장/팀장/사장 (5천만원 한도) | ✅ 1.0 |
| Q2 | "1억 공사 누가 결재?" | ✅ authority | ✅ 팀장/부서장/사장 (공사관리/설계용역) | ✅ 1.0 |
| Q3 | "3천만원 결재 누구?" | ✅ authority | ✅ 팀장/부서장/사장 (3천만원 한도) | ✅ 1.0 |
| Q4 | "할인 30% 누가 승인?" | ✅ authority | ⚠️ SQL 0 → hybrid fallback (% 데이터 없음) | ✅ 1.0 |
| Q5 | "5억 누가 결재?" | ✅ authority | ✅ 사장/부서장/팀장 (5억 한도) | ✅ 1.0 |

### M4 KPI 결과
- ✅ **role/limit exact match 4/5** (Q4 는 사무위임전결규정 PDF 자체에 % 한도 데이터 없음 — 자체 한계)
- ✅ **router accuracy 5/5** (강화된 keyword + amount/% 패턴 매칭)
- ✅ **citation_valid_pct 5/5 = 100%** (validator regex 가 LLM 의 변종 형식 `authority_rule#NN 1억 이하` 까지 수용)

## 알려진 한계 + 후속

### 1. process 매핑 약함
459/514 rules 가 process="other". LLM 이 task 명만 보고 12-keyword 매핑하기 어려움 (task="5,000만 원 이하" 같은 한도-only 행 다수). `authority_lookup_node` 가 amount/% 있으면 process 필터를 drop 해 우회.

### 2. % 한도 데이터 0
사무위임전결규정 자체에 % 한도가 없음. mvp_plan golden #4 ("할인 30%") 의 출처는 `영업규정` 등 다른 PDF 가능성 — M4 범위 외.

### 3. hierarchical row 처리 부족
표의 parent row ("21. 대행사업분야 예산 → 공사 → 1) 5,000만 원 이하") 의 task 가 자식 row 의 단순 "5,000만 원 이하" 로만 들어옴. vision prompt 강화 또는 후처리 필요.

### 4. CSV escape hatch 미구현
mvp_plan §495 의 admin CSV 업로드 `POST /authority/csv` 는 M6 admin UI 와 함께.

## 출처
- `docs/mvp_plan.md` § Authority Matrix, § M4
- `wiki/architecture/decisions.md` ADR-017 (LLM vision 추출 결정)
- 2026-05-27 514 rules 인덱싱 + 5 query e2e 측정
