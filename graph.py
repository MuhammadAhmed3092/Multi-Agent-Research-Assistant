"""
graph.py — Assembles and compiles the full LangGraph research graph.

Flow:
  START → plan_research → [route] → web_search / pdf_reader / code_executor
                                  → increment → [route] → ...
                                  → summarizer → END
"""

from langgraph.graph import StateGraph, START, END
from state import ResearchState
from agents.orchestrator import plan_research, route_next, increment_iteration


def build_graph():
    from agents.web_search import run_web_search
    from agents.pdf_reader import run_pdf_reader
    from agents.code_executor import run_code_executor
    from agents.summarizer import run_summarizer

    g = StateGraph(ResearchState)

    # Nodes
    g.add_node("plan_research",  plan_research)
    g.add_node("web_search",     run_web_search)
    g.add_node("pdf_reader",     run_pdf_reader)
    g.add_node("code_executor",  run_code_executor)
    g.add_node("summarizer",     run_summarizer)
    g.add_node("increment",      increment_iteration)

    ROUTE_MAP = {
        "web_search":    "web_search",
        "pdf_reader":    "pdf_reader",
        "code_executor": "code_executor",
        "summarizer":    "summarizer",
        "done":          END,
    }

    # Edges
    g.add_edge(START, "plan_research")
    g.add_conditional_edges("plan_research", route_next, ROUTE_MAP)

    for node in ["web_search", "pdf_reader", "code_executor"]:
        g.add_edge(node, "increment")

    g.add_conditional_edges("increment", route_next, ROUTE_MAP)
    g.add_edge("summarizer", END)

    return g.compile()


_graph = None

def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph
