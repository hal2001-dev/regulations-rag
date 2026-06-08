# Ingestion Pipeline

**상태**: active
**마지막 업데이트**: 2026-06-08 (별표 본문 경계 인식 추가 — [ISSUE-001](../issues/resolved/ISSUE-001.md))
**관련 페이지**: [../data/spec.md](../data/spec.md), [../architecture/pipeline.md](../architecture/pipeline.md), [authority_matrix.md](authority_matrix.md), [../issues/resolved/ISSUE-001.md](../issues/resolved/ISSUE-001.md)

## 요약
17 PDF → Docling text 추출 → 조 단위 chunking (breadcrumb prepend) → Postgres `documents`/`articles` 적재. M2 범위에서는 임베딩/Qdrant upsert 는 제외 (M3 retrieval 작업 시 본 파이프라인에 추가).

## 흐름

```
POST /ingest (source_path)
  → ingest_jobs row (status=queued)
indexer_worker (별도 프로세스)
  → claim_next_job (FOR UPDATE SKIP LOCKED)
  → content_hash (sha256) 로 dedup
  → doc_type_classifier.classify (파일명 휴리스틱 + admin override)
  → docling_loader.load_pdf_text (do_ocr=False, device=CPU)
  → structure.parse_document → ParsedArticle 리스트
  → article_chunker.chunk_document(title, articles) → Chunk 시퀀스
  → 1 트랜잭션: Document + Article × N bulk insert
  → mark_job_done (doc_id)
```

## 코드 위치
- `packages/loaders/docling_loader.py` — Docling wrapper + 한국어 friendly `normalize_markdown`
- `packages/regulation_parser/structure.py` — 6 regex 정의 + `parse_document` (markdown heading/list marker strip 포함)
- `packages/regulation_parser/article_chunker.py` — `chunk_document` (조 단위 + breadcrumb + >800 token 시 paragraph split)
- `packages/regulation_parser/doc_type_classifier.py` — 파일명 → doc_type + title 정제
- `apps/indexer_worker.py` — 폴링 루프 + 트랜잭션 책임
- `apps/routers/ingest.py` — POST /ingest enqueue
- `scripts/bulk_ingest.py` — 17 PDF 일괄 호출 + 폴링

## 구조 파서 (`structure.py`)

### 6 regex (mvp_plan §M2.3)
```python
CHAPTER  = r"^제\s*\d+\s*장\s+(.+)$"
SECTION  = r"^제\s*\d+\s*절\s+(.+)$"
ARTICLE  = r"^(제\s*\d+\s*조(?:의\d+)?)\s*(?:\(([^)]+)\))?(.*)$"
PARA     = r"^([①-⑳])\s*(.*)$"
ITEM_NUM = r"^(\d+)\.\s+(.*)$"
ITEM_KOR = r"^([가-힣])\.\s+(.*)$"
APPENDIX = r"^(별표\s*\d+(?:의\d+)?|별지\s*(?:제\s*)?\d+\s*호?)"  # 줄 맨 앞 단순형
```

### 별표 본문 경계 인식 (2026-06-08 추가 — ISSUE-001)
실 PDF 의 별표는 위 단순형(`별표 1 …`)으로 안 나오고, Docling 이 아래 3가지로 뽑는다 — **3가지 모두 인식**한다:
```python
APPENDIX_BODY_RE         = r"■.*?\[\s*별표\s*(\d+(?:의\d+)?)\s*\]"   # "■ 공무원 여비 규정 [별표 2] <개정…>" = 본문 경계
APPENDIX_TOC_RE          = r"^\[\s*별표\s*(\d+(?:의\d+)?)\s*\]\s*(.+)$"  # "[별표 2] 국내 여비 지급표(제10조 관련)" = 목차→제목
APPENDIX_TITLE_HEADER_RE = r"^(.+?)\s*\(제[^)]*관련\)\s*$"            # "이전비 지급 기준표 (제20조 관련)" = 제목만(번호 없음)
```
- **(1) `■[별표 N]` 헤더** — 번호 명시. 가장 명확.
- **(2) 목차 `[별표 N] 제목`** — `_scan_appendix_titles()` 가 사전 스캔해 `번호↔제목` 매핑 구축.
- **(3) 제목만 있는 헤더** — 일부 별표는 `■[별표 N]` 머릿글 없이 제목(`## 이전비 지급 기준표 (제20조 관련)`)만 나온다. 이를 (2)의 `제목→번호` 역매핑으로 역추적해 별표 경계로 인정. **단 이미 같은 별표 진행 중이면(제목 줄 중복) 새 경계로 만들지 않음.**
- 별표 진입 시 `chapter/section=None` (별표는 장/절 밖).
- **효과**: 공무원여비규정 별표 **6개→9개 전부 인식**(별표 5·6의2·8 = 제목만 있던 분 복구). 39→84 청크(행 청크 36 포함). 최대 청크 12,218→5,283자. 별표 2 가 독립 청크로 분리.
- 회귀: `structure.py::_self_check()` 에 별표 헤더 케이스 포함. 상세 [ISSUE-001](../issues/resolved/ISSUE-001.md).

### markdown prefix strip (M2 추가)
Docling 출력이 `## 제8조의2(중기성과품)` 같은 markdown heading 으로 나오는 케이스가 흔함 + `- ① ...` list marker 도 흔함. 라인 정규화 단계에서 `^(?:#+\s+|[-*]\s+)` 를 strip 하지 않으면 ARTICLE/PARA regex 가 모두 miss → 한 article 에 다음 조의 paragraph 가 흡수되는 hallucination. **상임이사및감사보수규정.pdf 1차 인덱싱에서 발견 → fix**.

