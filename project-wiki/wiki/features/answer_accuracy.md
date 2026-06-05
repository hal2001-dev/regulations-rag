# 규정·제도 질의 정확도 확보 방법

**상태**: active
**마지막 업데이트**: 2026-06-05
**관련 페이지**: [authority_matrix.md](authority_matrix.md), [citation.md](citation.md), [retrieval.md](retrieval.md), [generation.md](generation.md), [clarifier.md](clarifier.md), [ingestion.md](ingestion.md), [../overview.md](../overview.md)

## 요약
규정·제도 도메인의 질의는 일반 문서 검색과 정확도 기준이 다르다. "대략 맞는 요약"이 아니라 **어느 조항이 근거인지, 한도·비율·금액이 정확한지**가 답변 가치를 결정한다. 본 시스템은 단일 LLM 호출에 의존하지 않고, **(1) 인용 단위 = chunk 단위 일치 → (2) 위임전결의 구조화 SQL 조회 → (3) 계층적 인용 → (4) route별 검색 격리 → (5) 모호한 질문의 역질문 → (6) 컨텍스트 제약 생성 + 인용 검증** 의 6단계 파이프라인으로 정확도를 만든다. 이 페이지는 각 단계가 *어떤 부정확성 위험을 막는지* 를 한 곳에 정리한 플레이북이다.

---

## 규정 도메인에서 부정확성이 생기는 5가지 지점

| # | 위험 | 전형적 실패 | 일반 RAG 의 한계 |
|---|---|---|---|
| R1 | **조항 경계 절단** | chunk 가 `제12조 ②` 중간을 잘라 절반만 검색됨 | 고정 길이(512 token) chunking 이 조/항 경계 무시 |
| R2 | **한도·비율 hallucination** | "할인 30% → 본부장" 인데 "부장"으로 오인용 | 매트릭스 표를 텍스트로 평탄화 → LLM 이 임계값 혼동 |
| R3 | **인용 깨짐** | "23페이지"로 인용했는데 재발간으로 페이지 시프트 | page 번호 기반 인용은 문서 버전에 취약 |
| R4 | **오검색(misroute)** | 위임전결 질문에 보험약관 조항을 가져옴 | 전 문서를 한 풀에서 검색 → 도메인 혼입 |
| R5 | **질문 모호성** | "계약 누가 결재?"에 금액 미명시 → 임의 추정 | 모호해도 LLM 이 그냥 한 답을 지어냄 |

KPI 목표(PRD §24)는 citation 정확도 ≥95% / 검색 성공 ≥85% / faithfulness ≥0.95 이고, 위 5개 위험 중 하나만 터져도 미달한다. 그래서 정확도는 단일 기능이 아니라 **위험별 방어선의 합**이다.

---

## 정확도를 만드는 6가지 방법 (위험 → 대응)

### 1. 조항 단위 chunking — R1 방어
1 chunk = 1 `제N조` 를 원칙으로, 800 token 초과 시에만 `①②③` 항 단위로 분할한다. 항/호/목을 절대 중간 절단하지 않으므로 **검색 단위와 인용 단위가 일치**한다. chunk 본문 앞에 breadcrumb(`{문서명} > {장} > {조}`)을 prepend 해 chunk 자체가 self-contained 하고 BM25 recall 도 올린다.
→ 상세 [ingestion.md](ingestion.md), regex 는 [citation.md](citation.md) `structure.py` 표.

### 2. 위임전결의 구조화 SQL 조회 — R2 방어 (핵심 차별점)
위임전결처럼 `업무 × 결재권자 × 한도% × 금액 × 조건` 의 다축 매트릭스는 텍스트 RAG 로 처리하지 않는다. vision LLM 으로 표를 `authority_rules` 테이블(282행, doc_id=4)로 추출해 두고, 질문을 파싱해 **SQL exact match** 로 행을 가져온다. LLM 은 가져온 행을 포맷팅만 → 한도·금액 **hallucination 0**.
```sql
WHERE process = :proc AND amount_limit_krw >= :amount
ORDER BY approval_limit_pct LIMIT 5
```
SQL 0행이면 hybrid retrieval(authority_matrix 한정)로 fallback.
→ 상세 [authority_matrix.md](authority_matrix.md).

### 3. 계층적 인용 (heading_path) — R3 방어
인용은 page 번호가 아니라 `{문서명} > {장} > {조} > {항}` 으로 표시한다. Qdrant payload 는 `article_id` 만 들고, 렌더 시 **Postgres `articles` 를 source of truth 로 재조회**해 일관성을 보장한다(payload 가 stale 해도 인용은 정확). PDF 재발간으로 페이지가 밀려도 조항 인용은 유지된다.
→ 상세 [citation.md](citation.md).

