"""
state.py — Central LangGraph state schema.
Every agent reads from and writes to this TypedDict.
"""

from __future__ import annotations
from enum import Enum
from typing import Annotated, TypedDict
from pydantic import BaseModel, Field
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class AgentName(str, Enum):
    ORCHESTRATOR = "orchestrator"
    WEB_SEARCH   = "web_search"
    PDF_READER   = "pdf_reader"
    CODE_EXEC    = "code_executor"
    SUMMARIZER   = "summarizer"


class ResearchStatus(str, Enum):
    PENDING     = "pending"
    PLANNING    = "planning"
    SEARCHING   = "searching"
    READING     = "reading"
    EXECUTING   = "executing"
    SUMMARIZING = "summarizing"
    DONE        = "done"
    ERROR       = "error"


class Source(BaseModel):
    id: str
    title: str
    url: str | None = None
    snippet: str
    agent: AgentName
    score: float = 1.0


class CodeResult(BaseModel):
    code: str
    stdout: str
    stderr: str
    success: bool
    execution_time_ms: int = 0


class AgentStep(BaseModel):
    agent: AgentName
    action: str
    status: ResearchStatus
    detail: str = ""


class ResearchPlan(BaseModel):
    query: str
    sub_questions: list[str] = Field(default_factory=list)
    agents_to_use: list[AgentName] = Field(default_factory=list)
    parallel_groups: list[list[AgentName]] = Field(default_factory=list)
    reasoning: str = ""


class ResearchState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], add_messages]
    session_id: str
    user_query: str
    plan: ResearchPlan | None
    current_agent: AgentName | None
    iteration: int
    web_results: list[Source]
    pdf_results: list[Source]
    code_result: CodeResult | None
    all_sources: list[Source]
    final_answer: str
    citations: list[Source]
    status: ResearchStatus
    steps: list[AgentStep]
    error: str | None
    uploaded_pdf_paths: list[str]


def initial_state(user_query: str, session_id: str, pdf_paths: list[str] | None = None) -> ResearchState:
    return ResearchState(
        messages=[],
        session_id=session_id,
        user_query=user_query,
        plan=None,
        current_agent=None,
        iteration=0,
        web_results=[],
        pdf_results=[],
        code_result=None,
        all_sources=[],
        final_answer="",
        citations=[],
        status=ResearchStatus.PENDING,
        steps=[],
        error=None,
        uploaded_pdf_paths=pdf_paths or [],
    )


def append_step(state: ResearchState, agent: AgentName, action: str,
                status: ResearchStatus, detail: str = "") -> list[AgentStep]:
    step = AgentStep(agent=agent, action=action, status=status, detail=detail)
    return [*state.get("steps", []), step]


def merge_sources(*source_lists: list[Source]) -> list[Source]:
    seen: set[str] = set()
    merged: list[Source] = []
    for sources in source_lists:
        for src in sources:
            key = src.url or src.id
            if key not in seen:
                seen.add(key)
                merged.append(src)
    return sorted(merged, key=lambda s: s.score, reverse=True)
