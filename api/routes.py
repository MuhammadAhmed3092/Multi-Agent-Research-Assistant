"""
api/routes.py — FastAPI routes with:
  - User fingerprinting (IP + user-agent hash)
  - 6-prompt quota per user per 24h
  - Full query + agent-step logging to SQLite
  - SSE streaming research endpoint
  - Admin dashboard endpoint (protected by ADMIN_KEY)
"""

from __future__ import annotations
import uuid, json, asyncio, hashlib, time, os
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException, Request, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from loguru import logger

from state import initial_state, ResearchStatus
from graph import get_graph
from db import (
    get_or_create_user, check_and_increment_quota,
    log_query_start, log_query_complete, log_query_error, log_agent_step,
    get_all_users, get_recent_queries, get_query_agent_logs, get_stats,
    PROMPT_LIMIT,
)

router     = APIRouter()
UPLOAD_DIR = Path("./uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


def _fingerprint(request: Request) -> str:
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown")
    ua = request.headers.get("user-agent", "")
    return hashlib.sha256(f"{ip}::{ua}".encode()).hexdigest()[:32]


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


class ResearchRequest(BaseModel):
    query: str
    session_id: str | None = None
    pdf_filenames: list[str] = []


@router.get("/health")
async def health():
    return {"status": "ok", "service": "Multi-Agent Research Assistant"}


@router.post("/upload")
async def upload_pdf(file: UploadFile = File(...)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(400, "Only PDF files accepted.")
    safe = f"{uuid.uuid4()}_{file.filename}"
    path = UPLOAD_DIR / safe
    path.write_bytes(await file.read())
    return {"filename": file.filename, "saved_as": safe}


@router.get("/quota")
async def quota_status(request: Request):
    fp   = _fingerprint(request)
    ip   = request.headers.get("x-forwarded-for", request.client.host if request.client else "")
    user = get_or_create_user(fp, ip)
    from db import get_conn
    with get_conn() as conn:
        row = conn.execute("SELECT prompt_count, quota_reset_at FROM users WHERE id = ?",
                           (user["id"],)).fetchone()
        count    = dict(row)["prompt_count"] if row else 0
        reset_at = dict(row)["quota_reset_at"] if row else ""
    return {
        "prompts_used":      count,
        "prompts_remaining": max(0, PROMPT_LIMIT - count),
        "prompt_limit":      PROMPT_LIMIT,
        "quota_reset_at":    reset_at,
    }


@router.post("/research")
async def research(req: ResearchRequest, request: Request):
    fp         = _fingerprint(request)
    ip         = request.headers.get("x-forwarded-for", request.client.host if request.client else "")
    user       = get_or_create_user(fp, ip)
    session_id = req.session_id or str(uuid.uuid4())

    allowed, used, remaining = check_and_increment_quota(user["id"])
    if not allowed:
        async def over():
            yield sse("quota_exceeded", {
                "message": f"You have used all {PROMPT_LIMIT} free prompts for today.",
                "prompts_used": used, "prompts_remaining": 0,
                "prompt_limit": PROMPT_LIMIT,
                "reset_info": "Quota resets every 24 hours.",
            })
        return StreamingResponse(over(), media_type="text/event-stream")

    pdf_paths = [str(UPLOAD_DIR / f) for f in req.pdf_filenames
                 if (UPLOAD_DIR / f).exists()]
    query_id  = log_query_start(user["id"], session_id, req.query)

    async def stream():
        start = time.time()
        try:
            yield sse("start", {
                "session_id": session_id, "query": req.query,
                "prompts_used": used, "prompts_remaining": remaining,
                "prompt_limit": PROMPT_LIMIT,
            })

            state = initial_state(req.query, session_id, pdf_paths)
            seen  = 0

            for chunk in get_graph().stream(state, stream_mode="values"):
                steps = chunk.get("steps", [])
                while seen < len(steps):
                    s = steps[seen]
                    log_agent_step(query_id, s.agent.value, s.action, s.status.value, s.detail)
                    yield sse("step", {"agent": s.agent.value, "action": s.action,
                                       "status": s.status.value, "detail": s.detail})
                    seen += 1
                    await asyncio.sleep(0)

                if chunk.get("final_answer") and chunk.get("status") == ResearchStatus.DONE:
                    srcs = [{"id": s.id, "title": s.title, "url": s.url,
                              "snippet": s.snippet[:300], "agent": s.agent.value, "score": s.score}
                             for s in chunk.get("all_sources", [])]
                    yield sse("sources", {"sources": srcs})
                    yield sse("answer",  {"answer": chunk["final_answer"]})
                    log_query_complete(query_id, len(srcs),
                                       len(chunk["final_answer"]),
                                       int((time.time() - start) * 1000))

            yield sse("done", {"session_id": session_id,
                                "prompts_used": used, "prompts_remaining": remaining})

        except Exception as e:
            logger.error(f"[Research] {e}")
            log_query_error(query_id, str(e))
            yield sse("error", {"message": str(e)})

    return StreamingResponse(stream(), media_type="text/event-stream",
                              headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _check_admin(key: str):
    if key != os.getenv("ADMIN_KEY", "changeme"):
        raise HTTPException(403, "Invalid admin key.")


@router.get("/admin/stats")
async def admin_stats(x_admin_key: str = Header(default="")):
    _check_admin(x_admin_key)
    return get_stats()


@router.get("/admin/users")
async def admin_users(limit: int = 100, x_admin_key: str = Header(default="")):
    _check_admin(x_admin_key)
    return get_all_users(limit)


@router.get("/admin/queries")
async def admin_queries(limit: int = 50, x_admin_key: str = Header(default="")):
    _check_admin(x_admin_key)
    return get_recent_queries(limit)


@router.get("/admin/queries/{query_id}/logs")
async def admin_query_logs(query_id: str, x_admin_key: str = Header(default="")):
    _check_admin(x_admin_key)
    return get_query_agent_logs(query_id)
