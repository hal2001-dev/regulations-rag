# ISSUE-001: 별표(부표)가 단일 거대 청크로 뭉쳐 검색 실패

**상태**: resolved (청킹 구조 + retrieval 모두 ✅ — 아래 "최종 해결" 참조)
**발생일**: 2026-06-08
**해결일**: 2026-06-08
**관련 기능**: [features/ingestion.md](../../features/ingestion.md), [features/retrieval.md](../../features/retrieval.md)

## TL;DR
별표가 거대 청크에 뭉쳐 표(일비 등) 검색이 실패하던 문제. **4단계**로 해결했고, 각 기여를 ablation 으로 확인:
1. **별표 청킹** — `■[별표N]`/제목헤더 경계 인식으로 별표를 독립 청크화 (구조 토대, 단독으론 회귀)
2. **table linearization** — 표를 `구분 제2호: 일비 25,000` 행 문장 청크로 (reranker 가 잡을 후보 제공)
3. **HyDE 수정** — 거짓 "별표 1" 환각 제거 (검색 오염 차단)
4. **reranker (결정타)** — cross-encoder 가 "국내 2호 일비"↔별표 2 를 +3.5 로 정밀 매칭, 국외(별표 4)를 음수로 밀어냄
- **ablation 결론**: 같은 청킹에서 rerank OFF→실패 / ON→1위. **reranker 가 성능 1등**, linearization 은 후보를 깔아주는 보조. 정규식 일반화로 별표 6→9개 전수 인식.

## 증상
- 외부 RAG 비교 중 발견: "국내여비규정에서 2호구분에 해당하는 공무원의 **일비**는?" → 검색 실패.
  같은 질문에 "**하루** 일비는?" 처럼 단어 하나를 바꾸면 검색 성공.
- 본 시스템에서도 연차/일비류 질의의 retrieval score 가 0.03 수준으로 매우 낮아 불안정.
- 정답(별표 2 국내 여비 지급표의 제2호 일비 = 25,000원)이 검색 상위에 안 올라옴.

## 원인 분석
별표 2(국내 여비 지급표)의 일비표가 **독립 청크가 아니라 `제18조 ③` 청크(id 342)에 별표 1~9 전체와 함께 12,218자로 뭉쳐** 있었다.

1. **변환(Docling)은 정상** — 표를 행/열 살아있는 깔끔한 markdown 표로 추출 (`| 구분 | … | 일비 (1일당) | … |`).
2. **파싱(`structure.py`)이 실패** — 별표 인식 정규식 `APPENDIX_RE = ^(별표\s*\d+|…)` 는 *줄 맨 앞이 "별표N"* 이어야 매칭되는데, Docling 이 실제로 뽑은 별표 헤더는 셋 다 이 패턴에 안 걸림:
   | md 실제 출력 | 형태 | `^별표\d+` |
   |---|---|---|
   | `- [별표 2] 국내 여비 지급표(…)` (목차) | 불릿 + 대괄호 `[별표` | ❌ |
   | `■ 공무원 여비 규정 [별표 2] <개정…>` (본문 헤더) | `■` 머릿글 뒤 `[별표` | ❌ |
   | `## 국내 여비 지급표 (…관련)` (제목) | "별표" 단어 자체가 없음 | ❌ |
3. 그 결과 별표 경계가 하나도 안 잡혀 모든 별표 본문이 직전 조문(`제18조 ③`)에 흡수 → 12KB 단일 청크 + `chapter="제6장 보칙"` 오(誤)라벨.
4. **왜 "하루"가 통했나** — 신호가 약한(score 0.03) borderline 상태에서, 표 헤더가 "일비 **(1일당)**" 이라 "하루 일비" 쿼리가 임베딩상 표와 더 가까워져 컷오프를 우연히 넘긴 것. 모델이 똑똑해진 게 아니라 검색이 운에 좌우되는 brittle 상태였음.

## 해결 방법
`packages/regulation_parser/structure.py` 수정 (commit 후속):
- **`APPENDIX_BODY_RE = ■.*?\[\s*별표\s*(\d+(?:의\d+)?)\s*\]`** 추가 — `■` 머릿글이 동반된 `[별표 N]` 줄만 별표 *본문 경계*로 인식. 목차 줄(`■` 없음)과 자연히 구분됨.
- **`APPENDIX_TOC_RE`** + `_scan_appendix_titles()` — 사전 스캔으로 목차 `[별표 N] 제목(…관련)` 에서 `번호→제목` 매핑을 만들어, "별표" 단어가 없는 본문 제목 헤더에 제목을 역주입.
- 별표 진입 시 `chapter/section = None` 으로 끊음 (별표는 장/절 밖).

### 결과 (공무원여비규정.md 재파싱)
| 항목 | 수정 전 | 수정 후 |
|---|---|---|
| 총 청크 | 39 | 45 |
| 최대 청크 길이 | 12,218자 | 5,283자 |
| 별표 2 | 제18조 ③ 에 매몰 | 독립 청크 `공무원여비규정 > 별표 2 (국내 여비 지급표)` |
| 별표 2 chapter | "제6장 보칙" (오류) | None (정확) |
| 일비/제2호/25,000 | 거대 청크 내부 | 독립 청크에 온전 ✓ |

