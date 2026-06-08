# Troubleshooting — 자주 발생하는 에러

**상태**: active
**마지막 업데이트**: 2026-06-08
**관련 페이지**: [../features/ingestion.md](../features/ingestion.md), [../issues/resolved/ISSUE-001.md](../issues/resolved/ISSUE-001.md)

## 요약
반복적으로 부딪힌 문제와 즉시 적용 가능한 해결법 모음. 새 이슈가 resolved 되면 재발 가능성이 있는 것은 여기에 한 줄이라도 남긴다.

---

## 1. 표/별표가 검색에 안 잡힘 (질문 단어 하나에 결과가 뒤집힘)

**증상**: 표에 있는 값(예: 별표의 일비·한도·등급별 금액)을 묻는데 검색 실패. 단어를 조금 바꾸면(예: "일비" → "하루 일비") 갑자기 성공. retrieval score 가 0.0x 대로 매우 낮음.

**원인**: 표(별표)가 독립 청크로 분리되지 않고 직전 조문에 흡수되어 거대 청크가 됨 → 임베딩 신호 희석 → borderline score → 쿼리 단어에 따라 순위가 흔들림. 상세 [ISSUE-001](../issues/resolved/ISSUE-001.md).

**확인**:
```sql
-- 비정상적으로 큰 청크 탐지 (한 문서의 평균 대비 압도적으로 긴 것)
SELECT id, article_no, length(body)
FROM articles WHERE doc_id=:id ORDER BY length(body) DESC LIMIT 5;
```
한 청크만 1만자 이상이고 그 안에 `별표`/표(`| … |`)가 여럿이면 이 케이스.

**해결**: `structure.py` 의 별표 경계 인식 확인 — `■ … [별표 N]` 본문 헤더(`APPENDIX_BODY_RE`)와 목차 제목 매핑(`_scan_appendix_titles`). 새 문서가 다른 별표 머릿글 형태면 `data/parsed/<문서>.md` 를 열어 헤더 패턴을 보고 정규식 보강. 수정 후 해당 문서 재인덱싱(`POST /admin/reindex/{doc_id}`).

**재발 방지**: 인덱싱 후 문서별 max(length(body)) 를 품질 체크에 포함.

---

## 2. 파싱 후 조문이 다음 조문에 흡수됨 (markdown heading/list 마커)

**증상**: `제8조의2(…)` 같은 조가 별도 article 로 안 잡히고 직전 조에 붙음.

**원인**: Docling 이 `## 제8조의2(…)` / `- ① …` 처럼 markdown heading·list 마커를 붙여 출력 → ARTICLE/PARA 정규식 miss.

**해결**: `_strip_md_prefix` 가 `^(?:#+\s+|[-*]\s+)` 를 제거함(M2 fix). 새 마커 형태가 보이면 이 정규식 확장.

---

## 3. citation 에 `&lt;개정 …&gt;` HTML entity 노출

**증상**: 인용 표시(article_title 등)에 `&lt;`, `&gt;` 가 그대로 보임.

**원인**: Docling markdown 의 HTML entity 미디코딩.

**해결(예정)**: `normalize_markdown` 또는 retrieval/generation 직전 `html.unescape` 적용. [ingestion.md](../features/ingestion.md) 알려진 한계 #2 참조.

---

## 4. 웹 chat 500 / API 연결 실패 (포트 불일치)

**증상**: 웹에서 chat 시 500. 백엔드 단독 `curl` 은 정상.

**원인**: 백엔드 포트와 `web/next.config.ts` rewrite 대상(`:8001`)·`.env` `API_PORT` 불일치. 예) 백엔드를 8000 으로 띄움.

**해결**: 백엔드는 **`--port 8001`** 로 실행(설정 표준). 또는 `next.config.ts`/`.env` 를 백엔드 포트에 맞춰 **양쪽 일치**. 헬스: `curl localhost:8001/health`.

## 출처
- [ISSUE-001](../issues/resolved/ISSUE-001.md), [features/ingestion.md](../features/ingestion.md)
- 세션 트러블슈팅 기록 (2026-06-08)
