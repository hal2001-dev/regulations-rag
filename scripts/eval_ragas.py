#!/usr/bin/env python
"""M6 KPI 측정 스크립트.

기본 (빠름):
    python scripts/eval_ragas.py [--queries tests/e2e/golden_queries.yaml] [--out reports/eval.json]
- 각 golden query 를 /query/stream 호출하여 수집
- 측정: route accuracy, top-1 doc_id hit, citation valid %, latency p50/p95
- ragas 없이 동작 (HTTP + 수집 + 통계 만)

옵션 (--ragas):
    python scripts/eval_ragas.py --ragas
- ragas faithfulness / answer_relevancy 추가 (LLM 호출 비용 발생)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import yaml

DEFAULT_QUERIES = Path(__file__).resolve().parents[1] / "tests/e2e/golden_queries.yaml"
DEFAULT_OUT = Path(__file__).resolve().parents[1] / "reports/eval.json"
DEFAULT_BASE = "http://localhost:8001"


def load_queries(path: Path) -> list[dict[str, Any]]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    default_route = (raw.get("defaults") or {}).get("expected_route", "policy")
    out: list[dict[str, Any]] = []
    for q in raw["queries"]:
        out.append(
            {
                "id": q["id"],
                "question": q["question"],
                "expected_route": q.get("expected_route", default_route),
                "expected_doc_id": q.get("expected_doc_id"),
                "expected_keywords": q.get("expected_keywords", []),
            }
        )
    return out


async def run_query(
    client: httpx.AsyncClient,
    base: str,
    question: str,
    timeout_sec: float = 60.0,
) -> dict[str, Any]:
    """단일 query 의 SSE 흐름을 끝까지 읽고 collected dict 반환."""
    collected: dict[str, Any] = {
        "first_token_at": None,
        "done_at": None,
        "route": None,
        "sources": [],
        "answer": "",
        "citation_valid_pct": None,
        "timings": None,
        "error": None,
        "clarify": False,
    }
    started = time.perf_counter()

    try:
        async with client.stream(
            "POST",
            f"{base}/query/stream",
            json={"question": question},
            timeout=timeout_sec,
        ) as resp:
            event = "message"
            data_buf = ""
            async for line in resp.aiter_lines():
                if line == "":
                    if data_buf:
                        try:
                            payload = json.loads(data_buf)
                        except json.JSONDecodeError:
                            payload = {}
                        _handle(event, payload, collected, started)
                        data_buf = ""
                        event = "message"
                    continue
                if line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("data:"):
                    data_buf += line[5:].strip()
    except Exception as e:  # noqa: BLE001
        collected["error"] = f"{type(e).__name__}: {e}"

    collected["total_sec"] = time.perf_counter() - started
    return collected


def _handle(event: str, payload: dict, collected: dict, started: float) -> None:
    if event == "clarify":
        collected["clarify"] = True
    elif event == "route":
        collected["route"] = payload.get("route")
    elif event == "sources":
        collected["sources"] = payload.get("sources", [])
    elif event == "token":
        if collected["first_token_at"] is None:
            collected["first_token_at"] = time.perf_counter() - started
        collected["answer"] += payload.get("token", "")
    elif event == "citation":
        collected["citation_valid_pct"] = payload.get("valid_pct")
    elif event == "done":
        collected["done_at"] = time.perf_counter() - started
        collected["timings"] = payload.get("timings")
        if not collected["route"]:
            collected["route"] = payload.get("route")
    elif event == "error":
        collected["error"] = payload.get("message")


def score_one(q: dict, r: dict) -> dict:
    """단일 query 결과 채점."""
    route_ok = (r.get("route") == q["expected_route"]) if not r.get("clarify") else None

    top1_doc_id = None
    if r.get("sources"):
        top1_doc_id = r["sources"][0].get("doc_id")
    doc_ok = None
    if q.get("expected_doc_id") is not None:
        doc_ok = top1_doc_id == q["expected_doc_id"]

    answer = r.get("answer", "") or ""
    kw_hits = sum(1 for kw in q.get("expected_keywords", []) if kw in answer)
    kw_total = len(q.get("expected_keywords", []))
    kw_pct = (kw_hits / kw_total) if kw_total else None

    return {
        "id": q["id"],
        "question": q["question"],
        "expected_route": q["expected_route"],
        "actual_route": r.get("route"),
        "clarify": r.get("clarify"),
        "route_ok": route_ok,
        "expected_doc_id": q.get("expected_doc_id"),
        "top1_doc_id": top1_doc_id,
        "doc_ok": doc_ok,
        "citation_valid_pct": r.get("citation_valid_pct"),
        "kw_hits": kw_hits,
        "kw_total": kw_total,
        "kw_pct": kw_pct,
        "first_token_sec": r.get("first_token_at"),
        "total_sec": r.get("total_sec"),
        "error": r.get("error"),
        "answer_preview": answer[:300],
    }


def aggregate(scores: list[dict]) -> dict:
    def avg(xs: list[float]) -> float | None:
        return sum(xs) / len(xs) if xs else None

    def pct(xs: list[bool]) -> float | None:
        if not xs:
            return None
        return sum(1 for x in xs if x) / len(xs)

    route_pairs = [s for s in scores if s["route_ok"] is not None]
    doc_pairs = [s for s in scores if s["doc_ok"] is not None]
    citations = [s["citation_valid_pct"] for s in scores if s["citation_valid_pct"] is not None]
    kws = [s["kw_pct"] for s in scores if s["kw_pct"] is not None]
    fts = [s["first_token_sec"] for s in scores if s["first_token_sec"] is not None]
    totals = [s["total_sec"] for s in scores if s["total_sec"] is not None]

    return {
        "n": len(scores),
        "n_clarified": sum(1 for s in scores if s["clarify"]),
        "n_errors": sum(1 for s in scores if s["error"]),
        "route_accuracy": pct([s["route_ok"] for s in route_pairs]),
        "top1_doc_hit": pct([s["doc_ok"] for s in doc_pairs]),
        "citation_valid_avg": avg(citations),
        "keyword_recall_avg": avg(kws),
        "first_token_p50": _quantile(fts, 0.5),
        "first_token_p95": _quantile(fts, 0.95),
        "end_to_end_p50": _quantile(totals, 0.5),
        "end_to_end_p95": _quantile(totals, 0.95),
    }


def _quantile(xs: list[float], q: float) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    idx = max(0, min(len(s) - 1, round(q * (len(s) - 1))))
    return s[idx]


def kpi_table(agg: dict) -> str:
    """PRD §24 KPI 비교 표."""
    rows = [
        ("citation 정확도", agg["citation_valid_avg"], 0.95, "≥0.95", _fmt_pct),
        ("retrieval top-1", agg["top1_doc_hit"], 0.85, "≥0.85", _fmt_pct),
        ("route accuracy", agg["route_accuracy"], 0.85, "≥0.85", _fmt_pct),
        ("keyword recall", agg["keyword_recall_avg"], 0.80, "≥0.80 (proxy)", _fmt_pct),
        ("end-to-end p95", agg["end_to_end_p95"], 3.0, "≤3.0s", _fmt_sec_inv),
        ("first-token p95", agg["first_token_p95"], 1.0, "≤1.0s", _fmt_sec_inv),
    ]
    lines = [f"{'metric':<22} {'value':>10}  {'target':>14}  {'pass?'}"]
    lines.append("-" * 60)
    for name, val, tgt, label, fmt in rows:
        if val is None:
            lines.append(f"{name:<22} {'(none)':>10}  {label:>14}  -")
            continue
        # inverse means lower is better
        ok = (val >= tgt) if fmt is _fmt_pct else (val <= tgt)
        mark = "✅" if ok else "❌"
        lines.append(f"{name:<22} {fmt(val):>10}  {label:>14}  {mark}")
    return "\n".join(lines)


def _fmt_pct(x: float) -> str:
    return f"{x*100:.1f}%"


def _fmt_sec_inv(x: float) -> str:
    return f"{x:.2f}s"


async def main_async(args: argparse.Namespace) -> int:
    queries = load_queries(Path(args.queries))
    print(f"[eval] {len(queries)} queries from {args.queries}")
    print(f"[eval] base={args.base}")

    scores: list[dict] = []
    async with httpx.AsyncClient() as client:
        for i, q in enumerate(queries):
            print(f"  [{i+1:02d}/{len(queries)}] {q['id']} {q['question'][:50]} …", flush=True)
            r = await run_query(client, args.base, q["question"])
            s = score_one(q, r)
            scores.append(s)
            tag = "🟡 clarify" if s["clarify"] else (
                f"route={s['actual_route']} doc={s['top1_doc_id']} cit={s['citation_valid_pct']}"
            )
            print(f"       → {tag}, kw {s['kw_hits']}/{s['kw_total']}, {s['total_sec']:.1f}s")
            if s["error"]:
                print(f"       ⚠ error: {s['error']}")

    agg = aggregate(scores)
    print()
    print(kpi_table(agg))

    if args.ragas:
        try:
            ragas_metrics = await run_ragas(scores)
            agg["ragas"] = ragas_metrics
            print()
            print("ragas:", json.dumps(ragas_metrics, ensure_ascii=False, indent=2))
        except Exception as e:  # noqa: BLE001
            print(f"[ragas] skipped: {e}", file=sys.stderr)

    out = {"aggregate": agg, "scores": scores}
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[eval] saved → {out_path}")
    return 0


async def run_ragas(scores: list[dict]) -> dict:
    """ragas faithfulness + answer_relevancy. clarify 된 query 와 sources 없는 query 는 제외."""
    from datasets import Dataset
    from langchain_openai import ChatOpenAI, OpenAIEmbeddings
    from ragas import evaluate
    from ragas.metrics import answer_relevancy, faithfulness

    samples: list[dict] = []
    for s in scores:
        if s["clarify"] or not s.get("answer_preview"):
            continue
        samples.append(
            {
                "question": s["question"],
                "answer": s["answer_preview"],
                # ragas 는 contexts 가 필요 — sources body 의 일부를 사용
                "contexts": _contexts_from_scores(s),
            }
        )
    if not samples:
        return {"note": "no eligible samples"}
    ds = Dataset.from_list(samples)
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    emb = OpenAIEmbeddings(model="text-embedding-3-small")
    result = evaluate(ds, metrics=[faithfulness, answer_relevancy], llm=llm, embeddings=emb)
    return {k: float(v) if v is not None else None for k, v in result.to_pandas().mean().to_dict().items()}


def _contexts_from_scores(s: dict) -> list[str]:
    # scores 에는 sources body 가 없으므로 answer 안의 [근거] 영역만 사용 (보수적 proxy)
    parts = s.get("answer_preview", "").split("[근거]")
    return parts[1:] if len(parts) > 1 else [s.get("answer_preview", "")]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--queries", default=str(DEFAULT_QUERIES))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--ragas", action="store_true", help="ragas faithfulness/answer_relevancy 추가")
    args = ap.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