별표 1·2·3·4·9 가 제목까지 정상 분리.

## 재발 방지
- `structure.py::_self_check()` 에 `■ … [별표 N]` 본문 헤더 + 목차 제목 매핑 회귀 테스트 추가 (`python -m packages.regulation_parser.structure` 로 검증, exit=0).
- 파싱 규칙 변경이므로 [features/ingestion.md](../../features/ingestion.md) regex 표 갱신, [troubleshooting/common.md](../../troubleshooting/common.md) 등록.

## 재색인 검증 (2026-06-08) — ⚠️ retrieval 은 여전히 실패
`POST /admin/reindex/2` 실행 → 새 doc_id=5, **45 chunks / Qdrant 45 points**, 별표 1·2·3·4·7·9 독립 청크 DB 반영 확인. **구조는 의도대로.**

그러나 원래 질문으로 검색하면 별표 2 가 **여전히 상위에 안 옴**:
| 질문 | 별표 2 순위 |
|---|---|
| "…2호구분…일비는?" (원본) | top8 밖 ❌ |
| "…2호구분…**하루** 일비는?" | top8 밖 ❌ (재색인 후 "하루"도 무효) |
| "…별표2 제2호 25000" (키워드 명시) | **1위 ✅** (0.0323) |

- 별표 2 청크는 존재하고 **키워드가 정확하면 1위로 잡힘** → 청킹 버그 자체는 해결.
- 그러나 자연어 질문으로는 실패. 전 sources score 가 0.03 안팎으로 **변별력 거의 없음** — 표 청크의 dense 임베딩 신호가 약함(헤더에 "일비" 1회 + 본문 대부분 숫자/등급). HyDE 도 "별표 1 …금액" 식 부정확 가상문서로 오히려 방해.
- **결론: 별표 독립 청크화는 필요조건이나 충분조건이 아님.** retrieval 성공은 아래 후속(table linearization)이 핵심.

## 최종 해결 (2026-06-08)
위 "재색인 검증"은 reranker 도입 *전* 상태다. 이후 아래로 완전 해결:

### 1. table linearization (`article_chunker`)
별표 표를 행별 자연어 청크로 추가. `content_type='appendix_row'`. 별표는 표 행 구조 보존 위해 body 누적 시 줄바꿈 유지(`structure.py`). `linearize_appendix_tables` 토글.
예) `공무원여비규정 > 별표 2 (국내 여비 지급표) — 구분 제2호: … 일비 (1일당) 25,000, 식비 (1일당) 25,000`

### 2. HyDE 수정 (`query_rewriter_node`)
프롬프트에서 조문·별표 '번호' 추측 금지 + 동의어/자료유형만 확장, `temperature=0`. 거짓 "별표 1" 환각 제거.

### 3. reranker 연결 (`reranker.py`, `retriever_node`) — 결정타
RRF 후보(`rerank_candidate_k=60`)를 **BAAI/bge-reranker-base** cross-encoder 로 원질문과 1:1 재정렬. 상세 [retrieval.md](../../features/retrieval.md).

### 4. 별표 인식 정규식 일반화 (`structure.py`)
`■[별표N]` 외에 **제목 헤더 역추적**(`APPENDIX_TITLE_HEADER_RE` + 목차 `제목→번호` 매핑) 추가 → `■` 없이 제목만 있던 별표 5·6의2·8 까지 인식. 별표 6→9개 전수.

### Ablation (질문: "2호구분 일비")
| | rerank OFF | rerank ON |
|---|---|---|
| 별표 청킹만(linearize OFF) | 회귀, top8 밖 | 별표 2 1위 (-2.98) |
| + linearize ON | top6 밖 | **별표 2 1위 (+3.51)** |
- **rerank 가 성능 1등**(OFF→실패, ON→1위). linearize 는 안전마진(+6.5점) 보조.
- 별표 9개로 늘며 정답이 후보 top30 밖으로 밀린 회귀 → `rerank_candidate_k` 30→60 으로 해결.

### 최종 검증
- "2호구분 일비" / "하루 일비" → 별표 2 행 청크 1·2위, 답변 "1일당 25,000원" 정확.
- "상시 출장 여비"(별표 8) +7.3, "이전비"(별표 5) +4.9 — 신규 인식 별표도 정상.

## 남은 후속 (별건)
- 보험약관 본문 인라인 표(774+264행) linearization 확장 — reranker 가 커버하므로 보류.
- 컬렉션 확장 시 `rerank_candidate_k` 재조정.

## 출처
- `data/parsed/공무원여비규정.md` (Docling 산출), DB 조사
- `packages/regulation_parser/{structure,article_chunker}.py`, `packages/rag/{reranker,nodes/retriever_node,nodes/query_rewriter_node}.py`, `apps/config.py`