### 같은 줄 article + paragraph 처리
`제2조 (정의) ① 다음과 같다.` 처럼 한 줄에 article header 와 첫 paragraph 가 같이 있는 경우, ARTICLE_RE 매칭 후 tail (group 3) 을 PARA_RE 로 재매칭하여 paragraph 로 분리.

### article 직속 호 (paragraph 없이 `1.` 시작) 처리
가상 paragraph (`marker=""`) 자동 생성 후 item 추가. 한국 법령에서 흔한 패턴.

## 청커 (`article_chunker.py`)

### 분할 규칙
- 1 chunk = 1 article 기본 (`content_type='article'`)
- `_approx_tokens(text) > 800` 이면 paragraph 단위 분할 (`content_type='paragraph'`)
- `_approx_tokens` = `len(text) // 2` (한국어 1 token ≈ 2 chars 휴리스틱, tiktoken 없이 충분)
- 별표/별지 → `content_type='appendix'` (paragraph 분할 없음)

### Breadcrumb prepend
모든 chunk body 앞에 `{doc_title} > {chapter} > {section} > {article_no} ({article_title}) [> ①]` 를 한 줄로 prepend. BM25 recall + self-contained 인용 동시 만족.

## doc_type 분류 (`doc_type_classifier.py`)

```python
위임전결|직무권한 → authority_matrix
매뉴얼|가이드     → manual
100문|문답|FAQ   → faq
else             → policy
```
`POST /ingest` 의 `user_doc_type` 으로 override 가능.

## M2 KPI (2026-05-27 측정)
- ✅ 17/17 인덱싱 (extraction_quality=ok)
- ✅ article_no non-null 15/17 (≥14 충족), 그 15 docs 내 100% 채움
- ✅ heading_path random 10 검증 통과
- 총 chunks = 1,461

## 알려진 한계 (M2 후속 과제)

### 1. manual/faq 0-chunk 문제
| doc | 이유 | M2 후속 |
|---|---|---|
| 건설공사 안전관리 매뉴얼(2024) | `제N장/N조` 구조 부재 | manual 용 fallback chunker (markdown heading 단위) |
| 공무원여비100문100답 | `문 N / 답 N` 구조 | `faq_chunker.py` 별도 (mvp_plan §M2.4 에 명시) |

### 2. HTML entity 노출
Docling markdown 에 `&lt;개정 ...&gt;` 같은 entity 가 그대로. article_title 까지 흘러들어와 citation 표시에 영향. → M3 retrieval/generation 직전 `html.unescape` 적용 또는 `normalize_markdown` 에 unescape 단계 추가.

### 3. 매뉴얼의 헤더 vs 인용 법령 구분
`교육활동 보호 매뉴얼` 이 형사범죄 관련 법령을 인용하면서 `제N장 신용, 업무와 경매에 관한 죄` 같은 헤더가 article chapter 로 잡힘. citation 정확도에 영향 가능 — golden 쿼리 #7 (교육활동 침해 시 대응) 평가 시 재검토.

### 4. Apple Silicon MPS float64 미지원
Docling layout/table 모델이 float64 사용 → MPS 에러. `AcceleratorOptions(device=AcceleratorDevice.CPU)` 로 강제 (속도 약간 손해, ~30 PDF/분 가능).

### 5. OCR fallback 미구현
M2 는 OCR off 만. mvp_plan §M2.2 의 macOS Vision OCR fallback (`OcrMacOptions(lang=['ko-KR'])`) 은 스캔본 PDF 가 들어올 때 추가 (현재 17 PDF 모두 디지털).

### 6. 별표 표 행 단위 linearization + 별표 전수 인식 (2026-06-08, ISSUE-001 — ✅ 해결)
- **표 행 단위 linearization 적용** — 별표 표를 `별표 2 국내 여비 지급표 — 구분 제2호: 일비 25,000, …` 식 행 문장 청크로 변환(`article_chunker._parse_md_tables`/`_linearize_row`, `content_type='appendix_row'`). 원본 별표 청크는 맥락용으로 유지. `linearize_appendix_tables` 설정으로 토글. **현재 범위: 별표(is_appendix) 청크의 표만** (보험약관 본문 표는 미적용 — 후속).
- **별표 5·6의2·8 누락 해결** — 제목 헤더 역추적(`APPENDIX_TITLE_HEADER_RE`)으로 `■` 없는 별표까지 인식. 별표 6→9개 전부.
- 남은 후속: 보험약관 본문 인라인 표(774+264행) linearization 확장은 reranker 가 어느 정도 커버하므로 보류.

### 7. 파싱 산출 markdown 저장 (2026-06-08 추가)
`load_pdf_text(path, save_md_dir=...)` 로 정규화 markdown 을 디스크에 남길 수 있음. `indexer_worker` 가 ingest 시 `data/parsed/<문서>.md` 로 자동 저장 → 표/별표 청킹 디버깅·재현에 사용 (Docling 변환이 CPU 라 느려 캐시 효과도 있음). `.gitignore` 는 `data/parsed/*.md` 만 예외 추적.

## 출처
- `docs/mvp_plan.md` §Ingestion Pipeline + §M2
- `packages/regulation_parser/`, `packages/loaders/`, `apps/indexer_worker.py`
- 2026-05-27 17 PDF 인덱싱 측정 결과
