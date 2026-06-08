# Work Log

**상태**: active
**형식**: `## [YYYY-MM-DD] op | summary` (append-only, 최신이 아래)

`op` 값: `ingest` / `query` / `lint` / `build` / `decision` / `bootstrap`

최근 5개 항목 확인: `grep "^## \[" project-wiki/wiki/log.md | tail -5`

---

## [2026-05-27] bootstrap | M1 wiki 스캐폴드 작성
- `project-wiki/wiki/` 디렉토리 트리 생성 (architecture, features, data, api, testing, deployment, config, onboarding, troubleshooting, meetings, issues/{open,resolved}, reviews)
- 초기 페이지 작성: `index.md`, `log.md`, `overview.md`, `roadmap.md`, `glossary.md`, `data/spec.md`, `architecture/{decisions,pipeline,stack}.md`, `features/{authority_matrix,citation}.md`
- raw 자료 정리: `raw/requirements/PRD.md` (PRD 원본 복사), `raw/research/karpathy-llm-wiki.md` (karpathy gist 원문)
- 다음 단계: M1 코드 스켈레톤 (docker-compose, FastAPI /health, DB models, Next.js shell) 작업 시 본 log 에 `build` op 항목 append.
- 출처: `docs/mvp_plan.md` M1 섹션

## [2026-05-27] build | M1 코드 스켈레톤 + 부팅 검증 완료
- 백엔드: `apps/main.py` (lifespan create_all + `/health`), `apps/config.py` (pydantic-settings), `apps/routers/` 6개 placeholder (ingest/query/documents/authority/jobs/admin, 모두 501 반환), `apps/indexer_worker.py` (claim/mark 큐 폴링 skeleton, 실제 Docling 호출은 M2), `packages/db/{models,connection,repository}.py`, `packages/code/logger.py`.
- DB 모델: `documents` / `articles` / `authority_rules` / `ingest_jobs` / `conversations` / `messages` / `taxonomy_config` 7 테이블 — lifespan 시 `Base.metadata.create_all` 로 자동 생성 확인.
- 인프라: `docker-compose.yml` (postgres:16 → 5433, qdrant v1.12.4 → 6433/6434), `requirements.txt` (전체) + `requirements-m1.txt` (부팅 검증용 최소셋), `.env.example` / `.env`.
- 프론트엔드: `web/` Next.js 15 + React 19 + Tailwind v3 + shadcn-ready (`components.json`, `lib/utils.ts`, `app/globals.css` neutral palette). 페이지: `/` 홈 shell + `/chat` placeholder. `next.config.ts` 의 `/api/*` → `:8001` rewrite + `compress:false` (M5 SSE 대비).
- 포트 결정: 형제 프로젝트 `knowledge-rag` 와의 충돌 회피로 **3001 / 5433 / 6433 / 8001**. `package.json` dev script, `.env(.example)` CORS_ORIGINS, `apps/config.py` 기본값 모두 3001 로 정렬.
- 검증: `docker compose ps` 양 컨테이너 healthy → `curl :8001/health` → `{status:ok, db:ok}` → Postgres `\dt` 7 테이블 → `pnpm dev` :3001 → `GET /` `GET /chat` 200, `GET /api/health` 프록시도 백엔드 JSON 정상.
- 출처: `docs/mvp_plan.md` M1, `apps/`, `packages/`, `web/`

