# Evaluation

**상태**: active
**마지막 업데이트**: 2026-05-28
**관련 페이지**: [overview.md](../overview.md), [roadmap.md](../roadmap.md), [architecture/decisions.md](../architecture/decisions.md)

## 요약
M6 에서 30개 golden query 로 KPI 4종(citation/retrieval/route/latency) 자동 측정 인프라 도입. `tests/e2e/golden_queries.yaml` + `scripts/eval_ragas.py`. ragas faithfulness/answer_relevancy 는 `--ragas` 플래그로 옵션.

## 측정 방법

```bash
# 빠른 KPI (ragas 없이, ~5분, LLM 호출은 generator 만)
python scripts/eval_ragas.py
# ragas 포함 (LLM 호출 추가 비용)
python scripts/eval_ragas.py --ragas
```

각 query 는 `/query/stream` SSE 로 호출, 다음 metric 수집:
- **route_ok**: 기대 route 일치 (clarify 발동 시 None)
- **doc_ok**: top-1 source 의 `doc_id` 가 `expected_doc_id` 와 일치
- **kw_pct**: 답변 본문 안에 `expected_keywords` 가 얼마나 포함됐는지 (proxy)
- **citation_valid_pct**: `citation_validator` 노드가 채점한 valid 비율
- **first_token_sec / total_sec**: latency
- `--ragas`: faithfulness / answer_relevancy (LLM 평가)

집계: route_accuracy, top1_doc_hit, citation_valid_avg, keyword_recall_avg, first_token p50/p95, end-to-end p50/p95.

## 골든셋 구성 (30 query)
- **policy** ×15 — 11개 policy 문서 전반 (회계/감사/경비/여비/인사/이사회/영업/계약심사/상임이사보수 등). expected_doc_id 명시.
- **authority** ×10 — 위임전결 금액별/직위별 SQL exact 조회. amount 키워드 매칭 기반 채점.
- **manual / faq** ×5 — 교육활동 보호 / 자치법규 매뉴얼.

`tests/e2e/golden_queries.yaml`. 각 entry 는 `expected_route`, `expected_doc_id?`, `expected_keywords[]`.

## 실험 2026-05-28: M6 baseline

```
metric                      value          target  pass?
------------------------------------------------------------
citation 정확도                69.2%           ≥0.95  ❌
retrieval top-1             68.2%           ≥0.85  ❌
route accuracy              92.3%           ≥0.85  ✅
keyword recall              83.3%   ≥0.80 (proxy)  ✅
end-to-end p95             16.41s           ≤3.0s  ❌
first-token p95            10.79s           ≤1.0s  ❌
```

- 통과: route accuracy, keyword recall
- 미달: citation, retrieval top-1, latency 두 종
- clarify 발동 5건 (A03/A05/A10/M04 + 1): "1억원 계약 결재 권한" 같은 amount 단독은 process 슬롯 없어 clarifier 가 보수적 발동 — 정상 동작이나 KPI 채점에서 제외됨.

원인 분석:
1. **Citation 69.2%**: generator 의 답변에 `[근거]` 블록이 누락되거나 article_no 표기 다를 때 validator 매칭 실패. 일부 policy 쿼리에서 `[근거]` 자체 미생성 (e.g. P01/P02/P05/P14, M02/M03/M05). 후속: prompt 에 "[근거] 블록 필수" 강조 + few-shot 예시.
2. **Retrieval top-1 68.2%**: golden truth 가 "주된 문서" 단일이라 다중 문서에 분산된 답(e.g. 퇴직금 → 보수규정도 경비규정도 가능)이 패널티. 또 manual ↔ policy 가 헷갈리는 짧은 키워드 쿼리(M02/M03)가 doc_id 6 / 4 등 엉뚱한 doc 을 top-1. 후속: 골든셋에 `acceptable_doc_ids[]` 다중 허용 + manual 검색 boost.
3. **Latency p95 16.4s**: M3 결정사항 (ADR-016)과 일관. M5 에서 clarifier + rewriter 시리얼 LLM 호출 추가로 first-token 가 10s 대까지 늘어남. 후속(ADR-019 후보):
   - clarifier 와 rewriter 의 LLM 을 더 작은 모델(gpt-4o-mini → gpt-4o-mini still, but stream/parallel)
   - 명확 query 는 clarifier skip (heuristic prefilter)
   - HyDE를 dense embedding 으로 대체 (LLM 호출 1회 절약)
   - Claude Haiku 또는 prompt 압축

## 결과 파일
- `reports/eval.json` — aggregate + per-query scores (eval 실행 시 갱신)

## 후속 측정
- 동일 골든셋 + clarifier prompt 보강 후 재측정 (clarify 발동률 ↓)
- `--ragas` 한 번 실행해 faithfulness baseline 잡기
- citation prompt 보강 후 재측정 — **1차 적용 완료 (2026-05-28)**, 30-query 재측정 예정

## 사례 학습 2026-05-28: Generator prompt 보강 (M01 query)

질문 "교육활동 보호 매뉴얼에서 학생 폭언 대응 절차" 가 baseline 에서 citation_valid_pct=1.0 이지만 답변은 "절차가 명시되어 있지 않습니다" — *형식적 인용은 맞지만 의미적으로는 실패*. citation_valid 가 답변 정확도를 못 잡는 hole.

원인: generator 가 "학생 폭언" 정확한 단어가 sources 에 없다는 이유로 "내용 없음" 결론. 실제 sources 에는 "폭행, 모욕 등 침해행위 → 즉시 보호조치 → 관할청 보고" 가 충분히 있었음.

조치 (`packages/rag/nodes/generator_node.py` system prompt):
1. **의미적 용어 매핑 허용** — "학생 폭언" ↔ "폭행·모욕", "연차" ↔ "연가". "정확한 단어 없음" 으로 "내용 없음" 결론 금지.
2. **누락 금지** — 컨텍스트의 절차/조치/한도/기한/역할 모두 반영.
3. **다중 인용** — 관련 sources 최소 2~3개 [근거] 에 인용.
4. few-shot 예시 (학생 폭언 → 폭행·모욕).

결과: [결론] 구체화 + [근거] 1→2 + [절차] 단계화. Same sources, citation_valid_pct 동일 (1.0). generator 시간 3.3s → 13.4s (prompt 길이 + 답변 길이 trade-off).

후속: 30 query 재측정 시 citation 69.2% → 개선 폭 측정.

## 출처
- `docs/mvp_plan.md` §M6
- `scripts/eval_ragas.py`
- `tests/e2e/golden_queries.yaml`
- `reports/eval.json`
