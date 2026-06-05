# Ingestion Pipeline

**상태**: active
**마지막 업데이트**: 2026-05-27 (M2 완료)
**관련 페이지**: [../data/spec.md](../data/spec.md), [../architecture/pipeline.md](../architecture/pipeline.md), [authority_matrix.md](authority_matrix.md)

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
APPENDIX = r"^(별표\s*\d+|별지\s*(?:제\s*)?\d+\s*호?)"
```

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

## 출처
- `docs/mvp_plan.md` §Ingestion Pipeline + §M2
- `packages/regulation_parser/`, `packages/loaders/`, `apps/indexer_worker.py`
- 2026-05-27 17 PDF 인덱싱 측정 결과