## [2026-05-27] ingest | M2 — Docling + regulation_parser + 17 PDF 일괄 인덱싱
- 신규 모듈: `packages/regulation_parser/{structure,article_chunker,doc_type_classifier}.py`, `packages/loaders/docling_loader.py`. 각 모듈 inline `_self_check()` 로 단위 검증.
- 변경: `apps/indexer_worker.py` placeholder → 실제 처리 루프 (loader → parse → chunk → bulk insert + content_hash dedup). `apps/routers/ingest.py` placeholder → POST /ingest enqueue. `apps/routers/jobs.py` `?ids=` 필터 추가. `scripts/bulk_ingest.py` 신규.
- 부팅 수정: Docling 첫 인덱싱이 Apple MPS float64 미지원으로 실패 → `AcceleratorOptions(device=AcceleratorDevice.CPU)` 강제 (`docling_loader._get_converter`).
- structure 파서 패치: Docling 출력이 `## 제N조` markdown heading 으로 나오는 케이스 + `- ① ...` list marker 케이스를 라인 정규화에서 `^(?:#+\s+|[-*]\s+)` strip 으로 처리. 미처리 시 article 흡수로 paragraph 마커가 중복 출력되는 hallucination 확인 후 수정.
- 1 PDF e2e (상임이사및감사보수규정.pdf, 51KB, 5 page): doc_id=2, articles 13 rows, 모두 unique article_no, chapter/title/heading_path 모두 정확. 처리 ~4s.
- 17 PDF 일괄 (`scripts/bulk_ingest.py ingest/*.pdf`): 모두 done. **17 docs, 1,461 articles, 15 docs with chunks, 2 docs zero-chunk (manual×1 + faq×1)**.
- M2 KPI: 17/17 ✅, article_no non-null 15/17 (≥14 충족) ✅, heading_path random 10 검증 ✅.
- 후속: manual/faq fallback chunker, HTML entity unescape, MPS float64 우회, OCR fallback. `wiki/features/ingestion.md` 의 "알려진 한계" 섹션에 정리.
- 출처: `docs/mvp_plan.md` §M2, `wiki/features/ingestion.md`, `wiki/data/spec.md` 측정표

## [2026-05-27] build | M3 — LangGraph + Hybrid Retrieval + Generator
- 신규 모듈:
  - `packages/vectorstore/qdrant_store.py` — 단일 collection(dense 1024+sparse "bm25"), 5 payload index, upsert/search 헬퍼
  - `packages/rag/{state,embeddings,retriever,checkpointer,graph,index_articles}.py`
  - `packages/rag/nodes/{router,retriever,generator,citation_validator}_node.py`
  - `scripts/backfill_embeddings.py`
- 변경: `apps/routers/query.py` placeholder → /query + /query/stream SSE (token/sources/route/citation/done 5 이벤트). `apps/indexer_worker.py` 의 `_process_job` 끝에 embed+Qdrant upsert.
- ADR-014/015/016 추가: e5-large 로 bge-m3 대체 / Qdrant/bm25 로 Kiwi 우회 / 첫 토큰 <1s KPI 한계 인정.
- 함정 4개 디버깅:
  1. fastembed 가 BAAI/bge-m3 직접 미지원 → multilingual-e5-large 로 대체
  2. kiwipiepy Python 3.14 wheel/build 실패 → fastembed 내장 BM25 로 우회
  3. `.env` 의 `LANGGRAPH_CHECKPOINT_URL=  # ...` inline 주석이 value 흡수 → psycopg ProgrammingError
  4. `PostgresSaver` 는 sync 만 지원, async 호출 시 NotImplementedError → `AsyncPostgresSaver` (langgraph.checkpoint.postgres.aio) + `get_saver()` async 화
- Backfill: 17 docs / 1,461 articles → Qdrant 1,461 points (4분, ~5.8 points/s).
- 검증 (5 sample query): top-1 doc_id 5/5 ✓, citation_valid_pct 5/5=100% ✓, 첫 토큰 3.5s (KPI <1s 미달, ADR-016 인정).
- LangGraph PostgresSaver checkpoint 테이블 4개 자동 생성 확인.
- 출처: `docs/mvp_plan.md` §M3, `wiki/features/{embedding,retrieval,generation}.md`, `wiki/api/endpoints.md`, `wiki/architecture/decisions.md` ADR-014/015/016