### 4. route별 검색 격리 — R4 방어
router_node 가 질문을 `policy / authority / manual / faq` 로 분류하고, retriever 가 그 route 의 `doc_type` 으로 payload filter 를 건다. 위임전결 질문이 보험약관을 끌어오지 못하게 도메인을 격리한다. Dense(e5-large) + Sparse(BM25) 를 각각 30개 검색 후 **RRF(k=60)** 로 융합해 top-10 을 만든다. 필터 결과 0건이면 필터 해제 후 재검색하는 fallback 도 둔다.
→ 상세 [retrieval.md](retrieval.md).

### 5. 모호한 질문은 역질문(clarify) — R5 방어
질문이 모호하면 답을 지어내지 않고 되묻는다. clarifier 가 4 패턴(target_ambiguous / authority_slot / time_ambiguous / scope_wide)을 감지해 **confidence ≥ 0.7** 이고 선택지가 있을 때 `interrupt_before=clarify_pause` 로 멈추고 SSE `clarify` + quick-reply chip 을 보낸다. 예: "계약 누가 결재?" → "금액 범위가 어떻게 되나요?(5천만 이하 / ~1억 / 1억 이상)". 누적 2회 후엔 강제 통과(무한 역질문 방지).
→ 상세 [clarifier.md](clarifier.md).

### 6. 컨텍스트 제약 생성 + 인용 검증 — R2/R3 최종 방어선
generator 는 "주어진 [컨텍스트] 조항만 근거로, 없는 정보는 만들지 말 것" 제약 하에 `[결론][근거][적용 조건][절차][주의]` 5블록으로 답한다. `[근거]` 는 `[doc_id={N}, {조항}]` 형식을 강제한다. 그 뒤 citation_validator 가 `[근거]` 의 `(doc_id, article_no)` 를 실제 검색된 sources 와 대조해 `citation_valid_pct` 를 산출한다(LLM 의 콤마/파이프 변종 형식까지 수용).
> MVP 정책: 검증 실패해도 답변을 지우지 않고 경고만 부착 + 메트릭 누적. redaction 도입 여부는 eval 결과 보고 결정.
→ 상세 [generation.md](generation.md).

---

## 질문 유형별 정확도 경로

| 질문 유형 | 예시 | 경로 | 정확도 핵심 |
|---|---|---|---|
| 한도·결재권자 | "5천만원 계약 누가 결재?" | router→**authority_lookup(SQL)**→generator | 방법 2 (SQL exact) |
| 조항 내용 | "자동차보험 대인배상 보장범위?" | router→retriever→generator | 방법 1·3·4 |
| 절차·방법 | "출장 여비 청구 절차?" | router(manual/policy)→retriever→generator | 방법 4 (route) + 5블록 [절차] |
| 모호 | "계약 누가 결재?"(금액 무) | clarifier→**clarify_pause**→resume | 방법 5 (역질문) |

---

## 현재 정확도 수준 (ADR-019, 옛 17 PDF 30 query 기준)
| 지표 | 목표 | 현재 | 상태 |
|---|---|---|---|
| route 정확도 | — | 92.3% | ✅ |
| keyword 포함 | — | 83.3% | ✅ |
| citation 정확도 | ≥95% | 69.2% | ❌ carry-over |
| retrieval top-1 | ≥85% | 68.2% | ❌ carry-over |
| first-token p95 | <1s | 10.8s | ❌ (OpenAI 한계, ADR-016) |

> 위 수치는 **옛 17 PDF golden 기준**이라 현 4 PDF 데이터셋과 불일치 — eval 재작성이 선행 과제([data/spec.md](../data/spec.md)). citation/retrieval 미달의 후속 처방은 [overview.md](../overview.md) "다음 액션" 참조(인용 프롬프트 보강은 2026-05-28 1차 적용 완료).

## 정확도를 높이는 질문 작성 가이드 (사용자용)
- **문서/제도명을 포함**하면 route 정확도가 오른다. ("여비규정상 일당 한도")
- **한도 질문은 금액/비율을 명시**한다. ("5천만원 계약…") — 없으면 시스템이 되묻는다(방법 5).
- **조항을 알면 직접 지정**한다. ("개인용자동차보험약관 제12조") → top-1 검색에 유리.
- 답변의 `[근거]` chip 을 클릭하면 원문 조항으로 이동하니, **인용을 항상 검증**한 뒤 인용하라.

## 출처
- `docs/enterprise_policy_rag_prd_full.md` §24 (KPI)
- 기능 페이지: authority_matrix / citation / retrieval / generation / clarifier / ingestion
- `wiki/architecture/decisions.md` ADR-016/017/019
