"""ParsedArticle → articles 테이블 row (chunk) 시퀀스.

mvp_plan §M2.4:
- 1 chunk = 1 `제N조` 기본
- >800 token 이면 `①②③` 단위 분할
- breadcrumb (`{doc_title} > {chapter} > {article_no} {title}`) 본문 앞에 prepend
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from packages.regulation_parser.structure import (
    ParsedArticle,
    ParsedParagraph,
)

CHUNK_TOKEN_LIMIT = 800
CHARS_PER_TOKEN = 2  # 한국어 보수 휴리스틱 (tiktoken 없이 충분)

# 마크다운 표 파싱 (table linearization, ISSUE-001) ──────────────────
_TABLE_ROW_RE = re.compile(r"^\s*\|(.+)\|\s*$")
_TABLE_SEP_RE = re.compile(r"^\s*\|[\s:|\-]+\|\s*$")  # |---|:--:|


def _parse_md_tables(text: str) -> list[tuple[list[str], list[list[str]]]]:
    """본문에서 마크다운 표 블록을 (header, rows) 리스트로 추출."""
    tables: list[tuple[list[str], list[list[str]]]] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m = _TABLE_ROW_RE.match(lines[i])
        if m and i + 1 < len(lines) and _TABLE_SEP_RE.match(lines[i + 1]):
            header = [c.strip() for c in m.group(1).split("|")]
            rows: list[list[str]] = []
            j = i + 2
            while j < len(lines):
                if _TABLE_SEP_RE.match(lines[j]):
                    j += 1
                    continue
                rm = _TABLE_ROW_RE.match(lines[j])
                if not rm:
                    break
                rows.append([c.strip() for c in rm.group(1).split("|")])
                j += 1
            if rows:
                tables.append((header, rows))
            i = j
        else:
            i += 1
    return tables


def _linearize_row(prefix: str, header: list[str], cells: list[str]) -> str | None:
    """표 한 행 → 검색 친화 자연어 문장.

    예) prefix="공무원여비규정 > 별표 2 (국내 여비 지급표)",
        header=["구분","일비 (1일당)","식비 (1일당)"], cells=["제2호","25,000","25,000"]
      → "공무원여비규정 > 별표 2 (국내 여비 지급표) — 구분 제2호: 일비 (1일당) 25,000, 식비 (1일당) 25,000"
    """
    if not cells or not any(c for c in cells):
        return None
    subject = cells[0].strip()
    pairs = [
        f"{(header[k] if k < len(header) else '').strip()} {cells[k].strip()}".strip()
        for k in range(1, len(cells))
        if cells[k].strip()
    ]
    if not pairs:
        return None
    subj_label = (header[0].strip() + " " if header and header[0].strip() else "") + subject
    return f"{prefix} — {subj_label}: " + ", ".join(pairs)


@dataclass
class Chunk:
    """`articles` 테이블 1 row 에 대응."""

    chapter: str | None
    section: str | None
    article_no: str
    article_title: str | None
    paragraph: str | None  # split 된 경우 ① 등, 아니면 None
    body: str  # breadcrumb 가 prepend 된 최종 본문
    heading_path: dict[str, Any] = field(default_factory=dict)
    content_type: str = "article"  # article / paragraph / appendix


def _approx_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


def _render_item(marker: str, body: str) -> str:
    sep = "." if marker.isdigit() else "."
    return f"{marker}{sep} {body}".strip()


def _render_paragraph(p: ParsedParagraph) -> str:
    head = f"{p.marker} {p.body}".strip() if p.marker else p.body.strip()
    if not p.items:
        return head
    items = "\n".join(f"  {_render_item(it.marker, it.body)}" for it in p.items)
    return head + ("\n" + items if items else "")


def _render_full_article(a: ParsedArticle) -> str:
    """heading + body + 모든 paragraph + item 을 합친 문자열."""
    head = a.article_no
    if a.article_title:
        head += f" ({a.article_title})"
    parts: list[str] = [head]
    if a.body:
        parts.append(a.body)
    for p in a.paragraphs:
        parts.append(_render_paragraph(p))
    return "\n".join(parts)


def _breadcrumb(doc_title: str, a: ParsedArticle, paragraph: str | None = None) -> str:
    """`{doc_title} > {chapter} > {article_no} {title} [> ①]`."""
    parts = [doc_title]
    if a.chapter:
        parts.append(a.chapter)
    if a.section:
        parts.append(a.section)
    head = a.article_no
    if a.article_title:
        head += f" ({a.article_title})"
    parts.append(head)
    if paragraph:
        parts.append(paragraph)
    return " > ".join(parts)


def _heading_path(doc_title: str, a: ParsedArticle, paragraph: str | None = None) -> dict[str, Any]:
    return {
        "doc_title": doc_title,
        "chapter": a.chapter,
        "section": a.section,
        "article_no": a.article_no,
        "article_title": a.article_title,
        "paragraph": paragraph,
    }


def chunk_document(
    doc_title: str, articles: list[ParsedArticle], linearize_tables: bool = True
) -> list[Chunk]:
    """ParsedArticle 시퀀스 → Chunk 시퀀스.

    linearize_tables=True 면 별표 표를 행 단위 자연어 청크로 보강 (ISSUE-001).
    """
    out: list[Chunk] = []
    for a in articles:
        full = _render_full_article(a)
        breadcrumb = _breadcrumb(doc_title, a)
        full_body = breadcrumb + "\n\n" + full
        content_type = "appendix" if a.is_appendix else "article"

        # 별표 표 → 행 단위 자연어 청크 추가 (table linearization, ISSUE-001).
        # 원본 별표 청크(맥락)는 그대로 두고, 검색 친화 행 문장을 별도 청크로 보강.
        if a.is_appendix and linearize_tables:
            for header, rows in _parse_md_tables(full):
                for cells in rows:
                    sent = _linearize_row(breadcrumb, header, cells)
                    if not sent:
                        continue
                    out.append(
                        Chunk(
                            chapter=a.chapter,
                            section=a.section,
                            article_no=a.article_no,
                            article_title=a.article_title,
                            paragraph=None,
                            body=sent,
                            heading_path=_heading_path(doc_title, a),
                            content_type="appendix_row",
                        )
                    )

        if _approx_tokens(full_body) <= CHUNK_TOKEN_LIMIT or not a.paragraphs:
            out.append(
                Chunk(
                    chapter=a.chapter,
                    section=a.section,
                    article_no=a.article_no,
                    article_title=a.article_title,
                    paragraph=None,
                    body=full_body,
                    heading_path=_heading_path(doc_title, a),
                    content_type=content_type,
                )
            )
            continue

        # paragraph 단위 분할 — article header 도 각 chunk 앞에 같이 prepend (self-contained)
        header = a.article_no + (f" ({a.article_title})" if a.article_title else "")
        for p in a.paragraphs:
            para_text = _render_paragraph(p)
            paragraph_marker = p.marker or None
            crumb = _breadcrumb(doc_title, a, paragraph_marker)
            body = crumb + "\n\n" + header + "\n" + para_text
            out.append(
                Chunk(
                    chapter=a.chapter,
                    section=a.section,
                    article_no=a.article_no,
                    article_title=a.article_title,
                    paragraph=paragraph_marker,
                    body=body,
                    heading_path=_heading_path(doc_title, a, paragraph_marker),
                    content_type="paragraph",
                )
            )
    return out


# ────────────────────────────────────────────────────────────────────
# inline 검증
# ────────────────────────────────────────────────────────────────────


def _self_check() -> None:
    from packages.regulation_parser.structure import parse_document

    sample = """제1장 총칙