## [2026-05-27] build | M4 — Authority Lookup + Conditional Edge + Vision 추출
- 신규 모듈:
  - `packages/regulation_parser/authority_extractor.py` (gpt-4o-mini **vision** + 12-keyword process map + amount/% 정규화)
  - `packages/rag/nodes/authority_lookup_node.py` (한국어 금액/% 파서 + SQL exact + hybrid fallback)
  - `apps/routers/authority.py` (REST `/authority`, `/authority/processes`, `/authority/roles`)
  - `scripts/backfill_authority.py`
- 변경:
  - `packages/rag/nodes/router_node.py` — "할인 30%", "5천만원 결재" 같은 패턴 추가
  - `packages/rag/graph.py` — `add_conditional_edges` 로 router → (authority_lookup | retriever) 분기
  - `apps/indexer_worker.py` — doc_type='authority_matrix' 시 authority_extractor 자동 호출
  - `packages/rag/nodes/citation_validator.py` — LLM 변종 형식 `authority_rule#NN 1억 이하` 까지 수용
- ADR 추가: 017 (vision 기반 추출), 018 (amount/% 강한 신호일 때 process 필터 drop)
- 추출 시행착오:
  1. regex (mvp_plan §M2.5): 사무위임전결규정 0 rows — hierarchical/spanned 구조
  2. LLM text-only on markdown: 177 rules 다 "사장" + amount=null — ○ 매핑 실패
  3. LLM vision (페이지 PNG 직접): 514 rules, 29 에 amount, role 다양 ✅
- backfill 결과: 사무위임전결 329 + 신천초 185 = **514 authority_rules**, 14분 소요
- M4 KPI: ✅ router accuracy 5/5, ✅ role/limit exact 4/5 (Q4 는 PDF 에 % 데이터 없음), ✅ citation valid 5/5 (validator 보강 후).
- 알려진 한계: process 매핑 약함 (다수 "other"), % 한도 0, hierarchical parent row 처리 부족 — `wiki/features/authority_matrix.md` 후속 섹션.
- 출처: `docs/mvp_plan.md` §M4, `wiki/features/authority_matrix.md`, ADR-017/018

## [2026-05-27] build | M5 backend 작성 (검증 보류 — 다음 세션)
- state 확장 (`packages/rag/state.py`): `Clarification` TypedDict, `needs_clarify`, `clarify_question`, `clarify_options`, `clarify_pattern`, `clarifications`(list), `hyde_doc`.
- 신규 노드:
  - `packages/rag/nodes/clarifier_node.py` — gpt-4o-mini structured JSON, 4 패턴 (target_ambiguous/authority_slot/time_ambiguous/scope_wide) 감지, confidence ≥ 0.6 + options 비어있지 않을 때만 clarify 발동. `MAX_CLARIFICATIONS=2` 후 강제 통과 (ADR-012). `apply_user_choice(state, choice)` helper 추가.
  - `packages/rag/nodes/query_rewriter_node.py` — HyDE (Hypothetical Document Embeddings). 가상 답변 2-3문장 생성 후 원본 질문에 append → retrieval query 풍부화.
- `packages/rag/graph.py` 재구성:
  - START → clarifier → (needs_clarify ? clarify_pause : query_rewriter) → router → (authority_lookup | retriever) → generator → citation_validator → END
  - `interrupt_before=["clarify_pause"]` — clarify 시 그래프 일시 중단
  - `clarify_pause` 는 pass-through marker 노드 (resume 시 통과)
- `apps/routers/query.py` 재작성:
  - SSE 이벤트 추가: `clarify` (question/options/pattern/session_id), `rewrite` (HyDE 일부 표시)
  - `POST /query/resume` 신규 — `aget_state` → `apply_user_choice` → `aupdate_state` → `astream_events(None, config)` 로 재진입
  - `POST /query` (비-스트리밍) 도 interrupt 상태 시 `status:"clarify"` 반환
