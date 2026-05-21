"""
tests/test_agents.py — Unit tests for state, routing, and agent stubs.
Run with: pytest tests/ -v
"""

import pytest
from state import (
    initial_state, append_step, merge_sources,
    AgentName, ResearchStatus, Source, ResearchPlan,
)
from agents.orchestrator import route_next, _completed_agents


def make_state(query="Test query"):
    return initial_state(query, session_id="test-session")


def test_initial_state_keys():
    state = make_state()
    assert state["status"] == ResearchStatus.PENDING
    assert state["web_results"] == []
    assert state["iteration"] == 0


def test_append_step():
    state = make_state()
    steps = append_step(state, AgentName.WEB_SEARCH, "Searching", ResearchStatus.SEARCHING)
    assert len(steps) == 1
    assert steps[0].agent == AgentName.WEB_SEARCH


def test_merge_sources_deduplication():
    s1 = Source(id="1", title="A", url="https://a.com", snippet="...", agent=AgentName.WEB_SEARCH)
    s2 = Source(id="2", title="B", url="https://b.com", snippet="...", agent=AgentName.WEB_SEARCH)
    s3 = Source(id="3", title="A dup", url="https://a.com", snippet="...", agent=AgentName.WEB_SEARCH)
    merged = merge_sources([s1, s2], [s3])
    assert len(merged) == 2


def test_routing_follows_plan():
    state = make_state()
    state["plan"] = ResearchPlan(
        query="Test",
        agents_to_use=[AgentName.WEB_SEARCH, AgentName.SUMMARIZER],
        parallel_groups=[[AgentName.WEB_SEARCH], [AgentName.SUMMARIZER]],
    )
    assert route_next(state) == "web_search"


def test_routing_after_web_search():
    state = make_state()
    state["plan"] = ResearchPlan(
        query="Test",
        agents_to_use=[AgentName.WEB_SEARCH, AgentName.SUMMARIZER],
        parallel_groups=[[AgentName.WEB_SEARCH], [AgentName.SUMMARIZER]],
    )
    state["web_results"] = [
        Source(id="1", title="T", url="https://x.com", snippet="...", agent=AgentName.WEB_SEARCH)
    ]
    assert route_next(state) == "summarizer"


def test_max_iterations_guard():
    state = make_state()
    state["iteration"] = 999
    assert route_next(state) == "summarizer"
