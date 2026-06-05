"""LangGraph compile — M5: clarifier interrupt + HyDE + authority conditional.

흐름:
    START → clarifier
            ├ needs_clarify=True  → clarify_pause (interrupt_before) → query_rewriter
            └ needs_clarify=False → query_rewriter
    query_rewriter → router
            ├ route="authority"  → authority_lookup
            └ otherwise           → retriever
    → generator → citation_validator → END

interrupt: /query/resume 시 update_state 로 question/clarifications 갱신 후 ainvoke(None, config).
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from packages.code.logger import get_logger
from packages.rag.checkpointer import get_saver
from packages.rag.nodes.authority_lookup_node import authority_lookup_node
from packages.rag.nodes.citation_validator import citation_validator
from packages.rag.nodes.clarifier_node import clarifier_node
from packages.rag.nodes.generator_node import generator_node
from packages.rag.nodes.query_rewriter_node import query_rewriter_node
from packages.rag.nodes.retriever_node import retriever_node
from packages.rag.nodes.router_node import router_node
from packages.rag.state import QueryState

log = get_logger("packages.rag.graph")

_graph = None


def _pause_node(state: QueryState) -> dict:
    """clarify interrupt 의 marker — resume 시 정상 통과."""
    return {}


def _clarify_branch(state: QueryState) -> str:
    return "clarify_pause" if state.get("needs_clarify") else "query_rewriter"


def _route_branch(state: QueryState) -> str:
    return "authority_lookup" if state.get("route") == "authority" else "retriever"


async def build_graph():
    global _graph
    if _graph is not None:
        return _graph

    sg = StateGraph(QueryState)
    sg.add_node("clarifier", clarifier_node)
    sg.add_node("clarify_pause", _pause_node)
    sg.add_node("query_rewriter", query_rewriter_node)
    sg.add_node("router", router_node)
    sg.add_node("authority_lookup", authority_lookup_node)
    sg.add_node("retriever", retriever_node)
    sg.add_node("generator", generator_node)
    sg.add_node("citation_validator", citation_validator)

    sg.add_edge(START, "clarifier")
    sg.add_conditional_edges(
        "clarifier",
        _clarify_branch,
        {"clarify_pause": "clarify_pause", "query_rewriter": "query_rewriter"},
    )
    sg.add_edge("clarify_pause", "query_rewriter")
    sg.add_edge("query_rewriter", "router")
    sg.add_conditional_edges(
        "router",
        _route_branch,
        {"authority_lookup": "authority_lookup", "retriever": "retriever"},
    )
    sg.add_edge("authority_lookup", "generator")
    sg.add_edge("retriever", "generator")
    sg.add_edge("generator", "citation_validator")
    sg.add_edge("citation_validator", END)

    saver = await get_saver()
    _graph = sg.compile(checkpointer=saver, interrupt_before=["clarify_pause"])
    log.info("LangGraph compiled with clarifier interrupt + HyDE + authority conditional.")
    return _graph