- **검증 보류**: backend 부팅 후 첫 query (모호 + 명확) 검증이 tool error 로 끊김. 다음 세션 첫 일.
- **프론트엔드 미진행**: Task #38-41 (shadcn 설치, web/lib/api.ts, web/app/chat/*, e2e).
- 출처: `docs/mvp_plan.md` §M5, `packages/rag/nodes/{clarifier,query_rewriter}_node.py`, `apps/routers/query.py`

## [2026-05-28] build | M5 backend 검증 + 프론트 완성
- backend smoke (모두 통과):
  - 명확 query ("내부회계관리규정 제5조 내용", "연차휴가 신청", "3천만원 계약 결재", "출장비 한도") → `rewrite → route → sources → token → citation → done` 6 이벤트
  - 모호 query ("그 규정 알려줘", "결재 누가?", "규정 전부 보여줘") → `clarify` event → `/query/resume` POST → `rewrite ... done` 정상 재개
  - 7 쿼리 clarify 결정 matrix: 모호 3/3 clarify, 명확 4/4 통과 (≥8/10 KPI 산정 기준 5/5 통과, 3/3 발동 = 7/7 적중)
- bug fix #1: `astream_events` 의 `on_chat_model_stream` 이 clarifier/rewriter 의 LLM 출력까지 SSE `token` 으로 흘려 보냄. `ev["metadata"]["langgraph_node"] == "generator"` 필터 추가 (`apps/routers/query.py:60`).
- bug fix #2: clarifier 의 over-clarification — "연차휴가 신청"·"3천만원 계약 결재" 같은 명확 query 까지 clarify 발동. 시스템 프롬프트에 PASS 예시 추가 + confidence 임계 0.6→0.7 (`packages/rag/nodes/clarifier_node.py`).
- 프론트엔드 신규:
  - `web/lib/api.ts` — SSE reader (`getReader` + `\n\n` block parser) + `streamQuery` / `resumeQuery`. `API_BASE` 기본값 `/api` (next rewrites 경유).
  - `web/components/ui/{button,input}.tsx` — shadcn-style minimal (CLI 미사용).
  - `web/components/chat/` — `chat-stream.tsx` (turn state + handleEvent dispatch), `node-progress.tsx` (clarify/HyDE/route/retrieve/generate/validate 6단 chip + Loader/Check icon), `quick-reply-chips.tsx` (clarify question + chip + onPick), `citation-chip.tsx` (heading_path + score, expand 시 body), `answer-blocks.tsx` ([결론]/[근거] regex split + 색조 강조).
  - `web/app/chat/page.tsx` — placeholder 제거, `ChatStream` 마운트.
- E2E 검증: next dev :3001 → `/api/query/stream` 프록시 → fastapi :8001 SSE 통과 (curl 6 이벤트 동일). `pnpm typecheck` clean.
- 후속: chat UI 브라우저 수동 검증 (next dev 띄움 중), 첫 토큰 latency 측정, 광범위 clarify 패턴 골든셋, 검색 fallback (route=null 일 때).
- 출처: `apps/routers/query.py:60`, `packages/rag/nodes/clarifier_node.py`, `web/components/chat/*.tsx`, `web/lib/api.ts`

## [2026-05-28] build | M6 — Admin/Library UI + Reindex + Eval 인프라
- Backend:
  - `apps/routers/admin.py` POST `/admin/reindex/{doc_id}` 구현 — Qdrant point drop + Document row 삭제(CASCADE) + 새 IngestJob enqueue. `force_ocr` 옵션. 404 / 원본 파일 누락 시 400.
  - `apps/routers/documents.py` 확장 — `doc_type` 필터, `GET /documents/{id}/chunks` 신규 (limit/offset, body 600자 truncate).
