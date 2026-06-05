"""authority_matrix doc 들의 위임전결 표 추출 후 authority_rules 적재.

사용:
    python scripts/backfill_authority.py             # 모든 authority_matrix docs
    python scripts/backfill_authority.py --doc-ids 12,13
    python scripts/backfill_authority.py --reset     # 기존 rules 삭제 후 재추출
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, select  # noqa: E402

from packages.code.logger import get_logger  # noqa: E402
from packages.db.connection import session_scope  # noqa: E402
from packages.db.models import AuthorityRule, Document  # noqa: E402
from packages.regulation_parser.authority_extractor import (  # noqa: E402
    ExtractedRule,
    extract_authority_rules_from_pdf,
)

log = get_logger("scripts.backfill_authority")


def _insert_rules(session, doc_id: int, rules: list[ExtractedRule]) -> int:
    for r in rules:
        session.add(
            AuthorityRule(
                doc_id=doc_id,
                process=r.process,
                task=r.task,
                approval_role=r.approval_role,
                amount_limit_krw=r.amount_limit_krw,
                approval_limit_pct=r.approval_limit_pct,
                condition=r.condition,
                raw_row=r.raw_row,
                source_page=r.source_page,
                confidence="ok",
            )
        )
    return len(rules)


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--doc-ids", default=None, help="comma-separated doc_ids (default: all authority_matrix)")
    p.add_argument("--reset", action="store_true", help="기존 authority_rules 삭제 후 재추출")
    args = p.parse_args(argv)

    with session_scope() as s:
        if args.doc_ids:
            doc_ids = [int(x) for x in args.doc_ids.split(",") if x.strip()]
            docs = s.scalars(select(Document).where(Document.doc_id.in_(doc_ids))).all()
        else:
            docs = s.scalars(select(Document).where(Document.doc_type == "authority_matrix")).all()
        targets = [(d.doc_id, d.source_path, d.title) for d in docs]

    if not targets:
        print("No target docs.")
        return 1

    print(f"\n=== Targets ({len(targets)}) ===")
    for did, path, title in targets:
        print(f"  doc_id={did}: {title}")
    print()

    total_inserted = 0
    t0 = time.perf_counter()
    for did, path, title in targets:
        log.info("--- doc_id={d} {t} ---", d=did, t=title)
        try:
            rules = extract_authority_rules_from_pdf(path)
        except Exception as e:  # noqa: BLE001
            log.exception("doc_id={d} extract failed: {e}", d=did, e=e)
            continue

        if not rules:
            log.warning("doc_id={d}: 0 rules extracted", d=did)
            continue

        with session_scope() as s:
            if args.reset:
                s.execute(delete(AuthorityRule).where(AuthorityRule.doc_id == did))
            n = _insert_rules(s, did, rules)
            total_inserted += n
        print(f"  doc_id={did}: {n} rules inserted ({time.perf_counter()-t0:.1f}s elapsed)")

    print(f"\nTotal: {total_inserted} authority_rules inserted across {len(targets)} docs in {time.perf_counter()-t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