제1조 (목적) 이 규정은 정함을 목적으로 한다.

제2조 (정의) ① 용어의 뜻은 다음과 같다.
1. "직원"
② 본 규정 외 사항은 다른 사규에 따른다.

별표 1 직급체계표
"""
    arts = parse_document(sample)
    chunks = chunk_document("인사관리규정", arts)
    assert len(chunks) == 3, f"expected 3 chunks (1+1+1), got {len(chunks)}"
    assert chunks[0].article_no == "제1조"
    assert chunks[0].content_type == "article"
    assert chunks[0].body.startswith("인사관리규정 > 제1장 총칙 > 제1조 (목적)")
    assert chunks[1].article_no == "제2조"
    assert chunks[1].body.startswith("인사관리규정 > 제1장 총칙 > 제2조 (정의)")
    assert "용어의 뜻" in chunks[1].body
    assert "다른 사규" in chunks[1].body
    assert chunks[2].article_no == "별표 1"
    assert chunks[2].content_type == "appendix"
    print(f"self-check ok: {len(chunks)} chunks")
    for c in chunks:
        head = c.body.split("\n", 1)[0]
        print(f"  [{c.content_type}] {head}")

    # 분할 케이스: 매우 큰 paragraph 두 개를 가진 가짜 article
    big = "가" * 2000
    arts2 = parse_document(f"제3조 (시험) ① {big}\n② {big}")
    chunks2 = chunk_document("Big규정", arts2)
    assert len(chunks2) >= 2, f"expected split into 2+ chunks, got {len(chunks2)}"
    assert all(c.paragraph in ("①", "②") for c in chunks2), [c.paragraph for c in chunks2]
    print(f"split case ok: {len(chunks2)} chunks (paragraph markers: {[c.paragraph for c in chunks2]})")


if __name__ == "__main__":
    _self_check()