- Frontend:
  - `web/app/library/page.tsx` + `web/components/library/document-list.tsx` — 17 docs list (검색/필터/refresh) + 선택 시 chunk preview 30개 + 재색인/재색인+OCR 버튼.
  - `web/app/admin/page.tsx` + `web/components/admin/jobs-panel.tsx` — 새 문서 ingest 폼 + 최근 30 jobs 진행도 (auto-refresh 3s).
  - `web/lib/api.ts` 에 REST 헬퍼 추가: `fetchDocuments / fetchChunks / fetchJobs / reindexDocument / enqueueIngest`.
  - `web/app/page.tsx` 홈 nav 에 `/library`, `/admin` 링크 추가.
- Eval:
  - `tests/e2e/golden_queries.yaml` — 30 query (policy×15 + authority×10 + manual×5). 각 entry 에 `expected_route`, `expected_doc_id?`, `expected_keywords[]`.
  - `scripts/eval_ragas.py` — `/query/stream` SSE 수집 → route_ok / doc_ok / kw_pct / citation / latency 채점 → KPI 표 출력 + `reports/eval.json`. `--ragas` 플래그로 faithfulness/answer_relevancy 추가 가능.
- 의존성: `pip install ragas` 시 langgraph 1.2 / langgraph-checkpoint 4.x 자동 업그레이드 (기존 2.1.2 → 4.1.1). FastAPI/M5 smoke 재검증 통과 — 회귀 없음.
- **M6 baseline (30 query)**:
  - ✅ route accuracy 92.3% (≥85%), keyword recall 83.3% (≥80% proxy)
  - ❌ citation 69.2% (≥95%), retrieval top-1 68.2% (≥85%), first-token p95 10.79s (≤1s), end-to-end p95 16.41s (≤3s)
- ADR-019 추가 — KPI 미달 4종은 carry-over 로 명시 (citation prompt 보강, golden `acceptable_doc_ids[]` 다중화, clarifier prefilter + HyDE→dense 대체).
- 5 query 가 clarify 발동 (A03/A05/A10/M04 + 1) — 의도된 보수적 동작이나 doc_id 채점 제외. 명확 query 의 clarifier skip 휴리스틱이 후속 과제.
- 출처: `apps/routers/admin.py`, `apps/routers/documents.py`, `web/app/{library,admin}/*`, `tests/e2e/golden_queries.yaml`, `scripts/eval_ragas.py`, `reports/eval.json`, `features/evaluation.md`

## [2026-06-08] build | 별표(부표) 청킹 버그 수정 + Docling md 산출물 저장 — ISSUE-001
- **증상**: "국내여비규정 2호구분 공무원의 일비?" 검색 실패, "하루 일비?" 로 바꾸면 성공. retrieval score 0.0x 로 불안정.
- **원인**: 별표 2(국내 여비 지급표) 일비표가 독립 청크가 아니라 `제18조 ③`(id 342)에 별표 1~9 전체와 12,218자로 뭉침. `APPENDIX_RE=^별표\d+` 가 Docling 실제 출력(`- [별표 N]` 목차 / `■ … [별표 N]` 본문헤더 / `## 제목` 별표단어 없음)을 못 잡아 경계 미인식 → 직전 조문에 흡수 + `chapter="제6장 보칙"` 오라벨.
- **수정** (`packages/regulation_parser/structure.py`):
  - `APPENDIX_BODY_RE = ■.*?\[\s*별표\s*(\d+(?:의\d+)?)\s*\]` — ■ 동반 줄만 본문 경계 (목차와 구분)
  - `APPENDIX_TOC_RE` + `_scan_appendix_titles()` — 목차에서 번호→제목 매핑 역주입
  - 별표 진입 시 chapter/section=None
  - `_self_check()` 에 별표 헤더 회귀 케이스 추가 (exit=0)
