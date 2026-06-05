"""rule-based router — 질문 키워드로 doc_type route 결정.

M4 에서 authority route 는 SQL 직접 조회 분기. M3 에선 route 만 결정하고
retriever_node 에서 payload 필터로 사용.
"""

from __future__ import annotations

import re

from packages.rag.state import QueryState

# "한도" 는 여비/회계/할인/계약 등에 흔히 등장 → authority route 트리거하면 false-positive.
# 다음 중 하나면 authority:
#   (1) 명시적 결재/전결 단어
#   (2) 금액 + (누가/결재) 동시 등장
#   (3) % + (할인|승인|결재) 동시 등장
_AUTHORITY_EXPLICIT_KW = re.compile(r"결재|전결|위임전결|승인권자|결재권자|누가\s*승인|누가\s*결재")
_AMOUNT_NUM = re.compile(r"\d[\d,]*\s*(?:억|천만|백만|만\s*원?|원)")
_PCT_NUM = re.compile(r"\d+(?:\.\d+)?\s*(?:%|퍼센트|프로)")
_APPROVAL_VERB = re.compile(r"누가|결재|승인|할인|위임|전결")

_MANUAL_KW = re.compile(r"매뉴얼|점검\s*절차|침해.*대응|안전.*절차")
_FAQ_KW = re.compile(r"100문|문답")


def _is_authority(q: str) -> bool:
    if _AUTHORITY_EXPLICIT_KW.search(q):
        return True
    if _AMOUNT_NUM.search(q) and _APPROVAL_VERB.search(q):
        return True
    if _PCT_NUM.search(q) and _APPROVAL_VERB.search(q):
        return True
    return False


def router_node(state: QueryState) -> dict:
    q = state["question"]
    if _is_authority(q):
        route = "authority"
    elif _MANUAL_KW.search(q):
        route = "manual"
    elif _FAQ_KW.search(q):
        route = "faq"
    else:
        route = "policy"
    return {
        "route": route,
        # M5 의 query_rewriter 자리. M3 에선 원본 question 그대로 통과.
        "rewritten_question": q,
    }
