"""한국어 규정 문서의 계층(장/절/조/항/호/목/별표) 파서.

mvp_plan §M2.3 의 6 regex 를 사용하여 plain text 를 평탄한 `ParsedArticle` 리스트로 변환한다.
청크 분할은 본 모듈이 아닌 `article_chunker` 의 책임.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ────────────────────────────────────────────────────────────────────
# 6 regex — mvp_plan §M2.3
# ────────────────────────────────────────────────────────────────────

CHAPTER_RE = re.compile(r"^제\s*\d+\s*장\s+(.+)$")
SECTION_RE = re.compile(r"^제\s*\d+\s*절\s+(.+)$")
# group 1 = article_no ("제5조" 또는 "제5조의2"), group 2 = 괄호 안 title (있을 수도)
ARTICLE_RE = re.compile(r"^(제\s*\d+\s*조(?:의\d+)?)\s*(?:\(([^)]+)\))?\s*(.*)$")
PARA_RE = re.compile(r"^([①-⑳])\s*(.*)$")
ITEM_NUM_RE = re.compile(r"^(\d+)\.\s+(.*)$")
ITEM_KOR_RE = re.compile(r"^([가-힣])\.\s+(.*)$")
# "별표 1", "별지 제1호" 등을 인정. "별지" 도 동일 취급 (citation 단위로는 article 과 같은 레벨)
# 줄 맨 앞에서 시작하는 단순 형태 (예: "별표 1 직급체계표").
APPENDIX_RE = re.compile(r"^(별표\s*\d+(?:의\d+)?|별지\s*(?:제\s*)?\d+\s*호?)")

# Docling 이 법령 PDF 별표를 뽑을 때의 실제 본문 시작 헤더.
#   예) "■ 공무원 여비 규정 [별표 2] <개정 2023. 3. 2.>"
# 머릿글(■ … [별표 N])이 동반된 줄만 별표 *본문* 경계로 인식한다.
# (목차 줄 "[별표 N] 제목(제3조 관련)" 은 ■ 가 없으므로 여기에 안 걸려 경계로 오인하지 않음.)
APPENDIX_BODY_RE = re.compile(r"■.*?\[\s*별표\s*(\d+(?:의\d+)?)\s*\]")

# 목차 줄에서 별표 번호 → 제목 매핑을 뽑기 위한 패턴.
#   예) "[별표 2] 국내 여비 지급표(제10조부터 …관련)"  → ("2", "국내 여비 지급표")
APPENDIX_TOC_RE = re.compile(r"^\[\s*별표\s*(\d+(?:의\d+)?)\s*\]\s*(.+)$")
# 제목 뒤에 붙는 "(제N조 … 관련)" 출처 표기 제거용.
_APPENDIX_TITLE_TAIL_RE = re.compile(r"\s*\([^)]*관련\)\s*$")

# 일부 별표는 "■ … [별표 N]" 머릿글 없이 제목 헤더만 나온다 (Docling 변형).
#   예) "이전비 지급 기준표 (제20조 관련)"  (← 별표 5, 번호 표기 없음)
# 이런 줄을 목차에서 만든 {제목→번호} 매핑으로 역추적해 별표 경계로 인정한다.
# "(제N조 … 관련)" 출처 꼬리가 붙은 제목 줄만 후보로 (일반 문장 오인 방지).
APPENDIX_TITLE_HEADER_RE = re.compile(r"^(.+?)\s*\(제[^)]*관련\)\s*$")


# ────────────────────────────────────────────────────────────────────
# 데이터 클래스
# ────────────────────────────────────────────────────────────────────


@dataclass
class ParsedItem:
    """호/목 — `1.` 또는 `가.` 마커."""

    marker: str  # "1" / "가"
    body: str


@dataclass
class ParsedParagraph:
    """항 — `①` 등 동그라미 숫자 마커."""

    marker: str  # "①"
    body: str
    items: list[ParsedItem] = field(default_factory=list)


@dataclass
class ParsedArticle:
    """조 (또는 별표) — articles 테이블의 1+ row 가 됨 (chunker 결정)."""

    chapter: str | None  # "제2장 임용" (제목 포함 전체)
    section: str | None  # "제1절 채용"
    article_no: str  # "제5조" / "제5조의2" / "별표 1"
    article_title: str | None  # "(채용 절차)" 의 괄호 안 텍스트
    body: str  # paragraph 마커 이전의 줄거리 본문 (없으면 "")
    paragraphs: list[ParsedParagraph] = field(default_factory=list)
    is_appendix: bool = False  # 별표/별지 여부 (citation 라벨 차별화용)


# ────────────────────────────────────────────────────────────────────
# 파서
# ────────────────────────────────────────────────────────────────────


def _normalize_article_no(raw: str) -> str:
    """`제 5 조` → `제5조`, `제5조의2` 유지."""
    return re.sub(r"\s+", "", raw)


def _normalize_chapter(raw: str) -> str:
    return re.sub(r"\s+", " ", raw).strip()


_MD_PREFIX_RE = re.compile(r"^(?:#+\s+|[-*]\s+)")


def _strip_md_prefix(line: str) -> str:
    """Docling 마크다운의 heading(`## `) / list(`- `, `* `) 마커 제거.

    `## 제8조의2(...)` 같은 라인이 헤딩 prefix 때문에 ARTICLE/CHAPTER regex 에 안 잡히는 문제 회피.
    """
    return _MD_PREFIX_RE.sub("", line)


def _scan_appendix_titles(text: str) -> dict[str, str]:
    """별표 목차 줄(`[별표 N] 제목(…관련)`)을 미리 훑어 {"별표 N": "제목"} 매핑 구축.

    본문 헤더(■ … [별표 N])에는 번호만 있고 제목은 다음 줄에 오므로, 목차에서 제목을
    가져와 채운다. "삭제"된 별표는 제외.
    """
    titles: dict[str, str] = {}
    for raw in text.splitlines():
        line = _strip_md_prefix(raw.strip())
        if not line or "■" in line:  # 본문 헤더(■)는 목차가 아니므로 제외
            continue
        m = APPENDIX_TOC_RE.match(line)
        if not m:
            continue
        num = re.sub(r"\s+", "", m.group(1))
        title = _APPENDIX_TITLE_TAIL_RE.sub("", m.group(2).strip()).strip()
        if title and title != "삭제":
            titles[f"별표 {num}"] = title
    return titles


def parse_document(text: str) -> list[ParsedArticle]:
    """plain text → 평탄한 ParsedArticle 리스트.

    PDF 추출 텍스트가 항상 깨끗하진 않지만, 줄바꿈만 기준으로 보수적으로 파싱한다.
    매칭 안 되는 줄은 가장 깊이 열린 노드(item > paragraph > article)의 body 에 누적.
    """
    appendix_titles = _scan_appendix_titles(text)
    # 제목 → 별표 번호 역매핑 (제목만 나오는 별표 헤더 역추적용).
    title_to_no = {title: no for no, title in appendix_titles.items()}
    articles: list[ParsedArticle] = []
    cur_chapter: str | None = None
    cur_section: str | None = None
    cur_article: ParsedArticle | None = None
    cur_paragraph: ParsedParagraph | None = None
    cur_item: ParsedItem | None = None

    def attach_text(line: str) -> None:
        nonlocal cur_article, cur_paragraph, cur_item
        if cur_item is not None:
            cur_item.body = _join(cur_item.body, line)
        elif cur_paragraph is not None:
            cur_paragraph.body = _join(cur_paragraph.body, line)
        elif cur_article is not None:
            # 별표는 마크다운 표 행 구조를 보존해야 table linearization 가능 → 줄바꿈 유지.
            if cur_article.is_appendix:
                cur_article.body = (
                    cur_article.body + "\n" + line if cur_article.body else line
                )
            else:
                cur_article.body = _join(cur_article.body, line)
        # article 도 없으면 (preamble) 버림

    for raw_line in text.splitlines():
        line = _strip_md_prefix(raw_line.strip())
        if not line:
            cur_item = None  # 빈 줄은 item 종료 신호 (보수적)
            continue

        # ─ 장
        m = CHAPTER_RE.match(line)
        if m:
            cur_chapter = _normalize_chapter(line)
            cur_section = None
            cur_article = None
            cur_paragraph = None
            cur_item = None
            continue

        # ─ 절
        m = SECTION_RE.match(line)
        if m:
            cur_section = _normalize_chapter(line)
            cur_article = None
            cur_paragraph = None
            cur_item = None
            continue

        # ─ 별표 본문 시작 헤더 (■ … [별표 N]) — Docling 법령 PDF 의 실제 별표 경계.
        #   별표는 장/절 밖이므로 chapter/section 컨텍스트를 끊는다.
        m = APPENDIX_BODY_RE.search(line)
        if m:
            num = re.sub(r"\s+", "", m.group(1))
            no = f"별표 {num}"
            cur_chapter = None
            cur_section = None
            cur_article = ParsedArticle(
                chapter=None,
                section=None,
                article_no=no,
                article_title=appendix_titles.get(no),
                body="",
                is_appendix=True,
            )
            articles.append(cur_article)
            cur_paragraph = None
            cur_item = None
            continue

        # ─ 제목 헤더만 있는 별표 (■[별표 N] 머릿글 누락분) — 목차 제목으로 번호 역추적.
        #   예) "이전비 지급 기준표 (제20조 관련)" → title_to_no 로 "별표 5" 인식.
        #   이미 같은 별표를 진행 중이면(제목 줄 중복) 새 경계로 만들지 않고 본문에 누적.
        mt = APPENDIX_TITLE_HEADER_RE.match(line)
        if mt:
            cand_no = title_to_no.get(mt.group(1).strip())
            if cand_no and not (cur_article is not None and cur_article.article_no == cand_no):
                cur_chapter = None
                cur_section = None
                cur_article = ParsedArticle(
                    chapter=None,
                    section=None,
                    article_no=cand_no,
                    article_title=appendix_titles.get(cand_no),
                    body="",
                    is_appendix=True,
                )
                articles.append(cur_article)
                cur_paragraph = None
                cur_item = None
                continue

        # ─ 별표/별지 (줄 맨 앞 단순 형태, article 과 동일 레벨로 취급)
        m = APPENDIX_RE.match(line)
        if m:
            no = re.sub(r"\s+", " ", m.group(1)).strip()
            cur_article = ParsedArticle(
                chapter=cur_chapter,
                section=cur_section,
                article_no=no,
                article_title=appendix_titles.get(no),
                body=line[m.end() :].strip(),
                is_appendix=True,
            )
            articles.append(cur_article)
            cur_paragraph = None
            cur_item = None
            continue

        # ─ 조
        m = ARTICLE_RE.match(line)
        if m:
            tail = (m.group(3) or "").strip()
            cur_article = ParsedArticle(
                chapter=cur_chapter,
                section=cur_section,
                article_no=_normalize_article_no(m.group(1)),
                article_title=(m.group(2) or None),
                body="",
            )
            articles.append(cur_article)
            cur_paragraph = None
            cur_item = None
            # 같은 줄에 ① 등이 이어붙은 경우 paragraph 로 분리
            if tail:
                pm = PARA_RE.match(tail)
                if pm:
                    cur_paragraph = ParsedParagraph(marker=pm.group(1), body=pm.group(2).strip())
                    cur_article.paragraphs.append(cur_paragraph)
                else:
                    cur_article.body = tail
            continue

        # ─ 항
        m = PARA_RE.match(line)
        if m and cur_article is not None:
            cur_paragraph = ParsedParagraph(marker=m.group(1), body=m.group(2).strip())
            cur_article.paragraphs.append(cur_paragraph)
            cur_item = None
            continue

        # ─ 호 (숫자) — paragraph 없으면 가상 paragraph 자동 생성
        m = ITEM_NUM_RE.match(line)
        if m and cur_article is not None:
            if cur_paragraph is None:
                cur_paragraph = ParsedParagraph(marker="", body="")
                cur_article.paragraphs.append(cur_paragraph)
            cur_item = ParsedItem(marker=m.group(1), body=m.group(2).strip())
            cur_paragraph.items.append(cur_item)
            continue

        # ─ 목 (한글 1자) — 마찬가지
        m = ITEM_KOR_RE.match(line)
        if m and cur_article is not None:
            if cur_paragraph is None:
                cur_paragraph = ParsedParagraph(marker="", body="")
                cur_article.paragraphs.append(cur_paragraph)
            cur_item = ParsedItem(marker=m.group(1), body=m.group(2).strip())
            cur_paragraph.items.append(cur_item)
            continue

        # 매칭 실패 → 가장 깊은 노드에 라인 누적
        attach_text(line)

    return articles


def _join(prev: str, line: str) -> str:
    if not prev:
        return line
    return prev + " " + line


# ────────────────────────────────────────────────────────────────────
# inline 검증 (python -m packages.regulation_parser.structure)
# ────────────────────────────────────────────────────────────────────


def _self_check() -> None:
    sample = """제1장 총칙

