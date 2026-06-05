"""기존 인덱싱된 articles 를 임베딩 + Qdrant upsert.

M2 시점엔 Postgres articles 만 있고 Qdrant 는 비어있음. 이 스크립트로 일괄 인덱싱.
이후 새 PDF 는 indexer_worker 가 자동으로 upsert.

사용:
    python scripts/backfill_embeddings.py            # 전체 docs
    python scripts/backfill_embeddings.py --doc-ids 2,3,4
    python scripts/backfill_embeddings.py --reset    # 재시작 전 Qdrant 데이터 모두 삭제
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# project root 를 PYTHONPATH 에 추가 (스크립트 직접 실행 지원)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from packages.code.logger import get_logger
from packages.db.connection import session_scope
from packages.db.models import Document
from packages.rag.index_articles import ensure_index_ready, index_articles_for_doc, reset_doc_in_qdrant

log = get_logger("scripts.backfill_embeddings")


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="Backfill Qdrant embeddings from Postgres articles")
    p.add_argument("--doc-ids", default=None, help="comma-separated doc_ids (default: all)")
    p.add_argument("--reset", action="store_true", help="대상 doc 의 기존 Qdrant point 삭제 후 재색인")
    p.add_argument("--limit", type=int, default=None, help="최대 N docs 처리")
    args = p.parse_args(argv)

    ensure_index_ready()

    with session_scope() as s:
        if args.doc_ids:
            doc_ids = [int(x) for x in args.doc_ids.split(",") if x.strip()]
        else:
            rows = s.scalars(select(Document).order_by(Document.doc_id)).all()
            doc_ids = [d.doc_id for d in rows if d.chunk_count > 0]
        if args.limit:
            doc_ids = doc_ids[: args.limit]

    log.info("Backfill target: {n} docs", n=len(doc_ids))

    total = 0
    t0 = time.perf_counter()
    for i, did in enumerate(doc_ids, start=1):
        try:
            with session_scope() as s:
                if args.reset:
                    reset_doc_in_qdrant(s, did)
                n = index_articles_for_doc(s, did)
                total += n
            elapsed = time.perf_counter() - t0
            print(f"  [{i}/{len(doc_ids)}] doc_id={did}: {n} points (total {total}, {elapsed:.1f}s)")
        except Exception as e:  # noqa: BLE001
            log.exception("doc_id={d} failed: {e}", d=did, e=e)
            print(f"  [{i}/{len(doc_ids)}] doc_id={did}: FAILED ({type(e).__name__}: {e})")

    print(f"\nTotal: {total} points across {len(doc_ids)} docs in {time.perf_counter()-t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