- **검증** (공무원여비규정.md 재파싱): 39→45 청크, 최대 12,218→**5,283자**, 별표 2 가 `공무원여비규정 > 별표 2 (국내 여비 지급표)` 독립 청크로 분리 (일비/제2호/25,000 온전).
- **부수**: `docling_loader.load_pdf_text(save_md_dir=)` + `indexer_worker` 가 `data/parsed/<문서>.md` 자동 저장. `.gitignore` `data/` → `data/*` + `data/parsed/*.md` 추적. 4 PDF 변환 산출물 커밋.
- **후속(미해결)**: 별표 4(5,283자) 행 단위 분할(table linearization), 별표 5·6의2·8 누락(■ 헤더 형태 차이), **공무원여비규정 재인덱싱**(DB 반영) 필요.
- 영향 페이지: `features/ingestion.md`, `issues/resolved/ISSUE-001.md`, `troubleshooting/common.md`, `index.md`
- 출처: `packages/regulation_parser/structure.py`, `packages/loaders/docling_loader.py`, `apps/indexer_worker.py`, `data/parsed/`

## [2026-05-28] build | post-M6 — Chat UI 폴리시 + Generator prompt 보강
- `web/components/chat/starter-chips.tsx` 신규 — 빈 채팅 화면에 3 카테고리 (정책·규정 / 위임전결 / 매뉴얼) ×8 starter prompts. 클릭 시 `startTurn` 직접 호출. lucide-react `Scale/ScrollText/FileText` 아이콘.
- `chat-stream.tsx` 빈 상태 placeholder 제거하고 `StarterChips` 마운트. busy 상태 disabled 전달.
- bug fix: `crypto.randomUUID()` 가 secure context (https/localhost) 외에서 undefined → LAN IP 접속 시 "is not a function" 에러. `newId()` 헬퍼로 fallback (`Date.now() + Math.random()`).
- Generator prompt 보강 (`packages/rag/nodes/generator_node.py`):
  - **의미적 용어 매핑 허용** — "학생 폭언" ↔ "폭행·모욕", "연차" ↔ "연가" 같은 매핑 명시. "정확한 단어가 없다"는 이유로 "내용 없음" 결론 금지.
  - **누락 금지** — 컨텍스트의 절차/조치/한도/기한/역할 정보를 빠짐없이 반영.
  - **다중 인용** — N개 sources 중 관련 있는 것 최소 2~3개 [근거] 에 인용.
  - few-shot 예시 1개 (학생 폭언 → 폭행·모욕 매핑).
- 사례 검증 (M01 "교육활동 보호 매뉴얼에서 학생 폭언 대응 절차"):
  - **이전**: [결론] "구체적인 대응 절차가 명시되어 있지 않습니다" + [근거] 1개. citation_valid_pct=1.0 인데 답변은 무의미.
  - **이후**: [결론] "교육활동 침해행위로 간주… 즉시 보호조치 → 관할청 보고" 구체화. [근거] 2개. [절차] 1·2 단계. 동일 sources, citation_valid_pct=1.0.
  - trade-off: generator 시간 3.3s → 13.4s (prompt 토큰 증가 + 답변 길이 증가).
- 측면 발견: clarifier 가 동일 query 에서 가끔 발동 (이전 호출은 통과, 재호출 시 target_ambiguous). LLM temperature=0 인데도 발생 — 후속 prompt 안정화 과제.
- 다음 30-query 재측정 시 citation 69.2% → 향상 기대. ADR-019 의 "citation prompt 보강" 1차 적용.
- 출처: `packages/rag/nodes/generator_node.py`, `web/components/chat/starter-chips.tsx`, `web/components/chat/chat-stream.tsx`

## [2026-06-05] ingest | 데이터셋 전면 교체 — 17 PDF → 4 PDF 재색인
- 기존 색인 전부 삭제: Postgres `TRUNCATE documents, articles, authority_rules, ingest_jobs, conversations, messages, checkpoints, checkpoint_blobs, checkpoint_writes RESTART IDENTITY CASCADE` + Qdrant `regulations` collection drop → `ensure_collection()` 재생성.
- 신규 데이터셋 (`ingest/` 루트 4개, 기존 17개는 `ingest/temp/` 로 이동됨): `개인용자동차보험약관.pdf`(19MB), `공무원여비규정.pdf`, `레저보험약관.pdf`, `사무위임전결규정.pdf`.
- 색인 결과 (doc_id 1부터 재시작):
  | doc_id | title | doc_type | chunks |
  |---|---|---|---|
  | 1 | 개인용자동차보험약관 | policy | 303 |
  | 2 | 공무원여비규정 | policy | 39 |
  | 3 | 레저보험약관 | policy | 208 |
  | 4 | 사무위임전결규정 | authority_matrix | 29 |
