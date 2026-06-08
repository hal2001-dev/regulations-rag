"""Docling 기반 PDF → markdown text 로더.

M2 범위:
- 1차: OCR off (`do_ocr=False`) 디지털 PDF 텍스트 추출
- 결과 markdown 을 한국어 친화적으로 정규화 (NFC, weird space 제거, 페이지 번호 라인 제거 등)
- 추출 결과가 빈약하면(`scan_only` 의심) `extraction_quality` 라벨링용 휴리스틱 반환

스캔본 macOS Vision OCR fallback (OcrMacOptions, lang=ko-KR) 는 M2 후속.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from packages.code.logger import get_logger

log = get_logger("packages.loaders.docling_loader")


# ────────────────────────────────────────────────────────────────────
# 텍스트 정규화 (한국어 친화)
# ────────────────────────────────────────────────────────────────────

_WEIRD_SPACES_RE = re.compile(r"[  -​  　]")
_HYPHEN_LINEBREAK_RE = re.compile(r"(\w)-\s*\n\s*(\w)")
_PAGE_NUMBER_LINE_RE = re.compile(r"(?m)^[ \t]*-?\s*\d{1,4}\s*-?[ \t]*$")
_MULTI_SPACE_RE = re.compile(r" {2,}")
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")


def normalize_markdown(text: str) -> str:
    """Docling 마크다운의 전형적 아티팩트 정리."""
    if not text:
        return text
    text = unicodedata.normalize("NFC", text)
    text = _WEIRD_SPACES_RE.sub(" ", text)
    text = _HYPHEN_LINEBREAK_RE.sub(r"\1\2", text)
    text = _PAGE_NUMBER_LINE_RE.sub("", text)
    text = _MULTI_SPACE_RE.sub(" ", text)
    text = _MULTI_NEWLINE_RE.sub("\n\n", text)
    return text.strip()


# ────────────────────────────────────────────────────────────────────
# 로더
# ────────────────────────────────────────────────────────────────────


@dataclass
class LoadResult:
    text: str
    extraction_quality: str  # ok / partial / scan_only
    page_count: int


_converter = None


def _get_converter():
    """DocumentConverter lazy init (첫 호출 시 모델 다운로드).

    Apple Silicon MPS 백엔드가 float64 를 지원하지 않아 Docling layout/table 모델이
    실패하므로 CPU 로 강제 (`AcceleratorDevice.CPU`).
    """
    global _converter
    if _converter is None:
        from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption

        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = False  # M2 는 OCR off 1차
        pipeline_options.do_table_structure = True
        pipeline_options.accelerator_options = AcceleratorOptions(
            num_threads=4, device=AcceleratorDevice.CPU
        )

        _converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
            }
        )
        log.info("Docling DocumentConverter initialized (do_ocr=False, device=cpu)")
    return _converter


def load_pdf_text(path: str | Path, save_md_dir: str | Path | None = None) -> LoadResult:
    """PDF → 정규화된 markdown text + 품질 라벨.

    품질 라벨:
        scan_only — text 가 거의 없음 (< 200 chars total)
        partial   — 페이지 수 대비 텍스트가 적음 (< 100 chars/page)
        ok        — 기본

    save_md_dir 가 주어지면 정규화된 markdown 을 `<save_md_dir>/<stem>.md` 로 저장
    (디버깅/재현/표 청킹 분석용 중간 산출물). Docling 변환이 느리므로 캐시 효과도 있음.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)

    converter = _get_converter()
    log.info("Docling converting: {p}", p=path.name)
    result = converter.convert(str(path))
    doc = result.document

    md = doc.export_to_markdown()
    md = normalize_markdown(md)

    if save_md_dir is not None:
        out_dir = Path(save_md_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{path.stem}.md"
        out_path.write_text(md, encoding="utf-8")
        log.info("Saved parsed markdown: {p} ({c} chars)", p=str(out_path), c=len(md))

    # 페이지 수 추정
    try:
        page_count = len(doc.pages) if hasattr(doc, "pages") else 0
    except Exception:
        page_count = 0

    char_count = len(md)
    if char_count < 200:
        quality = "scan_only"
    elif page_count > 0 and char_count / page_count < 100:
        quality = "partial"
    else:
        quality = "ok"

    log.info(
        "Docling done: {p} → {c} chars, {pg} pages, quality={q}",
        p=path.name,
        c=char_count,
        pg=page_count,
        q=quality,
    )
    return LoadResult(text=md, extraction_quality=quality, page_count=page_count)


# ────────────────────────────────────────────────────────────────────
# 실행 entry — python -m packages.loaders.docling_loader <path>
# ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("usage: python -m packages.loaders.docling_loader <pdf_path>", file=sys.stderr)
        sys.exit(2)
    res = load_pdf_text(sys.argv[1])
    print(f"=== {len(res.text)} chars, {res.page_count} pages, quality={res.extraction_quality} ===")
    print(res.text[:2000])
