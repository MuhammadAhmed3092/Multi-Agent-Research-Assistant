"""
code_executor.py — Code Executor Agent.
Uses Groq to generate Python code, then runs it in a local restricted
sandbox (RestrictedPython). Completely free, no E2B needed.
"""

from __future__ import annotations
import time
import textwrap
from loguru import logger
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage

from state import (
    ResearchState, ResearchStatus, AgentName,
    CodeResult, append_step,
)
from config import settings


CODE_SYSTEM = """You are a Python code generation assistant.
Given a research question, write clean Python code to compute or analyse the answer.

Rules:
- Only use standard library modules (math, statistics, json, re, datetime, etc.)
- Do NOT use requests, urllib, or any network calls
- Do NOT use file I/O
- Print your results clearly with print()
- Keep code under 50 lines
- Return ONLY the Python code, no markdown fences, no explanation"""


def _generate_code(query: str) -> str:
    llm = ChatGroq(
        model=settings.orchestrator_model,
        api_key=settings.groq_api_key,
        temperature=0.1,
        max_tokens=512,
    )
    response = llm.invoke([
        SystemMessage(content=CODE_SYSTEM),
        HumanMessage(content=f"Write Python code to answer: {query}"),
    ])
    code = response.content.strip()
    # Strip fences if model added them anyway
    if code.startswith("```"):
        lines = code.split("\n")
        code = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
    return code


def _safe_exec(code: str) -> tuple[str, str, bool]:
    """
    Run code in a restricted local sandbox using RestrictedPython.
    Returns (stdout, stderr, success).
    """
    from restrictedpython import compile_restricted, safe_globals
    from io import StringIO
    import sys

    stdout_capture = StringIO()
    stderr_capture = StringIO()

    restricted_globals = {
        **safe_globals,
        "_print_": lambda *a, **kw: print(*a, **kw, file=stdout_capture),
        "__builtins__": {
            "print": lambda *a, **kw: print(*a, **kw, file=stdout_capture),
            "range": range, "len": len, "int": int, "float": float,
            "str": str, "list": list, "dict": dict, "set": set,
            "sum": sum, "min": min, "max": max, "abs": abs,
            "round": round, "sorted": sorted, "enumerate": enumerate,
            "zip": zip, "map": map, "filter": filter,
            "True": True, "False": False, "None": None,
        },
    }

    try:
        compiled = compile_restricted(code, "<research>", "exec")
        exec(compiled, restricted_globals)
        return stdout_capture.getvalue(), "", True
    except Exception as e:
        return "", str(e), False


def run_code_executor(state: ResearchState) -> dict:
    """Node — generate and execute Python code to answer the query."""
    query = state.get("user_query", "")
    logger.info(f"[CodeExecutor] Generating code for: {query}")

    steps = append_step(
        state, AgentName.CODE_EXEC,
        action="Generating Python code",
        status=ResearchStatus.EXECUTING,
    )

    try:
        code = _generate_code(query)
        logger.info(f"[CodeExecutor] Code generated ({len(code)} chars), executing...")

        start = time.time()
        stdout, stderr, success = _safe_exec(code)
        elapsed_ms = int((time.time() - start) * 1000)

        result = CodeResult(
            code=code,
            stdout=stdout[:2000],   # cap output length
            stderr=stderr[:500],
            success=success,
            execution_time_ms=elapsed_ms,
        )

        logger.info(f"[CodeExecutor] Done — success={success}, time={elapsed_ms}ms")
        steps = append_step(
            state, AgentName.CODE_EXEC,
            action=f"Code executed ({'success' if success else 'error'})",
            status=ResearchStatus.EXECUTING,
            detail=stdout[:200] if success else stderr[:200],
        )

    except Exception as e:
        logger.error(f"[CodeExecutor] Failed: {e}")
        result = CodeResult(code="", stdout="", stderr=str(e), success=False)
        steps = append_step(
            state, AgentName.CODE_EXEC,
            action="Code execution failed",
            status=ResearchStatus.ERROR,
            detail=str(e),
        )

    return {"code_result": result, "steps": steps}