- **합계: 4 docs / 579 articles / Qdrant 579 points** (전부 extraction_quality=ok, dense+sparse 임베딩 성공).
- ⚠️ **authority_rules 추출 실패 (0 rules)**: 사무위임전결규정 vision 추출이 OpenAI `429 insufficient_quota` (할당량/결제 초과) 로 32/32 페이지 전부 실패. dense 임베딩은 로컬 fastembed 라 영향 없으나, vision(authority) + generator(gpt-4o-mini) 는 동일 키라 쿼리 시에도 실패 예상. **OpenAI 키 결제/quota 복구 후 `POST /admin/reindex/4` (또는 `scripts/backfill_authority.py`) 재실행 필요.**
- 운영 메모: indexer_worker 무한루프를 `run_in_background` 로 띄우면, 이후 다른 background 명령 실행 시 SIGTERM 전파로 worker 가 종료됨 (job 단위로는 깨끗이 마무리). 단발 처리에는 큐 1건만 처리 후 종료하는 일회성 스크립트가 안전.
- 출처: `scripts/bulk_ingest.py`, `apps/indexer_worker.py`, `packages/regulation_parser/authority_extractor.py`, `data/spec.md`, `features/authority_matrix.md`

## [2026-06-05] ingest | authority_rules 재추출 — quota 복구 후 282 rules
- 직전 재색인 때 OpenAI `429 insufficient_quota` 로 0행이던 사무위임전결규정(doc_id=4) authority 추출을, 사용자 결제 정상화 후 `scripts/backfill_authority.py --doc-ids 4 --reset` 로 복구.
- 결과: **282 authority_rules** (19/32 페이지에 표, amount 18 / % 0, ~4.5분). process 분포 other 255 / approval_general 15 / personnel 12 (process 매핑 약함은 기존과 동일한 알려진 한계). 샘플: 팀장/부서장/본부장 + 금액 한도(5억·1억 등).
- 위임전결 SQL 정확 조회(차별점 1) 정상 동작 복구. chunk(29개)는 1차 색인 때 이미 적재돼 있어 backfill 은 authority_rules 만 재생성.
- 갱신 페이지: `features/authority_matrix.md`(blocked→active), `data/spec.md`, `overview.md`, `index.md`.
- 출처: `scripts/backfill_authority.py`, `authority_rules` 테이블 측정

## [2026-06-05] ingest | 신규 위키 페이지 — 규정 질의 정확도 확보 방법
- 사용자 요청: "규정 및 제도 관점에서 질문에 대한 정확한 답변을 얻는 방법"을 위키로 정리.
- 신규 페이지 `features/answer_accuracy.md` 작성 — 정확도 위험 5종(조항 절단/한도 hallucination/인용 깨짐/오검색/모호성) → 방어 6단계(조항 chunking·authority SQL·계층 인용·route 격리·clarify·컨텍스트 제약 생성+검증) 매핑 플레이북 + 질문 유형별 경로 + 사용자용 질문 작성 가이드. 기존 feature 페이지로 cross-link 만 하고 내용 중복 회피.
- 현 정확도 표는 ADR-019(옛 17 PDF 30 query) 기준임을 명시 — 현 4 PDF eval 재작성이 선행 과제.
- 갱신 페이지: `index.md`(카탈로그 + 날짜).
- 출처: `features/{authority_matrix,citation,retrieval,generation}.md`, PRD §24

