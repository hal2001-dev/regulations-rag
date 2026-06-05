"""ingest/ 경로의 PDF 들을 일괄로 큐에 enqueue 후, 인덱싱 완료까지 폴링한다.

사용:
    python scripts/bulk_ingest.py ingest/*.pdf
    python scripts/bulk_ingest.py ingest/감사규정.pdf --doc-type policy
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import httpx

DEFAULT_API = "http://127.0.0.1:8001"


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="Bulk enqueue PDFs to /ingest")
    p.add_argument("paths", nargs="+", help="PDF 파일 경로 (glob 가능, 셸이 펼침)")
    p.add_argument("--api", default=DEFAULT_API, help=f"API base url (default: {DEFAULT_API})")
    p.add_argument("--doc-type", default=None, help="user_doc_type override (전체 일괄 적용)")
    p.add_argument("--force-ocr", action="store_true", help="macOS Vision OCR 강제")
    p.add_argument("--no-wait", action="store_true", help="enqueue 만 하고 즉시 종료")
    p.add_argument(
        "--poll-interval",
        type=float,
        default=5.0,
        help="잡 상태 폴링 간격(초) (default: 5)",
    )
    args = p.parse_args(argv)

    files = [Path(x).resolve() for x in args.paths]
    missing = [f for f in files if not f.is_file()]
    if missing:
        for m in missing:
            print(f"  ✗ not a file: {m}", file=sys.stderr)
        return 2

    client = httpx.Client(base_url=args.api, timeout=30.0)

    # 1) enqueue
    job_ids: list[int] = []
    for f in files:
        body = {"source_path": str(f), "force_ocr": args.force_ocr}
        if args.doc_type:
            body["user_doc_type"] = args.doc_type
        try:
            r = client.post("/ingest", json=body)
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            print(f"  ✗ {f.name}: {e.response.status_code} {e.response.text}", file=sys.stderr)
            continue
        except Exception as e:
            print(f"  ✗ {f.name}: {type(e).__name__}: {e}", file=sys.stderr)
            continue
        data = r.json()
        job_ids.append(data["job_id"])
        print(f"  → enqueued job_id={data['job_id']:>4}: {f.name}")

    print(f"\nEnqueued {len(job_ids)}/{len(files)} jobs.")
    if not job_ids:
        return 1
    if args.no_wait:
        return 0

    # 2) poll
    print(f"Polling every {args.poll_interval}s (Ctrl-C to stop)...")
    pending = set(job_ids)
    summary: dict[int, dict] = {}
    while pending:
        time.sleep(args.poll_interval)
        try:
            r = client.get("/jobs", params={"ids": ",".join(map(str, pending))})
        except Exception as e:
            print(f"  poll error: {e}", file=sys.stderr)
            continue
        if r.status_code != 200:
            # /jobs 엔드포인트가 없거나 다른 응답 — 호출 형태 안내 후 종료
            print(
                f"  jobs endpoint returned {r.status_code}; install /jobs/{{id}} for live polling. "
                f"You can check progress directly: SELECT status, error FROM ingest_jobs WHERE id IN ({','.join(map(str, pending))});"
            )
            return 0
        rows = r.json().get("items", [])
        for j in rows:
            if j["status"] in ("done", "failed"):
                pending.discard(j["id"])
                summary[j["id"]] = j
                mark = "✓" if j["status"] == "done" else "✗"
                detail = (
                    f"doc_id={j.get('doc_id')}"
                    if j["status"] == "done"
                    else f"error={j.get('error', '')[:120]}"
                )
                print(f"  {mark} job {j['id']}: {j['status']} ({detail})")
        if pending:
            print(f"  ... {len(pending)} jobs still queued/running")

    done = sum(1 for j in summary.values() if j["status"] == "done")
    failed = sum(1 for j in summary.values() if j["status"] == "failed")
    print(f"\nResult: {done} done / {failed} failed out of {len(job_ids)} enqueued.")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
