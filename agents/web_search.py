"""
web_search.py — Web Search Agent.
Uses ddgs (DuckDuckGo, free, no API key) to search the web.
"""

from __future__ import annotations
import uuid
from loguru import logger

from state import (
    ResearchState, ResearchStatus, AgentName,
    Source, append_step,
)
from config import settings


def run_web_search(state: ResearchState) -> dict:
    """Node — search DuckDuckGo and return ranked Source objects."""
    query = state.get("user_query", "")
    logger.info(f"[WebSearch] Searching: {query}")

    steps = append_step(
        state, AgentName.WEB_SEARCH,
        action=f"Searching web for: {query}",
        status=ResearchStatus.SEARCHING,
    )

    results: list[Source] = []
    try:
        # Try new package name first, fall back to old
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS

        with DDGS() as ddgs:
            raw = list(ddgs.text(query, max_results=settings.max_search_results))

        for i, item in enumerate(raw):
            score = round(1.0 - (i * 0.15), 2)
            results.append(Source(
                id=str(uuid.uuid4()),
                title=item.get("title", "Untitled"),
                url=item.get("href", ""),
                snippet=item.get("body", ""),
                agent=AgentName.WEB_SEARCH,
                score=max(score, 0.1),
            ))

        logger.info(f"[WebSearch] Found {len(results)} results")
        steps = append_step(
            state, AgentName.WEB_SEARCH,
            action=f"Found {len(results)} web sources",
            status=ResearchStatus.SEARCHING,
            detail=", ".join(r.title for r in results[:3]),
        )

    except Exception as e:
        logger.error(f"[WebSearch] Failed: {e}")
        steps = append_step(
            state, AgentName.WEB_SEARCH,
            action="Web search failed",
            status=ResearchStatus.ERROR,
            detail=str(e),
        )

    return {
        "web_results": results,
        "all_sources": [*state.get("all_sources", []), *results],
        "steps": steps,
    }