## [2026-06-08] build | ISSUE-001 retrieval 완전 해결 — linearization + HyDE + reranker + 별표 정규식 일반화
- **table linearization** (`article_chunker`): 별표 표를 `구분 제2호: 일비 25,000` 행 문장 청크(`appendix_row`)로. 별표 body 줄바꿈 보존(`structure.py`). `linearize_appendix_tables` 토글. 범위=별표 표만(보험약관 본문 표 제외).
- **HyDE 수정** (`query_rewriter_node`): 조문·별표 번호 추측 금지 + 동의어/자료유형 확장, temperature 0. 거짓 "별표 1" 환각 제거.
- **reranker 연결** (`reranker.py` 신규, `retriever_node`): RRF 후보(`rerank_candidate_k=60`)를 BAAI/bge-reranker-base cross-encoder 로 원질문과 재정렬. jina-v2-multilingual/bge-v2-m3 는 fastembed 미지원이라 base 채택.
- **별표 정규식 일반화** (`structure.py`): `■[별표N]` 외 제목헤더 역추적(`APPENDIX_TITLE_HEADER_RE`+목차 매핑) → 별표 6→9개 전수(별표 5·6의2·8 복구).
- **ablation**: 같은 청킹에서 rerank OFF→top6밖 / ON→별표2 1위(+3.5). **reranker 가 성능 1등**, linearization 은 안전마진 보조. 별표 9개로 늘며 정답이 후보 top30 밖 밀린 회귀 → `rerank_candidate_k` 30→60(추론 +193ms, 전체의 1.3%)으로 해결.
- **검증**: "2호구분 일비"/"하루 일비" → 별표2 1·2위, 답변 "1일당 25,000원". 별표8 +7.3, 별표5 +4.9 신규 인식 정상.
- 신규 위키 `features/clarifier.md`(끊긴 링크 해소). 영향: `features/{retrieval,ingestion}.md`, `issues/resolved/ISSUE-001.md`, `troubleshooting/common.md`, `index.md`.
- 설정: `.env` `RERANK_ENABLED=true`, `RERANK_CANDIDATE_K=60`, `RERANKER_MODEL=BAAI/bge-reranker-base`.
- 출처: `packages/rag/{reranker,nodes/retriever_node,nodes/query_rewriter_node}.py`, `packages/regulation_parser/{structure,article_chunker}.py`, `apps/config.py`

## [2026-06-08] build | 멀티턴 대화 참조 (최근 5턴) — 메모리 + 맥락 재검색
- **배경**: conversations/messages 테이블은 있었으나 저장·참조 로직이 전혀 없어 각 질문이 독립 처리됨.
- **저장/로드** (`repository.py`): `save_turn`(user+assistant 메시지 + conversation upsert), `get_recent_history(limit_turns=5)`. `query.py` `_persist_turn` 으로 턴 완료 시 저장(clarify 대기 중 미저장, resume 완료 시 저장), 질문 시 최근 5턴 로드 → `state.history`.
- **노드 주입**: `generator_node`(history → Human/AI 메시지), `clarifier_node`(history 참조 → 후속/지시어 질문 통과, 역질문 억제), `query_rewriter_node`(history 로 HyDE 맥락 복원 → 검색 query 확장).
- **검증**: Q2 "방금 뭘 물었나" → 이전 질문 기억 / Q2' "그럼 식비는?" → HyDE "국내 출장 2호 식비" 복원 → 별표 2 식비 행 검색 → "1일당 25,000원".
- **한계**: reranker 는 원질문 사용(후속 질문 변별 약할 수 있음), clarifier 과민(ADR-019), router/authority 는 history 미사용.
- 신규 위키: `features/conversation_memory.md`. 영향: `index.md`.
- 커밋: `2b6ebf6`(메모리), `af2784d`(rewriter history).
- 출처: `packages/db/repository.py`, `packages/rag/state.py`, `apps/routers/query.py`, `packages/rag/nodes/{clarifier,query_rewriter,generator}_node.py`
