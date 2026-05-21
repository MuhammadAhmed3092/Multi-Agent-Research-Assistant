"""
summarizer.py — Summarizer Agent.
Uses Groq llama-3.1-8b-instant (free, very fast) to synthesise all
collected sources into a final, cited answer.
"""

from __future__ import annotations
from loguru import logger
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage

from state import (
    ResearchState, ResearchStatus, AgentName,
    Source, append_step, merge_sources,
)
from config import settings


SUMMARIZE_SYSTEM = """You are a research assistant synthesising information into a clear answer.

Instructions:
- Write a thorough, well-structured answer to the user's query
- Cite sources inline using [1], [2], etc. matching the numbered list provided
- If code was executed, include the key findings from the output
- Be factual, concise, and helpful
- End with a "## Sources" section listing all cited references"""


def _build_context(state: ResearchState) -> str:
    """Combine all agent outputs into a single context string for the LLM."""
    parts = [f"## User Query\n{state.get('user_query', '')}"]

    # Web results
    web = state.get("web_results", [])
    if web:
        parts.append("## Web Sources")
        for i, src in enumerate(web, 1):
            parts.append(f"[{i}] {src.title}\nURL: {src.url}\n{src.snippet}")

    # PDF results (continue numbering)
    pdf = state.get("pdf_results", [])
    offset = len(web)
    if pdf:
        parts.append("## PDF Sources")
        for i, src in enumerate(pdf, offset + 1):
            parts.append(f"[{i}] {src.title}\n{src.snippet}")

    # Code output
    code_result = state.get("code_result")
    if code_result and code_result.success:
        parts.append(f"## Code Execution Output\n```\n{code_result.stdout}\n```")

    return "\n\n".join(parts)


def run_summarizer(state: ResearchState) -> dict:
    """Node — synthesise all context into a final cited answer."""
    logger.info("[Summarizer] Synthesising final answer")

    steps = append_step(
        state, AgentName.SUMMARIZER,
        action="Synthesising final answer",
        status=ResearchStatus.SUMMARIZING,
    )

    context = _build_context(state)
    all_sources = merge_sources(
        state.get("web_results", []),
        state.get("pdf_results", []),
    )

    try:
        llm = ChatGroq(
            model=settings.summarizer_model,
            api_key=settings.groq_api_key,
            temperature=0.3,
            max_tokens=2048,
        )
        response = llm.invoke([
            SystemMessage(content=SUMMARIZE_SYSTEM),
            HumanMessage(content=context),
        ])
        answer = response.content.strip()

    except Exception as e:
        logger.error(f"[Summarizer] LLM call failed: {e}")
        answer = f"Research completed. Found {len(all_sources)} sources for: {state.get('user_query')}"

    logger.info(f"[Summarizer] Answer generated ({len(answer)} chars)")
    steps = append_step(
        state, AgentName.SUMMARIZER,
        action="Answer ready",
        status=ResearchStatus.DONE,
        detail=f"{len(all_sources)} sources cited",
    )

    return {
        "final_answer": answer,
        "citations": all_sources,
        "all_sources": all_sources,
        "status": ResearchStatus.DONE,
        "steps": steps,
    }
