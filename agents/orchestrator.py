"""
orchestrator.py — The brain of the research assistant.

Uses Groq llama-3.3-70b (free) to:
1. Parse the user query → produce a ResearchPlan
2. Route to the right sub-agent after each step
3. Decide when enough context exists to summarize
"""

from __future__ import annotations
import json
from loguru import logger
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage

from state import (
    ResearchState, ResearchStatus, AgentName,
    ResearchPlan, append_step, Source,
)
from config import settings


def get_llm() -> ChatGroq:
    return ChatGroq(
        model=settings.orchestrator_model,
        api_key=settings.groq_api_key,
        temperature=0.1,
        max_tokens=1024,
    )


PLAN_SYSTEM = """You are a research orchestrator. Given a user query, produce a JSON research plan.

Available agents:
- web_search     : searches the web via DuckDuckGo (always available)
- pdf_reader     : searches uploaded PDF documents (only if PDFs are uploaded)
- code_executor  : runs Python code for computation or data analysis
- summarizer     : synthesises all context into a final cited answer

Rules:
- Always end with summarizer
- Only include pdf_reader if PDFs are uploaded
- Only include code_executor if the query needs computation
- parallel_groups = lists of agents that can run at the same time

Respond ONLY with valid JSON:
{
  "query": "original query",
  "sub_questions": ["question 1", "question 2"],
  "agents_to_use": ["web_search", "summarizer"],
  "parallel_groups": [["web_search"], ["summarizer"]],
  "reasoning": "brief explanation"
}"""

ROUTE_SYSTEM = """You are deciding what the research agent should do next.
Respond with exactly one of: web_search | pdf_reader | code_executor | summarizer | done

- web_search     : need more information from the web
- pdf_reader     : need to search uploaded PDFs
- code_executor  : need to run code or analysis
- summarizer     : have enough context, write the final answer
- done           : research is complete"""


def plan_research(state: ResearchState) -> dict:
    """Node — create a ResearchPlan from the user query."""
    logger.info(f"[Orchestrator] Planning: {state['user_query']}")

    has_pdfs = bool(state.get("uploaded_pdf_paths"))
    prompt = f"Query: {state['user_query']}\nPDFs uploaded: {has_pdfs}"

    try:
        response = get_llm().invoke([
            SystemMessage(content=PLAN_SYSTEM),
            HumanMessage(content=prompt),
        ])
        raw = response.content.strip()
        # Strip ```json ... ``` fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        plan = ResearchPlan(**json.loads(raw))
    except Exception as e:
        logger.warning(f"[Orchestrator] Plan parse failed ({e}), using fallback")
        plan = ResearchPlan(
            query=state["user_query"],
            sub_questions=[state["user_query"]],
            agents_to_use=[AgentName.WEB_SEARCH, AgentName.SUMMARIZER],
            parallel_groups=[[AgentName.WEB_SEARCH], [AgentName.SUMMARIZER]],
            reasoning="Fallback plan: web search then summarize.",
        )

    logger.info(f"[Orchestrator] Plan ready — agents: {plan.agents_to_use}")
    steps = append_step(
        state, AgentName.ORCHESTRATOR,
        action=f"Plan created — agents: {', '.join(a.value for a in plan.agents_to_use)}",
        status=ResearchStatus.PLANNING,
        detail=plan.reasoning,
    )
    return {"plan": plan, "status": ResearchStatus.PLANNING, "steps": steps, "iteration": 0}


def route_next(state: ResearchState) -> str:
    """
    Conditional edge — returns the next node name.
    Follows the plan first; falls back to LLM routing.
    """
    if state.get("iteration", 0) >= settings.max_iterations:
        logger.warning("[Orchestrator] Max iterations hit, forcing summarizer")
        return "summarizer"

    if state.get("status") == ResearchStatus.DONE:
        return "done"

    plan: ResearchPlan | None = state.get("plan")
    if plan:
        done = _completed_agents(state)
        for agent in plan.agents_to_use:
            if agent not in done and agent != AgentName.ORCHESTRATOR:
                logger.info(f"[Orchestrator] → {agent.value}")
                return agent.value

    return _llm_route(state)


def _completed_agents(state: ResearchState) -> set[AgentName]:
    done = set()
    if state.get("web_results"):
        done.add(AgentName.WEB_SEARCH)
    if state.get("pdf_results"):
        done.add(AgentName.PDF_READER)
    if state.get("code_result") is not None:
        done.add(AgentName.CODE_EXEC)
    if state.get("final_answer"):
        done.add(AgentName.SUMMARIZER)
    return done


def _llm_route(state: ResearchState) -> str:
    context = (
        f"Query: {state.get('user_query')}\n"
        f"Web results: {len(state.get('web_results', []))}\n"
        f"PDF results: {len(state.get('pdf_results', []))}\n"
        f"Code done: {state.get('code_result') is not None}\n"
        f"Answer written: {bool(state.get('final_answer'))}\n"
        f"Iteration: {state.get('iteration', 0)}"
    )
    response = get_llm().invoke([
        SystemMessage(content=ROUTE_SYSTEM),
        HumanMessage(content=context),
    ])
    decision = response.content.strip().lower()
    valid = {"web_search", "pdf_reader", "code_executor", "summarizer", "done"}
    if decision not in valid:
        logger.warning(f"[Orchestrator] Bad route '{decision}', defaulting to summarizer")
        return "summarizer"
    logger.info(f"[Orchestrator] LLM routed → {decision}")
    return decision


def increment_iteration(state: ResearchState) -> dict:
    return {"iteration": state.get("iteration", 0) + 1}