제1조 (목적) 이 규정은 사내 인사관리에 관한 사항을 정함을 목적으로 한다.

제2조 (정의) ① 이 규정에서 사용하는 용어의 뜻은 다음과 같다.
1. "직원"이란 회사에 고용된 자를 말한다.
2. "임원"이란 이사회에서 선임된 자를 말한다.
② 본 규정 외의 사항은 다른 사규에 따른다.

제2장 임용

제5조의2 (특별채용) 회사는 다음 각 호의 경우 특별채용을 실시할 수 있다.
1. 우수인재 영입의 필요가 있는 경우
가. 박사 학위 소지자
나. 동종업계 5년 이상 경력자

별표 1 직급체계표
"""
    arts = parse_document(sample)
    assert len(arts) == 4, f"expected 4 articles, got {len(arts)}"
    assert arts[0].article_no == "제1조"
    assert arts[0].article_title == "목적"
    assert arts[0].chapter and "제1장" in arts[0].chapter
    assert arts[1].article_no == "제2조"
    assert len(arts[1].paragraphs) == 2
    assert arts[1].paragraphs[0].marker == "①"
    assert len(arts[1].paragraphs[0].items) == 2
    assert arts[1].paragraphs[0].items[0].marker == "1"
    assert arts[2].article_no == "제5조의2"
    assert arts[2].chapter and "제2장" in arts[2].chapter
    assert arts[2].paragraphs[0].items[0].marker == "1"
    # 가. 나. 는 paragraph 가 없는 article 직속에는 안 들어감 (paragraph 안에 있어야 함)
    assert arts[3].article_no == "별표 1"
    assert arts[3].is_appendix

    # ─ 별표 본문 헤더(■ … [별표 N]) + 목차 제목 매핑 케이스 (Docling 법령 PDF 형태)
    appendix_sample = """## 제6장 보칙

