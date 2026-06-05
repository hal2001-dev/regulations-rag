# Generation — gpt-4o-mini + 5-block prompt

**상태**: active
**마지막 업데이트**: 2026-05-27 (M3 완료)
**관련 페이지**: [retrieval.md](retrieval.md), [citation.md](citation.md), [../api/endpoints.md](../api/endpoints.md)

## 요약
gpt-4o-mini streaming. system prompt 가 `[결론][근거][적용 조건][절차][주의]` 5-block 출력 강제. LangChain ChatOpenAI 의 `astream()` 으로 token 청크가 LangGraph 의 `astream_events` 를 통해 SSE 로 forward.

## Prompt (요지)
- "주어진 [컨텍스트] 의 조항만 근거로. 컨텍스트에 없는 정보는 만들지 마세요."
- 5 블록 헤더를 한 줄로 시작, 그 다음 줄에 내용.
- `[근거]` 는 `[doc_id={N}, {조항}] {요약}` 형식 강제.

전체 prompt 는 `packages/rag/nodes/generator_node.py:SYSTEM_PROMPT`.

## SSE 이벤트 흐름

```
event: route        data: {"route":"policy"}
event: sources      data: {"sources":[{...}, ...8개]}
event: token        data: {"token":"["}
event: token        data: {"token":"결"}
... (수십~수백 토큰)
event: citation     data: {"valid_pct":1.0,"valid":[true,...]}
event: done         data: {"route":"policy","citation_valid_pct":1.0,"session_id":"...","timings":{retriever:0.04,generator:5.4}}
```

## Citation 검증 (`citation_validator`)
- `[근거]` 블록 추출 → `\[doc_id=(\d+)[,|]([^]]+)\]` 매칭.
- LLM 이 콤마 대신 파이프(`|`) 또는 article_no 뒤에 title (`제2조 직무`) 을 붙이는 변종 모두 수용.
- 매칭된 (doc_id, article_no) 가 retrieved sources 에 있는지 prefix 확인.

## 측정 결과 (5 sample query)
| 지표 | 값 |
|---|---|
| 첫 토큰 latency | **3.5s** (OpenAI API 자체 latency 의 영향) |
| 평균 generation 시간 | 3-7s |
| citation_valid_pct | **5/5 = 100%** (KPI ≥90%) |
| 총 token / 답변 | 평균 ~150 token |

## KPI 미달 (첫 토큰 <1s)
mvp_plan §M3 의 "첫 토큰 <1s" 는 OpenAI gpt-4o-mini API 자체 cold-start (보통 1~3s) 한계로 미달. 후속 옵션:
1. Anthropic Claude Haiku 4.5 (더 빠른 첫 토큰)
2. 로컬 LLM (Ollama, gpt-oss) — 비용/품질 trade-off
3. system prompt 압축 (현재 약 400 token)
4. 사용자 체감 개선: skeleton UI (M5 에서 chip + 진행상태 표시)

## 코드 위치
- `packages/rag/nodes/generator_node.py` — system prompt + astream
- `packages/rag/nodes/citation_validator.py` — `[근거]` 매칭

## 출처
- `docs/mvp_plan.md` §M3, §Generation 정책
- 2026-05-27 5 query 측정
