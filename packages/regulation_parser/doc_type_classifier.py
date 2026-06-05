"""파일명 휴리스틱 doc_type 분류기 — mvp_plan §M2.1.

admin 이 명시적으로 override 한 경우 (`user_doc_type`) 그 값을 그대로 반환.
"""

from __future__ import annotations

import re
from pathlib import Path

VALID_DOC_TYPES = {
    "policy",
    "authority_matrix",
    "manual",
    "faq",
    "notice",
    "guideline",
    "template",
}


def classify(filename: str | Path, user_doc_type: str | None = None) -> str:
    """파일명 휴리스틱 + admin override.

    매핑(우선순위 순):
        위임전결|직무권한 → authority_matrix
        매뉴얼|가이드     → manual
        100문|문답|FAQ   → faq
        그 외             → policy
    """
    if user_doc_type:
        if user_doc_type not in VALID_DOC_TYPES:
            raise ValueError(f"invalid user_doc_type={user_doc_type!r}, valid: {VALID_DOC_TYPES}")
        return user_doc_type

    name = Path(filename).name
    if re.search(r"위임전결|직무권한", name):
        return "authority_matrix"
    if re.search(r"매뉴얼|가이드", name):
        return "manual"
    if re.search(r"100문|문답|FAQ", name, re.IGNORECASE):
        return "faq"
    return "policy"


def derive_title(filename: str | Path) -> str:
    """파일명에서 확장자 + 명확한 noise 제거 후 title 로 사용."""
    name = Path(filename).stem
    # 날짜 suffix (_20250101 등) 제거
    name = re.sub(r"_?\d{6,8}$", "", name)
    # 선두 번호 (`31._`, `1.`, `01_` 등) 제거
    name = re.sub(r"^\d+[\._\s]+", "", name)
    return name.strip() or Path(filename).stem


def _self_check() -> None:
    cases = [
        ("사무위임전결규정.pdf", None, "authority_matrix"),
        ("신천초 위임전결규정 제 4차 개정(20190308)-1.pdf", None, "authority_matrix"),
        ("건설공사 안전관리 매뉴얼(2024).pdf", None, "manual"),
        ("교육활동 보호 매뉴얼.pdf", None, "manual"),
        ("공무원여비100문100답.pdf", None, "faq"),
        ("인사관리규정.pdf", None, "policy"),
        ("31._회계규정_20191128.pdf", None, "policy"),
        ("국립중앙도서관 규정집_2019.pdf", None, "policy"),
        ("인사관리규정.pdf", "manual", "manual"),  # override
    ]
    for filename, override, expected in cases:
        got = classify(filename, override)
        assert got == expected, f"{filename} (override={override}) → {got} (expected {expected})"
    print(f"doc_type classify: {len(cases)} cases ok")

    titles = [
        ("31._회계규정_20191128.pdf", "회계규정"),
        ("신천초 위임전결규정 제 4차 개정(20190308)-1.pdf", "신천초 위임전결규정 제 4차 개정(20190308)-1"),
        ("인사관리규정.pdf", "인사관리규정"),
    ]
    for filename, expected in titles:
        got = derive_title(filename)
        assert got == expected, f"derive_title({filename}) = {got!r} (expected {expected!r})"
    print(f"derive_title: {len(titles)} cases ok")


if __name__ == "__main__":
    _self_check()