제18조(근무지 내 출장) ③ 및 ④ 생략 [별표 1] 여비 지급 구분표(제3조 관련) [별표 2] 국내 여비 지급표(제10조 관련)

- [별표 1] 여비 지급 구분표(제3조 관련)
- [별표 2] 국내 여비 지급표(제10조부터 제13조까지 및 제16조제1항 관련)

## ■ 공무원 여비 규정 [별표 1] &lt;개정 2022. 5. 9.&gt;

## 여비 지급 구분표(제3조 관련)

| 구분 | 해당 공무원 |
|------|------|
| 제1호 | 대통령 등 |

- ■ 공무원 여비 규정 [별표 2] &lt;개정 2023. 3. 2.&gt;

## 국내 여비 지급표 (제10조부터 제13조까지 및 제16조제1항 관련)

| 구분 | 일비 (1일당) |
|------|------|
| 제2호 | 25,000 |
"""
    ax = parse_document(appendix_sample)
    by_no = {a.article_no: a for a in ax}
    assert "별표 1" in by_no and "별표 2" in by_no, [a.article_no for a in ax]
    assert by_no["별표 2"].is_appendix
    assert by_no["별표 2"].article_title == "국내 여비 지급표", by_no["별표 2"].article_title
    assert by_no["별표 2"].chapter is None  # 별표는 장/절 밖
    assert "25,000" in by_no["별표 2"].body
    assert "제18조" in by_no  # 조문 자체는 그대로 분리
    print("appendix-header self-check ok: 별표 2 →", by_no["별표 2"].article_title)

    print(f"self-check ok: parsed {len(arts)} articles")
    for a in arts:
        print(f"  {a.chapter} / {a.section} / {a.article_no} {a.article_title or ''}")
        for p in a.paragraphs:
            print(f"    {p.marker} {p.body[:40]}")
            for it in p.items:
                print(f"      {it.marker}. {it.body[:40]}")


if __name__ == "__main__":
    _self_check()
